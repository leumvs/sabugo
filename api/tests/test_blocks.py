"""Block seams must preserve the complete neighbourhood operation."""

import cv2
import numpy as np
import pytest

from imaging.pipeline import Params, _distance_transform, segment
from imaging.skeleton import _climb_starts, _detect_ridges, climb_starts, detect_ridges, skeletonize
from imaging.topology import _classify, classify


@pytest.mark.parametrize("height", [255, 256, 257, 511, 512, 513])
def test_neighbourhood_operations_match_full_image_at_seams(height):
    rng = np.random.default_rng(height)
    mask = (rng.random((height, 89)) > 0.75).astype(np.uint8) * 255
    cv2.line(mask, (0, 0), (88, height - 1), 255, 6)
    mask[:, 30:35] = 255  # odd and even plateaus, touching physical borders
    dt = _distance_transform(cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0))[1:-1, 1:-1]
    ridge = detect_ridges(mask, dt)
    assert np.array_equal(ridge, _detect_ridges(mask, dt))
    assert np.array_equal(climb_starts(mask, dt, ridge), _climb_starts(mask, dt, ridge))
    found, expected = classify(ridge), _classify(ridge)
    assert all(np.array_equal(found[key], expected[key]) for key in found)


def test_complete_skeleton_preserves_global_connections(monkeypatch):
    import imaging.skeleton as module

    image = np.full((600, 200), 255, np.uint8)
    cv2.line(image, (0, 0), (199, 599), 0, 7)
    image[252:260, 40:150] = 0
    image[507:515, 20:190] = 0
    seg = segment(image, 600, Params())
    tiled = skeletonize(seg.mask, seg.dt)
    monkeypatch.setattr(module, "BLOCK_ROWS", 1000)
    assert np.array_equal(tiled, skeletonize(seg.mask, seg.dt))
