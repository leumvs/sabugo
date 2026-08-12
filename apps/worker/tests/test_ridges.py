"""Ridge detection, the first step of skeletonization."""

import numpy as np
import pytest

from sabugo_worker import Params, segment
from sabugo_worker.skeleton import component_count, detect_ridges

DPI_1PX_PER_MM = 25.4


def ridges(image: np.ndarray):
    seg = segment(image, DPI_1PX_PER_MM, Params())
    return seg.mask, detect_ridges(seg.mask, seg.dt)


def band(width: int, height: int = 60, length: int = 80) -> np.ndarray:
    image = np.full((height, length), 255, np.uint8)
    top = (height - width) // 2
    image[top : top + width, 10 : length - 10] = 0
    return image


def test_one_pixel_line_is_entirely_ridge():
    mask, ridge = ridges(band(1))
    assert np.array_equal(mask, ridge)


def test_odd_width_band_ridges_on_the_single_centre_row():
    _, ridge = ridges(band(21))
    assert np.nonzero(ridge[:, 30])[0].tolist() == [10]


def test_even_width_band_keeps_both_plateau_rows():
    """No single row is a strict maximum, so only the plateau rule finds these."""
    _, ridge = ridges(band(20))
    assert np.nonzero(ridge[:, 30])[0].tolist() == [9, 10]


def test_staircase_diagonal_is_entirely_ridge():
    image = np.full((60, 60), 255, np.uint8)
    for i in range(50):
        image[5 + i, 5 + i] = 0
        image[5 + i, 6 + i] = 0  # two-wide, so the run is 8- but not 4-connected
    mask, ridge = ridges(image)
    assert component_count(ridge) == 1
    assert (ridge > 0).sum() >= (mask > 0).sum() // 2


def test_ridge_is_a_subset_of_the_mask():
    mask, ridge = ridges(band(20))
    assert not (ridge & ~mask).any()


def test_every_mask_component_carries_a_ridge():
    image = np.full((200, 200), 255, np.uint8)
    for i in range(5):
        image[20 + 35 * i : 20 + 35 * i + 10 + i, 20:180] = 0
    mask, ridge = ridges(image)
    assert component_count(mask) == 5
    assert component_count(ridge) == 5


def test_disc_ridges_at_the_centre_and_almost_nowhere_else():
    image = np.full((200, 200), 255, np.uint8)
    import cv2

    cv2.circle(image, (100, 100), 50, 0, -1)
    mask, ridge = ridges(image)
    assert ridge[ridge.shape[0] // 2, ridge.shape[1] // 2] == 255
    assert (ridge > 0).sum() < 0.05 * (mask > 0).sum()


def test_blank_mask_has_no_ridges():
    mask = np.zeros((20, 20), np.uint8)
    assert not detect_ridges(mask, np.zeros((20, 20), np.float32)).any()


@pytest.mark.parametrize("width", [1, 2, 3, 20, 21])
def test_ridge_never_leaves_a_component_empty(width):
    mask, ridge = ridges(band(width))
    assert component_count(ridge) == component_count(mask) == 1
