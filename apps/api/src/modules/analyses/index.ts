import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { parseMultipartRequest } from "@mjackson/multipart-parser";
import { streamSSE } from "hono/streaming";
import { ApiError, envelope } from "../../lib/errors";
import { isMultiPageTiff, SNIFF_BYTES, sniffFormat } from "../../lib/magic-bytes";
import type { Job, JobStore } from "../../services/jobs";
import type { Queue } from "../../services/queue";
import type { EventBus, JobEvent } from "../../services/sse-registry";
import {
  AcceptedSchema,
  DpiSchema,
  ErrorSchema,
  ParamsSchema,
  RoisSchema,
  UploadBodySchema,
} from "./model";

export type AnalysesDeps = {
  queue: Queue;
  jobs: JobStore;
  bus: EventBus;
  maxUploadBytes: number;
};

/** Without it an idle nginx (60 s default) drops a stream that is allowed to
 *  stay silent for up to the 120 s job timeout. */
const HEARTBEAT_MS = 25_000;

const postRoute = createRoute({
  method: "post",
  path: "/",
  tags: ["analyses"],
  summary: "Queue an analysis",
  description:
    "Send `dpi`, `params` and `rois` **before** `image`. The handler reads the " +
    "body part by part, so fields that arrive after the file are only seen once " +
    "the file has already been read — which defeats the early refusal.",
  request: {
    // A query flag and not a `params` field: it has to be readable before
    // the body is.
    query: z.object({
      preview: z
        .enum(["0", "1"])
        .optional()
        .describe("1 segments and stops: no metrics, no CSV, no feature image"),
    }),
    body: { content: { "multipart/form-data": { schema: UploadBodySchema } }, required: true },
  },
  responses: {
    202: {
      content: { "application/json": { schema: AcceptedSchema } },
      description: "accepted and queued; the result arrives on the event stream",
    },
    400: {
      content: { "application/json": { schema: ErrorSchema } },
      description: "invalid params",
    },
    415: {
      content: { "application/json": { schema: ErrorSchema } },
      description: "not one of BMP, JPEG, PNG, TIFF, or a multi-page TIFF",
    },
    500: {
      content: { "application/json": { schema: ErrorSchema } },
      description: "unexpected failure",
    },
    503: {
      content: { "application/json": { schema: ErrorSchema } },
      description: "the queue is full",
    },
  },
});

/** The statuses `postRoute` declares. The cast below is the only place the
 *  closed error table meets Hono's per-route response typing. */
type PostStatus = 400 | 415 | 500 | 503;

const eventsRoute = createRoute({
  method: "get",
  path: "/{id}/events",
  tags: ["analyses"],
  summary: "Follow one job",
  description:
    "The five events. The result travels inside `completed`, so there is " +
    "no second request to make. A client that connects after the job ended gets " +
    "the terminal event and the stream closes.",
  request: { params: z.object({ id: z.string() }) },
  responses: {
    200: {
      content: { "text/event-stream": { schema: { type: "string" } } },
      description: "queued, started, progress, completed, failed",
    },
  },
});

const exportRoute = createRoute({
  method: "get",
  path: "/{id}/export",
  tags: ["analyses"],
  summary: "Download the result",
  request: {
    params: z.object({ id: z.string() }),
    query: z.object({ format: z.enum(["csv"]).default("csv") }),
  },
  responses: {
    200: { content: { "text/csv": { schema: { type: "string" } } }, description: "features.csv" },
    404: {
      content: { "application/json": { schema: ErrorSchema } },
      description: "unknown job, or one that has not completed",
    },
  },
});

export function createAnalysesRoutes(deps: AnalysesDeps): OpenAPIHono {
  const routes = new OpenAPIHono();
  const { queue, jobs, bus } = deps;

  routes.openapi(postRoute, async (c) => {
    try {
      // Before a byte of the body is read. `enqueue` checks again, against a
      // request that arrives meanwhile.
      if (queue.isFull()) throw new ApiError("SERVICE_AT_CAPACITY", { queueDepth: queue.depth() });
      const job = await readUpload(c.req.raw, deps, c.req.query("preview") === "1");
      const queuePosition = queue.enqueue(job);

      return c.json(
        { id: job.id, status: "pending" as const, queuePosition, queuedAt: job.queuedAt },
        202,
      );
    } catch (error) {
      const failure = error instanceof ApiError ? error : new ApiError("INTERNAL_ERROR");

      return c.json(failure.envelope, failure.status as PostStatus);
    }
  });

  routes.openapi(eventsRoute, (c) => {
    const id = c.req.param("id");

    // Without these nginx buffers the stream and every progress event
    // arrives at once, at the end.
    c.header("Content-Encoding", "Identity");
    c.header("X-Accel-Buffering", "no");

    return streamSSE(
      c,
      async (stream) => {
        const job = jobs.get(id);
        if (!job) {
          await stream.writeSSE({ event: "failed", data: JSON.stringify(envelope("NOT_FOUND")) });
          return;
        }

        const pending: JobEvent[] = [];
        let wake: (() => void) | null = null;
        const push = (event: JobEvent) => {
          pending.push(event);
          wake?.();
        };

        const unsubscribe = bus.subscribe(id, push);
        // Subscribe first, then look: a job finishing in between would fall
        // through both checks. A duplicate is harmless.
        if (job.terminal) push(job.terminal);

        let aborted = false;
        stream.onAbort(() => {
          aborted = true;
          wake?.();
        });

        try {
          while (!aborted) {
            while (pending.length > 0) {
              const event = pending.shift() as JobEvent;
              await stream.writeSSE({ event: event.event, data: JSON.stringify(event.data) });
              if (event.event === "completed" || event.event === "failed") return;
            }
            const woken = await waitForEvent((resume) => {
              wake = resume;
              // An event published between the drain above and this line
              // would find `wake` still null and be lost.
              if (pending.length > 0 || aborted) resume();
            }, HEARTBEAT_MS);
            wake = null;
            if (!woken && !aborted) await stream.write(": ping\n\n");
          }
        } finally {
          unsubscribe();
        }
      },
      // Errors thrown mid-stream never reach Hono's `onError`: the response is
      // already being written. Handled here or the client waits forever.
      async (error, stream) => {
        console.error(JSON.stringify({ level: "error", jobId: id, error: String(error) }));
        await stream.writeSSE({
          event: "failed",
          data: JSON.stringify(envelope("INTERNAL_ERROR")),
        });
      },
    );
  });

  routes.openapi(exportRoute, (c) => {
    const id = c.req.param("id");
    const job = jobs.get(id);

    // Unknown, still running, failed or expired: all NOT_FOUND.
    if (job?.status !== "completed" || !job.csv) {
      return c.json(envelope("NOT_FOUND"), 404);
    }

    return c.body(job.csv, 200, {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="sabugo-${id}.csv"`,
    });
  });

  return routes;
}

/** Resolves `true` if an event woke it, `false` if the heartbeat interval elapsed. */
function waitForEvent(register: (resume: () => void) => void, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    const timer = setTimeout(() => {
      settled = true;
      resolve(false);
    }, timeoutMs);

    register(() => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(true);
    });
  });
}

/**
 * Read part by part instead of through `c.req.parseBody()`, which would hold
 * the whole body in memory on a public unauthenticated route.
 *
 * ⚠️ In `@mjackson/multipart-parser` 0.10.1 a part is yielded already
 * buffered, so there is no per-part stream to sniff the first KB of. What
 * bounds the body is `maxFileSize`, which aborts the read mid-file.
 */
async function readUpload(request: Request, deps: AnalysesDeps, preview: boolean): Promise<Job> {
  let dpi: number | undefined;
  let params = ParamsSchema.parse({});
  let rois: Job["rois"] = [];
  let image: Uint8Array | undefined;
  let format: string | undefined;
  let filename = "image";

  for await (const part of parseMultipartRequest(request, { maxFileSize: deps.maxUploadBytes })) {
    if (part.name === "image") {
      filename = safeStem(part.filename);
      format = sniffFormat(part.bytes.subarray(0, SNIFF_BYTES)) ?? undefined;
      if (!format) throw new ApiError("UNSUPPORTED_FORMAT", { reason: "magic_bytes" });
      if (format === "tiff" && isMultiPageTiff(part.bytes)) {
        throw new ApiError("UNSUPPORTED_FORMAT", { reason: "multi_page_tiff" });
      }
      image = part.bytes;
      continue;
    }

    const value = part.text;
    if (part.name === "dpi") dpi = parse(DpiSchema, value, "dpi");
    if (part.name === "params") params = parse(ParamsSchema, json(value, "params"), "params");
    if (part.name === "rois") rois = parse(RoisSchema, json(value, "rois"), "rois");
  }

  if (dpi === undefined) throw new ApiError("INVALID_PARAMS", { field: "dpi" });
  if (!image || !format) throw new ApiError("INVALID_PARAMS", { field: "image" });

  return {
    id: crypto.randomUUID(),
    dpi,
    params,
    rois,
    image,
    format,
    filename,
    preview,
    queuedAt: new Date().toISOString(),
    status: "pending",
  };
}

/**
 * It names a real file in a temporary directory, so it is rebuilt from
 * scratch rather than trusted: only the basename, only these characters, and
 * the extension re-added by the runner from the proven format.
 */
function safeStem(filename: string | undefined): string {
  const base = (filename ?? "").split(/[/\\]/).pop() ?? "";
  const stem = base.replace(/\.[^.]*$/, "").replace(/[^A-Za-z0-9._-]/g, "_");
  return stem.slice(0, 80) || "image";
}

function json(value: string, field: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    throw new ApiError("INVALID_PARAMS", { field, reason: "not_json" });
  }
}

function parse<T>(schema: z.ZodType<T>, value: unknown, field: string): T {
  const result = schema.safeParse(value);
  if (!result.success) {
    throw new ApiError("INVALID_PARAMS", { field, reason: reasonFor(result.error.issues[0]) });
  }
  return result.data;
}

/**
 * Zod's own `message` is an English sentence, so what travels is the issue
 * code, already snake_case, and the hand-written message for the refinements.
 */
function reasonFor(issue: z.core.$ZodIssue | undefined): string {
  if (!issue) return "invalid";
  return issue.code === "custom" ? issue.message : issue.code;
}
