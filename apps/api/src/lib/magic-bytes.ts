/** By magic bytes and never by extension or `Content-Type`: the endpoint is
 *  public, and both of those are written by the caller. */

export type ImageFormat = "bmp" | "jpeg" | "png" | "tiff";

const PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

/** Enough bytes to decide the format. */
export const SNIFF_BYTES = 16;

export function sniffFormat(bytes: Uint8Array): ImageFormat | null {
  if (bytes.length >= 2 && bytes[0] === 0x42 && bytes[1] === 0x4d) return "bmp";
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "jpeg";
  }
  if (bytes.length >= 8 && PNG.every((byte, index) => bytes[index] === byte)) return "png";
  if (tiffEndianness(bytes) !== null) return "tiff";
  return null;
}

/** `II*\0` little-endian, `MM\0*` big-endian — anything else is not a TIFF. */
function tiffEndianness(bytes: Uint8Array): boolean | null {
  if (bytes.length < 4) return null;
  const [a, b, c, d] = bytes;
  if (a === 0x49 && b === 0x49 && c === 0x2a && d === 0x00) return true;
  if (a === 0x4d && b === 0x4d && c === 0x00 && d === 0x2a) return false;
  return null;
}

/**
 * Needs the whole file and not the sniffed prefix: nothing obliges IFD0 to sit
 * near the start, and writers routinely put it at the end. A malformed chain
 * is reported as single-page and left to the decoder, which answers
 * `INVALID_IMAGE`.
 */
export function isMultiPageTiff(bytes: Uint8Array): boolean {
  const little = tiffEndianness(bytes);
  if (little === null) return false;

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const read32 = (at: number) => (at + 4 <= bytes.length ? view.getUint32(at, little) : null);

  const first = read32(4);
  if (first === null || first < 8 || first + 2 > bytes.length) return false;

  const entries = view.getUint16(first, little);
  const next = read32(first + 2 + entries * 12);
  // A second IFD that points anywhere real is a second page. Zero terminates
  // the chain, and an out-of-bounds offset is a broken file, not a page.
  return next !== null && next !== 0 && next < bytes.length;
}
