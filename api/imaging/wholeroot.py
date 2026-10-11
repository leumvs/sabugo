"""The whole-root metrics, and the root angles.

Whole root drops `num_branch_points` and `branching_frequency`: in
`feature_extraction.cpp` the two come out under an explicit `roottype` branch,
only for broken roots, and the column count of the reference row confirms it.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .segments import simplified_scales

REACH = 20  # px either side along the polyline, the paper's "40 x 40 locality"
ANGLE_BINS = (30.0, 60.0)  # shallow | medium | steep, measured from horizontal


def roots_per_row(mask: np.ndarray) -> np.ndarray:
    """Over the bbox-cropped mask, and empty rows count."""
    padded = np.pad(mask != 0, ((0, 0), (1, 0)))
    return (padded[:, 1:] & ~padded[:, :-1]).sum(axis=1)


def holes(mask: np.ndarray) -> list[float]:
    """A component touching the border is the outside, not a hole. Each area
    is the polygon the contour encloses and not its pixel count."""
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    # RETR_CCOMP puts outer boundaries at level 0 and holes at level 1
    return [
        cv2.contourArea(contour)
        for contour, entry in zip(contours, hierarchy[0])
        if entry[3] >= 0
    ]


def orientations(segments, reach: int = REACH, scales: list[np.ndarray] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """In degrees from the horizontal: the chord between the pixel `reach`
    steps back and `reach` steps forward along its own polyline. A 2D window
    instead collects other roots crossing it.

    Returned with a weight per angle, the length of the step that pixel opens,
    so the frequencies are fractions of length and not of pixels.
    """
    angles, weights = [], []
    for path_index, path in enumerate(segments):
        last = len(path) - 1
        factors = scales[path_index] if scales is not None else simplified_scales(path)
        for index in range(last):  # the step a pixel opens, so the last has none
            back = path[max(0, index - reach)]
            ahead = path[min(last, index + reach)]
            dy, dx = ahead[0] - back[0], ahead[1] - back[1]
            if dy or dx:
                angles.append(abs(math.degrees(math.atan2(dy, dx))))
                step = path[index + 1]
                weights.append(
                    math.dist(path[index], step) * factors[index]
                )
    turned = np.array(angles)
    # a chord pointing up-left and one pointing down-right are the same axis
    return np.where(turned > 90.0, 180.0 - turned, turned), np.array(weights)


def measure(
    mask: np.ndarray, dt: np.ndarray, segments, mm_per_px: float,
    scales: list[np.ndarray] | None = None,
) -> dict[str, float]:
    area = mm_per_px * mm_per_px
    height, width = mask.shape

    hull = cv2.convexHull(cv2.findNonZero(mask))
    # a root a single pixel wide has a hull of zero area, and solidity is then
    # undefined rather than infinite
    convex_area = cv2.contourArea(hull) * area
    depth = height * mm_per_px

    widest_row = int(np.unravel_index(int(dt.argmax()), dt.shape)[0])
    hole_areas = holes(mask)
    angles, weights = orientations(segments, scales=scales)
    counts = roots_per_row(mask)
    shallow, medium = ANGLE_BINS
    total_weight = float(weights.sum()) if weights.size else 0.0

    def share(selected) -> float:
        return float(weights[selected].sum() / total_weight) if total_weight else 0.0

    return {
        "median_number_of_roots": float(np.median(counts)),
        "max_number_of_roots": float(counts.max()),
        "depth": depth,
        "max_width": width * mm_per_px,
        "width_to_depth_ratio": width / height,
        "convex_area": convex_area,
        "solidity": (float(cv2.countNonZero(mask)) * area / convex_area) if convex_area else 0.0,
        "lower_root_area": float(cv2.countNonZero(mask[widest_row:])) * area,
        "holes": float(len(hole_areas)),
        "average_hole_size": float(np.mean(hole_areas)) * area if hole_areas else 0.0,
        "average_root_orientation": (
            float(np.average(angles, weights=weights)) if total_weight else 0.0
        ),
        "shallow_angle_frequency": share(angles <= shallow),
        "medium_angle_frequency": share((angles > shallow) & (angles <= medium)),
        "steep_angle_frequency": share(angles > medium),
    }
