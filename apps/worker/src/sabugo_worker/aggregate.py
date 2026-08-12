from __future__ import annotations

import math

import numpy as np

from .segments import simplified_scales

HISTOGRAMS = ("root_length", "projected_area", "surface_area", "volume")


def class_of(radius_px, mm_per_px: float, diameter_ranges_mm: list[float]):
    """`side="left"`: the classes are half-open, `[0, 2]` then `(2, 5]`."""
    return np.searchsorted(
        diameter_ranges_mm, 2.0 * np.asarray(radius_px) * mm_per_px, side="left"
    )


def class_labels(diameter_ranges_mm: list[float]) -> list[str]:
    edges = [0.0, *diameter_ranges_mm]
    labels = [f"{a:g}-{b:g}" for a, b in zip(edges, diameter_ranges_mm)]
    return [*labels, f"{edges[-1]:g}-above"]


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    """Weighted by length: a digital line of euclidean length L holds
    `L * max(|cos|, |sin|)` pixels, so counting pixels would weight an
    axis-aligned root up to 41% more heavily than a diagonal one."""
    total = float(weights.sum())
    return float(np.average(values, weights=weights)) if total else 0.0


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    total = float(weights.sum())
    if not total:
        return 0.0
    order = np.argsort(values)
    walked = np.cumsum(weights[order])
    return float(values[order][np.searchsorted(walked, total / 2.0)])


def _steps(segments: list[list[tuple[int, int]]]):
    starts = [point for path in segments for point in path[:-1]]
    ends = [point for path in segments for point in path[1:]]
    if not starts:
        return np.zeros((0, 2), int), np.zeros((0, 2), int), np.zeros(0)
    scales = np.concatenate([simplified_scales(path) for path in segments])
    return np.array(starts), np.array(ends), scales


def aggregate(
    dt: np.ndarray,
    segments: list[list[tuple[int, int]]],
    mm_per_px: float,
    diameter_ranges_mm: list[float],
) -> dict[str, object]:
    """Every step carries the local radius of the pixel it leaves, so a root
    that thins along its length lands in more than one class."""
    classes = len(diameter_ranges_mm) + 1
    starts, ends, scales = _steps(segments)

    radius = dt[starts[:, 0], starts[:, 1]].astype(np.float64)
    delta = np.hypot(*(ends - starts).T.astype(np.float64)) * scales
    where = class_of(radius, mm_per_px, diameter_ranges_mm)

    def binned(weights, unit):
        return list(np.bincount(where, weights, minlength=classes) * unit)

    length = mm_per_px
    area = mm_per_px**2
    histograms = {
        "root_length": binned(delta, length),
        "projected_area": binned(2.0 * radius * delta, area),
        "surface_area": binned(2.0 * math.pi * radius * delta, area),
        "volume": binned(math.pi * radius * radius * delta, mm_per_px**3),
    }

    diameters = 2.0 * radius * mm_per_px
    return {
        "histograms": histograms,
        "average_diameter": weighted_mean(diameters, delta),
        "median_diameter": weighted_median(diameters, delta),
        "surface_area": float(sum(histograms["surface_area"])),
        "volume": float(sum(histograms["volume"])),
        "total_root_length": float(sum(histograms["root_length"])),
    }
