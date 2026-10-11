"""Diameter-class histograms and the metrics that come with them."""

import math

import numpy as np
import pytest

from imaging import Params, segment
from imaging.aggregate import HISTOGRAMS, aggregate, class_labels
from imaging.segments import extract
from imaging.skeleton import skeletonize
from imaging.topology import classify

DPI_254 = 254.0  # 0.1 mm per pixel


def measure(image: np.ndarray, dpi: float = DPI_254, **params):
    parameters = Params(**params)
    seg = segment(image, dpi, parameters)
    skeleton = skeletonize(seg.mask, seg.dt)
    found = classify(skeleton)
    segments = extract(skeleton, found["tip"] | found["branch"])
    return aggregate(
        seg.dt, segments, seg.mm_per_px, parameters.diameter_ranges_mm
    )


def bars(*thicknesses: int, length: int = 200) -> np.ndarray:
    pitch = max(thicknesses) + 20
    image = np.full((pitch * len(thicknesses) + 20, length + 40), 255, np.uint8)
    for i, thickness in enumerate(thicknesses):
        top = 20 + i * pitch
        image[top : top + thickness, 20 : 20 + length] = 0
    return image


def test_class_labels_follow_the_rve_columns():
    assert class_labels([2.0, 5.0]) == ["0-2", "2-5", "5-above"]
    assert class_labels([1.0]) == ["0-1", "1-above"]


def test_rectangle_volume_and_diameter():
    """200x20 px at 254 DPI: a 2 mm cylinder, 20 mm long."""
    got = measure(bars(20))
    assert got["volume"] == pytest.approx(math.pi * 1.0**2 * 20, rel=0.10)
    # under 2 mm: the medial axis sends thin arms into the corners, and they
    # carry a local radius far below the bar's
    assert got["average_diameter"] == pytest.approx(2.0, rel=0.15)
    assert got["average_diameter"] < 2.0


def test_each_bar_lands_in_its_own_class():
    """10 px and 60 px thick at 254 DPI: 1 mm and 6 mm across."""
    got = measure(bars(10, 60), diameter_ranges_mm=[2.0, 5.0])
    length = got["histograms"]["root_length"]
    # the thin bar is 20 mm of class 1 on its own, and the thick bar keeps
    # 16.8 mm of core above 5 mm
    assert length[0] > 20.0
    assert length[2] == pytest.approx(16.8, rel=0.10)
    # the middle class is not empty: the corner arms of the thick bar taper
    # through it on their way in, which is exactly what the histogram is for
    assert 0 < length[1] < 0.6 * length[2]
    # and the thick bar dominates volume while carrying less length
    assert got["histograms"]["volume"][2] > 10 * got["histograms"]["volume"][0]


def test_a_diameter_exactly_on_the_boundary_falls_in_the_class_below():
    """The classes are half-open: [0, 2] then (2, 5].

    Hand-built, because a rendered bar never lands exactly on the boundary in
    floating point - and the boundary is the only place the rule shows.
    """
    skeleton = np.zeros((3, 12), np.uint8)
    skeleton[1, 1:11] = 255
    dt = np.zeros((3, 12), np.float32)
    dt[1, 1:11] = 1.0  # radius 1 px, so diameter 2 mm at 1 mm per pixel
    path = [(1, x) for x in range(1, 11)]

    got = aggregate(dt, [path], 1.0, [2.0])
    assert got["histograms"]["root_length"] == pytest.approx([9.0, 0.0])


def test_a_step_carries_the_radius_of_the_pixel_it_leaves():
    """Which of the two pixels of a step decides its class: the one it
    leaves, so a step out of a thin pixel into a thick one is thin.
    """
    skeleton = np.zeros((3, 6), np.uint8)
    skeleton[1, 1:5] = 255
    dt = np.zeros((3, 6), np.float32)
    dt[1, 1:4] = 1.0
    dt[1, 4] = 10.0
    path = [(1, x) for x in range(1, 5)]

    got = aggregate(dt, [path], 1.0, [4.0])
    assert got["histograms"]["root_length"] == pytest.approx([3.0, 0.0])


def test_a_bar_on_the_boundary_falls_in_the_class_below():
    """20 px at 254 DPI is exactly 2 mm, and the class is [0, 2]."""
    got = measure(bars(20), diameter_ranges_mm=[2.0])
    length = got["histograms"]["root_length"]
    assert length[1] == pytest.approx(0.0, abs=0.5)
    assert length[0] > 0


def test_totals_are_the_sum_of_their_bins():
    got = measure(bars(10, 30, 60), diameter_ranges_mm=[2.0, 5.0])
    assert got["total_root_length"] == pytest.approx(sum(got["histograms"]["root_length"]))
    assert got["volume"] == pytest.approx(sum(got["histograms"]["volume"]))
    assert got["surface_area"] == pytest.approx(sum(got["histograms"]["surface_area"]))


def test_surface_area_and_volume_agree_with_the_cylinder_they_describe():
    got = measure(bars(20))
    assert got["surface_area"] == pytest.approx(2 * math.pi * 1.0 * 20, rel=0.15)
    assert got["volume"] / got["surface_area"] == pytest.approx(1.0 / 2, rel=0.15)


def test_metrics_in_mm_survive_a_change_of_dpi():
    small = measure(bars(10, length=100), dpi=300.0)
    large = measure(bars(20, length=200), dpi=600.0)
    for key in ("total_root_length", "surface_area", "volume", "average_diameter"):
        assert small[key] == pytest.approx(large[key], rel=0.06), key


def test_thicker_roots_dominate_volume_but_not_length():
    got = measure(bars(10, 10, 10, 60), diameter_ranges_mm=[2.0, 5.0])
    length = got["histograms"]["root_length"]
    volume = got["histograms"]["volume"]
    assert length[0] > length[2]
    assert volume[2] > volume[0]


def test_every_histogram_has_one_cell_per_class():
    got = measure(bars(10), diameter_ranges_mm=[1.0, 2.0, 4.0])
    for name in HISTOGRAMS:
        assert len(got["histograms"][name]) == 4
