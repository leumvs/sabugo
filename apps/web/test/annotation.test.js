import { describe, expect, test } from "bun:test";
import { format, HEADER, parse } from "../src/lib/annotation.js";

// Spelled out and not imported: `apps/worker/src/sabugo_worker/cli.py` and
// `apps/api/src/services/runner.ts` carry the same string.
const LITERAL = "#ROI Name, Class Name, X Position, Y Position, Width, Height";

const FILE = `${LITERAL}
roi_1, root, 10, 20, 30, 40
roi_2, root, 5, 5, 10, 10
`;

describe("the RVE annotation format", () => {
  test("the header is the one the other two sides write", () => {
    expect(HEADER).toBe(LITERAL);
    expect(format([]).trim()).toBe(LITERAL);
  });

  test("reads a file the reference tool wrote", () => {
    expect(parse(FILE)).toEqual([
      { name: "roi_1", class: "root", x: 10, y: 20, width: 30, height: 40 },
      { name: "roi_2", class: "root", x: 5, y: 5, width: 10, height: 10 },
    ]);
  });

  test("comments and blank lines are skipped", () => {
    expect(parse("# a comment\n\nroi_1, root, 1, 2, 3, 4\n")).toHaveLength(1);
  });

  test("a round trip changes nothing", () => {
    expect(parse(format(parse(FILE)))).toEqual(parse(FILE));
  });

  test("what it refuses, it refuses with a token", () => {
    expect(() => parse("roi_1, root, 1, 2\n")).toThrow("annotation_needs_six_columns");
    expect(() => parse("roi_1, root, a, 2, 3, 4\n")).toThrow("annotation_needs_numbers");
    expect(() => parse(LITERAL)).toThrow("annotation_is_empty");
  });

  test("carries the class name the worker ignores", () => {
    const [roi] = parse("a, taproot, 1, 2, 3, 4\n");
    expect(roi.class).toBe("taproot");
    expect(format([roi])).toContain("a, taproot, 1, 2, 3, 4");
  });
});
