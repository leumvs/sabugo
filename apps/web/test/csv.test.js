import { describe, expect, test } from "bun:test";
import { columns, rowFor, toCsv } from "../src/lib/csv.js";

// The same header `apps/worker/tests/test_export.py` asserts on the other side,
// spelled out rather than derived.
const BROKEN_ROOT_HEADER =
  "File.Name,Region.of.Interest,Number.of.Root.Tips,Number.of.Branch.Points," +
  "Total.Root.Length.mm,Branching.frequency.per.mm,Network.Area.mm2," +
  "Average.Diameter.mm,Median.Diameter.mm,Maximum.Diameter.mm,Perimeter.mm," +
  "Volume.mm3,Surface.Area.mm2,Computation.Time.s," +
  "Root.Length.Diameter.Range.1.mm,Root.Length.Diameter.Range.2.mm," +
  "Root.Length.Diameter.Range.3.mm,Projected.Area.Diameter.Range.1.mm2," +
  "Projected.Area.Diameter.Range.2.mm2,Projected.Area.Diameter.Range.3.mm2," +
  "Surface.Area.Diameter.Range.1.mm2,Surface.Area.Diameter.Range.2.mm2," +
  "Surface.Area.Diameter.Range.3.mm2,Volume.Diameter.Range.1.mm3," +
  "Volume.Diameter.Range.2.mm3,Volume.Diameter.Range.3.mm3";

/** One value per diameter class, which is `ranges.length + 1` of them. */
function bins(value, classes) {
  const values = Array.from({ length: classes }, (_, index) => (index === 0 ? value : 0));
  return {
    rootLength: values,
    projectedArea: values,
    surfaceArea: values,
    volume: values,
  };
}

function rows(overrides = {}) {
  const mode = overrides.mode ?? "broken_roots";
  const ranges = overrides.ranges ?? [2.0, 5.0];
  const metrics =
    mode === "whole_root"
      ? {
          medianNumberOfRoots: 1,
          maxNumberOfRoots: 2,
          numRootTips: 3,
          totalRootLength: 4,
          depth: 5,
          maxWidth: 6,
          widthToDepthRatio: 7,
          networkArea: 8,
          convexArea: 9,
          solidity: 10,
          lowerRootArea: 11,
          averageDiameter: 12,
          medianDiameter: 13,
          maxDiameter: 14,
          perimeter: 15,
          volume: 16,
          surfaceArea: 17,
          holes: 18,
          averageHoleSize: 19,
          processingTimeMs: 2261,
          averageRootOrientation: 21,
          shallowAngleFrequency: 22,
          mediumAngleFrequency: 23,
          steepAngleFrequency: 24,
        }
      : {
          numRootTips: 12,
          numBranchPoints: 4,
          totalRootLength: 412.7,
          branchingFrequency: 0.0097,
          networkArea: 88.2,
          averageDiameter: 0.93,
          medianDiameter: 0.88,
          maxDiameter: 1.5,
          perimeter: 900.1,
          volume: 38.7,
          surfaceArea: 151.5,
          processingTimeMs: 2261,
        };

  const params = { mode, diameter_ranges_mm: ranges };
  const results = overrides.results ?? [
    { fileName: "root.png", roiName: "Full", metrics, bins: bins(300, ranges.length + 1) },
  ];
  return results.map((entry) => rowFor(entry, params));
}

describe("the column contract", () => {
  test("broken roots is the header the worker writes", () => {
    expect(columns([2.0, 5.0], "broken_roots").join(",")).toBe(BROKEN_ROOT_HEADER);
  });

  test("broken roots is 12 + 4*(n+1) columns, plus the two leading ones", () => {
    expect(columns([2.0, 5.0], "broken_roots")).toHaveLength(26);
    expect(columns([1.0], "broken_roots")).toHaveLength(2 + 12 + 4 * 2);
    expect(columns([1.0, 2.0, 4.0], "broken_roots")).toHaveLength(2 + 12 + 4 * 4);
  });

  test("whole root is 24 + 4*(n+1), and drops the two broken-root metrics", () => {
    const whole = columns([2.0, 5.0], "whole_root");
    expect(whole).toHaveLength(38);
    expect(whole).not.toContain("Number.of.Branch.Points");
    expect(whole).not.toContain("Branching.frequency.per.mm");
  });
});

describe("the rows", () => {
  test("one row per region, after the header", () => {
    const lines = toCsv(rows()).trim().split("\n");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toBe(BROKEN_ROOT_HEADER);
  });

  test("computation time is written in seconds, not milliseconds", () => {
    // The metric is in ms and the column in s.
    const cells = toCsv(rows()).trim().split("\n")[1].split(",");
    const index = BROKEN_ROOT_HEADER.split(",").indexOf("Computation.Time.s");
    expect(cells[index]).toBe("2.261000");
  });

  test("six decimals, which is what the worker emits", () => {
    const cells = toCsv(rows()).trim().split("\n")[1].split(",");
    expect(cells[2]).toBe("12.000000");
    expect(cells[4]).toBe("412.700000");
  });

  test("the leading two columns name the file and the region", () => {
    const cells = toCsv(rows()).trim().split("\n")[1].split(",");
    expect(cells.slice(0, 2)).toEqual(["root.png", "Full"]);
  });

  test("every row has exactly as many cells as the header has columns", () => {
    for (const ranges of [[1.0], [2.0, 5.0], [0.5, 1, 2, 4, 8]]) {
      for (const mode of ["broken_roots", "whole_root"]) {
        const text = toCsv(rows({ mode, ranges }));
        const [header, row] = text.trim().split("\n");
        expect(row.split(",")).toHaveLength(header.split(",").length);
      }
    }
  });
});

describe("the Features table accumulates", () => {
  test("rows from several runs go under one header", () => {
    const lines = toCsv([...rows(), ...rows(), ...rows()])
      .trim()
      .split("\n");
    expect(lines).toHaveLength(4);
    expect(lines[0]).toBe(BROKEN_ROOT_HEADER);
    expect(lines[1]).toBe(lines[3]);
  });

  test("a run with more classes keeps every column, and pads the older rows", () => {
    // Two sheet widths can sit in the table, and the narrower rows must not
    // shift into the wrong column.
    const text = toCsv([...rows({ ranges: [2.0, 5.0] }), ...rows({ ranges: [1, 2, 4, 8] })]);
    const [header, narrow, wide] = text.trim().split("\n");

    expect(header).toContain("Volume.Diameter.Range.5.mm3");
    for (const line of [narrow, wide]) {
      expect(line.split(",")).toHaveLength(header.split(",").length);
    }
    const at = header.split(",").indexOf("Root.Length.Diameter.Range.1.mm");
    expect(narrow.split(",")[at]).toBe("300.000000");
    expect(wide.split(",")[at]).toBe("300.000000");
  });
});
