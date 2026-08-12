import { describe, expect, test } from "bun:test";
import { clampToImage, rectFrom, toClientPoint, toImagePoint, toPercent } from "../src/lib/roi.js";

// A tall thin scan displayed at a third of its size, somewhere down the page.
const natural = { width: 900, height: 3000 };
const rect = { left: 120, top: 40, width: 300, height: 1000 };

describe("screen to image", () => {
  test("the corners map to the corners", () => {
    expect(toImagePoint({ x: 120, y: 40 }, rect, natural)).toEqual({ x: 0, y: 0 });
    expect(toImagePoint({ x: 420, y: 1040 }, rect, natural)).toEqual({ x: 900, y: 3000 });
  });

  test("the middle maps to the middle", () => {
    expect(toImagePoint({ x: 270, y: 540 }, rect, natural)).toEqual({ x: 450, y: 1500 });
  });

  test("the offset of the box is subtracted, not ignored", () => {
    // Drop the `left`/`top` terms and this is the assertion that goes red.
    const shifted = { ...rect, left: 0, top: 0 };
    expect(toImagePoint({ x: 270, y: 540 }, shifted, natural)).not.toEqual(
      toImagePoint({ x: 270, y: 540 }, rect, natural),
    );
  });

  test("zoom is read off the box, so no factor has to be tracked", () => {
    const zoomed = { left: 120, top: 40, width: 600, height: 2000 };
    expect(toImagePoint({ x: 420, y: 1040 }, zoomed, natural)).toEqual({ x: 450, y: 1500 });
  });
});

describe("round trip", () => {
  test("original → display → original is identity within a pixel", () => {
    const boxes = [
      { left: 0, top: 0, width: 900, height: 3000 },
      { left: 37, top: 11, width: 271, height: 903 },
      { left: -60, top: -400, width: 1800, height: 6000 },
    ];

    for (const box of boxes) {
      for (const point of [
        { x: 0, y: 0 },
        { x: 1, y: 2999 },
        { x: 899, y: 0 },
        { x: 123.4, y: 2345.6 },
      ]) {
        const back = toImagePoint(toClientPoint(point, box, natural), box, natural);
        expect(Math.abs(back.x - point.x)).toBeLessThan(1);
        expect(Math.abs(back.y - point.y)).toBeLessThan(1);
      }
    }
  });
});

describe("rectFrom", () => {
  test("a rectangle dragged upwards is the same as one dragged downwards", () => {
    const down = rectFrom({ x: 10, y: 20 }, { x: 110, y: 220 }, natural);
    const up = rectFrom({ x: 110, y: 220 }, { x: 10, y: 20 }, natural);

    expect(down).toEqual({ x: 10, y: 20, width: 100, height: 200 });
    expect(up).toEqual(down);
  });

  test("integer pixels, because the worker crops with them", () => {
    const roi = rectFrom({ x: 10.4, y: 20.6 }, { x: 110.5, y: 220.5 }, natural);
    for (const value of Object.values(roi)) expect(Number.isInteger(value)).toBe(true);
  });
});

describe("clamping", () => {
  test("a region dragged off the top left never goes negative", () => {
    const roi = rectFrom({ x: -500, y: -900 }, { x: 100, y: 200 }, natural);
    expect(roi.x).toBe(0);
    expect(roi.y).toBe(0);
    expect(roi).toEqual({ x: 0, y: 0, width: 100, height: 200 });
  });

  test("a region dragged past the far edge stops at the image", () => {
    const roi = rectFrom({ x: 800, y: 2900 }, { x: 5000, y: 9000 }, natural);
    expect(roi.x + roi.width).toBe(natural.width);
    expect(roi.y + roi.height).toBe(natural.height);
  });

  test("a region entirely outside is still inside afterwards", () => {
    const roi = clampToImage({ x: 4000, y: 9000, width: 10, height: 10 }, natural);
    expect(roi.x).toBeLessThan(natural.width);
    expect(roi.y).toBeLessThan(natural.height);
    expect(roi.x + roi.width).toBeLessThanOrEqual(natural.width);
    expect(roi.y + roi.height).toBeLessThanOrEqual(natural.height);
  });

  test("a click without a drag is one pixel, not zero", () => {
    const roi = rectFrom({ x: 50, y: 50 }, { x: 50, y: 50 }, natural);
    expect(roi.width).toBeGreaterThanOrEqual(1);
    expect(roi.height).toBeGreaterThanOrEqual(1);
  });
});

describe("toPercent", () => {
  test("the whole image is the whole box", () => {
    expect(toPercent({ x: 0, y: 0, width: 900, height: 3000 }, natural)).toEqual({
      left: 0,
      top: 0,
      width: 100,
      height: 100,
    });
  });

  test("a quarter down the image is a quarter down the box", () => {
    const percent = toPercent({ x: 450, y: 750, width: 225, height: 750 }, natural);
    expect(percent).toEqual({ left: 50, top: 25, width: 25, height: 25 });
  });
});
