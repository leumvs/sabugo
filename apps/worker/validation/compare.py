"""Sabugo against the simulated-root ground truth, next to RVE.

The images are the 100 ArchiSimple systems of Rose & Lobet (2018) rendered at
1200 DPI; the ground truth is the model's own geometry, and RVE's column comes
from the tables published with the RhizoVision Explorer paper, so neither
competitor has to be re-run.

    python validation/compare.py
"""

from __future__ import annotations

import csv
import math
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from metrics import agreement, markdown, table  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"
RESULTS = HERE / "results"
IMAGES = DATA / "simulated"
COMPETITORS = DATA / "competitors"
RESOLUTIONS = (800, 1200)

# Recovered from the data, not chosen. At 800 DPI `gray < 144` reproduces RVE's
# mask **pixel for pixel** on 94 of the 95 shared systems (143 and 145 land 0
# and 1, and the pipeline default of 200 reads 8.8% fatter). A fitted constant
# does not go pixel-exact on 94 independent images; this is the setting the
# published run used, and the paper's R script never recorded it. At 1200 the
# renderings are effectively binary — 223 mid-grey pixels in 761 million — and
# `gray < 144` and `gray < 200` give bit-identical masks on all 100, so the
# value there is cosmetic and stays at the default.
THRESHOLD = {800: 144, 1200: 200}


def truth_rows() -> dict[str, dict[str, float]]:
    """Length, mean diameter, surface and volume from the model's geometry.

    The model gives primary and lateral roots separately, so the whole-system
    diameter is the length-weighted mean of the two, and surface and volume
    follow from treating each as a cylinder — which is the same assumption
    every one of the tools makes when it integrates over the skeleton.
    """
    rows = {}
    with (IMAGES / "ground_truth_data_2D.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            primary = float(row["tot_prim_length"]), float(row["mean_prim_diameter"])
            lateral = float(row[" tot_lat_length"]), float(row["mean_lat_diameter"])
            total = float(row["tot_root_length"])
            rows[row["image"].removesuffix(".rsml")] = {
                "total_root_length": total,
                "average_diameter": sum(l * d for l, d in (primary, lateral)) / total,
                "surface_area": math.pi * sum(l * d for l, d in (primary, lateral)),
                "volume": math.pi / 4 * sum(l * d * d for l, d in (primary, lateral)),
            }
    return rows


COLUMNS = {
    "total_root_length": "Total.Root.Length.mm",
    "average_diameter": "Average.Diameter.mm",
    "surface_area": "Surface.Area.mm2",
    "volume": "Volume.mm3",
}


def measured_rows(path: pathlib.Path, key) -> dict[str, dict[str, float]]:
    """Rows the tool could not measure come through as NA and are dropped, for
    both tools alike — the comparison runs on the systems all three cover."""
    rows = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cells = {name: row[column] for name, column in COLUMNS.items()}
            if any(value.strip() in {"NA", ""} for value in cells.values()):
                continue
            rows[key(row["File.Name"])] = {k: float(v) for k, v in cells.items()}
    return rows


def competitor_rows(DPI: int, sheet: str = "all_analyses_fixed") -> dict[str, dict[str, dict[str, float]]]:
    """WinRhizo and IJ_Rhizo on the same systems, from the workbook shipped
    with the paper.

    `all_analyses_fixed` is the sheet the paper's own R script reads, and the
    workbook carries an `automatic` one beside it -- picking the wrong one
    silently changes who the competitors are. WinRhizo reports cm and cm3;
    the three conversion factors are the ones that script applies. IJ's
    Kimura length is already in mm, and it uses no conversion either.
    """
    from xlsx import rows

    book = COMPETITORS / "all_analyses_WR_IJ_RoseLobet2019.xlsx"
    table = rows(book, sheet)
    index = {name: i for i, name in enumerate(table[0])}
    winrhizo, kimura = {}, {}
    for row in table[1:]:
        if not row or not row[0].startswith(f"{DPI:04d}-"):
            continue
        key = row[0].removeprefix(f"{DPI:04d}-").removesuffix(".rsml")

        def cell(column):
            text = row[index[column]] if index[column] < len(row) else ""
            return float(text) if text not in {"", "NA"} else None

        length, surface = cell("WR_Length"), cell("WR_SurfArea(cm2)")
        diameter, volume = cell("WR_AvgDiam(mm)"), cell("WR_RootVolume(cm3)")
        if None not in (length, surface, diameter, volume):
            winrhizo[key] = {
                "total_root_length": length * 10,
                "average_diameter": diameter,
                "surface_area": surface * 100,
                "volume": volume * 1000,
            }
        ij_length, ij_diameter, ij_volume = (
            cell("IJ_Kimura_length"), cell("IJ_Mean_Dia"), cell("IJ_Eq_Vol")
        )
        if None not in (ij_length, ij_diameter, ij_volume):
            kimura[key] = {
                "total_root_length": ij_length,
                "average_diameter": ij_diameter,
                "surface_area": math.pi * ij_diameter * ij_length,
                "volume": ij_volume,
            }
    return {"WinRhizo": winrhizo, "IJ_Rhizo": kimura}


def system_of(DPI: int):
    return lambda name: name.removeprefix(f"{DPI}-").removesuffix("-deg0.jpg")


def run_pipeline(DPI: int, output: pathlib.Path) -> None:
    """One resolution's renderings through the CLI, at the threshold of THRESHOLD.

    The CLI takes one directory and both resolutions live in the same one, so
    the run is staged into a scratch copy holding only this DPI's renderings.

    `compare` skips this whenever `results/simulated-{dpi}.csv` already exists,
    so changing THRESHOLD means deleting that file or the new value does nothing.
    """
    with tempfile.TemporaryDirectory() as staged:
        for image in IMAGES.glob(f"{DPI}-*.jpg"):
            (pathlib.Path(staged) / image.name).write_bytes(image.read_bytes())
        subprocess.run(
            [sys.executable, "-m", "sabugo_worker.cli", staged, "--dpi", str(DPI),
             "--threshold", str(THRESHOLD[DPI]), "-o", str(output)],
            check=True,
            cwd=HERE.parent,
        )



def compare(dpi: int) -> list[dict]:
    ours_csv = RESULTS / f"simulated-{dpi}.csv"
    if not ours_csv.exists():
        run_pipeline(dpi, ours_csv)

    truth = truth_rows()
    key = system_of(dpi)
    tools = {
        "Sabugo": measured_rows(ours_csv, key),
        "RVE": measured_rows(COMPETITORS / f"featuresSimRootsRveDpi{dpi}.csv", key),
        **competitor_rows(dpi),
    }
    shared = sorted(set(truth).intersection(*(set(rows) for rows in tools.values())))
    print(f"== {dpi} DPI, {len(shared)} systems measured by all four tools")

    written = []
    for name, measured in tools.items():
        stats = {
            metric: agreement(
                [measured[k][metric] for k in shared], [truth[k][metric] for k in shared]
            )
            for metric in COLUMNS
        }
        print()
        print(f"-- {name}")
        print(table(stats))
        written += [{"tool": name, "dpi": dpi, "metric": m, **s} for m, s in stats.items()]

    # The acceptance criterion: Sabugo has to land inside the span the three
    # established tools already cover between them, metric by metric.
    print()
    print("acceptance: inside the span of the other three?")
    for metric in COLUMNS:
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
    written = [row for dpi in RESOLUTIONS for row in compare(dpi)]

    out = RESULTS / "simulated-agreement.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["tool", "dpi", "metric", "n", "r2", "rmse", "mbe"]
        )
        writer.writeheader()
        writer.writerows(written)
    print(f"written to {out.relative_to(HERE.parent)}")
    print()
    rendered = [{k: str(v) for k, v in row.items()} for row in written]
    print(markdown(rendered))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
