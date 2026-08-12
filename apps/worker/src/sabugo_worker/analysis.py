"""One image through the pipeline, from a region to its metrics."""

from __future__ import annotations

import time

from .aggregate import aggregate
from .pipeline import Params, metrics, segment
from .progress import Progress
from .pruning import prune
from .segments import extract, lengths
from .skeleton import skeletonize
from .topology import classify
from .wholeroot import measure as whole_root_metrics


def regions(image, params: Params):
    """One sub-image per ROI. The rectangle is x, y, width, height in pixels
    of the original image."""
    if not params.rois:
        return [("Full", image)]
    return [
        (name, image[y : y + height, x : x + width])
        for name, x, y, width, height in params.rois
    ]


def analyse(image, dpi: float, params: Params, progress: Progress | None = None, region: str = "Full"):
    progress = progress or Progress()
    started = time.perf_counter()
    seg = segment(image, dpi, params)
    progress.stage("segment", region)
    skeleton = skeletonize(seg.mask, seg.dt)
    progress.stage("skeletonize", region)
    if params.enable_root_pruning:
        skeleton = prune(skeleton, seg.dt, params.root_pruning_threshold)
        progress.stage("prune", region)
    found = classify(skeleton)
    segments = extract(skeleton, found["tip"] | found["branch"])
    progress.stage("topology", region)

    values = metrics(seg)
    values |= lengths(segments, seg.mm_per_px)
    values |= aggregate(
        seg.dt, segments, seg.mm_per_px, params.diameter_ranges_mm
    )
    if params.mode == "whole_root":
        values |= whole_root_metrics(seg.mask, seg.dt, segments, seg.mm_per_px)
    values["num_root_tips"] = float(found["tip"].sum())
    values["num_branch_points"] = float(found["branch"].sum())
    values["branching_frequency"] = (
        values["num_branch_points"] / values["total_root_length"]
        if values["total_root_length"]
        else 0.0
    )
    values["processing_time_ms"] = (time.perf_counter() - started) * 1000.0
    progress.stage("aggregate", region)
    return values, seg, skeleton
