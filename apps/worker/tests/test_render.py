"""The two derived images."""

import cv2
import numpy as np
import pytest

from sabugo_worker import Params, segment
from sabugo_worker.aggregate import class_of
from sabugo_worker.render import class_colours, segmented, skeleton_picture
from sabugo_worker.skeleton import skeletonize

DPI_254 = 254.0
RANGES = [2.0, 5.0]


def bars(*thicknesses: int, length: int = 200) -> np.ndarray:
    pitch = max(thicknesses) + 20
    image = np.full((pitch * len(thicknesses) + 20, length + 40), 255, np.uint8)
    for i, thickness in enumerate(thicknesses):
        top = 20 + i * pitch
        image[top : top + thickness, 20 : 20 + length] = 0
    return image


def rendered(image: np.ndarray, pen: int = 1, ranges=RANGES):
    seg = segment(image, DPI_254, Params(diameter_ranges_mm=ranges))
    skeleton = skeletonize(seg.mask, seg.dt)
    picture = skeleton_picture(
        seg.mask, seg.dt, skeleton, seg.mm_per_px, ranges, pen=pen
    )
    return picture, seg, skeleton


def test_viridis_is_monotone_in_luminance():
    """Monotone in luminance: the class order survives black and white."""
    for classes in (1, 2, 3, 5, 12):
        greys = [
            0.114 * b + 0.587 * g + 0.299 * r for b, g, r in class_colours(classes)
        ]
        assert greys == sorted(greys)
        assert len(set(greys)) == classes


def test_one_colour_per_class():
    assert len(class_colours(len(RANGES) + 1)) == 3
    assert len(class_colours(len([1.0, 2.0, 3.0, 4.0]) + 1)) == 5


def test_every_pixel_wears_the_class_the_histogram_counted():
    """The point of the shared `class_of`: picture and number cannot disagree."""
    picture, seg, skeleton = rendered(bars(10, 30, 60))
    colours = class_colours(len(RANGES) + 1)

    on = skeleton != 0
    expected = class_of(seg.dt[on], seg.mm_per_px, RANGES)
    painted = picture[on]
    for index, colour in enumerate(colours):
        chosen = expected == index
        if chosen.any():
            assert (painted[chosen] == colour).all(), index


def test_a_thicker_root_gets_a_higher_colour():
    picture, seg, skeleton = rendered(bars(10, 60))
    colours = class_colours(3)
    present = {tuple(int(c) for c in colour) for colour in picture[skeleton != 0]}
    assert colours[0] in present
    assert colours[2] in present


def test_a_diameter_on_the_boundary_takes_the_class_below():
    """20 px at 254 DPI is exactly 2 mm, and the classes are half-open."""
    picture, _, skeleton = rendered(bars(20), ranges=[2.0])
    present = {tuple(int(c) for c in colour) for colour in picture[skeleton != 0]}
    assert class_colours(2)[1] not in present


def test_the_pen_thickens_without_changing_the_colours():
    thin, _, skeleton = rendered(bars(10, 60), pen=1)
    thick, _, _ = rendered(bars(10, 60), pen=3)

    def painted(picture):
        colours = {tuple(int(c) for c in p) for p in picture.reshape(-1, 3)}
        return colours - {(255, 255, 255), (215, 215, 215)}

    assert painted(thin) == painted(thick)
    assert (thick != 255).sum() > (thin != 255).sum()


def test_the_mask_goes_under_the_skeleton():
    picture, seg, skeleton = rendered(bars(60))
    assert (picture[(seg.mask > 0) & (skeleton == 0)] == 215).all()
    assert not (picture[skeleton != 0] == 215).all()


def test_the_segmented_image_is_dark_on_white():
    mask = np.zeros((20, 20), np.uint8)
    mask[5:15, 5:15] = 255
    picture = segmented(mask)
    assert (picture[mask > 0] == 60).all()
    assert (picture[mask == 0] == 255).all()


def test_an_image_without_a_skeleton_is_just_the_mask():
    mask = np.zeros((20, 20), np.uint8)
    mask[5:15, 5:15] = 255
    dt = np.zeros((20, 20), np.float32)
    picture = skeleton_picture(mask, dt, np.zeros_like(mask), 0.1, RANGES)
    assert (picture[mask > 0] == 215).all()


def test_an_empty_mask_renders_a_blank_page():
    empty = np.zeros((12, 12), np.uint8)
    picture = skeleton_picture(empty, np.zeros((12, 12), np.float32), empty, 0.1, RANGES)
    assert (picture == 255).all()


@pytest.mark.parametrize("classes", [1, 3, 12])
def test_the_palette_never_repeats_a_colour(classes):
    assert len(set(class_colours(classes))) == classes


def test_each_overlay_adds_ink_and_none_hides_the_medial_axis():
    image = bars(30)
    seg = segment(image, DPI_254, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    axis = {tuple(int(c) for c in colour) for colour in class_colours(3)}

    def draw(**options):
        return skeleton_picture(
            seg.mask, seg.dt, skeleton, seg.mm_per_px, RANGES, **options
        )

    plain = draw()
    # a plain bar encloses nothing, so `holes` has its own fixture below
    for option in ("hull", "contour"):
        overlaid = draw(**{option: True})
        assert (overlaid != plain).any(), option
        # the axis survives every one of them
        painted = {tuple(int(c) for c in p) for p in overlaid[skeleton != 0]}
        assert painted & axis, option


def test_the_distance_map_paints_the_root_by_radius():
    image = bars(40)
    seg = segment(image, DPI_254, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    picture = skeleton_picture(
        seg.mask, seg.dt, skeleton, seg.mm_per_px, RANGES, show_distance_map=True
    )
    inside = picture[(seg.mask > 0) & (skeleton == 0)]
    assert len({tuple(int(c) for c in p) for p in inside}) > 5
    assert (picture[seg.mask == 0] == 255).all()


def test_medial_axis_off_leaves_the_mask_alone():
    image = bars(10, 60)
    seg = segment(image, DPI_254, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    picture = skeleton_picture(
        seg.mask, seg.dt, skeleton, seg.mm_per_px, RANGES, medial_axis=False
    )
    painted = {tuple(int(c) for c in p) for p in picture.reshape(-1, 3)}
    assert painted == {(255, 255, 255), (215, 215, 215)}


def test_class_colour_off_paints_the_axis_in_one_colour():
    image = bars(10, 60)
    seg = segment(image, DPI_254, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    picture = skeleton_picture(
        seg.mask, seg.dt, skeleton, seg.mm_per_px, RANGES, colour_by_class=False
    )
    on = {tuple(int(c) for c in p) for p in picture[skeleton != 0]}
    assert on == {(60, 60, 60)}
    # the two bars fall in different classes, so a coloured render would differ
    assert len(set(class_colours(3)) & on) == 0


def test_a_ring_gets_its_hole_filled():
    mask = np.zeros((80, 80), np.uint8)
    cv2.circle(mask, (40, 40), 30, 255, -1)
    cv2.circle(mask, (40, 40), 12, 0, -1)
    dt = np.zeros_like(mask, np.float32)
    blank = np.zeros_like(mask)

    plain = skeleton_picture(mask, dt, blank, 0.1, RANGES)
    filled = skeleton_picture(mask, dt, blank, 0.1, RANGES, holes=True)
    assert (plain[40, 40] == 255).all()
    assert not (filled[40, 40] == 255).all()
