"""Sabugo against the copper-wire ground truth, next to the other three.

Twenty-eight scans of copper wires of known gauge, so the truth is a physical
dimension and not a model's own geometry: length measured with a ruler, diameter
from the gauge. Trivial topology, which is the point — it exercises binarization
and calibration and almost nothing else, and those are where the 800 DPI
threshold defect turned out to live.

Everything but the images ships with the paper's own archive: RVE's outputs and
the ground truth in `rveOutputsandGroundTruth.csv`, WinRhizo in the two
`winRhDpi600Th*CuWireScans.csv`, IJ_Rhizo in `IJ_Kimura.csv`.

    python validation/wires.py

Following the paper's R script: 600 DPI only, both thresholds, and the twelve
wire `MD_...` scan excluded.
"""

from __future__ import annotations

import csv
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from metrics import agreement, markdown, table  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
COMPETITORS = DATA / "competitors"
RESULTS = HERE / "results"
IMAGES = DATA / "wires"

DPI = 600
THRESHOLDS = (191, 222)

# The paper's script drops this one without saying why. Kept out so the
# comparison is the published one; it is the only 12-wire scan in the set.
EXCLUDED = "MD_40_32_28_22_16_10_40_32_28_22_16_10_W111111222222_600_dpi.tif"

METRICS = ("total_root_length", "average_diameter", "surface_area", "volume")


def _stem(name: str) -> str:
    """`G_10_W1_600_dpi.tif`, `..._seg`, `..._600_dpi` all key on the same scan."""
    return name.removesuffix(".tif").removesuffix("_seg")


def truth_rows() -> dict[str, dict[str, float]]:
    """The wires themselves: gauge for the diameter, a ruler for the length.

    `AverageWeightedDiameter` is the diameter weighted by each wire's length,
    which is what a whole-scan average diameter has to be compared against when
    a scan mixes gauges. The `LMY` columns are the measured ones — the plain
    `TotalLength`/`TotalVolume` beside them are nominal, and the paper's script
    uses `LMY`.
    """
    rows = {}
    with (COMPETITORS / "rveOutputsandGroundTruth.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["DPI"] != str(DPI) or row["File.Name"] == EXCLUDED:
                continue
            rows[_stem(row["File.Name"])] = {
                "total_root_length": float(row["TotalLengthLMY"]),
                "average_diameter": float(row["AverageWeightedDiameter"]),
                "surface_area": float(row["TotalSurfaceAreaLMY"]),
                "volume": float(row["TotalVolumeLMY"]),
            }
    return rows


def rve_rows(threshold: int) -> dict[str, dict[str, float]]:
    rows = {}
    with (COMPETITORS / "rveOutputsandGroundTruth.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row["DPI"], row["Threshold"]) != (str(DPI), str(threshold)):
                continue
            if row["File.Name"] == EXCLUDED:
                continue
            rows[_stem(row["File.Name"])] = {
                "total_root_length": float(row["Total.Root.Length.mm"]),
                "average_diameter": float(row["Average.Diameter.mm"]),
                "surface_area": float(row["Surface.Area.mm2"]),
                "volume": float(row["Volume.mm3"]),
            }
    return rows


def winrhizo_rows(threshold: int) -> dict[str, dict[str, float]]:
    """Tab separated, five preamble lines, and the last seven header names are
    padding the file does not carry — all three are what the paper's
    `readWinRhizoData` does. Reports cm and cm3, converted here as it converts."""
    path = COMPETITORS / f"winRhDpi{DPI}Th{threshold}CuWireScans.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        table_ = list(csv.reader(handle, delimiter="\t"))
    index = {name: i for i, name in enumerate(table_[0][:-7])}

    rows = {}
    for row in table_[5:]:
        if not row or row[index["ImageFileName"]] == EXCLUDED:
            continue
        rows[_stem(row[index["ImageFileName"]])] = {
            "total_root_length": float(row[index["Length(cm)"]]) * 10,
            "average_diameter": float(row[index["AvgDiam(mm)"]]),
            "surface_area": float(row[index["SurfArea(cm2)"]]) * 100,
            "volume": float(row[index["RootVolume(cm3)"]]) * 1000,
        }
    return rows


def ij_rows() -> dict[str, dict[str, float]]:
    """One run only: IJ_Rhizo was given images already segmented, so it has no
    threshold of its own and the same column stands in both panels."""
    rows = {}
    with (COMPETITORS / "IJ_Kimura.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows[_stem(row["File_Name"])] = {
                "total_root_length": float(row["Kimura_length"]),
                "average_diameter": float(row["Mean_Dia"]),
                "surface_area": float(row["Eq_Surf"]),
                "volume": float(row["Eq_Vol"]),
            }
    return rows


COLUMNS = {
    "total_root_length": "Total.Root.Length.mm",
    "average_diameter": "Average.Diameter.mm",
    "surface_area": "Surface.Area.mm2",
    "volume": "Volume.mm3",
}


def sabugo_rows(threshold: int) -> dict[str, dict[str, float]]:
    output = RESULTS / f"wires-{threshold}.csv"
    if not output.exists():
        run_pipeline(threshold, output)

    rows = {}
    with output.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cells = {name: row[column] for name, column in COLUMNS.items()}
            if any(value.strip() in {"NA", ""} for value in cells.values()):
                continue
            rows[_stem(row["File.Name"])] = {k: float(v) for k, v in cells.items()}
    return rows


def run_pipeline(threshold: int, output: pathlib.Path) -> None:
    """The published run's own settings, from the `RVE_metadata.csv` beside the
    images — pruning **on** at 5 px, and the background noise filter at 8 mm².

    Running the defaults instead measures a different tool. It cost a whole
    round here: with pruning off, a single wire came out with 196 root tips
    against RVE's 2, and the comparison was reading spur suppression as a
    length error. `Diameter Range 1, 0, above` in that file is one class rather
    than the default three, which moves only the histogram columns — none of
    the four metrics compared here — so `--dranges` is left alone.

    Delete `results/wires-{threshold}.csv` to re-run; this skips otherwise.
    """
    if not IMAGES.is_dir():
        raise SystemExit(
            f"copper wire images not found under {IMAGES} — see apps/worker/README.md"
        )
    subprocess.run(
        [sys.executable, "-m", "sabugo_worker.cli", str(IMAGES), "--dpi", str(DPI),
         "--threshold", str(threshold),
         "--prune", "--prunethreshold", "5",
         "--filter-background-noise", "--max-background-noise-mm2", "8",
         "-o", str(output)],
        check=True,
        cwd=HERE.parent,
    )


def compare(threshold: int) -> list[dict]:
    truth = truth_rows()
    tools = {
        "Sabugo": sabugo_rows(threshold),
        "RVE": rve_rows(threshold),
        "WinRhizo": winrhizo_rows(threshold),
        "IJ_Rhizo": ij_rows(),
    }
    shared = sorted(set(truth).intersection(*(set(rows) for rows in tools.values())))
    print(f"== threshold {threshold}, {len(shared)} scans measured by all four tools")

    written = []
    for name, measured in tools.items():
        stats = {
            metric: agreement(
                [measured[k][metric] for k in shared], [truth[k][metric] for k in shared]
            )
            for metric in METRICS
        }
        print()
        print(f"-- {name}")
        print(table(stats))
        written += [
            {"tool": name, "threshold": threshold, "metric": m, **s}
            for m, s in stats.items()
        ]

    print()
    print("acceptance: inside the span of the other three?")
    for metric in METRICS:
        mine = next(r for r in written if r["tool"] == "Sabugo" and r["metric"] == metric)
        others = [r for r in written if r["tool"] != "Sabugo" and r["metric"] == metric]
        verdict = []
        for statistic in ("rmse", "mbe"):
            worst = max(abs(r[statistic]) for r in others)
            inside = abs(mine[statistic]) <= worst
            verdict.append(
                f"{statistic} {'ok' if inside else 'OUT'} "
                f"({abs(mine[statistic]):.3f} vs worst {worst:.3f})"
            )
        print(f"  {metric:<20} {'  '.join(verdict)}")
    print()
    return written


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    written = [row for t in THRESHOLDS for row in compare(t)]

    out = RESULTS / "wires-agreement.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["tool", "threshold", "metric", "n", "r2", "rmse", "mbe"]
        )
        writer.writeheader()
        writer.writerows(written)
    print(f"written to {out.relative_to(HERE.parent)}")
    print()
    rendered = [{k: str(v) for k, v in row.items()} for row in written]
    print(markdown(rendered, axis="threshold", heading="Threshold"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
