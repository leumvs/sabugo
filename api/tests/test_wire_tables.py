"""The copper-wire readers, against the tables the paper distributes.

Three of the four columns are read out of files, not computed, and a misread
column is the failure mode that does not announce itself — it produces a
plausible number for the wrong quantity. These lock the readings that the
paper's own R script defines: the `LMY` (measured) ground truth rather than the
nominal one beside it, WinRhizo's three unit conversions, and the twelve-wire
scan the script excludes.

Skipped when `validation/data/` is absent, which is most of the time: the
archive is not in version control. The result CSV that comes out of it is.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))

import wires  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (wires.COMPETITORS / "rveOutputsandGroundTruth.csv").exists(),
    reason="copper wire tables not downloaded; see api/README.md",
)


def test_the_four_tools_cover_the_same_scans():
    truth = wires.truth_rows()
    assert len(truth) == 27  # 28 scans at 600 DPI, less the excluded one
    assert wires.EXCLUDED.removesuffix(".tif") not in truth

    for threshold in wires.THRESHOLDS:
        for rows in (wires.rve_rows(threshold), wires.winrhizo_rows(threshold)):
            assert set(rows) >= set(truth)
    assert set(wires.ij_rows()) >= set(truth)


def test_the_ground_truth_is_the_measured_column_not_the_nominal_one():
    """`TotalLengthLMY` and `TotalLength` differ by up to 28%, and the script
    uses the first. Reading the other would move every RMSE in the table."""
    truth = wires.truth_rows()
    thinnest = truth["G_40_W1_600_dpi"]
    assert thinnest["average_diameter"] == pytest.approx(0.07)
    assert thinnest["total_root_length"] == pytest.approx(309.3)


def test_winrhizo_arrives_in_millimetres():
    """It reports cm, cm2 and cm3; the three factors are the script's own.

    Guarded by an identity rather than a constant: a wire is a cylinder, so its
    surface has to be pi x d x l in whatever units the row is finally in. A
    missed conversion puts the two sides a factor of 100 apart.
    """
    import math

    rows = wires.winrhizo_rows(191)
    for name in ("G_10_W1_600_dpi", "G_22_W1_600_dpi", "G_40_W1_600_dpi"):
        row = rows[name]
        implied = math.pi * row["average_diameter"] * row["total_root_length"]
        assert implied == pytest.approx(row["surface_area"], rel=0.10), name


def test_the_wire_lengths_cannot_settle_end_shortening():
    """A negative result, held down so nobody spends a day rediscovering it.

    The per-scan length error has a 6% spread and all four tools carry the
    *same* one — Sabugo and RVE correlate at 0.9998 and differ by 0.12%. When
    every tool disagrees with the truth identically, the scatter is in the
    truth: these lengths were measured with string and a meter stick, which is
    what `copper_wire_ground_truth_method.txt` says. The diameters came off a
    micrometer, and that is the axis this set can actually resolve.
    """
    import statistics

    truth = wires.truth_rows()
    names = sorted(truth)
    ours = wires.rve_rows(191)  # RVE stands in for any tool here; see below
    winrhizo = wires.winrhizo_rows(191)

    def error(rows):
        return [
            (rows[n]["total_root_length"] - truth[n]["total_root_length"])
            / truth[n]["total_root_length"]
            for n in names
        ]

    a, b = error(ours), error(winrhizo)
    assert statistics.pstdev(a) > 0.04  # the spread that swamps a 6% effect
    covariance = statistics.correlation(a, b)
    assert covariance > 0.9  # two independent tools, one shared disagreement


def test_the_threshold_fattens_the_wire_in_every_tool():
    """The wires are the one set where the paper varies the threshold itself,
    and it moves the diameter the way the threshold sweep shows: a looser threshold
    takes more of the anti-aliased edge, so every tool reads the wire thicker.
    """
    truth = wires.truth_rows()
    for reader in (wires.rve_rows, wires.winrhizo_rows):
        tight = reader(191)
        loose = reader(222)
        for name in truth:
            assert loose[name]["average_diameter"] >= tight[name]["average_diameter"], name
