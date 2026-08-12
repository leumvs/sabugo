import { describe, expect, test } from "bun:test";
import { isMultiPageTiff, sniffFormat } from "../../src/lib/magic-bytes";

const bytes = (...values) => new Uint8Array(values);

describe("sniffFormat", () => {
  test("recognises the four accepted formats", () => {
    expect(sniffFormat(bytes(0x42, 0x4d, 0x00, 0x00))).toBe("bmp");
    expect(sniffFormat(bytes(0xff, 0xd8, 0xff, 0xe0))).toBe("jpeg");
    expect(sniffFormat(bytes(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a))).toBe("png");
    expect(sniffFormat(bytes(0x49, 0x49, 0x2a, 0x00))).toBe("tiff");
    expect(sniffFormat(bytes(0x4d, 0x4d, 0x00, 0x2a))).toBe("tiff");
  });

  test("a file named .png that is not one is refused", () => {
    expect(sniffFormat(new TextEncoder().encode("MZ\x90\x00 executable"))).toBeNull();
    expect(sniffFormat(new TextEncoder().encode("#!/bin/sh\nrm -rf /"))).toBeNull();
  });

  test("a truncated header decides nothing", () => {
    expect(sniffFormat(bytes(0x89, 0x50))).toBeNull();
    expect(sniffFormat(bytes())).toBeNull();
  });
});

/** IFD0 at `offset`, `entries` entries, then a pointer to `next`. */
function tiff({ entries = 1, next = 0, little = true } = {}) {
  const size = 8 + 2 + entries * 12 + 4 + 16;
  const buffer = new Uint8Array(size);
  const view = new DataView(buffer.buffer);

  if (little) buffer.set([0x49, 0x49, 0x2a, 0x00]);
  else buffer.set([0x4d, 0x4d, 0x00, 0x2a]);
  view.setUint32(4, 8, little);
  view.setUint16(8, entries, little);
  view.setUint32(8 + 2 + entries * 12, next, little);
  return buffer;
}

describe("isMultiPageTiff", () => {
  test("a single IFD chain ends at zero", () => {
    expect(isMultiPageTiff(tiff({ next: 0 }))).toBe(false);
    expect(isMultiPageTiff(tiff({ next: 0, little: false }))).toBe(false);
  });

  test("a second IFD is a second page, and it is refused", () => {
    expect(isMultiPageTiff(tiff({ next: 30 }))).toBe(true);
    expect(isMultiPageTiff(tiff({ next: 30, little: false }))).toBe(true);
  });

  test("both byte orders are read, not just the little-endian one", () => {
    const big = tiff({ entries: 3, next: 50, little: false });
    expect(isMultiPageTiff(big)).toBe(true);
  });

  test("a chain pointing past the end is a broken file, not a page", () => {
    // Left to the decoder, which answers `INVALID_IMAGE`.
    expect(isMultiPageTiff(tiff({ next: 99_999 }))).toBe(false);
  });

  test("a PNG is never a multi-page TIFF", () => {
    expect(isMultiPageTiff(bytes(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a))).toBe(false);
  });
});
