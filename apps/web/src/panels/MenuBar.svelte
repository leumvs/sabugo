<script>
import logo from "../assets/sabugo.svg";
import { format, parse } from "../lib/annotation.js";
import { download } from "../lib/api.js";
import { toCsv } from "../lib/csv.js";
import { LANGUAGES, locale, setLanguage, t } from "../lib/i18n.svelte.js";
import { clampToImage } from "../lib/roi.js";
import {
  chooseFile,
  loadSettings,
  MAX_ROIS,
  markSaved,
  session,
  settingsJson,
  shown,
} from "../lib/state.svelte.js";

let { onError } = $props();

let imagePicker = $state(null);
let annotationPicker = $state(null);
let settingsPicker = $state(null);
let about = $state(null);

const stem = $derived(
  (session.file?.name ?? "sabugo").replace(/\.[^.]+$/, "").replace(/^/, "sabugo-"),
);

let bar = $state(null);

/** A `<details>` stays open after a click, and the shared `name` only closes
 *  the other menus. */
function closeMenus() {
  for (const menu of bar?.querySelectorAll("details[open]") ?? []) menu.open = false;
}

$effect(() => {
  const away = (event) => {
    if (!bar.contains(event.target)) closeMenus();
  };
  document.addEventListener("pointerdown", away);
  return () => document.removeEventListener("pointerdown", away);
});

function takeImage(files) {
  const file = files?.[0];
  if (file) chooseFile(file);
}

async function takeAnnotation(files) {
  const file = files?.[0];
  if (!file) return;
  try {
    // The same clamp the drawing uses: a file written against a bigger scan
    // cannot place a region outside this one.
    const loaded = parse(await file.text()).slice(0, MAX_ROIS);
    session.rois = loaded.map((roi) => ({
      ...roi,
      ...clampToImage(
        roi,
        session.imageSize ?? { width: roi.x + roi.width, height: roi.y + roi.height },
      ),
    }));
  } catch (error) {
    onError(error.message);
  }
}

async function takeSettings(files) {
  const file = files?.[0];
  if (!file) return;
  try {
    loadSettings(await file.text());
  } catch {
    onError("settings_unreadable");
  }
}

function text(name, body, type) {
  download(name, new Blob([body], { type: `${type};charset=utf-8` }));
}

async function saveDisplayed() {
  const source = shown();
  if (!source) return onError("needImage");
  download(`${stem}-${session.display}.png`, await (await fetch(source)).blob());
}

function saveFeatures() {
  if (session.rows.length === 0) return onError("noRows");
  text(`${stem}.csv`, toCsv(session.rows.map((row) => row.cells)), "text/csv");
  markSaved();
}
</script>

<nav
  bind:this={bar}
  class="flex shrink-0 items-center gap-1 border-base-300 border-b bg-base-100 px-2 py-1"
  aria-label="menu"
>
  <img src={logo} alt="" class="mr-1 size-5" />
  <span class="plate mr-2 font-bold text-[0.8125rem]">Sabugo</span>

  <details class="dropdown" name="menubar">
    <summary class="btn btn-ghost btn-xs">{t("menuFile")}</summary>
    <!-- Pinned to the viewport below `sm`, or a menu opened from the fourth
         button widens the page and lets it scroll sideways. -->
    <ul
      class="dropdown-content menu z-10 w-56 border border-base-300 bg-base-100 p-1 text-[0.8125rem] shadow max-sm:fixed max-sm:inset-x-2 max-sm:w-auto"
    >
      <li><button type="button" onclick={() => { closeMenus(); imagePicker.click(); }}>{t("openImage")}</button></li>
      <li><button type="button" onclick={() => { closeMenus(); annotationPicker.click(); }}>{t("loadAnnotation")}</button></li>
      <li><button type="button" onclick={() => { closeMenus(); settingsPicker.click(); }}>{t("loadSettings")}</button></li>
      <li>
        <span class="plate text-base-content/45">{t("save")}</span>
        <ul>
          <li><button type="button" onclick={() => { closeMenus(); saveDisplayed(); }}>{t("saveDisplayed")}</button></li>
          <li><button type="button" onclick={() => { closeMenus(); text(`${stem}-rois.csv`, format(session.rois), "text/csv"); }}>{t("saveAnnotation")}</button></li>
          <li><button type="button" onclick={() => { closeMenus(); saveFeatures(); }}>{t("saveFeatures")}</button></li>
          <li><button type="button" onclick={() => { closeMenus(); text(`${stem}-settings.json`, settingsJson(), "application/json"); }}>{t("saveSettings")}</button></li>
        </ul>
      </li>
    </ul>
  </details>

  <details class="dropdown" name="menubar">
    <summary class="btn btn-ghost btn-xs">{t("menuEdit")}</summary>
    <ul
      class="dropdown-content menu z-10 w-56 border border-base-300 bg-base-100 p-1 text-[0.8125rem] shadow max-sm:fixed max-sm:inset-x-2 max-sm:w-auto"
    >
      <li><button type="button" onclick={() => { closeMenus(); session.rois = []; }}>{t("clearRois")}</button></li>
      <li>
        <button
          type="button"
          onclick={() => { closeMenus(); session.params.invert_image = !session.params.invert_image; }}
        >
          {t("invertColors")}
        </button>
      </li>
    </ul>
  </details>

  <details class="dropdown" name="menubar">
    <summary class="btn btn-ghost btn-xs">{t("menuView")}</summary>
    <ul
      class="dropdown-content menu z-10 w-56 border border-base-300 bg-base-100 p-1 text-[0.8125rem] shadow max-sm:fixed max-sm:inset-x-2 max-sm:w-auto"
    >
      {#each [["options", "parameters"], ["rois", "roiManager"], ["bottom", "featuresTab"]] as [dock, label] (dock)}
        <li>
          <label class="gap-2">
            <input type="checkbox" class="checkbox checkbox-xs" bind:checked={session.docks[dock]} />
            {t(label)}
          </label>
        </li>
      {/each}
    </ul>
  </details>

  <details class="dropdown" name="menubar">
    <summary class="btn btn-ghost btn-xs">{t("menuHelp")}</summary>
    <ul
      class="dropdown-content menu z-10 w-56 border border-base-300 bg-base-100 p-1 text-[0.8125rem] shadow max-sm:fixed max-sm:inset-x-2 max-sm:w-auto"
    >
      <li><button type="button" onclick={() => { closeMenus(); about.showModal(); }}>{t("about")}</button></li>
    </ul>
  </details>

  <div class="join ml-auto" role="group" aria-label={t("language")}>
    {#each LANGUAGES as code (code)}
      <button
        type="button"
        class="btn join-item btn-ghost btn-xs plate"
        class:btn-active={locale.language === code}
        aria-pressed={locale.language === code}
        onclick={() => setLanguage(code)}
      >
        {code}
      </button>
    {/each}
  </div>
</nav>

<input
  bind:this={imagePicker}
  type="file"
  class="hidden"
  accept="image/bmp,image/jpeg,image/png,image/tiff"
  onchange={(event) => takeImage(event.currentTarget.files)}
/>
<input
  bind:this={annotationPicker}
  type="file"
  class="hidden"
  accept=".csv,text/csv,text/plain"
  onchange={(event) => takeAnnotation(event.currentTarget.files)}
/>
<input
  bind:this={settingsPicker}
  type="file"
  class="hidden"
  accept=".json,application/json"
  onchange={(event) => takeSettings(event.currentTarget.files)}
/>

<dialog bind:this={about} class="modal">
  <div class="modal-box">
    <h3 class="plate">Sabugo</h3>
    <p class="mt-2 text-[0.8125rem]">{t("aboutText")}</p>
    <form method="dialog" class="modal-action">
      <button type="submit" class="btn btn-sm">{t("close")}</button>
    </form>
  </div>
  <form method="dialog" class="modal-backdrop"><button type="submit">{t("close")}</button></form>
</dialog>
