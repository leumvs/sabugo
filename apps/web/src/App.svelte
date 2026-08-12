<script>
import { t } from "./lib/i18n.svelte.js";
import { colourStatistics } from "./lib/image.js";
import { hasUnsavedResult, session } from "./lib/state.svelte.js";
import Busy from "./panels/Busy.svelte";
import Features from "./panels/Features.svelte";
import Log from "./panels/Log.svelte";
import MenuBar from "./panels/MenuBar.svelte";
import Options from "./panels/Options.svelte";
import RoiManager from "./panels/RoiManager.svelte";
import Stage from "./panels/Stage.svelte";
import ToolBar from "./panels/ToolBar.svelte";

let bottomTab = $state("features");
let problem = $state(null);
let stats = $state(null);
let statsDialog = $state(null);

// The tab is the only place a result exists (3), so a reload is real data loss.
$effect(() => {
  const guard = (event) => {
    if (!hasUnsavedResult()) return;
    event.preventDefault();
  };
  window.addEventListener("beforeunload", guard);
  return () => window.removeEventListener("beforeunload", guard);
});

async function showColourStats(roi) {
  if (!session.file) {
    problem = "needImage";
    return;
  }
  stats = { region: roi?.name ?? t("wholeImage"), ...(await colourStatistics(session.file, roi)) };
  statsDialog.showModal();
}

function show(value) {
  return value.toFixed(2);
}
</script>

<div class="flex h-dvh flex-col bg-base-200 text-base-content">
  <MenuBar onError={(token) => (problem = token)} />
  <ToolBar onColourStats={showColourStats} />
  <Busy />

  {#if problem}
    <div class="alert alert-error alert-soft mx-3 mt-2 py-2" role="alert">
      <p class="text-[0.8125rem]">{t(problem)}</p>
      <button type="button" class="btn btn-ghost btn-xs" onclick={() => (problem = null)}>
        {t("close")}
      </button>
    </div>
  {/if}

  <!-- Stacked below `lg` the page itself scrolls; from `lg` each dock
       scrolls on its own. -->
  <div class="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
    {#if session.docks.options}
      <section
        class="shrink-0 border-base-300 border-b bg-base-100 lg:w-72 lg:min-h-0 lg:overflow-hidden lg:border-r lg:border-b-0"
        aria-label={t("parameters")}
      >
        <Options />
      </section>
    {/if}

    <!-- `min-w-0`: a flex item defaults to `min-width: auto`, so a zoomed
         image would widen this column past its share and push the ROI manager
         off the screen instead of scrolling inside its own pane. -->
    <section
      class="flex min-h-[50vh] flex-col lg:min-h-0 lg:min-w-0 lg:flex-1"
      aria-label={t("stage")}
    >
      <Stage />
    </section>

    {#if session.docks.rois}
      <section
        class="shrink-0 border-base-300 border-t bg-base-100 lg:w-72 lg:min-h-0 lg:border-t-0 lg:border-l"
        aria-label={t("roiManager")}
      >
        <RoiManager />
      </section>
    {/if}
  </div>

  {#if session.docks.bottom}
    <section
      class="flex h-64 shrink-0 flex-col border-base-300 border-t bg-base-100"
      aria-label={t("featuresTab")}
    >
      <div role="tablist" class="tabs tabs-border tabs-xs shrink-0 px-2">
        {#each [["log", "log"], ["features", "featuresTab"]] as [id, label] (id)}
          <button
            type="button"
            role="tab"
            class="tab plate"
            class:tab-active={bottomTab === id}
            onclick={() => (bottomTab = id)}
          >
            {t(label)}
          </button>
        {/each}
      </div>
      <div class="min-h-0 flex-1">
        {#if bottomTab === "features"}<Features />{:else}<Log />{/if}
      </div>
    </section>
  {/if}
</div>

<dialog bind:this={statsDialog} class="modal">
  <div class="modal-box">
    <h3 class="plate">{t("colourStats")} — <span class="datum">{stats?.region}</span></h3>
    {#if stats}
      <table class="table mt-3 table-xs">
        <thead>
          <tr><th></th><th class="datum text-right">R</th><th class="datum text-right">G</th><th class="datum text-right">B</th></tr>
        </thead>
        <tbody>
          {#each [[t("mean"), stats.mean], [t("sd"), stats.sd]] as [label, values] (label)}
            <tr class="border-base-300">
              <th class="font-normal text-base-content/60">{label}</th>
              {#each values as value, channel (channel)}
                <td class="tnum text-right">{show(value)}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
    <form method="dialog" class="modal-action">
      <button type="submit" class="btn btn-sm">{t("close")}</button>
    </form>
  </div>
  <form method="dialog" class="modal-backdrop"><button type="submit">{t("close")}</button></form>
</dialog>
