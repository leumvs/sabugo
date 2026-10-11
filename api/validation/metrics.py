"""Agreement statistics for the validation against ground truth.

R², RMSE and MBE, which is the vocabulary the RhizoVision Explorer paper and
the field use. Not percentage deviation, which compares to nothing published.
"""

from __future__ import annotations

import numpy as np


def agreement(measured, truth) -> dict[str, float]:
    """How well `measured` reproduces `truth`, for one metric over one dataset.

    R² is the coefficient of determination against the 1:1 line, not the square
    of a correlation: a tool that reads every length as twice the truth
    correlates perfectly and is still wrong, and only the first of the two
    says so.
    """
    measured = np.asarray(measured, dtype=np.float64)
    truth = np.asarray(truth, dtype=np.float64)
    if measured.shape != truth.shape or measured.size == 0:
        raise ValueError("measured and truth must be non-empty and the same length")

    error = measured - truth
    total = float(((truth - truth.mean()) ** 2).sum())
    return {
        "n": float(measured.size),
        "r2": float(1.0 - (error**2).sum() / total) if total else float("nan"),
        "rmse": float(np.sqrt((error**2).mean())),
        "mbe": float(error.mean()),
    }


def table(rows: dict[str, dict[str, float]]) -> str:
    """The comparison as the paper prints it, one line per metric."""
    lines = [f"{'metric':<24}{'n':>5}{'R2':>9}{'RMSE':>10}{'MBE':>10}"]
    for name, stats in rows.items():
        lines.append(
            f"{name:<24}{int(stats['n']):>5}{stats['r2']:>9.3f}"
            f"{stats['rmse']:>10.3f}{stats['mbe']:>10.3f}"
        )
    return "\n".join(lines)


TOOLS = ("Sabugo", "RVE", "WinRhizo", "IJ_Rhizo")

LABELS = {
    "metric": "Metric",
    "total_root_length": "Total root length (mm)",
    "average_diameter": "Average diameter (mm)",
    "surface_area": "Surface area (mm²)",
    "volume": "Volume (mm³)",
}


def markdown(
    rows: list[dict[str, str]],
    statistic: str = "rmse",
    axis: str = "dpi",
    heading: str = "DPI",
    labels: dict[str, str] = LABELS,
) -> str:
    """The README table, rendered from the versioned results and nothing else.

    Typing the numbers into the README by hand is how a table starts lying:
    someone re-runs the comparison, the CSV moves, and the prose does not. So
    the README carries what this produces, and a test re-renders it from the
    same CSV and demands they match — which works in CI because the CSV is in
    the repository even though the images it came from are not.

    `axis` is the column the simulated roots vary by resolution and the copper
    wires vary by threshold; everything else about the two tables is the same.
    """
    grouped: dict[tuple[str, str], dict[str, float]] = {}
    resolutions = []
    for row in rows:
        grouped[(row[axis], row["metric"], row["tool"])] = float(row[statistic])
        if row[axis] not in resolutions:
            resolutions.append(row[axis])

    lines = [
        f"| {labels['metric']} | {heading} | "
        + " | ".join(f"**{TOOLS[0]}**" if i == 0 else t for i, t in enumerate(TOOLS))
        + " |",
        "|---|---|" + "---|" * len(TOOLS),
    ]
    for metric, label in ((k, v) for k, v in labels.items() if k != "metric"):
        for dpi in resolutions:
            values = [grouped[(dpi, metric, tool)] for tool in TOOLS]
            best = min(values)
            cells = [
                f"**{value:.3f}**" if value == best else f"{value:.3f}"
                for value in values
            ]
            lines.append(f"| {label} | {dpi} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
