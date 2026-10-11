"""Skeleton classification: tips, branch points, overlap points."""

import numpy as np
import pytest

from imaging.topology import classify


def skeleton(*rows: str) -> np.ndarray:
    return np.where(np.array([list(r) for r in rows]) == "#", 255, 0).astype(np.uint8)


def found(kind: str, *rows: str) -> set[tuple[int, int]]:
    return {tuple(p) for p in np.argwhere(classify(skeleton(*rows))[kind])}


def test_straight_line_has_two_tips_and_no_branch():
    rows = (".....", "#####", ".....")
    assert found("tip", *rows) == {(1, 0), (1, 4)}
    assert found("branch", *rows) == set()


def test_staircase_end_counts_as_a_tip():
    """Two neighbours adjacent in the ring: the staircase artefact."""
    rows = (".#...", "##...", ".....")
    assert found("tip", *rows) == {(0, 1), (1, 0)}


def test_y_has_three_tips_and_one_branch():
    rows = ("#...#", ".#.#.", "..#..", "..#..")
    assert found("tip", *rows) == {(0, 0), (0, 4), (3, 2)}
    assert found("branch", *rows) == {(2, 2)}


def test_crossing_is_an_overlap_and_also_a_branch():
    rows = ("..#..", "..#..", "#####", "..#..", "..#..")
    assert found("overlap", *rows) == {(2, 2)}
    assert found("branch", *rows) == {(2, 2)}
    assert found("tip", *rows) == {(0, 2), (2, 0), (2, 4), (4, 2)}


def test_diagonal_crossing_is_an_overlap():
    rows = ("#...#", ".#.#.", "..#..", ".#.#.", "#...#")
    assert found("overlap", *rows) == {(2, 2)}


def test_isolated_pixel_is_neither():
    """`nsum == 0` falls through both branches of the source. Quirk, kept."""
    rows = ("...", ".#.", "...")
    assert found("tip", *rows) == set()
    assert found("branch", *rows) == set()


@pytest.mark.parametrize(
    "rows",
    [
        (".....", "#####", "....."),  # pass-through, two opposite neighbours
        ("..#..", "..#..", "..#..") ,  # vertical pass-through
    ],
)
def test_pass_through_pixels_are_not_branches(rows):
    assert found("branch", *rows) == set()


def test_six_neighbours_in_a_degenerate_layout_is_not_a_branch():
    """N1 and N2 both background: excluded by the source despite the run of three."""
    rows = ("##.", "##.", "###")
    assert (1, 1) not in found("branch", *rows)


def test_three_contiguous_neighbours_is_not_a_branch():
    """The run-of-three clause starts at four neighbours, not three."""
    rows = (".##", ".##", "...")
    assert (1, 1) not in found("branch", *rows)


def test_seven_neighbours_is_not_a_branch():
    """The clause stops below seven."""
    rows = ("###", "###", "##.")
    assert (1, 1) not in found("branch", *rows)


def test_five_neighbours_with_a_run_of_three_is_a_branch():
    """The same shape one neighbour lighter: the exclusion only fires at six."""
    rows = ("##.", "##.", ".##")
    assert (1, 1) in found("branch", *rows)
