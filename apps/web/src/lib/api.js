/** `dpi`, `params` and `rois` go in **before** `image`: the route reads the
 *  body part by part, so a file sent first is read in full before anything
 *  can refuse it. Throws the error envelope. */
export async function submit({ file, dpi, params, rois, preview = false }) {
  const body = new FormData();
  body.append("dpi", String(dpi));
  body.append("params", JSON.stringify(params));
  if (rois.length > 0) {
    body.append("rois", JSON.stringify(rois.map(({ class: _, ...rect }) => rect)));
  }
  body.append("image", file);

  const url = preview ? "/api/analyses?preview=1" : "/api/analyses";
  const response = await fetch(url, { method: "POST", body });
  const data = await response.json();
  if (!response.ok) throw data;
  return data;
}

/**
 * Call it right after the 202: SSE has no replay beyond the terminal event.
 *
 * ⚠️ The terminal event has to close the source. An EventSource treats a
 * closed stream as a dropped connection and reconnects a few seconds later,
 * which the server answers with the same terminal event, forever.
 */
export function follow(id, handlers) {
  const source = new EventSource(`/api/analyses/${id}/events`);

  for (const name of ["queued", "started", "progress"]) {
    source.addEventListener(name, (event) => handlers[name]?.(JSON.parse(event.data)));
  }
  for (const name of ["completed", "failed"]) {
    source.addEventListener(name, (event) => {
      source.close();
      handlers[name]?.(JSON.parse(event.data));
    });
  }

  return () => source.close();
}

export function download(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
