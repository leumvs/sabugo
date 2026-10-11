"""One image through the pipeline, from a region to its metrics."""

from __future__ import annotations

import time

from .aggregate import aggregate
import numpy as np

from .pipeline import Params, PipelineError, Segmentation, metrics, segment
from .progress import Progress
from .pruning import prune
from .segments import extract, simplified_scales
from .skeleton import skeletonize
from .topology import classify
from .wholeroot import measure as whole_root_metrics


def regions(image: np.ndarray, params: Params) -> list[tuple[str, np.ndarray]]:
    """One sub-image per ROI. The rectangle is x, y, width, height in pixels
    of the original image."""
    if not params.rois:
        return [("Full", image)]
    height, width = image.shape[:2]
    for index, (_, x, y, w, h) in enumerate(params.rois):
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise PipelineError("INVALID_PARAMS", {"field": "rois", "reason": "roi_out_of_bounds", "index": index})
    return [
        (name, image[y : y + height, x : x + width])
        for name, x, y, width, height in params.rois
    ]


def analyse(image: np.ndarray, dpi: float, params: Params, progress: Progress | None = None,
            region: str = "Full") -> tuple[dict[str, object], Segmentation, np.ndarray]:
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
    values["num_segments"] = float(len(segments))
    scales = [simplified_scales(path) for path in segments]
    values |= aggregate(
        seg.dt, segments, seg.mm_per_px, params.diameter_ranges_mm, scales
    )
    if params.mode == "whole_root":
        values |= whole_root_metrics(seg.mask, seg.dt, segments, seg.mm_per_px, scales)
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
