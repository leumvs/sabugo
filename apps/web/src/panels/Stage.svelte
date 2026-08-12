<script>
import { tick } from "svelte";
import logo from "../assets/sabugo.svg";
import { t } from "../lib/i18n.svelte.js";
import { classLabels } from "../lib/metrics.js";
import { rectFrom, toImagePoint, toPercent } from "../lib/roi.js";
import { addRoi, chooseFile, currentRun, session, shown } from "../lib/state.svelte.js";
import Histogram from "./Histogram.svelte";

let dragging = $state(false);
let overlay = $state(null);
let picture = $state(null);
let pane = $state(null);
let grabbing = $state(false);
let viewport = $state(0);
let paneWidth = $state(0);
/** Size of whatever is on screen; `session.imageSize` is the input's, which
 *  is what the ROI maths needs. */
let shownSize = $state(null);
let drawing = $state(null);
let anchor = null;

const natural = $derived(session.imageSize);
const source = $derived(shown());
const run = $derived(currentRun());
// The derived images come back at the size of the region, so the overlay only
// lines up with the input.
const drawable = $derived(session.display === "input" && session.mouseMode === "roi");

const entry = $derived(session.display === "processed" ? run?.result?.results?.[0] : null);

/** A scan far taller than the pane fills the width and scrolls instead:
 *  fitting its height leaves a sliver where a 3 px medial axis is invisible. */
const fillWidth = $derived(
  session.zoom === 0 &&
    shownSize &&
    viewport > 0 &&
    shownSize.height / shownSize.width > viewport / paneWidth,
);

function take(files) {
  const file = files?.[0];
  if (file) chooseFile(file);
}

function onDrop(event) {
  event.preventDefault();
  dragging = false;
  take(event.dataTransfer?.files);
}

function onLoad(event) {
  shownSize = {
    width: event.currentTarget.naturalWidth,
    height: event.currentTarget.naturalHeight,
  };
  if (session.display !== "input") return;
  session.imageSize = shownSize;
}

/**
 * Capture keeps the drag alive when the pointer leaves the element.
 *
 * ⚠️ It has to be allowed to fail: `setPointerCapture` throws `NotFoundError`
 * for a pointer id the browser does not consider active — every synthesised
 * pointer — and an unguarded call aborts the whole handler on its first line.
 */
function capture(element, event) {
  try {
    element.setPointerCapture(event.pointerId);
  } catch {}
}

function at(event) {
  // The box the browser laid out is the scale, so zoom and scrolling need no
  // bookkeeping of their own.
  return toImagePoint(
    { x: event.clientX, y: event.clientY },
    overlay.getBoundingClientRect(),
    natural,
  );
}

function startDraw(event) {
  if (!drawable || !natural || event.button !== 0) return;
  capture(overlay, event);
  anchor = at(event);
  drawing = rectFrom(anchor, anchor, natural);
}

function moveDraw(event) {
  if (!anchor) return;
  drawing = rectFrom(anchor, at(event), natural);
}

function endDraw() {
  if (drawing && (drawing.width > 4 || drawing.height > 4)) addRoi(drawing);
  anchor = null;
  drawing = null;
}

/**
 * `zoom === 0` means fit, and the factor that produced it is only known from
 * the box the browser laid out, so the first notch starts from what is on
 * screen. The pixel under the cursor stays under it: the pane is scrolled back
 * by however far that point moved, after the new size is on screen.
 */
async function onWheel(event) {
  if (!picture || !shownSize) return;
  event.preventDefault();

  const before = picture.getBoundingClientRect();
  const current = session.zoom || before.width / shownSize.width;
  const held = {
    x: (event.clientX - before.left) / before.width,
    y: (event.clientY - before.top) / before.height,
  };

  session.zoom = Math.min(Math.max(current * (event.deltaY < 0 ? 1.25 : 0.8), 0.05), 16);
  await tick();

  const after = picture.getBoundingClientRect();
  pane.scrollLeft += after.left + held.x * after.width - event.clientX;
  pane.scrollTop += after.top + held.y * after.height - event.clientY;
}

function startPan(event) {
  if (session.mouseMode !== "pan" || event.button !== 0) return;
  capture(pane, event);
  grabbing = true;
  anchor = { x: event.clientX, y: event.clientY, left: pane.scrollLeft, top: pane.scrollTop };
}

function movePan(event) {
  if (!grabbing) return;
  pane.scrollLeft = anchor.left - (event.clientX - anchor.x);
  pane.scrollTop = anchor.top - (event.clientY - anchor.y);
}

function endPan() {
  grabbing = false;
  anchor = null;
}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="flex min-h-0 min-w-0 flex-1 flex-col"
  ondragover={(event) => {
    event.preventDefault();
    dragging = true;
  }}
  ondragleave={() => {
    dragging = false;
  }}
  ondrop={onDrop}
>
  {#if session.imageUrl}
    {#if entry}
      <details class="shrink-0 border-base-300 border-b bg-base-100" open>
        <summary class="plate cursor-pointer px-4 py-1.5 text-base-content/55">
          {t("byClass")} · Root.Length (mm)
        </summary>
        <div class="px-4 pb-2">
          <Histogram
            values={entry.bins.rootLength}
            labels={classLabels(run.params.diameter_ranges_mm)}
            unit="mm"
          />
        </div>
      </details>
    {/if}

    <!--
      The scan is the lightest thing on screen and the chrome sits below it,
      like a specimen on a light table. Nothing is painted behind it: the
      background of a root scan is its own white paper.

      `justify-center-safe`, not `justify-center`: once the zoomed image is
      wider than the pane, plain centring puts its left edge at a negative
      offset that no amount of scrolling reaches.
    -->
    <div
      bind:this={pane}
      class="flex min-h-0 min-w-0 flex-1 justify-center-safe overflow-scroll px-4 py-2"
      class:cursor-grab={session.mouseMode === "pan" && !grabbing}
      class:cursor-grabbing={grabbing}
      bind:clientHeight={viewport}
      bind:clientWidth={paneWidth}
      onwheel={onWheel}
      onpointerdown={startPan}
      onpointermove={movePan}
      onpointerup={endPan}
      onpointercancel={endPan}
    >
      <div class="relative h-fit w-fit">
        <!--
          The fit is a measured pixel value, not `max-h-full`: a percentage
          max-height resolves against a parent that shrink-wraps this image,
          which is circular, and the browser drops it — leaving a 3000 px scan
          rendered at full size. The wrapper has to shrink-wrap so the overlay
          lines up with the image exactly.
        -->
        <!-- `draggable="false"`: an `<img>` is natively draggable, so pressing
             on it starts the browser's own drag, which cancels the pointer
             stream the pan and the ROI rectangle are built from. -->
        <img
          bind:this={picture}
          src={source}
          alt={session.file.name}
          draggable="false"
          onload={onLoad}
          style:width={session.zoom && shownSize
            ? `${session.zoom * shownSize.width}px`
            : fillWidth
              ? `${paneWidth - 32}px`
              : null}
          style:max-height={session.zoom || fillWidth ? null : `${viewport - 16}px`}
          class="block max-w-none border border-base-300 bg-base-100"
        />

        {#if session.display === "input"}
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <div
            bind:this={overlay}
            class="absolute inset-0 touch-none"
            class:cursor-crosshair={drawable}
            class:pointer-events-none={!drawable}
            onpointerdown={startDraw}
            onpointermove={moveDraw}
            onpointerup={endDraw}
            onpointercancel={endDraw}
          >
            {#each session.rois as roi (roi.name)}
              {@const box = toPercent(roi, natural)}
              <div
                class="absolute border border-primary bg-primary/10"
                style:left="{box.left}%"
                style:top="{box.top}%"
                style:width="{box.width}%"
                style:height="{box.height}%"
              >
                <span class="datum absolute top-0 left-0 bg-primary px-1 text-primary-content">
                  {roi.name}
                </span>
              </div>
            {/each}

            {#if drawing}
              {@const box = toPercent(drawing, natural)}
              <div
                class="absolute border border-base-content border-dashed"
                style:left="{box.left}%"
                style:top="{box.top}%"
                style:width="{box.width}%"
                style:height="{box.height}%"
              ></div>
            {/if}
          </div>
        {/if}
      </div>
    </div>

    <p class="datum shrink-0 px-4 pb-2 text-center text-base-content/45">
      {session.file.name}
      {#if natural}
        · {natural.width}×{natural.height} px
      {/if}
      {#if drawable}
        · {t("drawHint")}
      {/if}
    </p>
  {:else}
    <div class="flex min-h-0 flex-1 items-center justify-center p-6">
      <label
        class="flex max-w-md cursor-pointer flex-col items-center gap-3 rounded-box border border-dashed px-8 py-12 text-center transition-colors motion-reduce:transition-none"
        class:border-base-content={dragging}
        class:border-base-300={!dragging}
      >
        <img src={logo} alt="Sabugo" class="mb-1 size-24" />
        <span class="text-lg">{t("dropHere")}</span>
        <span class="text-[0.8125rem] text-base-content/55">{t("dropHint")}</span>
        <input
          type="file"
          class="file-input file-input-sm mt-1"
          accept="image/bmp,image/jpeg,image/png,image/tiff"
          onchange={(event) => take(event.currentTarget.files)}
        />
      </label>
    </div>
  {/if}
</div>
