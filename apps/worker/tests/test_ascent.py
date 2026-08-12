"""Steepest ascent and thinning, the second and third steps."""

import cv2
import numpy as np
import pytest

from sabugo_worker import Params, segment
from sabugo_worker.skeleton import (
    component_count,
    detect_ridges,
    ridge_endpoints,
    skeletonize,
    steepest_ascent,
)

DPI_1PX_PER_MM = 25.4


def parts(image: np.ndarray):
    seg = segment(image, DPI_1PX_PER_MM, Params())
    ridge = detect_ridges(seg.mask, seg.dt)
    return seg, ridge, steepest_ascent(seg.mask, seg.dt, ridge)


def band(width: int, height: int = 60, length: int = 80) -> np.ndarray:
    image = np.full((height, length), 255, np.uint8)
    top = (height - width) // 2
    image[top : top + width, 10 : length - 10] = 0
    return image


def jagged_bar() -> np.ndarray:
    rng = np.random.default_rng(0)
    image = np.full((80, 200), 255, np.uint8)
    for x in range(10, 190):
        thickness = rng.integers(6, 16)
        image[40 - thickness // 2 : 40 - thickness // 2 + thickness, x] = 0
    return image


def test_ascent_joins_a_fragmented_ridge():
    _, ridge, ascended = parts(jagged_bar())
    assert component_count(ridge) == 33
    assert component_count(ascended) == 1


def test_ascent_leaves_an_already_connected_ridge_alone():
    _, ridge, ascended = parts(band(20))
    assert component_count(ridge) == 1
    assert np.array_equal(ridge, ascended)


def test_ascent_only_adds_pixels_and_only_inside_the_mask():
    seg, ridge, ascended = parts(jagged_bar())
    assert not (ridge & ~ascended).any()
    assert not (ascended & ~seg.mask).any()
    assert (ascended > 0).sum() > (ridge > 0).sum()


def test_walk_passes_through_a_lone_ridge_pixel():
    """A climb stops on a ridge pixel with more than one ridge neighbour.

    A stray one-pixel fragment is not a fragment to stop at, and stopping
    there would leave the two real pieces unjoined.
    """
    mask = np.zeros((9, 21), np.uint8)
    mask[3:6, 1:20] = 255
    padded = cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    dt = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]

    ridge = np.zeros_like(mask)
    ridge[4, 1:7] = 255  # left fragment
    ridge[4, 10] = 255  # the lone pixel on the way
    ridge[4, 14:20] = 255  # right fragment
    assert component_count(ridge) == 3

    # one pass: stopping at the lone pixel would need a second one to recover,
    # and the point is that a single climb crosses it
    assert component_count(steepest_ascent(mask, dt, ridge, max_passes=1)) == 1


def test_thinning_leaves_one_pixel_per_cross_section():
    seg = segment(band(20), DPI_1PX_PER_MM, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    assert np.count_nonzero(skeleton[:, 30]) == 1
    assert component_count(skeleton) == 1


def test_skeleton_of_a_one_pixel_line_is_the_line():
    seg = segment(band(1), DPI_1PX_PER_MM, Params())
    assert np.array_equal(skeletonize(seg.mask, seg.dt), seg.mask)


def ridge_from(rows: list[str]) -> np.ndarray:
    return np.where(np.array([list(r) for r in rows]) == "#", 255, 0).astype(np.uint8)


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        # one neighbour: a plain line end
        ([".....", ".###.", "....."], {(1, 1), (1, 3)}),
        # two neighbours, adjacent in the ring: still an end (the staircase)
        (["..#..", ".##..", "....."], {(0, 2), (1, 1)}),
        # two neighbours on opposite sides: a pass-through pixel, never an end
        ([".....", "#####", "....."], {(1, 0), (1, 4)}),
    ],
)
def test_ridge_endpoint_rules(rows, expected):
    found = {tuple(p) for p in np.argwhere(ridge_endpoints(ridge_from(rows)))}
    assert found == expected
