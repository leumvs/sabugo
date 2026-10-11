<script>
import { t } from "../lib/i18n.svelte.js";
import { currentRun } from "../lib/state.svelte.js";

const run = $derived(currentRun());
const busy = $derived(run?.status === "pending" || run?.status === "processing");
</script>

<!-- Covers the window: a run's parameters are snapshotted when it starts,
     so editing the panel mid-run would show numbers that no longer describe
     what is being measured. -->
{#if busy}
  <div
    class="fixed inset-0 z-50 grid place-items-center bg-base-300/70"
    role="alert"
    aria-live="polite"
    aria-busy="true"
  >
    <div class="grid justify-items-center gap-3">
      <span class="loading loading-lg loading-spinner text-primary"></span>
      <p class="plate">{t(run.stage ?? run.status)}</p>
      <p class="datum tnum text-base-content/60">{Math.round(run.percent)}%</p>
    </div>
  </div>
{/if}
