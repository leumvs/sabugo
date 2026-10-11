/** ROI annotations exchanged with the reference tool. */

export const HEADER = "#ROI Name, Class Name, X Position, Y Position, Width, Height";

export function parse(text) {
  const rois = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const fields = line.split(",").map((piece) => piece.trim());
    if (fields.length < 6) throw new Error("annotation_needs_six_columns");

    const [name, className, ...numbers] = fields;
    const [x, y, width, height] = numbers.map(Number);
    if ([x, y, width, height].some(Number.isNaN)) throw new Error("annotation_needs_numbers");
    rois.push({ name, class: className || "root", x, y, width, height });
  }
  if (rois.length === 0) throw new Error("annotation_is_empty");
  return rois;
}

export function format(rois) {
  const lines = rois.map(
    (roi) => `${roi.name}, ${roi.class ?? "root"}, ${roi.x}, ${roi.y}, ${roi.width}, ${roi.height}`,
  );
  return [HEADER, ...lines, ""].join("\n");
}
