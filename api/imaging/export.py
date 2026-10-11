"""One `features.csv` row per image or per ROI, under the column names the
other root-scanning tools emit."""

from __future__ import annotations

import csv
from typing import IO

from .aggregate import HISTOGRAMS

BROKEN_ROOT_COLUMNS = {
    "num_root_tips": "Number.of.Root.Tips",
    "num_branch_points": "Number.of.Branch.Points",
    "total_root_length": "Total.Root.Length.mm",
    "branching_frequency": "Branching.frequency.per.mm",
    "network_area": "Network.Area.mm2",
    "average_diameter": "Average.Diameter.mm",
    "median_diameter": "Median.Diameter.mm",
    "max_diameter": "Maximum.Diameter.mm",
    "perimeter": "Perimeter.mm",
    "volume": "Volume.mm3",
    "surface_area": "Surface.Area.mm2",
    "processing_time_ms": "Computation.Time.s",
}

WHOLE_ROOT_COLUMNS = {
    "median_number_of_roots": "Median.Number.of.Roots",
    "max_number_of_roots": "Maximum.Number.of.Roots",
    "num_root_tips": "Number.of.Root.Tips",
    "total_root_length": "Total.Root.Length.mm",
    "depth": "Depth.mm",
    "max_width": "Maximum.Width.mm",
    "width_to_depth_ratio": "Width-to-Depth.Ratio",
    "network_area": "Network.Area.mm2",
    "convex_area": "Convex.Area.mm2",
    "solidity": "Solidity",
    "lower_root_area": "Lower.Root.Area.mm2",
    "average_diameter": "Average.Diameter.mm",
    "median_diameter": "Median.Diameter.mm",
    "max_diameter": "Maximum.Diameter.mm",
    "perimeter": "Perimeter.mm",
    "volume": "Volume.mm3",
    "surface_area": "Surface.Area.mm2",
    "holes": "Holes",
    "average_hole_size": "Average.Hole.Size.mm2",
    "processing_time_ms": "Computation.Time.s",
    "average_root_orientation": "Average.Root.Orientation.deg",
    "shallow_angle_frequency": "Shallow.Angle.Frequency",
    "medium_angle_frequency": "Medium.Angle.Frequency",
    "steep_angle_frequency": "Steep.Angle.Frequency",
}


def globals_for(mode: str) -> dict[str, str]:
    return WHOLE_ROOT_COLUMNS if mode == "whole_root" else BROKEN_ROOT_COLUMNS


HISTOGRAM_COLUMNS = {
    "root_length": ("Root.Length", "mm"),
    "projected_area": ("Projected.Area", "mm2"),
    "surface_area": ("Surface.Area", "mm2"),
    "volume": ("Volume", "mm3"),
}


def histogram_column(name: str, index: int) -> str:
    """`Root.Length.Diameter.Range.1.mm`. The class is a number, so the header
    says nothing about the boundaries used."""
    metric, unit = HISTOGRAM_COLUMNS[name]
    return f"{metric}.Diameter.Range.{index + 1}.{unit}"


def columns(diameter_ranges_mm: list[float], mode: str = "broken_roots") -> list[str]:
    classes = len(diameter_ranges_mm) + 1
    histograms = [
        histogram_column(name, index)
        for name in HISTOGRAMS
        for index in range(classes)
    ]
    return [
        "File.Name",
        "Region.of.Interest",
        *globals_for(mode).values(),
        *histograms,
    ]


def row(
    file_name: str,
    values: dict[str, object],
    diameter_ranges_mm: list[float],
    region: str = "Full",
    mode: str = "broken_roots",
) -> dict[str, str]:
    """One line of `features.csv`, at six decimals."""
    cells = {"File.Name": file_name, "Region.of.Interest": region}
    for key, column in globals_for(mode).items():
        number = values[key]
        if key == "processing_time_ms":
            number = number / 1000.0  # the column is seconds; the metric is ms
        cells[column] = f"{number:.6f}"

    for name in HISTOGRAMS:
        for index, cell in enumerate(values["histograms"][name]):
            cells[histogram_column(name, index)] = f"{cell:.6f}"
    return cells


def writer(
    handle: IO[str], diameter_ranges_mm: list[float], mode: str = "broken_roots"
) -> csv.DictWriter:
    """Always writes a header, never appends."""
    out = csv.DictWriter(handle, fieldnames=columns(diameter_ranges_mm, mode))
    out.writeheader()
    return out
