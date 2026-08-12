import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { existsSync, readdirSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { ParamsSchema } from "../../../src/modules/analyses/model";
import { createWorkerRunner } from "../../../src/services/runner";

/** These drive the real `python -m sabugo_worker.cli`, and skip themselves
 *  where the worker is not installed. */
const WORKER = resolve(import.meta.dir, "../../../../worker");
const CANDIDATES = [
  join(WORKER, ".venv/Scripts/python.exe"),
  join(WORKER, ".venv/bin/python"),
  "python3",
  "python",
];

function findPython() {
  for (const candidate of CANDIDATES) {
    if (candidate.includes("/") && !existsSync(candidate)) continue;
    const probe = Bun.spawnSync([candidate, "-c", "import sabugo_worker"], { cwd: WORKER });
    if (probe.exitCode === 0) return candidate;
  }
  return null;
}

const python = findPython();
const runIfWorker = python ? test : test.skip;

let images;

function job({ params, ...overrides } = {}) {
  return {
    id: crypto.randomUUID(),
    dpi: 300,
    params: ParamsSchema.parse(params ?? {}),
    rois: [],
    image: new Uint8Array(),
    format: "png",
    filename: "scan-04",
    preview: false,
    queuedAt: new Date().toISOString(),
    status: "pending",
    ...overrides,
  };
}

function runner(overrides = {}) {
  return createWorkerRunner({
    pythonBin: python ?? "python",
    workerCwd: WORKER,
    maxMegapixels: 100,
    timeoutSeconds: 120,
    ...overrides,
  });
}

beforeAll(async () => {
  if (!python) return;
  images = await mkdtemp(join(tmpdir(), "sabugo-fixtures-"));
  const script = `
import cv2, numpy as np
image = np.full((200, 300), 255, np.uint8)
image[40:60, 20:280] = 0
cv2.imwrite(r"${join(images, "bar.png").replaceAll("\\", "\\\\")}", image)
cv2.imwrite(r"${join(images, "blank.png").replaceAll("\\", "\\\\")}", np.full((80, 80), 255, np.uint8))
`;
  const drawn = Bun.spawnSync([python, "-c", script], { cwd: WORKER });
  expect(drawn.exitCode).toBe(0);
});

afterAll(async () => {
  if (images) await rm(images, { recursive: true, force: true });
});

function bytes(name) {
  return new Uint8Array(require("node:fs").readFileSync(join(images, name)));
}

describe("the worker subprocess", () => {
  runIfWorker("returns the metrics and the two derived images", async () => {
    const events = [];
    const { result, csv } = await runner()(job({ image: bytes("bar.png") }), (e) => events.push(e));

    const [entry] = result.results;
    expect(result.pipelineVersion).toMatch(/^\d+\.\d+\.\d+$/);
    expect(entry.roiIndex).toBe(-1);
    expect(entry.metrics.totalRootLength).toBeGreaterThan(0);
    expect(Object.keys(entry.bins)).toEqual([
      "rootLength",
      "projectedArea",
      "surfaceArea",
      "volume",
    ]);

    expect(entry.segmentedImage).toStartWith("data:image/png;base64,");
    expect(entry.skeletonImage).toStartWith("data:image/png;base64,");
    expect(entry.segmentedImagePath).toBeUndefined();

    expect(entry.fileName).toBe("scan-04.png");

    expect(csv.split("\n")[0]).toStartWith("File.Name,Region.of.Interest,");
    expect(csv.split("\n")[1]).toStartWith("scan-04.png,Full,");
  });

  runIfWorker("reports the stage of the pipeline as it goes", async () => {
    const events = [];
    await runner()(job({ image: bytes("bar.png") }), (e) => events.push(e));

    expect(events.length).toBeGreaterThan(2);
    expect(events.every((event) => event.event === "progress")).toBe(true);
    expect(events.map((e) => e.data.stage)).toContain("skeletonize");
    expect(events.at(-1).data.percent).toBeGreaterThanOrEqual(95);
  });

  runIfWorker("a non-zero exit becomes the token the worker printed", async () => {
    const failure = runner()(job({ image: bytes("blank.png") }), () => {});
    expect(failure).rejects.toMatchObject({ code: "NO_ROOTS_DETECTED", status: 422 });
  });

  runIfWorker("an undecodable file is INVALID_IMAGE", async () => {
    const garbage = new TextEncoder().encode("certainly not a PNG");
    const failure = runner()(job({ image: garbage }), () => {});
    expect(failure).rejects.toMatchObject({ code: "INVALID_IMAGE" });
  });

  runIfWorker("the megapixel ceiling of the environment reaches the worker", async () => {
    // Without the flag the configured number never reaches the worker and the
    // default silently applies.
    const failure = runner({ maxMegapixels: 0.01 })(job({ image: bytes("bar.png") }), () => {});
    expect(failure).rejects.toMatchObject({ code: "IMAGE_TOO_LARGE", status: 413 });
  });

  runIfWorker("a run past the timeout is killed and reported", async () => {
    const failure = runner({ timeoutSeconds: 0.05 })(job({ image: bytes("bar.png") }), () => {});
    expect(failure).rejects.toMatchObject({ code: "PROCESSING_TIMEOUT" });
  });

  runIfWorker("the temporary directory is removed on both paths", async () => {
    const before = readdirSync(tmpdir()).filter((name) => name.startsWith("sabugo-job-"));

    await runner()(job({ image: bytes("bar.png") }), () => {});
    await runner()(job({ image: bytes("blank.png") }), () => {}).catch(() => {});

    const after = readdirSync(tmpdir()).filter((name) => name.startsWith("sabugo-job-"));
    expect(after).toEqual(before);
  });

  // Asserted through the picture and not the argv: an option that reaches the
  // CLI and changes nothing would pass an argv check.
  describe("the output display options", () => {
    async function skeletonOf(params) {
      const { result } = await runner()(job({ image: bytes("bar.png"), params }), () => {});
      return result.results[0].skeletonImage;
    }

    runIfWorker("each one changes the feature image", async () => {
      const plain = await skeletonOf({});
      for (const params of [
        { show_medial_axis: false },
        { show_medial_axis_diameter: false },
        { medial_axis_width: 9 },
        { show_contours: true },
        { show_convex_hull: true },
        { show_dist_map: true },
      ]) {
        expect(await skeletonOf(params)).not.toBe(plain);
      }
    });

    runIfWorker("and none of them moves a number", async () => {
      const measure = async (params) => {
        const { result } = await runner()(job({ image: bytes("bar.png"), params }), () => {});
        return result.results[0].metrics.totalRootLength;
      };
      expect(await measure({ show_dist_map: true, show_convex_hull: true })).toBe(
        await measure({}),
      );
    });
  });

  describe("a preview", () => {
    runIfWorker("returns the mask and stops before the skeleton", async () => {
      const events = [];
      const { result } = await runner()(job({ image: bytes("bar.png"), preview: true }), (e) =>
        events.push(e),
      );

      const [entry] = result.results;
      expect(entry.segmentedImage).toStartWith("data:image/png;base64,");
      expect(entry.skeletonImage).toBeNull();
      expect(entry.thresholdValueUsed).toBe(200);
      expect(entry.metrics).toBeUndefined();
      expect(events.map((e) => e.data.stage)).not.toContain("skeletonize");
    });

    runIfWorker("writes no CSV, which is what makes the export route a 404", async () => {
      const { csv } = await runner()(job({ image: bytes("bar.png"), preview: true }), () => {});
      expect(csv).toBe("");
    });
  });

  runIfWorker("each ROI becomes its own result row, and no Full row beside them", async () => {
    const rois = [
      { name: "roi_1", x: 10, y: 10, width: 280, height: 80 },
      { name: "roi_2", x: 10, y: 30, width: 280, height: 60 },
    ];
    const { result } = await runner()(job({ image: bytes("bar.png"), rois }), () => {});

    expect(result.results.map((entry) => entry.roiIndex)).toEqual([0, 1]);
    expect(result.results.map((entry) => entry.roiName)).toEqual(["roi_1", "roi_2"]);
  });
});
