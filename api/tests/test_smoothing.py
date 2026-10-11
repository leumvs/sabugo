"""Contour smoothing."""

import cv2
import numpy as np
import pytest

from imaging import Params, segment
from imaging.pipeline import smooth_contours

DPI_254 = 254.0


def jagged_bar(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = np.full((80, 220), 255, np.uint8)
    for x in range(20, 200):
        thickness = int(rng.integers(8, 18))
        image[40 - thickness // 2 : 40 - thickness // 2 + thickness, x] = 0
    return image


def ring(inner: int = 12, outer: int = 30) -> np.ndarray:
    mask = np.zeros((90, 90), np.uint8)
    cv2.circle(mask, (45, 45), outer, 255, -1)
    cv2.circle(mask, (45, 45), inner, 0, -1)
    return mask


def perimeter_of(mask: np.ndarray) -> float:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    return sum(cv2.arcLength(contour, True) for contour in contours)


def test_smoothing_takes_the_jaggedness_off():
    mask = (jagged_bar() == 0).astype(np.uint8) * 255
    smoothed = smooth_contours(mask, 2.0)

    assert perimeter_of(smoothed) < 0.8 * perimeter_of(mask)
    assert (smoothed > 0).sum() == pytest.approx((mask > 0).sum(), rel=0.10)


def test_a_bigger_epsilon_smooths_more():
    mask = (jagged_bar() == 0).astype(np.uint8) * 255
    perimeters = [perimeter_of(smooth_contours(mask, eps)) for eps in (1.0, 3.0, 6.0)]
    assert perimeters == sorted(perimeters, reverse=True)


def test_epsilon_zero_keeps_the_shape():
    mask = (jagged_bar() == 0).astype(np.uint8) * 255
    assert (smooth_contours(mask, 0.0) > 0).sum() == pytest.approx(
        (mask > 0).sum(), rel=0.001
    )


def test_a_hole_stays_a_hole():
    """`linesim` hands the RETR_TREE hierarchy to the drawing for this reason.

    Rasterizing the outlines without it fills every hole, which would change
    `network_area` — the one metric that does not discount holes anyway,
    so the error would be invisible in the number that mentions them.
    """
    mask = ring()
    smoothed = smooth_contours(mask, 2.0)
    assert smoothed[45, 45] == 0
    assert (smoothed > 0).sum() == pytest.approx((mask > 0).sum(), rel=0.02)


def test_the_polygon_is_closed():
    """`doughlas_peucker(contour, epsilon, true)` in the source, and a contour
    is a loop, so the seam between its first and last point is an edge like any
    other. Simplified as an open polyline the seam is pinned instead, which
    leaves a notch there: 263 px of difference on this fixture at epsilon 6.

    Exact counts, because the difference is a shape and not a direction —
    both readings shrink or grow the area depending on where the seam lands.
    """
    mask = (jagged_bar() == 0).astype(np.uint8) * 255
    assert int((smooth_contours(mask, 2.0) > 0).sum()) == 2370
    assert int((smooth_contours(mask, 6.0) > 0).sum()) == 2938
    assert int((smooth_contours(ring(), 6.0) > 0).sum()) == 2292


def test_a_square_keeps_its_corners():
    mask = np.zeros((60, 60), np.uint8)
    mask[15:45, 15:45] = 255
    assert (smooth_contours(mask, 2.0) > 0).sum() == pytest.approx(30 * 30, rel=0.05)


def test_disabled_by_default_and_inert_when_off():
    image = jagged_bar()
    plain = segment(image, DPI_254, Params())
    assert Params().enable_edge_smoothing is False
    assert Params().edge_smoothing_threshold == 2.0
    assert np.array_equal(plain.mask, segment(image, DPI_254, Params()).mask)


def test_smoothing_reaches_the_metrics_that_come_after_it():
    """It runs before the distance transform, so the skeleton sees it too."""
    image = jagged_bar()
    plain = segment(image, DPI_254, Params())
    smooth = segment(
        image, DPI_254, Params(enable_edge_smoothing=True, edge_smoothing_threshold=3.0)
    )
    assert perimeter_of(smooth.mask) < perimeter_of(plain.mask)
    assert not np.array_equal(plain.dt, smooth.dt)


def test_smoothing_survives_an_image_with_nothing_to_smooth():
    mask = np.zeros((20, 20), np.uint8)
    mask[10, 10] = 255
    assert (smooth_contours(mask, 2.0) >= 0).all()
