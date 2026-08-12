import { OpenAPIHono } from "@hono/zod-openapi";
import { Scalar } from "@scalar/hono-api-reference";
import { serveStatic } from "hono/bun";
import { rateLimiter } from "hono-rate-limiter";
import { clientIp } from "./lib/client-ip";
import { envelope } from "./lib/errors";
import { createAnalysesRoutes } from "./modules/analyses";
import { createHealthRoutes } from "./modules/health";
import { createJobStore, type JobStore } from "./services/jobs";
import { createQueue, type Queue } from "./services/queue";
import type { Runner } from "./services/runner";
import { createEventBus, type EventBus } from "./services/sse-registry";

export type AppDeps = {
  clientDist: string;
  runner: Runner;
  jobs?: JobStore;
  bus?: EventBus;
  queue?: Queue;
  maxQueueDepth?: number;
  maxUploadBytes?: number;
  uploadsPerHour?: number;
};

/** Dependencies arrive as arguments so a test can point the mount-order
 *  check at a real client build. */
export function createApp(deps: AppDeps) {
  if (!deps.clientDist) {
    throw new Error("clientDist_is_required");
  }

  const clientDist = deps.clientDist;
  const jobs = deps.jobs ?? createJobStore();
  const bus = deps.bus ?? createEventBus();
  const queue =
    deps.queue ??
    createQueue({
      maxDepth: deps.maxQueueDepth ?? 10,
      runner: deps.runner,
      jobs,
      bus,
    });

  const app = new OpenAPIHono();
  const api = new OpenAPIHono();

  api.route("/health", createHealthRoutes());
  api.use(
    "/analyses",
    // Not a defence: switching IP resets the counter. The queue depth is the
    // real ceiling.
    rateLimiter({
      windowMs: 60 * 60 * 1000,
      limit: deps.uploadsPerHour ?? 200,
      keyGenerator: (c) => clientIp(c.req.header("x-forwarded-for")) ?? "unknown",
      // Without this the library answers in plain text, and the client, which
      // parses every error body as the envelope, reports INTERNAL_ERROR.
      handler: (c) => c.json(envelope("RATE_LIMITED"), 429),
    }),
  );
  api.route(
    "/analyses",
    createAnalysesRoutes({
      queue,
      jobs,
      bus,
      maxUploadBytes: deps.maxUploadBytes ?? 256 * 1024 * 1024,
    }),
  );

  app.route("/api", api);

  // On the root app and after mounting: generated from the sub-app, every path
  // would come out without the `/api` prefix and document routes that 404.
  app.doc("/api/openapi.json", {
    openapi: "3.1.0",
    info: { title: "Sabugo", version: "0.1.0" },
  });
  app.get("/api/docs", Scalar({ url: "/api/openapi.json" }));

  // A mistyped API path is JSON, not the SPA's HTML with a 200.
  app.all("/api/*", (c) => c.json(envelope("NOT_FOUND"), 404));

  app.use("*", serveStatic({ root: clientDist }));
  app.get("*", (c) => {
    const path = c.req.path;
    if (path.startsWith("/api/")) {
      return c.json(envelope("NOT_FOUND"), 404);
    }

    return c.html(
      `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>404 · Sabugo</title>
    <style>
      :root { color-scheme: light; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f5f7f2; color: #173f29; }
      .card { text-align: center; padding: 2.5rem 2rem; border-radius: 24px; background: white; box-shadow: 0 20px 45px rgba(23, 63, 41, 0.08); max-width: 420px; width: min(90vw, 420px); }
      img { width: 120px; height: 120px; margin-bottom: 1rem; }
      h1 { margin: 0 0 0.5rem; font-size: 2rem; }
      p { margin: 0; color: #5e6f61; line-height: 1.5; }
    </style>
  </head>
  <body>
    <main class="card">
      <img src="/favicon.svg" alt="Sabugo logo" />
      <h1>404</h1>
      <p>The page you are looking for could not be found.</p>
    </main>
  </body>
</html>`,
      404,
    );
  });

  return app;
}
