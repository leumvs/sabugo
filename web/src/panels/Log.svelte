<script>
import { locale, t } from "../lib/i18n.svelte.js";
import { currentRun, session } from "../lib/state.svelte.js";

const run = $derived(currentRun());

function clock(date) {
  return new Intl.DateTimeFormat(locale.language, { timeStyle: "medium" }).format(date);
}
</script>

<div class="flex h-full flex-col">
  {#if session.runs.length > 1}
    <div class="flex shrink-0 gap-1 overflow-x-auto px-3 py-1.5">
      {#each session.runs as item, index (item.at.getTime())}
        <button
          type="button"
          class="btn btn-ghost btn-xs datum shrink-0"
          class:btn-active={session.selected === index}
          aria-pressed={session.selected === index}
          onclick={() => {
            session.selected = index;
          }}
        >
          {clock(item.at)}{item.preview ? " ·" : ""}
        </button>
      {/each}
    </div>
  {/if}

  {#if !run}
    <p class="px-3 py-2 text-[0.8125rem] text-base-content/55">{t("noResultYet")}</p>
  {:else}
    {#if run.status === "failed"}
      <div class="mx-3 mt-2 alert alert-error alert-soft" role="alert">
        <div>
          <p class="datum">{run.error?.code}</p>
          <p class="mt-1 text-[0.8125rem]">{t(run.error?.code)}</p>
        </div>
      </div>
    {/if}

    <ol class="min-h-0 flex-1 overflow-y-auto px-3 py-2">
      {#each run.log as line (line.at.getTime() + line.token)}
        <li class="flex gap-2 text-[0.75rem]">
          <span class="tnum text-base-content/40">{clock(line.at)}</span>
          <span class="datum">{line.token}</span>
          {#if line.detail}
            <span class="datum text-base-content/45">{JSON.stringify(line.detail)}</span>
          {/if}
        </li>
      {/each}
    </ol>

    {#if run.result}
      <dl class="grid shrink-0 grid-cols-4 gap-x-3 border-base-300 border-t px-3 py-2 text-[0.75rem]">
        <dt class="plate text-base-content/40">pipeline</dt>
        <dd class="tnum">{run.result.pipelineVersion}</dd>
        <dt class="plate text-base-content/40">threshold</dt>
        <dd class="tnum">{run.result.results[0]?.thresholdValueUsed}</dd>
      </dl>
    {/if}
  {/if}
</div>
