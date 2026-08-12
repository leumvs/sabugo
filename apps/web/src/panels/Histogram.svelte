<script>
import { locale } from "../lib/i18n.svelte.js";
import ramp from "../lib/viridis.json";

let { values, labels, unit } = $props();

// The same ramp `render.class_colours` paints the skeleton with, so a bar and
// the roots it counts are the same colour. `apps/worker/tests/test_viridis_table.py`
// keeps the two in step.
const colours = $derived(ramp[String(values.length)] ?? []);
const largest = $derived(Math.max(...values, 0));

function show(value) {
  return new Intl.NumberFormat(locale.language, { maximumFractionDigits: 2 }).format(value);
}
</script>

<ul class="grid gap-1.5">
  {#each values as value, index (index)}
    <li class="grid grid-cols-[3.5rem_1fr_auto] items-center gap-2">
      <span class="datum text-right text-base-content/55">{labels[index]}</span>
      <span class="h-3 bg-base-200" role="presentation">
        <span
          class="block h-full transition-[width] duration-300 motion-reduce:transition-none"
          style:width="{largest > 0 ? (value / largest) * 100 : 0}%"
          style:background-color={colours[index]}
        ></span>
      </span>
      <span class="datum tnum w-16 text-right">{show(value)}</span>
    </li>
  {/each}
</ul>
<p class="datum mt-1.5 text-right text-base-content/40">{unit}</p>
