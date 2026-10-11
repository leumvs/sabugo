"""Sabugo against shapes whose truth is exact by construction.

Stamp a disc of radius `r` along a curve `C`. The shape is every point within
`r` of `C`, and while `r` stays below the curve's radius of curvature the
medial axis of that shape **is** `C`. So the truth is not measured:

    total root length = arc length of C        average diameter = 2r
    surface area = 2*pi*r*len(C)               volume = pi*r^2*len(C)

Calibration is fixed at 25.4 DPI, so one pixel is one millimetre and every
number below is already in pixels.

    python validation/synthetic.py

Needs no download, unlike `compare.py` and `wires.py`.
"""

from __future__ import annotations

import csv
import math
import pathlib
import sys
from dataclasses import dataclass
from typing import Callable

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from imaging import Params, segment  # noqa: E402
from imaging.aggregate import aggregate  # noqa: E402
from imaging.pruning import prune  # noqa: E402
from imaging.segments import (  # noqa: E402
    SIMPLIFY_EPSILON,
    extract,
    simplified_length,
    stepwise_length,
)
from imaging.skeleton import skeletonize  # noqa: E402
from imaging.topology import classify  # noqa: E402
from imaging.wholeroot import measure as whole_root_metrics  # noqa: E402
from imaging.wholeroot import orientations  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"

DPI_1PX_PER_MM = 25.4
MARGIN_PX = 8
PRUNE_THRESHOLD_PX = 5  # the published copper wire setting

# The curve is nudged off the pixel lattice: without it a pixel centre lands
# exactly at distance `r` from the axis and a floating-point tie decides
# whether the band is 2r or 2r+1 wide.
SUBPIXEL_NUDGE = 0.137

RADII = (0.75, 1.5, 2.25, 3.5, 7.5, 15.0, 30.0)
LENGTHS = (200.0, 400.0, 800.0)
ANGLES = (0.0, 15.0, 22.5, 30.0, 45.0)
# (curvature radius, arc length), holding the angular span at 2 rad so the
# shape never doubles back on itself. Sweeping curvature at a fixed length
# closes the arc into a ring, where the medial axis stops being the curve.
ARCS = ((50.0, 100.0), (100.0, 200.0), (200.0, 400.0))
# One radius per regime for the axes that sweep something else.
SAMPLE_RADII = (1.5, 3.5, 15.0)


@dataclass(frozen=True)
class Curve:
    """A curve that knows its own exact length and its distance field.

    `distance` is analytic rather than sampled: a sampled polyline would put
    its own discretization error inside the thing being measured.
    """

    length: float
    outline: np.ndarray  # (x, y) samples, for the bounding box and nothing else
    distance: Callable[[np.ndarray, np.ndarray], np.ndarray]


def line(length: float, angle_deg: float = 0.0) -> Curve:
    """A straight segment of exactly `length`, at `angle_deg` from horizontal."""
    dx = math.cos(math.radians(angle_deg))
    dy = math.sin(math.radians(angle_deg))
    end = np.array([length * dx, length * dy])

    def distance(x, y):
        t = np.clip(x * dx + y * dy, 0.0, length)
        return np.hypot(x - t * dx, y - t * dy)

    return Curve(length, np.array([[0.0, 0.0], end]), distance)


def arc(length: float, radius: float) -> Curve:
    """A circular arc of exactly `length`, curving with the given radius.

    Centred on the origin and opening downwards, so the sampled outline is
    what sizes the canvas.
    """
    span = length / radius
    if span > math.pi:
        # past a half turn the two ends approach each other, they merge once
        # they are within 2r, and the medial axis is no longer the curve
        raise ValueError("arc span over pi: the truth stops being the arc length")
    centre = np.array([0.0, radius])

    def distance(x, y):
        px, py = x - centre[0], y - centre[1]
        radial = np.hypot(px, py)
        # atan2 measured from straight up, which is where the arc is centred
        theta = np.arctan2(px, -py)
        inside = np.abs(theta) <= span / 2
        ends = np.stack(
            [
                np.hypot(x - radius * math.sin(s * span / 2),
                         y - radius * (1 - math.cos(s * span / 2)))
                for s in (-1.0, 1.0)
            ]
        ).min(axis=0)
        return np.where(inside, np.abs(radial - radius), ends)

    steps = np.linspace(-span / 2, span / 2, 256)
    outline = np.stack([radius * np.sin(steps), radius * (1 - np.cos(steps))], axis=1)
    return Curve(length, outline, distance)


def cross(length: float, angle_deg: float) -> Curve:
    """Two straight segments of `length` each, crossing at `angle_deg`.

    The union of the two capsules is the shape, and its medial axis is **not**
    both segments: near the crossing they merge into one blob, which is the
    whole point. The exact truth is what two separate roots would measure, so
    the length is the sum of the two.
    """
    if not 0.0 < angle_deg <= 90.0:
        raise ValueError("crossing angle must be in (0, 90]")
    half = length / 2.0
    axes = [
        (math.cos(math.radians(a)), math.sin(math.radians(a)))
        for a in (-angle_deg / 2.0, angle_deg / 2.0)
    ]

    def distance(x, y):
        return np.stack(
            [
                np.hypot(x - np.clip(x * dx + y * dy, -half, half) * dx,
                         y - np.clip(x * dx + y * dy, -half, half) * dy)
                for dx, dy in axes
            ]
        ).min(axis=0)

    outline = np.array([[s * half * dx, s * half * dy]
                        for dx, dy in axes for s in (-1.0, 1.0)])
    return Curve(2.0 * length, outline, distance)


def crown(alphas: tuple[float, ...], length: float) -> Curve:
    """A fan of `2*len(alphas)` roots leaving one point, opening downwards.

    Each angle contributes a root to the left and one to the right, so the
    shape is symmetric and every whole-root truth closes in one line:

        total length = 2*n*length          orientation = mean(alphas)
        depth  = length*sin(max) + 2r      width = 2*(length*cos(min) + r)

    The angle is what this exists for. It is measured from the horizontal and
    the published paper says otherwise, so the convention had been carried by
    one reported mean and by unit shapes; here the answer is constructed.
    """
    if not all(0.0 < a <= 90.0 for a in alphas):
        raise ValueError("angles from the horizontal must be in (0, 90]")
    axes = [
        (side * math.cos(math.radians(a)), math.sin(math.radians(a)))
        for a in alphas
        for side in (-1.0, 1.0)
    ]

    def distance(x, y):
        return np.stack(
            [
                np.hypot(x - np.clip(x * dx + y * dy, 0.0, length) * dx,
                         y - np.clip(x * dx + y * dy, 0.0, length) * dy)
                for dx, dy in axes
            ]
        ).min(axis=0)

    outline = np.array([[0.0, 0.0], *[[length * dx, length * dy] for dx, dy in axes]])
    return Curve(len(axes) * length, outline, distance)


def crown_truth(alphas: tuple[float, ...], length: float, radius: float) -> dict:
    """The whole-root truths of a fan, none of them measured."""
    bins = [0, 0, 0]
    for a in alphas:
        bins[0 if a <= 30.0 else 1 if a <= 60.0 else 2] += 2
    total = 2 * len(alphas)
    return {
        "average_root_orientation": float(np.mean(alphas)),
        "shallow_angle_frequency": bins[0] / total,
        "medium_angle_frequency": bins[1] / total,
        "steep_angle_frequency": bins[2] / total,
        "depth": length * math.sin(math.radians(max(alphas))) + 2.0 * radius,
        "max_width": 2.0 * (length * math.cos(math.radians(min(alphas))) + radius),
    }


def steinmetz(radius: float, angle_deg: float) -> float:
    """Volume shared by two cylinders of equal radius crossing at an angle.

    `16r³/(3·sin θ)`. Two roots that cross occupy this twice over if each is
    integrated on its own, so the exact volume of the pair is the sum of the
    two cylinders minus one of these.
    """
    return 16.0 * radius**3 / (3.0 * math.sin(math.radians(angle_deg)))


def render(curve: Curve, radius: float) -> np.ndarray:
    """The digitization of `{p : dist(p, curve) <= radius}`: a pixel is root
    when its **centre** lies inside the shape. That is the standard reading,
    and it is what makes the continuous shape the ground truth rather than a
    description of the bitmap."""
    pad = radius + MARGIN_PX
    low = curve.outline.min(axis=0) - pad + SUBPIXEL_NUDGE
    high = curve.outline.max(axis=0) + pad
    width = int(math.ceil(high[0] - low[0]))
    height = int(math.ceil(high[1] - low[1]))

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float64)
    inside = curve.distance(xx + low[0], yy + low[1]) <= radius
    return np.where(inside, 0, 255).astype(np.uint8)


def truth_of(curve: Curve, radius: float) -> dict[str, float]:
    return {
        "total_root_length": curve.length,
        "average_diameter": 2.0 * radius,
        "surface_area": 2.0 * math.pi * radius * curve.length,
        "volume": math.pi * radius * radius * curve.length,
    }


def _pipeline(image: np.ndarray, pruning: bool):
    params = Params(
        enable_root_pruning=pruning, root_pruning_threshold=PRUNE_THRESHOLD_PX
    )
    seg = segment(image, DPI_1PX_PER_MM, params)
    skeleton = skeletonize(seg.mask, seg.dt)
    if pruning:
        skeleton = prune(skeleton, seg.dt, PRUNE_THRESHOLD_PX)
    found = classify(skeleton)
    return seg, skeleton, found, extract(skeleton, found["tip"] | found["branch"])


def _skeleton_of(image: np.ndarray, pruning: bool = True):
    """Just the polylines and the scale, for sweeps that vary what comes after."""
    seg, _, _, segments = _pipeline(image, pruning)
    return segments, seg.mm_per_px


def measure(image: np.ndarray, pruning: bool = False) -> dict[str, float]:
    """The whole pipeline over one rendered shape, at 1 px per mm."""
    seg, skeleton, found, segments = _pipeline(image, pruning)

    values = {"num_segments": float(len(segments))}
    values |= aggregate(
        seg.dt, segments, seg.mm_per_px, Params().diameter_ranges_mm
    )
    # what `total_root_length` was before the simplification, kept so the angle
    # table can show the surplus the change removed
    values["chain_code_length"] = (
        sum(map(stepwise_length, segments)) * seg.mm_per_px
    )
    values["network_area"] = float(np.count_nonzero(seg.mask))
    values["num_root_tips"] = float(found["tip"].sum())
    values["num_branch_points"] = float(found["branch"].sum())
    return values


METRICS = ("total_root_length", "average_diameter", "surface_area", "volume")

FIELDS = [
    "shape", "radius", "length", "angle", "curvature", "pruned",
    "num_root_tips", "num_branch_points", "network_area",
    "chain_code_length", "chain_code_length_error",
    *(f"{name}_{kind}" for name in METRICS for kind in ("true", "measured", "error")),
]


def case(shape: str, curve: Curve, radius: float, pruning: bool, **axes) -> dict:
    truth = truth_of(curve, radius)
    got = measure(render(curve, radius), pruning)
    row = {
        "shape": shape,
        "radius": radius,
        "length": curve.length,
        "angle": axes.get("angle", 0.0),
        "curvature": axes.get("curvature", ""),
        "pruned": int(pruning),
        "num_root_tips": got["num_root_tips"],
        "num_branch_points": got["num_branch_points"],
        "network_area": got["network_area"],
        "chain_code_length": got["chain_code_length"],
        "chain_code_length_error": got["chain_code_length"] - curve.length,
    }
    for name in METRICS:
        row[f"{name}_true"] = truth[name]
        row[f"{name}_measured"] = got[name]
        row[f"{name}_error"] = got[name] - truth[name]
    return row


def sweep() -> list[dict]:
    rows = []
    for pruning in (False, True):
        for radius in RADII:
            for length in LENGTHS:
                rows.append(case("line", line(length), radius, pruning))
        for radius in SAMPLE_RADII:
            for angle in ANGLES[1:]:  # angle 0 is the full sweep above
                for length in LENGTHS:
                    rows.append(
                        case("line", line(length, angle), radius, pruning, angle=angle)
                    )
            for curvature, length in ARCS:
                # the medial axis stops being the curve once the disc reaches
                # the centre of curvature, so keep well clear of it
                if curvature <= 3 * radius:
                    continue
                rows.append(
                    case(
                        "arc", arc(length, curvature), radius, pruning,
                        curvature=curvature,
                    )
                )
        print(f"  pruned={int(pruning)}: {len(rows)} cases so far")
    return rows


def _pick(rows, **conditions) -> list[dict]:
    return [
        row for row in rows
        if all(row[key] == value for key, value in conditions.items())
    ]


def _split(cases: list[dict], column: str = "total_root_length_error") -> tuple[float, float]:
    """`length_error = alpha + beta*L`, fitted over the three lengths.

    `alpha` is what happens at the two ends and does not scale; `beta` is the
    per-pixel digitization surplus, which does. One line separates the two
    terms the copper wires could not tell apart.
    """
    ordered = sorted(cases, key=lambda row: row["length"])
    beta, alpha = np.polyfit(
        [row["length"] for row in ordered], [row[column] for row in ordered], 1
    )
    return float(alpha), float(beta)


def fit(rows: list[dict]) -> list[dict]:
    """The radius axis: one row per width, measured axis-aligned so the
    digitization surplus is zero and cannot contaminate it.

    `average_diameter` is a mean over every skeleton pixel, so the pixels near
    the two ends are in it, and they carry a smaller radius than the shaft. On
    a longer shape they are diluted, which makes the error a function of
    length as well as of width. Regressing it on `1/L` separates the two: the
    intercept is what the shaft alone reads, the slope is what the ends cost.
    Without that split the shaft bias and the end contamination are read as
    one width-dependent curve, which is exactly the misreading the copper wire
    table invited.
    """
    model = []
    for pruning in (False, True):
        for radius in RADII:
            straight = sorted(
                _pick(rows, shape="line", radius=radius, angle=0.0, pruned=int(pruning)),
                key=lambda row: row["length"],
            )
            alpha, beta = _split(straight)
            ends, shaft = np.polyfit(
                [1.0 / row["length"] for row in straight],
                [row["average_diameter_error"] for row in straight],
                1,
            )
            at_400 = next(
                row["average_diameter_error"]
                for row in straight
                if row["length"] == 400.0
            )
            model.append({
                "pruned": int(pruning),
                "radius": radius,
                "true_diameter": 2.0 * radius,
                "shaft_diameter_error": float(shaft),
                "diameter_error_at_400px": at_400,
                "end_dilution_px2": float(ends),
                "end_term_px": alpha,
                "digitization_per_100px": beta * 100.0,
                "tips": float(np.mean([row["num_root_tips"] for row in straight])),
            })
    return model


def fit_angles(rows: list[dict]) -> list[dict]:
    """The angle axis: the same split, per angle, pooled over the three radii.

    A digital straight line off the axes is a staircase, and the chain code of
    5.3a walks every step of it. The surplus is a percentage of the length,
    not a constant, which is what separates it from the end term.
    """
    model = []
    for pruning in (False, True):
        for angle in ANGLES:
            for radius in SAMPLE_RADII:
                cases = _pick(
                    rows, shape="line", radius=radius, angle=angle,
                    pruned=int(pruning),
                )
                alpha, beta = _split(cases)
                # what the same skeleton read before the simplification: the
                # chain code walks every step of the staircase, and the gap
                # between the two columns is what the change is worth
                _, chain_code = _split(cases, "chain_code_length_error")
                model.append({
                    "pruned": int(pruning),
                    "angle": angle,
                    "true_diameter": 2.0 * radius,
                    "end_term_px": alpha,
                    "reported_percent": beta * 100.0,
                    "chain_code_percent": chain_code * 100.0,
                })
    return model


def zero_crossing(model: list[dict], pruned: int) -> float | None:
    """Where the diameter error changes sign, by linear interpolation."""
    rows = [row for row in model if row["pruned"] == pruned]
    for below, above in zip(rows, rows[1:]):
        if below["shaft_diameter_error"] * above["shaft_diameter_error"] < 0:
            span = above["shaft_diameter_error"] - below["shaft_diameter_error"]
            weight = -below["shaft_diameter_error"] / span
            return below["true_diameter"] + weight * (
                above["true_diameter"] - below["true_diameter"]
            )
    return None


CROSSING_ANGLES = (15.0, 30.0, 45.0, 60.0, 90.0)
CROSSING_LENGTH = 400.0
CROSSING_FIELDS = [
    "angle", "radius", "true_length", "measured_length", "length_percent",
    "true_volume", "measured_volume", "volume_percent", "num_branch_points",
]


def crossing_sweep() -> list[dict]:
    """Two roots that cross, against the truth of two roots that do not.

    The one defect this project has named and never measured directly. Both
    signs come out of the same geometry: the two capsules merge into one blob,
    so the skeleton runs through it once instead of twice — length short — and
    the distance transform reports the blob's radius there — volume long.
    """
    rows = []
    for angle in CROSSING_ANGLES:
        for radius in SAMPLE_RADII:
            curve = cross(CROSSING_LENGTH, angle)
            got = measure(render(curve, radius), pruning=True)
            true_volume = math.pi * radius**2 * curve.length - steinmetz(radius, angle)
            rows.append({
                "angle": angle,
                "radius": radius,
                "true_length": curve.length,
                "measured_length": got["total_root_length"],
                "length_percent": 100.0 * (got["total_root_length"] / curve.length - 1.0),
                "true_volume": true_volume,
                "measured_volume": got["volume"],
                "volume_percent": 100.0 * (got["volume"] / true_volume - 1.0),
                "num_branch_points": got["num_branch_points"],
            })
        print(f"  crossing at {angle:g} degrees")
    return rows


def crossing_markdown(rows: list[dict]) -> str:
    """One row per crossing angle, pooled over the three widths."""
    lines = [
        "| Crossing angle | Length | Volume | Branch points |",
        "|---|---|---|---|",
    ]
    for angle in CROSSING_ANGLES:
        found = [row for row in rows if row["angle"] == angle]
        lines.append(
            f"| {angle:g}° | {np.mean([r['length_percent'] for r in found]):+.2f}% "
            f"| {np.mean([r['volume_percent'] for r in found]):+.2f}% "
            f"| {np.mean([r['num_branch_points'] for r in found]):.1f} |"
        )
    return "\n".join(lines)


CROWNS = ((10.0, 20.0, 25.0), (15.0, 45.0, 75.0), (70.0, 80.0, 85.0))
CROWN_LENGTH = 300.0
CROWN_RADIUS = 3.5
CROWN_FIELDS = [
    "fan", "metric", "true", "measured",
]


def crown_sweep() -> list[dict]:
    """The whole-root metrics, which neither ground-truth set covers.

    Three fans: one landing in a single bin, one spread over all three, one in
    the last, so a frequency right by accident has to be right three times.
    """
    rows = []
    for alphas in CROWNS:
        curve = crown(alphas, CROWN_LENGTH)
        seg, _, _, segments = _pipeline(render(curve, CROWN_RADIUS), pruning=True)
        got = whole_root_metrics(seg.mask, seg.dt, segments, seg.mm_per_px)
        truth = crown_truth(alphas, CROWN_LENGTH, CROWN_RADIUS)
        label = "/".join(f"{a:g}" for a in alphas)
        rows += [
            {"fan": label, "metric": name, "true": value, "measured": got[name]}
            for name, value in truth.items()
        ]
        print(f"  crown {label}")
    return rows


def crown_markdown(rows: list[dict]) -> str:
    """One row per fan, the angle convention and the bounding box side by side."""
    lines = [
        "| Fan, from the horizontal | Orientation | Shallow / medium / steep | "
        "Depth | Width |",
        "|---|---|---|---|---|",
    ]
    for label in dict.fromkeys(row["fan"] for row in rows):
        cell = {row["metric"]: row for row in rows if row["fan"] == label}
        freqs = [
            f"{cell[f'{name}_angle_frequency']['measured']:.2f}"
            for name in ("shallow", "medium", "steep")
        ]
        true_freqs = [
            f"{cell[f'{name}_angle_frequency']['true']:.2f}"
            for name in ("shallow", "medium", "steep")
        ]
        angle = cell["average_root_orientation"]
        lines.append(
            f"| {label}° | {angle['true']:.1f}° → {angle['measured']:.1f}° "
            f"| {'/'.join(true_freqs)} → {'/'.join(freqs)} "
            f"| {cell['depth']['measured'] - cell['depth']['true']:+.1f} px "
            f"| {cell['max_width']['measured'] - cell['max_width']['true']:+.1f} px |"
        )
    return "\n".join(lines)


EPSILONS = (0.0, 0.25, 0.5, 0.71, 1.0, 1.5, 2.0, 3.0)
# Tighter than ARCS on purpose. A simplification that flattens curvature only
# pays for it where there is curvature to lose, and the three arcs the rest of
# this file sweeps bend too gently to expose it: their radius runs 50 to 200 px.
EPSILON_ARCS = ((15.0, 45.0), (25.0, 75.0), *ARCS)
EPSILON_FIELDS = ["epsilon", "angle", "surplus_percent", "arc_percent"]


def epsilon_sweep() -> list[dict]:
    """The skeleton is extracted once per shape and only the simplification
    varies. The error is fitted over the three lengths and only the slope is
    kept: at a single length the two ends contribute several percent of their
    own, and the sweep would rank epsilons by how much end they cancel.
    """
    raw = []
    for angle in ANGLES:
        for radius in SAMPLE_RADII:
            for length in LENGTHS:
                curve = line(length, angle)
                segments, mm_per_px = _skeleton_of(render(curve, radius))
                for epsilon in EPSILONS:
                    measured = mm_per_px * sum(
                        simplified_length(path, epsilon) for path in segments
                    )
                    raw.append({
                        "epsilon": epsilon, "angle": angle, "radius": radius,
                        "length": length, "error": measured - curve.length,
                    })
        print(f"  epsilon sweep at {angle:g} degrees")

    # The counter-check, and the reason the smallest epsilon at the floor wins
    # rather than the largest: on an arc there is real curvature to lose, and
    # simplification that flattens it takes length with it. Not fitted over
    # length here — an arc varies its curvature too — but the end term is the
    # same for every epsilon, so the comparison between them still holds.
    arcs: dict[float, list[float]] = {epsilon: [] for epsilon in EPSILONS}
    for curvature, length in EPSILON_ARCS:
        for radius in SAMPLE_RADII:
            if curvature <= 3 * radius:
                continue
            curve = arc(length, curvature)
            segments, mm_per_px = _skeleton_of(render(curve, radius))
            for epsilon in EPSILONS:
                measured = mm_per_px * sum(
                    simplified_length(path, epsilon) for path in segments
                )
                arcs[epsilon].append(100.0 * (measured / curve.length - 1.0))
    print(f"  epsilon sweep over {len(ARCS)} arcs")

    rows = []
    for epsilon in EPSILONS:
        for angle in ANGLES:
            slopes = [
                _split(_pick(raw, epsilon=epsilon, angle=angle, radius=radius), "error")[1]
                for radius in SAMPLE_RADII
            ]
            rows.append({
                "epsilon": epsilon,
                "angle": angle,
                "surplus_percent": 100.0 * float(np.mean(slopes)),
                "arc_percent": float(np.mean(arcs[epsilon])),
            })
    return rows


def epsilon_markdown(rows: list[dict]) -> str:
    """Digitization surplus per epsilon, pooled over the angles it exists at."""
    lines = [
        "| Epsilon | Mean \\|surplus\\| on straight lines | Worst angle | On arcs |",
        "|---|---|---|---|",
    ]
    for epsilon in EPSILONS:
        found = [row for row in rows if row["epsilon"] == epsilon]
        mean = np.mean([abs(row["surplus_percent"]) for row in found])
        worst = max(found, key=lambda row: abs(row["surplus_percent"]))
        label = f"**{epsilon:g}**" if epsilon == SIMPLIFY_EPSILON else f"{epsilon:g}"
        lines.append(
            f"| {label} | {mean:.2f}% | {worst['angle']:g}° "
            f"({worst['surplus_percent']:+.2f}%) | {found[0]['arc_percent']:+.2f}% |"
        )
    return "\n".join(lines)


def markdown(model: list[dict], pruned: int = 1) -> str:
    """The README table: one row per width, the three terms side by side."""
    lines = [
        "| True diameter (px) | Shaft diameter error (px) | At 400 px long (px) | "
        "Length error at the ends (px) |",
        "|---|---|---|---|",
    ]
    for row in model:
        if row["pruned"] != pruned:
            continue
        lines.append(
            f"| {row['true_diameter']:g} | {row['shaft_diameter_error']:+.2f} | "
            f"{row['diameter_error_at_400px']:+.2f} | {row['end_term_px']:+.2f} |"
        )
    return "\n".join(lines)


def angle_markdown(angles: list[dict], pruned: int = 1) -> str:
    """The digitization surplus per angle, pooled over the three widths: what
    the pipeline reports, against the chain code it replaced on the same
    skeleton."""
    lines = [
        "| Angle | `total_root_length` | Chain code, replaced |",
        "|---|---|---|",
    ]
    for angle in ANGLES:
        found = [
            row for row in angles if row["pruned"] == pruned and row["angle"] == angle
        ]
        reported = np.mean([row["reported_percent"] for row in found])
        chain_code = np.mean([row["chain_code_percent"] for row in found])
        lines.append(f"| {angle:g}° | {reported:+.2f}% | {chain_code:+.2f}% |")
    return "\n".join(lines)


def main() -> int:
    # The tables carry degrees, arrows and squared units, and a Windows console
    # defaults to cp1252, which raises on the first one it cannot encode.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    RESULTS.mkdir(exist_ok=True)
    print("== sweeping")
    rows = sweep()

    out = RESULTS / "synthetic.csv"
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"written to {out.relative_to(HERE.parent)}")

    print("== crowns")
    crowns = crown_sweep()
    print("== crossings")
    crossings = crossing_sweep()
    print("== epsilon")
    epsilons = epsilon_sweep()

    model, angles = fit(rows), fit_angles(rows)
    for name, fitted in (
        ("synthetic-model", model),
        ("synthetic-angles", angles),
        ("synthetic-crossings", crossings),
        ("synthetic-epsilon", epsilons),
        ("synthetic-crowns", crowns),
    ):
        path = RESULTS / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fitted[0]))
            writer.writeheader()
            writer.writerows(fitted)
        print(f"written to {path.relative_to(HERE.parent)}")

    for pruned in (0, 1):
        crossing = zero_crossing(model, pruned)
        print()
        print(f"-- pruning {'on' if pruned else 'off'}")
        print(markdown(model, pruned))
        print(
            f"diameter error crosses zero at {crossing:.1f} px of width"
            if crossing
            else "diameter error keeps its sign over every swept width"
        )
        print()
        print("digitization surplus, as a share of true length:")
        print(angle_markdown(angles, pruned))

    print()
    print("whole root, against a fan whose geometry is exact:")
    print(crown_markdown(crowns))
    print()
    print("two roots crossing, against the truth of two that do not:")
    print(crossing_markdown(crossings))
    print()
    print("what the simplification epsilon is worth:")
    print(epsilon_markdown(epsilons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
