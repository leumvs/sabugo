<script>
import { t } from "../lib/i18n.svelte.js";
import { currentRun, measure, session, setMouseMode, setRotation } from "../lib/state.svelte.js";

let { onColourStats } = $props();

const MODES = [
  { id: "pan", label: "panMode", path: "M8 2v12M2 8h12" },
  { id: "roi", label: "roiMode", path: "M2.5 2.5h11v11h-11z" },
];

const OUTPUTS = ["input", "segmented", "processed"];
const LABEL = { input: "inputImage", segmented: "segmentedImage", processed: "processedImage" };

const run = $derived(currentRun());
const ready = $derived(Boolean(session.file));
const busy = $derived(run?.status === "pending" || run?.status === "processing");
const available = $derived(
  new Set(["input", ...(run?.status === "completed" ? outputsOf(run) : [])]),
);

/** A preview produces no feature image, so the selector must not offer one. */
function outputsOf(finished) {
  const entry = finished.result?.results?.[0];
  return [entry?.segmentedImage && "segmented", entry?.skeletonImage && "processed"].filter(
    Boolean,
  );
}

function zoomBy(factor) {
  const current = session.zoom || 1;
  session.zoom = Math.min(Math.max(current * factor, 0.1), 16);
}
</script>

<div
  class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-base-300 border-b bg-base-100 px-3 py-1.5"
>
  <div class="join" role="group" aria-label={t("roiMode")}>
    {#each MODES as mode (mode.id)}
      <button
        type="button"
        class="btn join-item btn-square btn-ghost btn-xs"
        class:btn-active={session.mouseMode === mode.id}
        aria-pressed={session.mouseMode === mode.id}
        title={t(mode.label)}
        aria-label={t(mode.label)}
        onclick={() => setMouseMode(mode.id)}
      >
        <svg viewBox="0 0 16 16" class="size-3.5" fill="none" stroke="currentColor" stroke-width="1.25" aria-hidden="true">
          <path d={mode.path} stroke-linecap="round" />
        </svg>
      </button>
    {/each}
  </div>

  <div class="join" role="group" aria-label={t("zoomFit")}>
    <button
      type="button"
      class="btn join-item btn-ghost btn-xs datum"
      title={t("zoomOut")}
      aria-label={t("zoomOut")}
      onclick={() => zoomBy(0.5)}>−</button
    >
    <button
      type="button"
      class="btn join-item btn-ghost btn-xs datum"
      title={t("zoomIn")}
      aria-label={t("zoomIn")}
      onclick={() => zoomBy(2)}>+</button
    >
    <button
      type="button"
      class="btn join-item btn-ghost btn-xs datum"
      class:btn-active={session.zoom === 0}
      title={t("zoomFit")}
      aria-label={t("zoomFit")}
      onclick={() => {
        session.zoom = 0;
      }}>fit</button
    >
  </div>

  <div class="join" role="group" aria-label={t("colourStats")}>
    <button
      type="button"
      class="btn join-item btn-ghost btn-xs datum"
      disabled={!ready}
      onclick={() => onColourStats(null)}
    >
      {t("colourStats")}
    </button>
    <button
      type="button"
      class="btn join-item btn-ghost btn-xs datum"
      disabled={!ready || session.rois.length === 0}
      onclick={() => onColourStats(session.rois[0])}
    >
      ROI
    </button>
  </div>

  <button
    type="button"
    class="btn btn-ghost btn-xs datum"
    class:btn-active={session.params.invert_image}
    aria-pressed={session.params.invert_image}
    title={t("invertColors")}
    onclick={() => {
      session.params.invert_image = !session.params.invert_image;
    }}
  >
    {t("invertColors")}
  </button>

  <label class="flex items-center gap-1.5">
    <span class="datum text-base-content/55">{t("rotation")}</span>
    <select
      class="select select-xs tnum w-20"
      disabled={!ready}
      value={session.rotation}
      onchange={(event) => setRotation(Number(event.currentTarget.value))}
    >
      {#each [0, 90, 180, 270] as degrees (degrees)}
        <option value={degrees}>{degrees}°</option>
      {/each}
    </select>
  </label>

  <label class="flex items-center gap-1.5">
    <span class="datum text-base-content/55">{t("displayOutput")}</span>
    <select class="select select-xs w-40" bind:value={session.display}>
      {#each OUTPUTS as output (output)}
        <option value={output} disabled={!available.has(output)}>{t(LABEL[output])}</option>
      {/each}
    </select>
  </label>

  <button
    type="button"
    class="btn btn-primary btn-xs ml-auto"
    disabled={!ready || busy}
    onclick={() => measure()}
  >
    {t("run")}
  </button>
</div>
