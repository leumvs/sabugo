"""The agreement statistics the validation reports."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))

from metrics import agreement, table  # noqa: E402


def test_a_perfect_tool_scores_perfectly():
    got = agreement([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert (got["r2"], got["rmse"], got["mbe"]) == (1.0, 0.0, 0.0)


def test_bias_shows_up_in_mbe_and_rmse():
    got = agreement([2.0, 3.0, 4.0], [1.0, 2.0, 3.0])
    assert got["mbe"] == pytest.approx(1.0)
    assert got["rmse"] == pytest.approx(1.0)
    assert got["r2"] < 1.0


def test_scatter_without_bias_leaves_mbe_at_zero():
    """RMSE and MBE answer different questions, and both are reported."""
    got = agreement([2.0, 1.0, 4.0, 3.0], [1.0, 2.0, 3.0, 4.0])
    assert got["mbe"] == pytest.approx(0.0)
    assert got["rmse"] == pytest.approx(1.0)


def test_r2_is_against_the_one_to_one_line():
    """A tool reading double correlates perfectly and is still wrong."""
    truth = [1.0, 2.0, 3.0, 4.0]
    assert agreement([2 * t for t in truth], truth)["r2"] < 0


def test_a_flat_truth_has_no_variance_to_explain():
    assert math.isnan(agreement([1.0, 2.0], [3.0, 3.0])["r2"])


@pytest.mark.parametrize(
    ("measured", "truth"), [([], []), ([1.0], [1.0, 2.0])]
)
def test_mismatched_input_is_refused(measured, truth):
    with pytest.raises(ValueError):
        agreement(measured, truth)


def test_table_prints_one_line_per_metric():
    printed = table({"total_root_length": agreement([1.0, 2.0], [1.0, 2.0])})
    assert "total_root_length" in printed
    assert len(printed.splitlines()) == 2
