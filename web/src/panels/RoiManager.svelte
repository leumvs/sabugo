<script>
import { t } from "../lib/i18n.svelte.js";
import { clampToImage } from "../lib/roi.js";
import { MAX_ROIS, removeRoi, session } from "../lib/state.svelte.js";

const FIELDS = ["x", "y", "width", "height"];

let draft = $state({ name: "", class: "root", x: 0, y: 0, width: 0, height: 0 });

const full = $derived(session.rois.length >= MAX_ROIS);
const valid = $derived(
  Boolean(session.imageSize) &&
    draft.width > 0 &&
    draft.height > 0 &&
    !session.rois.some((roi) => roi.name === name()),
);

function name() {
  return draft.name.trim() || `roi_${session.rois.length + 1}`;
}

/** Through the same clamp the drawing uses, so a typed number cannot put a
 *  region outside the image. */
function edit(roi, field, value) {
  Object.assign(roi, clampToImage({ ...roi, [field]: Number(value) }, session.imageSize));
}

function add() {
  session.rois.push({
    name: name(),
    class: draft.class.trim() || "root",
    ...clampToImage(draft, session.imageSize),
  });
  draft = { name: "", class: "root", x: 0, y: 0, width: 0, height: 0 };
}
</script>

<div class="flex h-full flex-col" aria-label={t("roiManager")}>
  <h2 class="plate shrink-0 px-3 py-2.5 text-base-content/55">{t("roiManager")}</h2>

  <div class="shrink-0 border-base-300 border-b px-3 pb-3">
    <label class="floating-label">
      <span>{t("roiName")}</span>
      <input type="text" class="input input-sm w-full" placeholder={name()} bind:value={draft.name} />
    </label>
    <label class="floating-label mt-1">
      <span>{t("roiClass")}</span>
      <input type="text" class="input input-sm w-full" bind:value={draft.class} />
    </label>
    <div class="mt-1 grid grid-cols-2 gap-1">
      {#each FIELDS as field (field)}
        <label class="floating-label">
          <span>{field}</span>
          <input
            type="number"
            class="input input-sm tnum w-full"
            min="0"
            bind:value={draft[field]}
          />
        </label>
      {/each}
    </div>
    <button
      type="button"
      class="btn btn-block btn-sm mt-2"
      disabled={!valid || full}
      onclick={add}
    >
      {t("addRoi")}
    </button>
    {#if full}
      <p class="datum mt-1 text-warning">{t("roiLimit")}</p>
    {/if}
  </div>

  <div class="min-h-0 flex-1 overflow-y-auto px-3 py-2">
    <div class="flex items-baseline justify-between">
      <h3 class="plate text-base-content/55">{t("roiList")}</h3>
      <p class="datum text-base-content/40">{t("roiReplacesWhole")}</p>
    </div>

    <ul class="mt-1 grid gap-2">
      {#each session.rois as roi (roi.name)}
        <li class="border-base-300 border-b pb-2">
          <div class="flex items-center gap-2">
            <span class="datum grow">{roi.name}</span>
            <span class="datum text-base-content/40">{roi.class ?? "root"}</span>
            <button
              type="button"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="{t('removeRegion')} {roi.name}"
              onclick={() => removeRoi(roi.name)}
            >
              <svg viewBox="0 0 16 16" class="size-3.5" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                <path d="m4 4 8 8M12 4l-8 8" stroke-linecap="round" />
              </svg>
            </button>
          </div>
          <div class="mt-1 grid grid-cols-2 gap-1">
            {#each FIELDS as field (field)}
              <label class="flex items-center gap-1">
                <span class="datum w-12 text-base-content/45">{field}</span>
                <input
                  type="number"
                  class="input input-xs tnum w-full"
                  value={roi[field]}
                  onchange={(event) => edit(roi, field, event.currentTarget.value)}
                />
              </label>
            {/each}
          </div>
        </li>
      {/each}
    </ul>
  </div>
</div>
