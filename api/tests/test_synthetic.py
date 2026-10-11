"""The synthetic fixtures whose truth is exact by construction.

These run live rather than reading `results/synthetic.csv`: the point is to
guard the pipeline, and a test that reads a recorded number stays green
through a broken pipeline until someone re-runs the script. The recorded CSV
is what the README table is checked against, which is a different contract.

No download, so unlike the other two validation scripts this runs in CI.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))

import synthetic  # noqa: E402


def straight(radius, length=400.0, angle=0.0, pruning=True):
    curve = synthetic.line(length, angle)
    return synthetic.measure(synthetic.render(curve, radius), pruning), curve


def test_the_renderer_draws_the_shape_it_claims():
    """Area of a capsule is the rectangle plus the two half-discs. If this is
    wrong every truth below is wrong with it."""
    for radius in (3.5, 15.0):
        got, curve = straight(radius)
        expected = 2 * radius * curve.length + math.pi * radius**2
        assert got["network_area"] == pytest.approx(expected, rel=0.01)


def test_the_medial_axis_is_the_curve():
    """Two tips, no branch point: what the construction guarantees, and what
    makes the arc length the true root length."""
    for radius in synthetic.RADII:
        got, _ = straight(radius)
        assert got["num_root_tips"] == 2
        assert got["num_branch_points"] == 0


def shaft_diameter_error(radius):
    """The diameter error with the two ends extrapolated away, `1/L -> 0`."""
    rows = [
        synthetic.case("line", synthetic.line(length), radius, True)
        for length in synthetic.LENGTHS
    ]
    _, intercept = np.polyfit(
        [1.0 / row["length"] for row in rows],
        [row["average_diameter_error"] for row in rows],
        1,
    )
    return float(intercept)


def test_the_shaft_diameter_error_is_a_step_not_a_width_trend():
    """With the ends extrapolated away, the shaft error stays in [0, 1.5] px
    at every width from 1.5 to 60 and is never negative: a rounding step, not
    a trend against width.
    """
    errors = [shaft_diameter_error(radius) for radius in synthetic.RADII]
    assert min(errors) > -0.25
    assert max(errors) < 1.6


def test_the_shaft_diameter_is_the_pixel_width_rounded_up_to_even():
    """Which is what makes the step a step: the distance transform counts
    whole pixels out from the axis, so a band 15 px wide reports 16 and one 30
    px wide reports 30. The error is that rounding, not a bias — it is bounded
    by one pixel and it has no sign preference across widths."""
    for radius in (1.5, 3.5, 7.5, 15.0):
        image = synthetic.render(synthetic.line(800.0), radius)
        rows = int(np.count_nonzero((image == 0).any(axis=1)))
        got = synthetic.measure(image, pruning=True)
        assert got["average_diameter"] == pytest.approx(
            2 * math.ceil(rows / 2), abs=0.1
        )


def test_the_ends_pull_the_mean_diameter_down():
    """`average_diameter` is a mean over every skeleton pixel and the ones near
    the two ends carry a smaller radius than the shaft, so a short thick shape
    reads narrow and a long one reads true. That is a dilution, not a bias, and
    a constant radius correction cannot represent it.
    """
    radius = 30.0
    short, long = (
        synthetic.case("line", synthetic.line(length), radius, True)[
            "average_diameter_error"
        ]
        for length in (200.0, 800.0)
    )
    assert short < long - 1.0


def test_the_end_term_does_not_scale_with_length():
    """Length error at 800 px equals length error at 200 px, so whatever
    happens at the two ends is a constant and not a percentage. This is the
    split the copper wires could not make, their truth being +-6%."""
    for radius in (1.5, 3.5, 15.0):
        short, long = (
            straight(radius, length)[0]["total_root_length"] - length
            for length in (200.0, 800.0)
        )
        assert short == pytest.approx(long, abs=2.0)


def test_skeletonization_does_not_shorten_the_ends():
    """On a shape whose true length is known, the end term is never negative
    at any width: the ends are not where length goes missing.
    """
    for radius in synthetic.RADII:
        rows = [
            synthetic.case("line", synthetic.line(length), radius, True)
            for length in synthetic.LENGTHS
        ]
        end_term, _ = synthetic._split(rows)
        assert end_term > -2.0


@pytest.mark.parametrize("angle", [0.0, 15.0, 22.5, 30.0, 45.0])
def test_the_reported_length_holds_at_every_angle(angle):
    """A digital line off the axes is a staircase, and walking every step of it
    is what the chain code did — up to +8.4%, peaking near 22.5°. Simplifying
    first is what makes the error an angle-independent fraction of a
    percent, and that is the whole reason the length method changed.

    The bound is 2% and not tighter because what is left at 0°, where there is
    no staircase at all, is the end term of the shape's two caps — the chain
    code carries it too, and simplifying was never going to remove it.
    """
    got, curve = straight(3.5, angle=angle)
    error = (got["total_root_length"] - curve.length) / curve.length
    assert abs(error) < 0.02


def test_the_chain_code_is_what_had_the_surplus():
    got, curve = straight(3.5, angle=22.5)
    chain_code = (got["chain_code_length"] - curve.length) / curve.length
    reported = (got["total_root_length"] - curve.length) / curve.length
    assert chain_code > 0.05
    assert abs(reported) < 0.2 * chain_code


def fan(alphas, length=300.0, radius=3.5):
    curve = synthetic.crown(alphas, length)
    seg, _, _, segments = synthetic._pipeline(synthetic.render(curve, radius), True)
    got = synthetic.whole_root_metrics(seg.mask, seg.dt, segments, seg.mm_per_px)
    return got, synthetic.crown_truth(alphas, length, radius)


@pytest.mark.parametrize("alphas", synthetic.CROWNS)
def test_the_angle_is_measured_from_the_horizontal(alphas):
    """On a fan of known angles the two conventions are `theta` and
    `90 - theta`, and only one can be within a degree of six roots at once."""
    got, truth = fan(alphas)
    expected = truth["average_root_orientation"]
    assert got["average_root_orientation"] == pytest.approx(expected, abs=2.0)
    if abs(expected - 45.0) > 5.0:  # a fan centred on 45 reads the same either way
        assert abs(got["average_root_orientation"] - (90.0 - expected)) > 5.0


@pytest.mark.parametrize("alphas", synthetic.CROWNS)
def test_the_bounding_box_of_a_fan_is_its_geometry(alphas):
    got, truth = fan(alphas)
    assert got["depth"] == pytest.approx(truth["depth"], abs=1.0)
    assert got["max_width"] == pytest.approx(truth["max_width"], abs=1.0)
    # A fan encloses nothing, but two roots leaving at a narrow angle pinch off
    # a pocket a few pixels across where they separate. Those are in the mask,
    # so the detector is right to find them; what it must not do is invent one
    # the size of the wedge between two roots.
    assert got["average_hole_size"] < 10.0


@pytest.mark.parametrize("alphas", synthetic.CROWNS)
def test_the_angle_frequencies_are_fractions_of_length(alphas):
    """Each angle carries the step it opens, so a fan of equal roots splits
    into equal shares.

    Counting pixels instead is a real bias and this fixture found it: a
    digital line of euclidean length L holds `L*max(|cos|, |sin|)` of them, so
    the 15/45/75 fan of three equal thirds reported 0.37 / 0.27 / 0.36. The
    weighting is what removes it, and this test is what would notice it coming
    back.
    """
    got, truth = fan(alphas)
    for name in ("shallow", "medium", "steep"):
        # the hub is the slack: where six roots meet, the +-20 px chord spans
        # two of them and the angle it reports belongs to neither
        assert got[f"{name}_angle_frequency"] == pytest.approx(
            truth[f"{name}_angle_frequency"], abs=0.05
        )


def test_pixel_counting_would_have_biased_the_middle_fan():
    """The counter-check, so the mechanism above is documented and not folk
    knowledge: recomputed unweighted, the equal thirds come apart again."""
    alphas = (15.0, 45.0, 75.0)
    curve = synthetic.crown(alphas, 300.0)
    seg, _, _, segments = synthetic._pipeline(synthetic.render(curve, 3.5), True)
    angles, _ = synthetic.orientations(segments)

    unweighted = float((angles > 30.0).mean() - (angles > 60.0).mean())
    assert unweighted < 0.30  # the middle bin, which owes a third of the length


def test_the_mean_diameter_is_weighted_by_length_and_not_by_pixels():
    """The same defect the fan found in the angle frequencies, in the other
    average. Two roots of equal true length, one horizontal and 20 px wide, one
    at 45 degrees and 8 px: the truth is 14, and counting pixels reads 15.0
    because the diagonal one carries 29% fewer of them.
    """
    length, thick, thin = 300.0, 10.0, 4.0
    flat = synthetic.render(synthetic.line(length, 0.0), thick)
    angled = synthetic.render(synthetic.line(length, 45.0), thin)

    height = max(flat.shape[0], angled.shape[0]) + 40
    canvas = np.full((height, flat.shape[1] + angled.shape[1] + 40), 255, np.uint8)
    canvas[20 : 20 + flat.shape[0], 20 : 20 + flat.shape[1]] = flat
    offset = flat.shape[1] + 40
    canvas[20 : 20 + angled.shape[0], offset : offset + angled.shape[1]] = angled

    got = synthetic.measure(canvas, pruning=True)
    assert got["average_diameter"] == pytest.approx(thick + thin, abs=0.5)
    # what counting pixels would have returned, so the mechanism is on record
    assert got["average_diameter"] < 14.6


def crossing(radius, angle, length=400.0):
    curve = synthetic.cross(length, angle)
    return synthetic.measure(synthetic.render(curve, radius), True), curve


def test_two_crossing_roots_read_long_in_volume():
    """The defect the simulated roots pin at +0.78 against their `overlap`
    column, on a shape whose truth is exact instead. The two capsules merge
    into one blob, the distance transform reports the blob's radius there, and
    the volume is over at every crossing angle."""
    for angle in (15.0, 45.0, 90.0):
        got, curve = crossing(3.5, angle)
        truth = math.pi * 3.5**2 * curve.length - synthetic.steinmetz(3.5, angle)
        assert got["volume"] > truth


def test_a_shallow_crossing_is_where_length_goes_missing():
    """And the same geometry costs length, but only while the two roots run
    close to parallel: past 45 degrees the skeleton crosses in one pixel and
    there is nothing left to lose."""
    shallow, curve = crossing(3.5, 15.0)
    square, _ = crossing(3.5, 90.0)
    assert shallow["total_root_length"] < 0.98 * curve.length
    assert square["total_root_length"] > 0.98 * curve.length


def test_the_two_capsules_are_one_shape_with_two_branch_points():
    """Guards the fixture, not the pipeline: a crossing that renders as two
    separate shapes would measure the truth perfectly and prove nothing."""
    got, _ = crossing(3.5, 45.0)
    assert got["num_branch_points"] >= 2


@pytest.mark.parametrize("angle", [15.0, 22.5, 30.0])
def test_the_simplification_epsilon_earns_its_value(angle):
    """The same skeleton, only the epsilon varying: simplifying has to beat
    not simplifying."""
    curve = synthetic.line(400.0, angle)
    segments, mm_per_px = synthetic._skeleton_of(synthetic.render(curve, 3.5))
    error = lambda eps: abs(  # noqa: E731
        mm_per_px * sum(synthetic.simplified_length(p, eps) for p in segments)
        - curve.length
    )
    assert error(synthetic.SIMPLIFY_EPSILON) < 0.25 * error(0.0)


def test_an_arc_over_a_half_turn_is_refused():
    """It closes into a ring: the tips go to zero and the medial axis stops
    being the curve."""
    synthetic.arc(100.0, 50.0)
    with pytest.raises(ValueError, match="arc span"):
        synthetic.arc(400.0, 50.0)


def test_a_curve_keeps_its_own_arc_length():
    """Curvature must not cost the truth: the arc's length is analytic, and
    the measured length stays inside the straight-line surplus."""
    curve = synthetic.arc(200.0, 100.0)
    got = synthetic.measure(synthetic.render(curve, 1.5), pruning=True)
    assert got["num_root_tips"] == 2
    assert got["total_root_length"] == pytest.approx(curve.length, rel=0.10)


def test_the_two_terms_come_out_of_the_fit_separately():
    """`length_error = alpha + beta*L` over three lengths, which is what turns
    the sweep into a model instead of a table."""
    rows = [
        synthetic.case("line", synthetic.line(length), 3.5, True)
        for length in synthetic.LENGTHS
    ]
    alpha, beta = synthetic._split(rows)
    assert beta == pytest.approx(0.0, abs=0.005)
    # with no length-proportional term, alpha is the whole error at every length
    for row in rows:
        assert row["total_root_length_error"] == pytest.approx(alpha, abs=0.5)


def test_the_distance_field_is_analytic_not_sampled():
    """A sampled polyline would put its own discretization inside the thing
    being measured. Distances have to be exact at sub-pixel offsets."""
    curve = synthetic.line(10.0)
    x = np.array([5.0, 5.0, -3.0])
    y = np.array([0.25, 2.0, 4.0])
    assert curve.distance(x, y) == pytest.approx([0.25, 2.0, 5.0])
