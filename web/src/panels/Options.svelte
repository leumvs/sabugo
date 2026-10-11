<script>
import { t } from "../lib/i18n.svelte.js";
import { measure, session, setMode } from "../lib/state.svelte.js";

const params = $derived(session.params);

// Outside 200–1200 the value is accepted and only flagged.
const dpiUnusual = $derived(
  session.calibration.unit === "dpi" &&
    (session.calibration.value < 200 || session.calibration.value > 1200),
);

const rangesError = $derived.by(() => {
  const values = params.diameter_ranges_mm;
  if (values.some((value) => Number.isNaN(value))) return "diameter_ranges_not_numbers";
  if (values.some((value) => value <= 0)) return "diameter_ranges_must_be_positive";
  if (values.some((value, index) => index > 0 && value <= values[index - 1])) {
    return "diameter_ranges_must_be_strictly_increasing";
  }
  return null;
});

const ready = $derived(Boolean(session.file) && !rangesError && session.calibration.value > 0);
const wholeRoot = $derived(params.mode === "whole_root");

/** n boundaries make n+1 rows, and the lower bound of a row is the upper
 *  bound of the one above it. */
const rows = $derived(
  params.diameter_ranges_mm.map((upper, index) => ({
    index,
    lower: index === 0 ? 0 : params.diameter_ranges_mm[index - 1],
    upper,
  })),
);

function addRange() {
  if (params.diameter_ranges_mm.length >= 11) return;
  params.diameter_ranges_mm.push(params.diameter_ranges_mm.at(-1) + 1);
}

function removeRange() {
  if (params.diameter_ranges_mm.length <= 1) return;
  params.diameter_ranges_mm.pop();
}
</script>

<div class="flex h-full flex-col">
  <div class="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
    <!-- One page open at a time: `type="radio"` with a shared name is what
         enforces it, since daisyUI reads the input's checked state. -->
    <div class="collapse-arrow collapse rounded-none border-base-300 border-b">
      <input type="radio" name="analysis-options" checked />
      <div class="collapse-title plate min-h-0 py-2.5 text-base-content/70">
        {t("preprocessing")}
      </div>
      <!-- `min-w-0` on both, and daisyUI's `.fieldset` is why: it is a grid
           with `min-width: min-content`, so its widest row sets a floor the
           column cannot go under and at 375 px the page scrolls sideways. -->
      <div class="collapse-content min-w-0">
        <fieldset class="fieldset min-w-0 py-0">
          <label class="floating-label">
            <span>{t("analysisMode")}</span>
            <select
              class="select select-sm w-full"
              value={params.mode}
              onchange={(event) => setMode(event.currentTarget.value)}
            >
              <option value="broken_roots">{t("modeBroken")}</option>
              <option value="whole_root">{t("modeWhole")}</option>
            </select>
          </label>

          <div class="mt-1 flex gap-2">
            <label class="floating-label grow">
              <span>{t("calibration")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="1"
                bind:value={session.calibration.value}
              />
            </label>
            <select class="select select-sm w-28" bind:value={session.calibration.unit}>
              <option value="dpi">DPI</option>
              <option value="px_mm">px/mm</option>
            </select>
          </div>
          {#if dpiUnusual}
            <p class="text-[0.75rem] text-warning">{t("dpiUnusual")}</p>
          {:else}
            <p class="text-[0.75rem] text-base-content/55">{t("dpiHint")}</p>
          {/if}

          <label class="floating-label mt-1">
            <span>{t("thresholdMethod")}</span>
            <select class="select select-sm w-full" bind:value={params.threshold_method}>
              <option value="manual">{t("thresholdManual")}</option>
              <option value="otsu">{t("thresholdOtsu")}</option>
            </select>
          </label>

          {#if params.threshold_method === "manual"}
            <p class="mt-1 text-[0.75rem]">{t("thresholdLevel")}</p>
            <div class="flex items-center gap-3">
              <input
                type="range"
                class="range range-xs grow"
                min="0"
                max="255"
                aria-label={t("thresholdLevel")}
                bind:value={params.threshold_value}
              />
              <span class="datum tnum w-8 text-right">{params.threshold_value}</span>
            </div>
            <p class="text-[0.75rem] text-base-content/55">{t("thresholdHint")}</p>
          {/if}

          <label class="label mt-1 gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.invert_image}
            />
            {t("invertImage")}
          </label>

          <label class="label gap-2">
            <input type="checkbox" class="checkbox checkbox-sm" bind:checked={params.keep_largest} />
            {t("keepLargest")}
          </label>

          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.filter_background_noise}
            />
            {t("filterNonRoot")}
          </label>
          {#if params.filter_background_noise}
            <label class="floating-label">
              <span>{t("maximumSize")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="0.01"
                step="0.1"
                bind:value={params.max_background_noise_mm2}
              />
            </label>
          {/if}

          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.filter_foreground_noise}
            />
            {t("fillHoles")}
          </label>
          {#if params.filter_foreground_noise}
            <label class="floating-label">
              <span>{t("maximumSize")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="0.01"
                step="0.1"
                bind:value={params.max_foreground_noise_mm2}
              />
            </label>
          {/if}

          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.enable_edge_smoothing}
            />
            {t("edgeSmoothing")}
          </label>
          {#if params.enable_edge_smoothing}
            <label class="floating-label">
              <span>{t("edgeSmoothingThreshold")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="0.1"
                step="0.5"
                bind:value={params.edge_smoothing_threshold}
              />
            </label>
          {/if}

          <button
            type="button"
            class="btn btn-block btn-sm mt-2"
            disabled={!ready}
            onclick={() => measure({ preview: true })}
          >
            {t("previewSegmented")}
          </button>
        </fieldset>
      </div>
    </div>

    <div class="collapse-arrow collapse rounded-none border-base-300 border-b">
      <input type="radio" name="analysis-options" />
      <div class="collapse-title plate min-h-0 py-2.5 text-base-content/70">{t("features")}</div>
      <div class="collapse-content min-w-0">
        <fieldset class="fieldset min-w-0 py-0">
          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.enable_root_pruning}
            />
            {t("rootPruning")}
          </label>
          {#if params.enable_root_pruning}
            <label class="floating-label">
              <span>{t("rootPruningThreshold")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="0"
                step="1"
                bind:value={params.root_pruning_threshold}
              />
            </label>
            <p class="text-[0.75rem] text-base-content/55">{t("pruningHint")}</p>
          {/if}

          <p class="mt-2 text-[0.75rem]">{t("diameterRanges")}</p>
          <ul class="mt-1 grid gap-1">
            {#each rows as row (row.index)}
              <li class="flex items-center gap-2">
                <span class="datum w-14 text-base-content/55">{t("rangeRow")} #{row.index + 1}</span>
                <input type="number" class="input input-xs tnum w-16" value={row.lower} readonly />
                <span class="datum text-base-content/55">{t("rangeTo")}</span>
                <input
                  type="number"
                  class="input input-xs tnum w-16"
                  min="0.01"
                  step="0.1"
                  bind:value={params.diameter_ranges_mm[row.index]}
                />
              </li>
            {/each}
            <li class="flex items-center gap-2">
              <span class="datum w-14 text-base-content/55">
                {t("rangeRow")} #{rows.length + 1}
              </span>
              <input
                type="number"
                class="input input-xs tnum w-16"
                value={params.diameter_ranges_mm.at(-1)}
                readonly
              />
              <span class="datum text-base-content/55">{t("rangeAbove")}</span>
            </li>
          </ul>

          <div class="mt-1 flex gap-1">
            <button
              type="button"
              class="btn btn-xs"
              aria-label={t("addRange")}
              disabled={params.diameter_ranges_mm.length >= 11}
              onclick={addRange}
            >
              +
            </button>
            <button
              type="button"
              class="btn btn-xs"
              aria-label={t("removeRange")}
              disabled={params.diameter_ranges_mm.length <= 1}
              onclick={removeRange}
            >
              −
            </button>
          </div>
          {#if rangesError}
            <p class="datum text-error">{t(rangesError)}</p>
          {:else}
            <p class="text-[0.75rem] text-base-content/55">
              {t("classCount").replace("{n}", params.diameter_ranges_mm.length + 1)}
            </p>
          {/if}
        </fieldset>
      </div>
    </div>

    <div class="collapse-arrow collapse rounded-none border-base-300 border-b">
      <input type="radio" name="analysis-options" />
      <div class="collapse-title plate min-h-0 py-2.5 text-base-content/70">
        {t("outputDisplay")}
      </div>
      <div class="collapse-content min-w-0">
        <fieldset class="fieldset min-w-0 py-0">
          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.show_medial_axis}
            />
            {t("showMedialAxis")}
          </label>
          {#if params.show_medial_axis}
            <label class="floating-label">
              <span>{t("medialAxisWidth")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="1"
                max="20"
                bind:value={params.medial_axis_width}
              />
            </label>
            <label class="label gap-2">
              <input
                type="checkbox"
                class="checkbox checkbox-sm"
                bind:checked={params.show_medial_axis_diameter}
              />
              {t("colourByDiameter")}
            </label>
          {/if}

          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.show_contours}
            />
            {t("showRootContour")}
          </label>
          {#if params.show_contours}
            <label class="floating-label">
              <span>{t("contourWidth")}</span>
              <input
                type="number"
                class="input input-sm tnum w-full"
                min="1"
                max="20"
                bind:value={params.contour_width}
              />
            </label>
          {/if}

          <!-- Whole root only: a hull around loose fragments means nothing. -->
          <label class="label gap-2" title={wholeRoot ? null : t("wholeRootOnly")}>
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              disabled={!wholeRoot}
              bind:checked={params.show_convex_hull}
            />
            {t("showConvexHull")}
          </label>

          <label class="label gap-2" title={wholeRoot ? null : t("wholeRootOnly")}>
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              disabled={!wholeRoot}
              bind:checked={params.show_holes}
            />
            {t("showHoles")}
          </label>
          {#if !wholeRoot}
            <p class="text-[0.75rem] text-base-content/55">{t("wholeRootOnly")}</p>
          {/if}

          <label class="label gap-2">
            <input
              type="checkbox"
              class="checkbox checkbox-sm"
              bind:checked={params.show_dist_map}
            />
            {t("showDistanceMap")}
          </label>
        </fieldset>
      </div>
    </div>
  </div>

  <div class="border-base-300 border-t p-3">
    <button
      type="button"
      class="btn btn-primary btn-block btn-sm"
      disabled={!ready}
      onclick={() => measure()}
    >
      {t("run")}
    </button>
  </div>
</div>
