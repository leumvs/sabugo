"""Segmentation: red channel, threshold, noise filters, smoothing, distance
transform."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

class PipelineError(Exception):
    """Carries one of the closed error codes as its message."""


@dataclass
class Params:
    mode: str = "broken_roots"
    threshold_method: str = "manual"
    threshold_value: int = 200
    invert_image: bool = False
    keep_largest: bool = True
    filter_background_noise: bool = False
    max_background_noise_mm2: float = 1.0
    filter_foreground_noise: bool = False
    max_foreground_noise_mm2: float = 1.0
    enable_edge_smoothing: bool = False
    edge_smoothing_threshold: float = 2.0  # Douglas-Peucker epsilon, in px
    enable_root_pruning: bool = False
    root_pruning_threshold: int = 5  # slack in px added to the local radius
    diameter_ranges_mm: list[float] = field(default_factory=lambda: [2.0, 5.0])
    # (name, x, y, width, height) in pixels of the original image
    rois: list[tuple[str, int, int, int, int]] = field(default_factory=list)


@dataclass
class Segmentation:
    mask: np.ndarray
    dt: np.ndarray
    mm_per_px: float
    threshold_value_used: int


# Peak memory is about 48 MB per megapixel. A limit on the file size does not
# bound it: an A4 page at 1200 DPI is 97 MP and 0.6 MB as PNG.
MAX_PIXELS = 100_000_000


def load_image(path: str, max_pixels: int = MAX_PIXELS) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise PipelineError("INVALID_IMAGE")
    if image.shape[0] * image.shape[1] > max_pixels:
        raise PipelineError("IMAGE_TOO_LARGE")
    return image


def to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = image[:, :, 2]  # BGR, red channel only
    if image.dtype == np.uint16:
        # Never min-max: that would make the threshold content-dependent.
        image = (image // 257).astype(np.uint8)
    return np.ascontiguousarray(image)


def _components(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return labels, stats[:, cv2.CC_STAT_AREA]


def _drop_smaller_than(mask: np.ndarray, min_area_px: float) -> np.ndarray:
    labels, areas = _components(mask)
    keep = areas >= min_area_px
    keep[0] = False
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _keep_largest(mask: np.ndarray) -> np.ndarray:
    labels, areas = _components(mask)
    if len(areas) < 2:
        return mask
    return np.where(labels == 1 + int(np.argmax(areas[1:])), 255, 0).astype(np.uint8)


def segment(image: np.ndarray, dpi: float, params: Params) -> Segmentation:
    mm_per_px = 25.4 / dpi
    px2_per_mm2 = 1.0 / (mm_per_px * mm_per_px)

    gray = to_gray(image)
    if params.invert_image:
        gray = 255 - gray

    if params.threshold_method == "otsu":
        used, mask = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
        )
        threshold_value_used = int(used)
    else:
        threshold_value_used = int(params.threshold_value)
        mask = np.where(gray < threshold_value_used, 255, 0).astype(np.uint8)

    if params.mode == "whole_root" and params.keep_largest:
        mask = _keep_largest(mask)
    else:
        if params.filter_background_noise:
            mask = _drop_smaller_than(mask, params.max_background_noise_mm2 * px2_per_mm2)
        if params.filter_foreground_noise:
            filled = _drop_smaller_than(
                255 - mask, params.max_foreground_noise_mm2 * px2_per_mm2
            )
            mask = 255 - filled

    if not mask.any():
        raise PipelineError("NO_ROOTS_DETECTED")

    x, y, w, h = cv2.boundingRect(mask)
    mask = np.ascontiguousarray(mask[y : y + h, x : x + w])

    if params.enable_edge_smoothing:
        mask = smooth_contours(mask, params.edge_smoothing_threshold)

    # A mask touching the border has no background to measure against, and the
    # bbox crop guarantees it touches on all four sides: pad, measure, unpad.
    padded = cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    dt = _distance_transform(padded)[1:-1, 1:-1]
    return Segmentation(mask, dt, mm_per_px, threshold_value_used)


def smooth_contours(mask: np.ndarray, epsilon_px: float) -> np.ndarray:
    """Translated from `linesim()` in `cvutil/cvutil_linesim.cpp` of cvutil,
    Copyright (C) Noble Research Institute, LLC, GPL-3.0.

    `RETR_TREE` and not `RETR_EXTERNAL`, which drops the holes. Everything
    downstream reads the smoothed mask.
    """
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return mask

    # Indices have to line up with the hierarchy, so a contour too short to
    # simplify is kept as it is rather than dropped.
    simplified = [
        cv2.approxPolyDP(contour, epsilon_px, True) if len(contour) > 2 else contour
        for contour in contours
    ]
    result = np.zeros_like(mask)
    cv2.drawContours(result, simplified, -1, 255, cv2.FILLED, 8, hierarchy)
    return result


def _distance_transform(mask: np.ndarray) -> np.ndarray:
    """OpenCV 5.0.0 returns one of two arrays for the same input, differing by
    one ULP on a few hundred pixels; it tracks the allocation, not the thread
    count, so `setNumThreads` does not fix it. Ridge detection compares
    distances for equality, so the wobble changes the topology.
    """
    return snap_to_exact(cv2.distanceTransform(mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE))


def snap_to_exact(dt: np.ndarray) -> np.ndarray:
    """Every exact euclidean distance is the square root of an integer. In
    place. Skipped past a radius of ~790 px, where the squaring error reaches
    half a unit and the rounding lands on the wrong integer."""
    if float(dt.max()) ** 2 * 4e-7 < 0.25:
        np.square(dt, out=dt)
        np.rint(dt, out=dt)
        np.sqrt(dt, out=dt)
    return dt


def metrics(seg: Segmentation) -> dict[str, float]:
    mm = seg.mm_per_px
    contours, _ = cv2.findContours(seg.mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    return {
        "network_area": cv2.countNonZero(seg.mask) * mm * mm,
        "max_diameter": 2.0 * float(seg.dt.max()) * mm,
        "perimeter": sum(cv2.arcLength(c, True) for c in contours) * mm,
    }
