"""Synthetic fixtures that do not depend on the skeleton."""

import math

import cv2
import numpy as np
import pytest

from imaging import Params, PipelineError, metrics, segment
from imaging.analysis import analyse
from imaging.pipeline import load_image, snap_to_exact

DPI_1PX_PER_MM = 25.4  # mm_per_px == 1, so metrics come out in pixel units
DPI_254 = 254.0  # mm_per_px == 0.1


def canvas(height: int, width: int) -> np.ndarray:
    return np.full((height, width), 255, np.uint8)


def rect_image(margin: int = 30) -> np.ndarray:
    image = canvas(20 + 2 * margin, 200 + 2 * margin)
    image[margin : margin + 20, margin : margin + 200] = 0
    return image


def disc_image(radius: int) -> np.ndarray:
    image = canvas(4 * radius, 4 * radius)
    cv2.circle(image, (2 * radius, 2 * radius), radius, 0, -1)
    return image


def run(image, dpi=DPI_1PX_PER_MM, **kwargs):
    return metrics(segment(image, dpi, Params(**kwargs)))


def test_rectangle_200x20_at_254_dpi():
    m = run(rect_image(), dpi=DPI_254)
    assert m["network_area"] == pytest.approx(200 * 20 * 0.01)
    assert m["max_diameter"] == pytest.approx(2.0)
    # closed chain of the 200x20 block, in pixel steps: 2*(199 + 19)
    assert m["perimeter"] == pytest.approx(436 * 0.1)


def test_disc_radius_50():
    m = run(disc_image(50))
    assert m["network_area"] == pytest.approx(math.pi * 50**2, rel=0.02)
    assert m["max_diameter"] == pytest.approx(100, rel=0.03)
    # 8-connected chain code overestimates a digital circle by a few percent
    assert m["perimeter"] == pytest.approx(2 * math.pi * 50, rel=0.10)


def test_bounding_box_crop_keeps_metrics_and_drops_the_margin():
    assert run(rect_image(margin=5)) == pytest.approx(run(rect_image(margin=400)))
    assert segment(rect_image(margin=400), DPI_254, Params()).mask.shape == (20, 200)


def test_same_object_at_300_and_600_dpi_agrees_in_mm():
    small = run(disc_image(50), dpi=300.0)
    large = run(disc_image(100), dpi=600.0)
    assert small["network_area"] == pytest.approx(large["network_area"], rel=0.01)
    assert small["max_diameter"] == pytest.approx(large["max_diameter"], rel=0.01)


def test_8_and_16_bit_are_identical():
    image = rect_image()
    wide = image.astype(np.uint16) * 257
    assert run(image) == pytest.approx(run(wide))


def test_16_bit_reduction_is_absolute_not_min_max():
    """threshold_value must mean the same thing whatever the image holds."""
    dim = np.full((60, 60), 30000, np.uint16)
    dim[20:40, 20:40] = 20000
    # 30000 // 257 == 116, still below the threshold: the whole frame is root
    assert run(dim, dpi=DPI_254)["network_area"] == pytest.approx(60 * 60 * 0.01)


def test_threshold_is_strictly_below():
    image = canvas(60, 120)
    image[10:50, 10:50] = 0
    image[10:50, 70:110] = 200  # exactly at the threshold: background
    assert run(image, dpi=DPI_254)["network_area"] == pytest.approx(40 * 40 * 0.01)


def test_only_the_red_channel_segments():
    image = rect_image()
    color = np.zeros((*image.shape, 3), np.uint8)
    color[:, :, 2] = image  # BGR: red carries the root, green and blue are dark
    assert run(color) == pytest.approx(run(image))


def test_background_noise_filter_removes_salt_and_pepper():
    image = rect_image()
    image[0:5:2, 0 : image.shape[1] : 7] = 0  # isolated single-pixel specks

    noisy = run(image, dpi=DPI_254)
    cleaned = run(
        image,
        dpi=DPI_254,
        filter_background_noise=True,
        max_background_noise_mm2=0.02,  # 2 px at 254 DPI
    )
    assert noisy["network_area"] > cleaned["network_area"]
    assert cleaned == pytest.approx(run(rect_image(), dpi=DPI_254))


def test_noise_filter_keeps_components_above_the_limit():
    image = rect_image()
    image[0:5:2, 0:3] = 0  # three 3-px specks, above a 2-px limit
    kept = run(
        image,
        dpi=DPI_254,
        filter_background_noise=True,
        max_background_noise_mm2=0.02,  # 2 px at 254 DPI
    )
    assert kept["network_area"] == pytest.approx((200 * 20 + 9) * 0.01)


def test_snap_to_exact_removes_the_one_ulp_wobble():
    """What makes the distance transform reproducible: ridges compare for ==."""
    exact = np.sqrt(np.array([2, 5, 25, 50, 212], np.float32))
    wobbled = np.nextafter(exact, np.float32(0))
    assert not (wobbled == exact).any()
    assert (snap_to_exact(wobbled) == exact).all()


def test_snap_to_exact_leaves_large_radii_alone():
    huge = np.array([2000.0, 1234.5678], np.float32)
    assert (snap_to_exact(huge.copy()) == huge).all()


def test_blank_image_raises_no_roots_detected():
    with pytest.raises(PipelineError, match="NO_ROOTS_DETECTED"):
        run(canvas(50, 50))


def test_the_same_image_twice_gives_the_same_answer():
    """`snap_to_exact` exists because `cv2.distanceTransform` with
    `DIST_MASK_PRECISE` returns one of two arrays for the same input, and ridge detection
    compares distances for equality. That has a unit test; this one guards the
    property it was written for, over the whole pipeline, where the next
    non-deterministic call will land instead.

    A shape with branches and a crossing, so ridge detection, the ascent and
    the topology all have ties to break.
    """
    image = canvas(240, 240)
    cv2.line(image, (30, 40), (200, 200), 0, 7)
    cv2.line(image, (200, 60), (40, 190), 0, 5)
    cv2.line(image, (120, 120), (210, 130), 0, 4)

    first, second = (analyse(image, DPI_254, Params())[0] for _ in range(2))
    assert first.keys() == second.keys()
    for key, value in first.items():
        if key == "processing_time_ms":
            continue
        assert second[key] == value, key


def test_an_image_over_the_pixel_limit_is_refused(tmp_path):
    """A file size limit bounds bytes, and peak memory scales with
    pixels. The two are unrelated: an A4 page at 1200 DPI is 97 MP and
    compresses to 0.6 MB as PNG, so a limit on the upload lets through an
    image that needs about 4.8 GB. `max_pixels` is a parameter so this does
    not have to allocate one to prove it.
    """
    path = tmp_path / "wide.png"
    cv2.imwrite(str(path), canvas(200, 200))

    assert load_image(str(path), max_pixels=40_000).shape == (200, 200)
    with pytest.raises(PipelineError, match="IMAGE_TOO_LARGE"):
        load_image(str(path), max_pixels=40_000 - 1)




def test_an_unreadable_file_raises_invalid_image(tmp_path):
    broken = tmp_path / "not-an-image.png"
    broken.write_bytes(b"certainly not a PNG")
    with pytest.raises(PipelineError, match="INVALID_IMAGE"):
        load_image(str(broken))


def test_invert_image():
    inverted = 255 - rect_image()
    assert run(inverted, dpi=DPI_254, invert_image=True) == pytest.approx(
        run(rect_image(), dpi=DPI_254)
    )


def test_otsu_matches_manual_on_a_clean_fixture():
    assert run(rect_image(), threshold_method="otsu") == pytest.approx(run(rect_image()))
