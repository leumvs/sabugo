import { HISTOGRAMS, metricsFor } from "./metrics.js";

/** Built in the browser from what the `completed` event carried, under the
 *  column names and order of `export.py`. */

function histogramColumn(histogram, index) {
  return `${histogram.column}.Diameter.Range.${index + 1}.${histogram.unit}`;
}

export function columns(diameterRanges, mode) {
  const classes = diameterRanges.length + 1;
  const histograms = HISTOGRAMS.flatMap((histogram) =>
    Array.from({ length: classes }, (_, index) => histogramColumn(histogram, index)),
  );
  return [
    "File.Name",
    "Region.of.Interest",
    ...metricsFor(mode).map((metric) => metric.column),
    ...histograms,
  ];
}

function cell(value) {
  return Number(value).toFixed(6);
}

/** Keyed by column name and not by position: two runs with different
 *  `diameter_ranges_mm` are sheets of different widths. */
export function rowFor(entry, params) {
  const values = [entry.fileName, entry.roiName];
  for (const metric of metricsFor(params.mode)) {
    const raw = entry.metrics[metric.key];
    values.push(cell(metric.seconds ? raw / 1000 : raw));
  }
  for (const histogram of HISTOGRAMS) {
    for (const value of entry.bins[histogram.key]) values.push(cell(value));
  }
  return Object.fromEntries(
    columns(params.diameter_ranges_mm, params.mode).map((name, index) => [name, values[index]]),
  );
}

export function toCsv(rows) {
  const header = [...new Set(rows.flatMap(Object.keys))];
  return [header, ...rows.map((row) => header.map((name) => row[name] ?? ""))]
    .map((row) => row.join(","))
    .join("\n")
    .concat("\n");
}
