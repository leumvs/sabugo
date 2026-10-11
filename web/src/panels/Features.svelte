<script>
import { download } from "../lib/api.js";
import { toCsv } from "../lib/csv.js";
import { t } from "../lib/i18n.svelte.js";
import { markSaved, session } from "../lib/state.svelte.js";

/** Accumulates one row per region per run; only `setMode` clears it. Rows
 *  are keyed by column name, so a run with more diameter classes widens the
 *  table instead of shifting older rows into the wrong cells. */
const header = $derived([...new Set(session.rows.flatMap((row) => Object.keys(row.cells)))]);

function saveCsv() {
  download(
    `sabugo-features.csv`,
    new Blob([toCsv(session.rows.map((row) => row.cells))], { type: "text/csv;charset=utf-8" }),
  );
  markSaved();
}
</script>

<div class="flex h-full flex-col">
  <div class="flex shrink-0 items-center gap-3 px-3 py-1.5">
    <p class="datum text-base-content/40">{t("rowsKeep")}</p>
    <button
      type="button"
      class="btn btn-sm ml-auto"
      disabled={session.rows.length === 0}
      onclick={saveCsv}
    >
      {t("downloadCsv")}
    </button>
  </div>

  {#if session.rows.length === 0}
    <p class="px-3 pb-3 text-[0.8125rem] text-base-content/55">{t("noRows")}</p>
  {:else}
    <div class="min-h-0 flex-1 overflow-auto">
      <table class="table table-pin-rows table-xs">
        <thead>
          <tr>
            <th class="w-8"></th>
            {#each header as column (column)}
              <th class="datum whitespace-nowrap font-normal">{column}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each session.rows as row, index (index)}
            <tr class="border-base-300">
              <th class="tnum font-normal text-base-content/40">{index + 1}</th>
              {#each header as column (column)}
                <td class="tnum whitespace-nowrap">{row.cells[column] ?? ""}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
