/**
 * Screen coordinates to pixels of the original image, and back.
 *
 * ⚠️ Fails silently: if the conversion is wrong the worker measures a
 * different region from the one that was marked and returns plausible metrics
 * of the wrong root.
 *
 * `rect` is what `getBoundingClientRect()` returns for the displayed image;
 * reading the scale off it is what stays correct under CSS transforms,
 * scrolling and layout changes.
 */

export function toImagePoint(client, rect, natural) {
  return {
    x: ((client.x - rect.left) / rect.width) * natural.width,
    y: ((client.y - rect.top) / rect.height) * natural.height,
  };
}

export function toClientPoint(point, rect, natural) {
  return {
    x: rect.left + (point.x / natural.width) * rect.width,
    y: rect.top + (point.y / natural.height) * rect.height,
  };
}

/** Integer pixels, at least one pixel of each side, never outside the
 *  image. */
export function rectFrom(a, b, natural) {
  return clampToImage(
    {
      x: Math.min(a.x, b.x),
      y: Math.min(a.y, b.y),
      width: Math.abs(a.x - b.x),
      height: Math.abs(a.y - b.y),
    },
    natural,
  );
}

/** The worker crops with these numbers directly, and one pixel over the edge
 *  is an exception on the other side. */
export function clampToImage(roi, natural) {
  const left = Math.min(Math.max(Math.round(roi.x), 0), natural.width - 1);
  const top = Math.min(Math.max(Math.round(roi.y), 0), natural.height - 1);
  const right = Math.min(Math.max(Math.round(roi.x + roi.width), left + 1), natural.width);
  const bottom = Math.min(Math.max(Math.round(roi.y + roi.height), top + 1), natural.height);

  return { x: left, y: top, width: right - left, height: bottom - top };
}

export function toPercent(roi, natural) {
  return {
    left: (roi.x / natural.width) * 100,
    top: (roi.y / natural.height) * 100,
    width: (roi.width / natural.width) * 100,
    height: (roi.height / natural.height) * 100,
  };
}
