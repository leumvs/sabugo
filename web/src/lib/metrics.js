/** The output contract, in the order `export.py` emits it: the result table
 *  reads `unit`, the CSV export reads `column` and the order. */

const BROKEN_ROOTS = [
  { key: "numRootTips", column: "Number.of.Root.Tips", unit: "" },
  { key: "numBranchPoints", column: "Number.of.Branch.Points", unit: "" },
  { key: "totalRootLength", column: "Total.Root.Length.mm", unit: "mm" },
  { key: "branchingFrequency", column: "Branching.frequency.per.mm", unit: "mm⁻¹" },
  { key: "networkArea", column: "Network.Area.mm2", unit: "mm²" },
  { key: "averageDiameter", column: "Average.Diameter.mm", unit: "mm" },
  { key: "medianDiameter", column: "Median.Diameter.mm", unit: "mm" },
  { key: "maxDiameter", column: "Maximum.Diameter.mm", unit: "mm" },
  { key: "perimeter", column: "Perimeter.mm", unit: "mm" },
  { key: "volume", column: "Volume.mm3", unit: "mm³" },
  { key: "surfaceArea", column: "Surface.Area.mm2", unit: "mm²" },
  // The metric is in milliseconds; the column is seconds.
  { key: "processingTimeMs", column: "Computation.Time.s", unit: "ms", seconds: true },
];

const WHOLE_ROOT = [
  { key: "medianNumberOfRoots", column: "Median.Number.of.Roots", unit: "" },
  { key: "maxNumberOfRoots", column: "Maximum.Number.of.Roots", unit: "" },
  { key: "numRootTips", column: "Number.of.Root.Tips", unit: "" },
  { key: "totalRootLength", column: "Total.Root.Length.mm", unit: "mm" },
  { key: "depth", column: "Depth.mm", unit: "mm" },
  { key: "maxWidth", column: "Maximum.Width.mm", unit: "mm" },
  { key: "widthToDepthRatio", column: "Width-to-Depth.Ratio", unit: "" },
  { key: "networkArea", column: "Network.Area.mm2", unit: "mm²" },
  { key: "convexArea", column: "Convex.Area.mm2", unit: "mm²" },
  { key: "solidity", column: "Solidity", unit: "" },
  { key: "lowerRootArea", column: "Lower.Root.Area.mm2", unit: "mm²" },
  { key: "averageDiameter", column: "Average.Diameter.mm", unit: "mm" },
  { key: "medianDiameter", column: "Median.Diameter.mm", unit: "mm" },
  { key: "maxDiameter", column: "Maximum.Diameter.mm", unit: "mm" },
  { key: "perimeter", column: "Perimeter.mm", unit: "mm" },
  { key: "volume", column: "Volume.mm3", unit: "mm³" },
  { key: "surfaceArea", column: "Surface.Area.mm2", unit: "mm²" },
  { key: "holes", column: "Holes", unit: "" },
  { key: "averageHoleSize", column: "Average.Hole.Size.mm2", unit: "mm²" },
  { key: "processingTimeMs", column: "Computation.Time.s", unit: "ms", seconds: true },
  { key: "averageRootOrientation", column: "Average.Root.Orientation.deg", unit: "°" },
  { key: "shallowAngleFrequency", column: "Shallow.Angle.Frequency", unit: "" },
  { key: "mediumAngleFrequency", column: "Medium.Angle.Frequency", unit: "" },
  { key: "steepAngleFrequency", column: "Steep.Angle.Frequency", unit: "" },
];

export function metricsFor(mode) {
  return mode === "whole_root" ? WHOLE_ROOT : BROKEN_ROOTS;
}

export const HISTOGRAMS = [
  { key: "rootLength", column: "Root.Length", unit: "mm" },
  { key: "projectedArea", column: "Projected.Area", unit: "mm2" },
  { key: "surfaceArea", column: "Surface.Area", unit: "mm2" },
  { key: "volume", column: "Volume", unit: "mm3" },
];

/** `[2, 5]` names three classes: `0–2`, `2–5`, `5+`. The boundaries are the
 *  inner ones. */
export function classLabels(diameterRanges) {
  const edges = [0, ...diameterRanges];
  const labels = diameterRanges.map((upper, index) => `${edges[index]}–${upper}`);
  return [...labels, `${edges.at(-1)}+`];
}
