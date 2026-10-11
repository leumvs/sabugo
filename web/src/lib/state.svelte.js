import { follow, submit } from "./api.js";
import { rowFor } from "./csv.js";
import { rotate } from "./image.js";

function defaults() {
  return {
    mode: "broken_roots",
    threshold_method: "manual",
    threshold_value: 200,
    invert_image: false,
    keep_largest: true,
    filter_background_noise: false,
    max_background_noise_mm2: 1.0,
    filter_foreground_noise: false,
    max_foreground_noise_mm2: 1.0,
    enable_edge_smoothing: false,
    edge_smoothing_threshold: 2.0,
    enable_root_pruning: true,
    root_pruning_threshold: 5,
    diameter_ranges_mm: [2.0, 5.0],
    show_medial_axis: true,
    medial_axis_width: 3,
    show_medial_axis_diameter: true,
    show_contours: false,
    contour_width: 1,
    show_convex_hull: false,
    show_holes: false,
    show_dist_map: false,
  };
}

/** ⚠️ The only place a result exists: there is no database and no way to
 *  fetch one back, so a refresh loses real work. */
export const session = $state({
  original: null,
  file: null,
  imageUrl: null,
  imageSize: null,
  /** 0 fits the viewport; anything else is a factor of the natural size. */
  zoom: 0,
  /** DPI or pixels per mm — only DPI travels, see `dpi()`. */
  calibration: { value: 600, unit: "dpi" },
  params: defaults(),
  rois: [],
  runs: [],
  selected: 0,
  display: "input",
  mouseMode: "pan",
  rotation: 0,
  rows: [],
  docks: { options: true, rois: true, bottom: true },
  resultIndex: 0,
});

/** Only DPI travels; pixels per mm is converted here. */
export function dpi() {
  const { value, unit } = session.calibration;
  return unit === "dpi" ? value : value * 25.4;
}

export function chooseFile(file) {
  session.original = file;
  session.rotation = 0;
  present(file);
}

/** Rotates the upload and not the element on screen, so the ROI rectangles
 *  stop describing the image the moment it turns. */
export async function setRotation(degrees) {
  if (!session.original) return;
  session.rotation = degrees;
  present(await rotate(session.original, degrees));
}

function present(file) {
  if (session.imageUrl) URL.revokeObjectURL(session.imageUrl);
  session.file = file;
  session.imageUrl = URL.createObjectURL(file);
  session.imageSize = null;
  session.rois = [];
  session.display = "input";
  session.zoom = 0;
}

/** The two modes are sheets of different widths, so this is what clears the
 *  Features table. */
export function setMode(next) {
  if (next === session.params.mode) return;
  session.params.mode = next;
  session.rows = [];
}

export const MAX_ROIS = 10;

export function addRoi(rect) {
  if (session.rois.length >= MAX_ROIS) return;
  // `roi_1` upward: the name that comes back in `Region.of.Interest`.
  let index = 1;
  while (session.rois.some((roi) => roi.name === `roi_${index}`)) index += 1;
  session.rois.push({ name: `roi_${index}`, class: "root", ...rect });
}

export function removeRoi(name) {
  session.rois = session.rois.filter((roi) => roi.name !== name);
}

export function currentRun() {
  return session.runs[session.selected] ?? null;
}

export function hasUnsavedResult() {
  return session.rows.length > 0 && !session.rows.some((row) => row.saved);
}

/** The derived images come back cropped to the mask's bounding box, so a
 *  region marked on one of them would describe a different part of the scan. */
export function setMouseMode(mode) {
  session.mouseMode = mode;
  if (mode === "roi") session.display = "input";
}

export function currentEntry() {
  const run = currentRun();
  return run?.result?.results?.[session.resultIndex] ?? null;
}

export function shown() {
  const entry = currentEntry();
  if (session.display === "segmented") return entry?.segmentedImage ?? null;
  if (session.display === "processed") return entry?.skeletonImage ?? null;
  return session.imageUrl;
}

export async function measure({ preview = false } = {}) {
  if (!session.file) return;

  session.runs.unshift({
    id: null,
    at: new Date(),
    preview,
    status: "pending",
    stage: null,
    percent: 0,
    // Snapshotted: editing the panel must not rewrite a finished result.
    params: $state.snapshot(session.params),
    dpi: dpi(),
    rois: $state.snapshot(session.rois),
    result: null,
    error: null,
    log: [],
  });
  session.selected = 0;
  session.resultIndex = 0;
  // Read it back out of the array: `session` is deeply reactive, so the proxy
  // is what notifies. Mutating the object we just built would write through to
  // the same data and update nothing on screen.
  const run = session.runs[0];

  try {
    const accepted = await submit({
      file: session.file,
      dpi: run.dpi,
      params: run.params,
      rois: run.rois,
      preview,
    });
    run.id = accepted.id;
    note(run, "queued", { queuePosition: accepted.queuePosition });

    follow(accepted.id, {
      started: () => {
        run.status = "processing";
        note(run, "started");
      },
      progress: (data) => {
        run.stage = data.stage;
        run.percent = data.percent;
      },
      completed: (data) => {
        run.status = "completed";
        run.percent = 100;
        run.result = data;
        session.display = preview ? "segmented" : "processed";
        if (session.mouseMode === "roi") session.mouseMode = "pan";
        if (!preview) record(run);
        note(run, "completed");
      },
      failed: (envelope) => {
        run.status = "failed";
        run.error = envelope;
        note(run, envelope.code);
      },
    });
  } catch (envelope) {
    run.status = "failed";
    run.error = envelope.code ? envelope : { code: "INTERNAL_ERROR" };
    note(run, run.error.code);
  }
}

/** One row per region, appended. Only `setMode` ever removes any of them. */
function record(run) {
  for (const entry of run.result.results) {
    session.rows.push({ at: run.at, saved: false, cells: rowFor(entry, run.params) });
  }
}

export function markSaved() {
  for (const row of session.rows) row.saved = true;
}

/** What File ▸ Save ▸ Settings writes, and File ▸ Load Settings reads back. */
export function settingsJson() {
  return JSON.stringify(
    { params: $state.snapshot(session.params), calibration: $state.snapshot(session.calibration) },
    null,
    2,
  );
}

export function loadSettings(text) {
  const saved = JSON.parse(text);
  // Unknown keys are dropped and missing ones keep their default: a settings
  // file from an older build has to stay loadable.
  const params = { ...defaults(), ...saved.params };
  setMode(params.mode);
  Object.assign(session.params, params);
  if (saved.calibration) Object.assign(session.calibration, saved.calibration);
}

function note(run, token, detail) {
  run.log.push({ at: new Date(), token, detail });
}
