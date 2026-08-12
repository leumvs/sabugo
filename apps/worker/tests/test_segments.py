"""Polylines between notable points, and their length."""

import math

import cv2
import numpy as np
import pytest

from sabugo_worker import Params, segment
from sabugo_worker.aggregate import aggregate
from sabugo_worker.segments import (
    extract,
    lengths,
    simplified_length,
    simplified_scales,
)
from sabugo_worker.skeleton import skeletonize
from sabugo_worker.topology import classify

DPI_1PX_PER_MM = 25.4
DPI_254 = 254.0


def measure(image: np.ndarray, dpi: float = DPI_254, **params):
    seg = segment(image, dpi, Params(**params))
    skeleton = skeletonize(seg.mask, seg.dt)
    found = classify(skeleton)
    segments = extract(skeleton, found["tip"] | found["branch"])
    measured = lengths(segments, seg.mm_per_px) | aggregate(
        seg.dt, segments, seg.mm_per_px, Params(**params).diameter_ranges_mm
    )
    return measured, skeleton, segments


def bar(length: int = 200, thickness: int = 20, margin: int = 30) -> np.ndarray:
    image = np.full((thickness + 2 * margin, length + 2 * margin), 255, np.uint8)
    image[margin : margin + thickness, margin : margin + length] = 0
    return image


def test_rectangle_matches_its_medial_axis():
    """200x20 at 254 DPI.

    Not 20 mm: the medial axis of a rectangle runs 180 px down the middle and
    then sends four 10*sqrt(2) arms into the corners. The centre line alone is
    20 mm — but the corner arms are real skeleton and RVE has
    them too.
    """
    expected = (200 - 20 + 4 * 10 * math.sqrt(2)) * 0.1
    got, _, _ = measure(bar())
    # a few percent under the analytic axis: the ends are what skeletonization
    # shortens
    assert got["total_root_length"] == pytest.approx(expected, rel=0.04)


def test_diagonal_length_uses_the_sqrt_two_correction():
    image = np.full((120, 120), 255, np.uint8)
    for i in range(100):
        image[10 + i, 10 + i] = 0
    got, _, _ = measure(image, dpi=DPI_1PX_PER_MM)

    assert got["total_root_length"] == pytest.approx(99 * math.sqrt(2), rel=0.005)
    # without the correction this would read 99: a 41% error
    assert got["total_root_length"] > 1.3 * 99


def test_five_bars_sum_to_five_times_one():
    image = np.full((200, 200), 255, np.uint8)
    for i in range(5):
        image[20 + 35 * i : 30 + 35 * i, 20:180] = 0
    five, _, _ = measure(image, dpi=DPI_1PX_PER_MM)

    one = np.full((60, 200), 255, np.uint8)
    one[20:30, 20:180] = 0
    single, _, _ = measure(one, dpi=DPI_1PX_PER_MM)

    assert five["total_root_length"] == pytest.approx(
        5 * single["total_root_length"], rel=0.01
    )


def test_a_closed_loop_keeps_its_length():
    """A ring has no tip and no branch point: nothing to walk between.

    Dropped, it would take its length with it in silence, and a scan carries
    thousands of them.
    """
    image = np.full((80, 80), 255, np.uint8)
    cv2.circle(image, (40, 40), 25, 0, 4)
    got, _, _ = measure(image, dpi=DPI_1PX_PER_MM)
    assert got["total_root_length"] == pytest.approx(2 * math.pi * 25, rel=0.03)


def test_length_in_mm_survives_a_change_of_dpi():
    small, _, _ = measure(bar(length=100, thickness=10, margin=15), dpi=300.0)
    large, _, _ = measure(bar(length=200, thickness=20, margin=30), dpi=600.0)
    # not exact: the end shortening is a pixel-sized effect, so it costs the
    # smaller rendering relatively more
    assert small["total_root_length"] == pytest.approx(
        large["total_root_length"], rel=0.04
    )


def test_every_skeleton_pixel_belongs_to_a_segment():
    _, skeleton, segments = measure(bar())
    covered = {point for path in segments for point in path}
    assert covered == {tuple(p) for p in np.argwhere(skeleton)}


@pytest.mark.parametrize(
    "path",
    [
        [(0, x) for x in range(20)],  # straight: nothing to simplify
        [(x, x) for x in range(20)],  # diagonal: nothing to simplify either
        [(x // 2, x) for x in range(60)],  # the staircase of ~22.5 degrees
        [(0, 0)],  # an isolated pixel
    ],
)
def test_the_scaled_steps_add_up_to_the_simplified_length(path):
    """What lets `total_root_length` stay the sum of the histogram.

    The scaling is per step so that each one keeps the radius of its own pixel,
    and the equality has to be exact — an approximation here would show up as a
    total that disagrees with the bins it is made of.
    """
    walk = np.hypot(*np.diff(np.array(path, float), axis=0).T) if len(path) > 1 else []
    scaled = float(np.sum(walk * simplified_scales(path)))
    assert scaled == pytest.approx(simplified_length(path), abs=1e-9)


def test_simplification_only_removes_the_staircase():
    straight = simplified_scales([(x, x) for x in range(20)])
    staircase = simplified_scales([(x // 2, x) for x in range(60)])
    assert straight == pytest.approx(1.0)
    assert 0.9 < staircase.mean() < 1.0
