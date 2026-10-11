"""Whole-root metrics and the root angles."""

import cv2
import numpy as np
import pytest

from imaging import Params, segment
from imaging.segments import extract
from imaging.skeleton import skeletonize
from imaging.topology import classify
from imaging.wholeroot import holes, measure, orientations, roots_per_row

DPI_254 = 254.0


def measured(image: np.ndarray, dpi: float = DPI_254):
    seg = segment(image, dpi, Params(mode="whole_root", keep_largest=False))
    skeleton = skeletonize(seg.mask, seg.dt)
    found = classify(skeleton)
    segments = extract(skeleton, found["tip"] | found["branch"])
    return measure(seg.mask, seg.dt, segments, seg.mm_per_px)


def line(vertical: bool, length: int = 200, thickness: int = 6) -> np.ndarray:
    image = np.full((260, 260), 255, np.uint8)
    start = (260 - length) // 2
    if vertical:
        image[start : start + length, 130 - thickness // 2 : 130 + thickness // 2] = 0
    else:
        image[130 - thickness // 2 : 130 + thickness // 2, start : start + length] = 0
    return image


def test_depth_and_width_are_the_bounding_box():
    image = np.full((200, 300), 255, np.uint8)
    image[50:150, 40:240] = 0  # 100 px tall, 200 px wide, at 254 DPI
    got = measured(image)
    assert got["depth"] == pytest.approx(10.0, rel=0.01)
    assert got["max_width"] == pytest.approx(20.0, rel=0.01)
    assert got["width_to_depth_ratio"] == pytest.approx(2.0, rel=0.01)


def test_a_filled_shape_is_almost_all_of_its_hull():
    image = np.full((200, 200), 255, np.uint8)
    cv2.circle(image, (100, 100), 60, 0, -1)
    got = measured(image)
    assert got["solidity"] == pytest.approx(1.0, rel=0.02)
    assert got["holes"] == 0


def test_a_ring_has_exactly_one_hole():
    image = np.full((200, 200), 255, np.uint8)
    cv2.circle(image, (100, 100), 60, 0, -1)
    cv2.circle(image, (100, 100), 30, 255, -1)
    got = measured(image)
    assert got["holes"] == 1
    # the polygon through the pixel centres, so a shade under pi * 30^2 px
    assert got["average_hole_size"] == pytest.approx(np.pi * 3.0**2, rel=0.05)
    assert got["solidity"] < 1.0


def test_only_enclosed_gaps_count_as_holes():
    """A gap open to the outside is background, not a hole.

    The area is the polygon the hole's contour encloses and not its pixel
    count, which is what crown1 settled: the pixel reading puts the mean at
    14.2 mm² against the 4.840 reported, and the polygon reading agrees.
    """
    mask = np.zeros((40, 40), np.uint8)
    mask[5:35, 5:35] = 255
    mask[10:16, 10:16] = 0  # enclosed
    mask[20:30, 30:35] = 0  # a bite out of the edge, open to the outside
    assert len(holes(mask)) == 1
    assert holes(mask)[0] > 0


def test_a_vertical_root_is_steep_and_a_horizontal_one_is_shallow():
    """The only fixture that catches a flipped
    axis: the bin names read the same either way, and only the average tells."""
    upright = measured(line(vertical=True))
    flat = measured(line(vertical=False))

    assert upright["steep_angle_frequency"] > 0.9
    assert upright["average_root_orientation"] > 80
    assert flat["shallow_angle_frequency"] > 0.9
    assert flat["average_root_orientation"] < 10


def test_the_frequencies_add_up_to_one():
    got = measured(line(vertical=True))
    total = sum(
        got[f"{name}_angle_frequency"] for name in ("shallow", "medium", "steep")
    )
    assert total == pytest.approx(1.0)


def test_a_diagonal_lands_in_the_middle_bin():
    image = np.full((260, 260), 255, np.uint8)
    for i in range(200):
        image[30 + i : 34 + i, 30 + i : 34 + i] = 0
    got = measured(image)
    assert got["average_root_orientation"] == pytest.approx(45.0, abs=5.0)
    assert got["medium_angle_frequency"] > 0.8


def test_the_angle_walk_reaches_along_the_polyline():
    straight = [[(10, x) for x in range(10, 60)]]
    for reach in (5, 20, 40):
        angles, weights = orientations(straight, reach=reach)
        assert angles.max() == pytest.approx(0.0)
        # one weight per angle, and a horizontal run steps one pixel at a time
        assert weights.shape == angles.shape
        assert weights.sum() == pytest.approx(49.0)


def test_roots_per_row_counts_transitions_not_pixels():
    mask = np.zeros((3, 10), np.uint8)
    mask[0, 1:4] = 255  # one root, three pixels wide
    mask[1, 1:3] = 255
    mask[1, 6:8] = 255  # two roots
    assert roots_per_row(mask).tolist() == [1, 2, 0]


def test_the_median_keeps_the_empty_rows():
    """The empty rows count, and dropping them changes the answer.

    Two bars with a wide gap: 20 rows hold a root and 40 hold nothing, all of
    them inside the crop. Counting every row the median is 0; counting only
    the rows that have a root it would be 1.
    """
    image = np.full((120, 200), 255, np.uint8)
    image[20:30, 20:180] = 0
    image[70:80, 20:180] = 0

    counts = roots_per_row((image < 200).astype(np.uint8) * 255)
    assert (counts == 0).sum() > (counts > 0).sum()
    assert measured(image)["median_number_of_roots"] == 0.0
    assert measured(image)["max_number_of_roots"] == 1.0


def test_lower_root_area_looks_below_the_widest_point():
    """Turn the plant upside down and the number has to move.

    Thick part at the top puts the widest row near the top, so nearly the whole
    root lies below it. Upside down, the widest row is near the bottom and only
    the lower half of the thick block is under it — the same shape, a very
    different number, and the proxy for deep biomass the metric is for.
    """
    top = np.full((300, 200), 255, np.uint8)
    top[20:60, 60:140] = 0  # the thick part up here
    top[60:280, 95:105] = 0  # a thin tail below it

    thick_at_the_top = measured(top)
    thick_at_the_bottom = measured(top[::-1].copy())
    assert thick_at_the_top["lower_root_area"] > 2 * thick_at_the_bottom["lower_root_area"]


def test_an_image_with_one_pixel_does_not_divide_by_zero():
    image = np.full((40, 40), 255, np.uint8)
    image[20, 20] = 0
    got = measured(image)
    assert got["holes"] == 0
    assert got["depth"] > 0
