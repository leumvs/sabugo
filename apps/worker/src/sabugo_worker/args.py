"""The command line surface: the parser and the types it validates with."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import MAX_PIXELS


def diameter_ranges(text: str) -> list[float]:
    try:
        ranges = [float(piece) for piece in text.split(",") if piece.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("expected decimals separated by commas") from None
    if not ranges:
        raise argparse.ArgumentTypeError("expected at least one boundary")
    if len(ranges) > 11:
        raise argparse.ArgumentTypeError("at most 11 boundaries, so at most 12 classes")
    if ranges[0] <= 0:
        raise argparse.ArgumentTypeError("boundaries must be greater than zero")
    if any(b <= a for a, b in zip(ranges, ranges[1:])):
        raise argparse.ArgumentTypeError("boundaries must be strictly increasing")
    return ranges


def read_annotations(path: Path) -> list[tuple[str, int, int, int, int]]:
    """`#ROI Name, Class Name, X Position, Y Position, Width, Height`, with
    `#` lines as comments and the class name ignored."""
    rois = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [piece.strip() for piece in line.split(",")]
        if len(fields) < 6:
            raise argparse.ArgumentTypeError(f"expected six columns, got: {line!r}")
        name, _, x, y, width, height = fields[:6]
        rois.append((name, int(x), int(y), int(width), int(height)))
    if len(rois) > 10:
        raise argparse.ArgumentTypeError("at most 10 ROIs per analysis")
    return rois


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m sabugo_worker.cli")
    p.add_argument("path", type=Path, help="image file or directory")
    scale = p.add_mutually_exclusive_group(required=True)
    scale.add_argument("--dpi", type=float)
    scale.add_argument("--pixels-per-mm", type=float, help="same calibration as --dpi")
    p.add_argument("--mode", choices=["broken_roots", "whole_root"], default="broken_roots")
    p.add_argument("--threshold-method", choices=["manual", "otsu"], default="manual")
    p.add_argument("--threshold", type=int, default=200, dest="threshold_value")
    p.add_argument("--invert", action="store_true", dest="invert_image")
    p.add_argument("--no-keep-largest", action="store_false", dest="keep_largest")
    p.add_argument("--filter-background-noise", action="store_true")
    p.add_argument("--max-background-noise-mm2", type=float, default=1.0)
    p.add_argument("--filter-foreground-noise", action="store_true")
    p.add_argument("--max-foreground-noise-mm2", type=float, default=1.0)
    p.add_argument("--smooth", action="store_true", dest="enable_edge_smoothing")
    p.add_argument(
        "--smooththreshold",
        type=float,
        default=2.0,
        dest="edge_smoothing_threshold",
        help="Douglas-Peucker epsilon in px for the outline (default 2.0)",
    )
    p.add_argument("--prune", action="store_true", dest="enable_root_pruning")
    p.add_argument(
        "--prunethreshold",
        type=int,
        default=5,
        dest="root_pruning_threshold",
        help="slack in px added to the radius at the branch point (default 5)",
    )
    p.add_argument(
        "--dranges",
        type=diameter_ranges,
        default=[2.0, 5.0],
        dest="diameter_ranges_mm",
        help="inner class boundaries in mm, comma separated (default 2.0,5.0)",
    )
    p.add_argument("--segment", action="store_true", help="write the segmented image")
    p.add_argument("--contour", action="store_true", help="draw the root contour")
    p.add_argument("--contourwidth", type=int, default=1)
    p.add_argument("--hull", action="store_true", help="draw the convex hull")
    p.add_argument("--holes", action="store_true", help="fill the enclosed holes")
    p.add_argument("--distancemap", action="store_true", help="colour the root by radius")
    p.add_argument("--medialwidth", type=int, default=3, help="medial axis width in px")
    p.add_argument("--no-medialaxis", action="store_false", dest="medialaxis")
    p.add_argument("--no-classcolour", action="store_false", dest="classcolour")
    p.add_argument("--feature", action="store_true", help="write the coloured skeleton")
    p.add_argument(
        "--preview",
        action="store_true",
        help="segment only: no skeleton, no metrics, no CSV",
    )
    p.add_argument("--ssuffix", default="_seg", help="suffix for --segment (default _seg)")
    p.add_argument("--fsuffix", default="_feat", help="suffix for --feature (default _feat)")
    p.add_argument(
        "--roipath",
        type=Path,
        help="RVE ROI annotation CSV; each rectangle becomes its own result row",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write features.csv here instead of printing; overwrites the file",
    )
    p.add_argument(
        "--json",
        type=Path,
        dest="json_output",
        help="write the result here as JSON; overwrites the file",
    )
    p.add_argument(
        "--progress",
        action="store_true",
        help="report the current stage as NDJSON on stderr",
    )
    p.add_argument(
        "--max-megapixels",
        type=float,
        dest="max_megapixels",
        help=f"refuse an image above this, after decoding (default {MAX_PIXELS // 1_000_000})",
    )
    return p
