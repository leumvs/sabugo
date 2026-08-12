import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createApp } from "../src/app";

export const INDEX_HTML = "<!doctype html><title>Sabugo</title>";

/** A real client build on disk, which the mount-order test needs to mean
 *  anything: without files to serve, `serveStatic` falls through either way. */
export async function clientBuild() {
  const dir = await mkdtemp(join(tmpdir(), "sabugo-dist-"));
  await writeFile(join(dir, "index.html"), INDEX_HTML);
  return dir;
}

export const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
]);

/** A runner that never spawns Python: these tests are about the API's own
 *  path, not about OpenCV. */
export function fakeRunner(overrides = {}) {
  const {
    delayMs = 0,
    fail = null,
    gate = null,
    progress = [{ stage: "segment", percent: 20 }],
    csv = "File.Name,Region.of.Interest\nimage.png,Full\n",
  } = overrides;

  const runner = async (job, emit) => {
    runner.calls.push(job);
    // Held until the test says go: a timer would make the assertions depend
    // on whether the run outlasts the connect.
    if (gate) await gate;
    for (const event of progress) emit({ event: "progress", data: event });
    if (delayMs) await Bun.sleep(delayMs);
    if (fail) throw fail;
    return {
      result: {
        pipelineVersion: "1.3.0",
        results: [{ roiIndex: -1, metrics: { totalRootLength: 12.5 }, bins: {} }],
      },
      csv,
    };
  };
  runner.calls = [];
  return runner;
}

/** A `fakeRunner` that does nothing until `release()` — see the note there. */
export function gatedRunner(overrides = {}) {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const runner = fakeRunner({ ...overrides, gate });
  runner.release = release;
  return runner;
}

export function upload({
  dpi = "600",
  params,
  rois,
  image = PNG_BYTES,
  name = "root.png",
  fieldsFirst = true,
} = {}) {
  const body = new FormData();
  const file = new File([image], name, { type: "image/png" });

  // The fields have to precede the file.
  if (fieldsFirst) {
    body.append("dpi", dpi);
    if (params) body.append("params", JSON.stringify(params));
    if (rois) body.append("rois", JSON.stringify(rois));
    body.append("image", file);
  } else {
    body.append("image", file);
    body.append("dpi", dpi);
  }
  return { method: "POST", body };
}

export async function makeApp(overrides = {}) {
  const clientDist = await clientBuild();
  const runner = overrides.runner ?? fakeRunner();
  const app = createApp({ clientDist, runner, ...overrides });
  return { app, runner, clientDist };
}

/** Collects an SSE response into `[{ event, data }]`, stopping at the terminal. */
export async function readEvents(response, limit = 50) {
  const events = [];
  let buffer = "";

  for await (const chunk of response.body) {
    buffer += new TextDecoder().decode(chunk);
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const event = /^event: (.+)$/m.exec(frame)?.[1];
      const data = /^data: (.+)$/m.exec(frame)?.[1];
      if (event) events.push({ event, data: data ? JSON.parse(data) : null });
      if (event === "completed" || event === "failed" || events.length >= limit) return events;
      split = buffer.indexOf("\n\n");
    }
  }
  return events;
}
