"""The human-readable result on stdout, beside `export` (CSV) and `jsonout`."""

from __future__ import annotations

from pathlib import Path

from . import PIPELINE_VERSION
from .aggregate import HISTOGRAMS, class_labels

UNITS = {
    "network_area": "mm2",
    "max_diameter": "mm",
    "perimeter": "mm",
    "total_root_length": "mm",
    "average_diameter": "mm",
    "median_diameter": "mm",
    "volume": "mm3",
    "surface_area": "mm2",
    "processing_time_ms": "ms",
    "branching_frequency": "mm-1",
    "num_root_tips": "",
    "num_branch_points": "",
    "num_segments": "",
    "median_number_of_roots": "",
    "max_number_of_roots": "",
    "depth": "mm",
    "max_width": "mm",
    "width_to_depth_ratio": "",
    "convex_area": "mm2",
    "solidity": "",
    "lower_root_area": "mm2",
    "holes": "",
    "average_hole_size": "mm2",
    "average_root_orientation": "deg",
    "shallow_angle_frequency": "",
    "medium_angle_frequency": "",
    "steep_angle_frequency": "",
}


def report(image_path: Path, region: str, values, threshold_value_used: int, ranges) -> None:
    histograms = values["histograms"]
    print(image_path if region == "Full" else f"{image_path} [{region}]")
    print(f"  pipeline_version {PIPELINE_VERSION}")
    print(f"  threshold_value_used {threshold_value_used}")
    for name, value in values.items():
        if name != "histograms":
            print(f"  {name} {value:.4f} {UNITS[name]}".rstrip())
    for name in HISTOGRAMS:
        cells = " ".join(f"{a}={b:.4f}" for a, b in zip(class_labels(ranges), histograms[name]))
        print(f"  {name} {cells}")
