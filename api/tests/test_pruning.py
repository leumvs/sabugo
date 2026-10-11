"""Root pruning."""

import numpy as np
import pytest

from imaging import Params, segment
from imaging.pruning import _is_simple, prune
from imaging.skeleton import component_count, skeletonize
from imaging.topology import classify


def tee(limb: int, radius: float, height: int = 40, width: int = 60):
    """A horizontal root with one vertical limb of `limb` px hanging off it.

    Hand-built rather than rendered: the criterion is the point here, and a
    rendered bar puts the branch point half a thickness away from the edge,
    which buries the length being tested under the geometry of the fixture.
    """
    skeleton = np.zeros((height, width), np.uint8)
    dt = np.zeros((height, width), np.float32)

    trunk = height // 2
    skeleton[trunk, 5 : width - 5] = 255
    dt[trunk, 5 : width - 5] = radius

    junction = width // 2
    skeleton[trunk - limb : trunk, junction] = 255
    dt[trunk - limb : trunk, junction] = 1.0
    return skeleton, dt


def tips(skeleton: np.ndarray) -> int:
    return int(classify(skeleton)["tip"].sum())


def test_the_same_limb_goes_off_a_thick_root_and_stays_off_a_thin_one():
    """The only fixture that separates the real criterion
    from a plain maximum length: 10 px is short next to a radius of 10 and
    long next to a radius of 2."""
    thick, thick_dt = tee(limb=10, radius=10.0)
    thin, thin_dt = tee(limb=10, radius=2.0)

    assert tips(prune(thick, thick_dt, 5)) == 2  # limb gone, trunk ends left
    assert tips(prune(thin, thin_dt, 5)) == 3  # limb kept


def test_the_inequality_is_not_strict():
    """The comparison is `<=`, so a limb exactly on the limit goes."""
    skeleton, dt = tee(limb=8, radius=3.0)  # 8 == 3 + 5, exactly on the limit
    assert tips(prune(skeleton, dt, 5)) == 2


def test_a_limb_one_pixel_over_the_limit_survives():
    skeleton, dt = tee(limb=9, radius=3.0)
    assert tips(prune(skeleton, dt, 5)) == 3


def test_the_threshold_is_slack_on_top_of_the_radius():
    skeleton, dt = tee(limb=12, radius=3.0)
    assert tips(prune(skeleton, dt, 5)) == 3
    assert tips(prune(skeleton, dt, 20)) == 2


def test_pruning_repeats_until_nothing_moves():
    skeleton = np.zeros((40, 60), np.uint8)
    dt = np.zeros((40, 60), np.float32)
    skeleton[20, 5:55] = 255
    dt[20, 5:55] = 3.0
    for x in (20, 30, 40):  # three spurs, each exposed only after the last
        skeleton[16:20, x] = 255
        dt[16:20, x] = 1.0

    pruned = prune(skeleton, dt, 5)
    assert tips(pruned) == 2
    assert int(classify(pruned)["branch"].sum()) == 0


def test_pruning_twice_changes_nothing_the_second_time():
    skeleton, dt = tee(limb=10, radius=10.0)
    once = prune(skeleton, dt, 5)
    assert np.array_equal(prune(once, dt, 5), once)


def test_a_whole_root_is_never_pruned():
    skeleton = np.zeros((20, 20), np.uint8)
    dt = np.zeros((20, 20), np.float32)
    skeleton[10, 8:12] = 255
    dt[10, 8:12] = 1.0
    assert np.array_equal(prune(skeleton, dt, 50), skeleton)


def test_pruning_only_ever_removes_pixels():
    skeleton, dt = tee(limb=10, radius=10.0)
    pruned = prune(skeleton, dt, 5)
    assert not (pruned & ~skeleton).any()
    assert (pruned > 0).sum() < (skeleton > 0).sum()


def test_a_root_without_spurs_is_left_alone():
    skeleton = np.zeros((20, 40), np.uint8)
    dt = np.zeros((20, 40), np.float32)
    skeleton[10, 5:35] = 255
    dt[10, 5:35] = 4.0
    assert np.array_equal(prune(skeleton, dt, 5), skeleton)


def test_the_branch_pixel_stays_behind():
    skeleton, dt = tee(limb=10, radius=10.0)
    pruned = prune(skeleton, dt, 5)
    assert pruned[20, 30] == 255


def test_disabled_pruning_leaves_the_pipeline_untouched():
    image = np.full((80, 260), 255, np.uint8)
    image[30:50, 30:230] = 0
    seg = segment(image, 254.0, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    assert Params().enable_root_pruning is False
    assert Params().root_pruning_threshold == 5
    assert np.array_equal(skeleton, skeletonize(seg.mask, seg.dt))


def test_pruning_a_rendered_root_reduces_its_tips():
    image = np.full((80, 260), 255, np.uint8)
    image[30:50, 30:230] = 0
    seg = segment(image, 254.0, Params())
    skeleton = skeletonize(seg.mask, seg.dt)
    pruned = prune(skeleton, seg.dt, 5)
    assert tips(pruned) < tips(skeleton)
    assert not (pruned & ~skeleton).any()


@pytest.mark.parametrize("threshold", [0, 5, 20])
def test_pruning_never_grows_the_tip_count(threshold):
    skeleton, dt = tee(limb=10, radius=4.0)
    assert tips(prune(skeleton, dt, threshold)) <= tips(skeleton)


def grid(*rows: str) -> np.ndarray:
    return np.where(np.array([list(r) for r in rows]) == "#", 255, 0).astype(np.uint8)


@pytest.mark.parametrize(
    ("rows", "simple"),
    [
        ((".#.", ".#.", "..."), True),  # end of a line: nothing to disconnect
        # a pixel mid-line is not simple, and that is why the peeling walks from
        # the tip inwards: each pixel becomes an end once its successor is gone
        ((".#.", ".#.", ".#."), False),
        ((".#.", "###", ".#."), False),  # a cross: erasing it breaks four ways
        ((".#.", ".#.", "#.."), False),  # a bridge between two runs
        (("...", ".#.", "..."), False),  # alone: no neighbour to stay connected
    ],
)
def test_simple_point_test(rows, simple):
    assert _is_simple(grid(*rows), (1, 1)) is simple


def test_pruning_does_not_break_a_root_in_two():
    """The guard the reference image exposed.

    Erasing a whole limb can take a piece of the root with it when a polyline
    shares an interior pixel with another one, or when a `tip` by the ring rule
    still has a neighbour carrying on elsewhere. On crown1 that left the
    skeleton in 10 pieces instead of 1, with every metric still plausible.
    """
    skeleton = grid(
        "..........",
        ".####.....",
        "....#.....",
        "...#.#....",
        "..#...#...",
        ".#.....#..",
    )
    dt = np.where(skeleton > 0, 3.0, 0.0).astype(np.float32)
    before = component_count(skeleton)
    assert component_count(prune(skeleton, dt, 50)) <= before
