import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import { ApiError, type ErrorCode, isErrorCode } from "../lib/errors";
import type { Job } from "./jobs";
import type { CompletedPayload, JobEvent } from "./sse-registry";

export type Runner = (job: Job, emit: (event: JobEvent) => void) => Promise<RunResult>;

export type RunResult = { result: CompletedPayload; csv: string };

export type RunnerConfig = {
  pythonBin: string;
  workerCwd: string;
  maxMegapixels: number;
  timeoutSeconds: number;
};

const EXTENSION: Record<string, string> = {
  bmp: "bmp",
  jpeg: "jpg",
  png: "png",
  tiff: "tif",
};

/** One Python process per image: peak memory is about 48 MB per megapixel,
 *  and a process that dies gives it all back to the OS. */
export function createWorkerRunner(config: RunnerConfig): Runner {
  return async function run(job, emit) {
    const dir = await mkdtemp(join(tmpdir(), "sabugo-job-"));
    try {
      // The worker reports whatever it read as `File.Name`. Sanitised in
      // `safeStem`, with the extension from the format the magic bytes proved.
      const image = join(dir, `${job.filename}.${EXTENSION[job.format] ?? "png"}`);
      const jsonPath = join(dir, "result.json");
      const csvPath = join(dir, "features.csv");
      await writeFile(image, job.image);

      // A preview writes no CSV, which is what makes the export route answer
      // NOT_FOUND for it with no check of its own.
      const argv = [image, ...flags(job, config), "--json", jsonPath];
      if (!job.preview) argv.push("-o", csvPath);
      if (job.rois.length > 0) {
        const roiPath = join(dir, "rois.csv");
        await writeFile(roiPath, annotationCsv(job.rois), "utf8");
        argv.push("--roipath", roiPath);
      }

      const child = Bun.spawn([interpreter(config.pythonBin), "-m", "sabugo_worker.cli", ...argv], {
        cwd: resolve(config.workerCwd),
        stdout: "ignore",
        stderr: "pipe",
        timeout: config.timeoutSeconds * 1000,
        killSignal: "SIGKILL",
      });

      // Read while it runs, or every progress line arrives at once at the end.
      const stderr = await drain(child.stderr, emit);
      const code = await child.exited;

      if (child.signalCode === "SIGKILL") throw new ApiError("PROCESSING_TIMEOUT");
      if (code !== 0) throw new ApiError(tokenIn(stderr));

      const result = JSON.parse(await readFile(jsonPath, "utf8")) as CompletedPayload;
      const csv = job.preview ? "" : await readFile(csvPath, "utf8");
      return { result: await withPictures(result), csv };
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  };
}

/** A bare name is looked up on PATH; a path resolves against the server's
 *  cwd, not the child's, which is the worker directory. */
function interpreter(pythonBin: string): string {
  const isPath = pythonBin.includes("/") || pythonBin.includes("\\");
  return isPath && !isAbsolute(pythonBin) ? resolve(pythonBin) : pythonBin;
}

function flags(job: Job, config: RunnerConfig): string[] {
  const p = job.params;
  const argv = [
    "--dpi",
    String(job.dpi),
    "--mode",
    p.mode,
    "--threshold-method",
    p.threshold_method,
    "--threshold",
    String(p.threshold_value),
    "--dranges",
    p.diameter_ranges_mm.join(","),
    "--max-megapixels",
    String(config.maxMegapixels),
    "--progress",
    "--segment",
  ];
  if (job.preview) argv.push("--preview");
  else argv.push("--feature", "--medialwidth", String(p.medial_axis_width));
  if (!p.show_medial_axis) argv.push("--no-medialaxis");
  if (!p.show_medial_axis_diameter) argv.push("--no-classcolour");
  if (p.show_contours) argv.push("--contour", "--contourwidth", String(p.contour_width));
  if (p.show_convex_hull) argv.push("--hull");
  if (p.show_holes) argv.push("--holes");
  if (p.show_dist_map) argv.push("--distancemap");
  if (p.invert_image) argv.push("--invert");
  if (!p.keep_largest) argv.push("--no-keep-largest");
  if (p.filter_background_noise) {
    argv.push(
      "--filter-background-noise",
      "--max-background-noise-mm2",
      String(p.max_background_noise_mm2),
    );
  }
  if (p.filter_foreground_noise) {
    argv.push(
      "--filter-foreground-noise",
      "--max-foreground-noise-mm2",
      String(p.max_foreground_noise_mm2),
    );
  }
  if (p.enable_edge_smoothing) {
    argv.push("--smooth", "--smooththreshold", String(p.edge_smoothing_threshold));
  }
  if (p.enable_root_pruning) {
    argv.push("--prune", "--prunethreshold", String(p.root_pruning_threshold));
  }
  return argv;
}

/** The format `read_annotations` reads: name, class, x, y, width, height. */
function annotationCsv(rois: Job["rois"]): string {
  const header = "#ROI Name, Class Name, X Position, Y Position, Width, Height";
  const lines = rois.map((r) => `${r.name}, root, ${r.x}, ${r.y}, ${r.width}, ${r.height}`);
  return [header, ...lines, ""].join("\n");
}

/** NDJSON progress and plain error tokens share the stream: if a line is not
 *  JSON it is the error text kept for the `failed` envelope. */
async function drain(stream: ReadableStream<Uint8Array>, emit: (event: JobEvent) => void) {
  const decoder = new TextDecoder();
  let pending = "";
  let text = "";

  for await (const chunk of stream) {
    const decoded = decoder.decode(chunk, { stream: true });
    text += decoded;
    pending += decoded;

    const lines = pending.split("\n");
    pending = lines.pop() ?? "";
    for (const line of lines) {
      const data = parseProgress(line);
      if (data) emit({ event: "progress", data });
    }
  }
  return text;
}

function parseProgress(line: string) {
  if (!line.startsWith("{")) return null;
  try {
    const data = JSON.parse(line) as { stage?: string; percent?: number; region?: string };
    if (typeof data.stage !== "string" || typeof data.percent !== "number") return null;
    return { stage: data.stage, percent: data.percent, region: data.region };
  } catch {
    return null;
  }
}

/** The tokens the worker emits are error codes verbatim, so changing one in
 *  `pipeline.py` means changing `lib/errors.ts`. */
function tokenIn(stderr: string): ErrorCode {
  for (const token of stderr.match(/\b[A-Z][A-Z_]{4,}\b/g) ?? []) {
    if (isErrorCode(token)) return token;
  }
  return "INTERNAL_ERROR";
}

/** The worker reports where it wrote them, so nothing here rebuilds a
 *  filename from a suffix. */
async function withPictures(result: CompletedPayload): Promise<CompletedPayload> {
  const results = await Promise.all(
    result.results.map(async (entry) => ({
      ...entry,
      segmentedImage: await dataUri(entry.segmentedImagePath as string | null),
      skeletonImage: await dataUri(entry.skeletonImagePath as string | null),
      segmentedImagePath: undefined,
      skeletonImagePath: undefined,
    })),
  );
  return { ...result, results };
}

async function dataUri(path: string | null): Promise<string | null> {
  if (!path) return null;
  const bytes = await readFile(path);
  return `data:image/png;base64,${bytes.toString("base64")}`;
}
