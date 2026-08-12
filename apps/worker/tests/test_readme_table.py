"""The README table has to be the versioned results, not a transcription.

Typing numbers into prose is how a table starts lying: someone re-runs the
comparison, the CSV moves, and the README does not. This runs in CI because
the results CSV is in the repository even though the images behind it are not.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))

from metrics import markdown  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "apps" / "worker"
RESULTS = WORKER / "validation" / "results" / "simulated-agreement.csv"


WIRES = WORKER / "validation" / "results" / "wires-agreement.csv"


def rendered(**kwargs) -> str:
    with RESULTS.open(encoding="utf-8") as handle:
        return markdown(list(csv.DictReader(handle)), **kwargs)


def rendered_wires(heading: str = "Threshold", **kwargs) -> str:
    with WIRES.open(encoding="utf-8") as handle:
        return markdown(
            list(csv.DictReader(handle)), axis="threshold", heading=heading, **kwargs
        )


def test_the_readme_carries_the_generated_table():
    assert rendered() in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_readme_carries_the_generated_wire_table():
    assert rendered_wires() in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_worker_readme_carries_the_same_tables():
    readme = (WORKER / "README.md").read_text(encoding="utf-8")
    assert rendered() in readme
    assert rendered_wires() in readme


def test_the_table_covers_every_tool_metric_and_resolution():
    with RESULTS.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["tool"] for row in rows} == {"Sabugo", "RVE", "WinRhizo", "IJ_Rhizo"}
    assert {row["dpi"] for row in rows} == {"800", "1200"}
    assert len(rows) == 4 * 2 * 4  # tools x resolutions x metrics


def test_the_wire_table_covers_every_tool_metric_and_threshold():
    with WIRES.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["tool"] for row in rows} == {"Sabugo", "RVE", "WinRhizo", "IJ_Rhizo"}
    assert {row["threshold"] for row in rows} == {"191", "222"}
    assert {int(float(row["n"])) for row in rows} == {27}
    assert len(rows) == 4 * 2 * 4  # tools x thresholds x metrics


def test_the_markers_are_there_for_the_regeneration():
    for readme in (ROOT / "README.md", WORKER / "README.md"):
        text = readme.read_text(encoding="utf-8")
        for marker in ("validation", "wires"):
            assert text.count(f"<!-- {marker}:start") == 1
            assert text.count(f"<!-- {marker}:end -->") == 1

    worker = (WORKER / "README.md").read_text(encoding="utf-8")
    for marker in ("synthetic", "angles"):
        assert worker.count(f"<!-- {marker}:start") == 1
        assert worker.count(f"<!-- {marker}:end -->") == 1


def _typed(path, ints=(), floats=()):
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update({name: int(row[name]) for name in ints})
        row.update({name: float(row[name]) for name in floats})
    return rows


def test_the_worker_readme_carries_the_synthetic_tables():
    import synthetic  # noqa: PLC0415 — validation/ is on the path above

    readme = (WORKER / "README.md").read_text(encoding="utf-8")
    model = _typed(
        WORKER / "validation" / "results" / "synthetic-model.csv",
        ints=("pruned",),
        floats=(
            "true_diameter", "shaft_diameter_error",
            "diameter_error_at_400px", "end_term_px",
        ),
    )
    angles = _typed(
        WORKER / "validation" / "results" / "synthetic-angles.csv",
        ints=("pruned",),
        floats=("angle", "reported_percent", "chain_code_percent"),
    )
    crossings = _typed(
        WORKER / "validation" / "results" / "synthetic-crossings.csv",
        ints=(),
        floats=(
            "angle", "radius", "true_length", "measured_length", "length_percent",
            "true_volume", "measured_volume", "volume_percent", "num_branch_points",
        ),
    )
    epsilons = _typed(
        WORKER / "validation" / "results" / "synthetic-epsilon.csv",
        ints=(),
        floats=("epsilon", "angle", "surplus_percent", "arc_percent"),
    )
    assert synthetic.markdown(model) in readme
    assert synthetic.angle_markdown(angles) in readme
    crowns = _typed(
        WORKER / "validation" / "results" / "synthetic-crowns.csv",
        ints=(),
        floats=("true", "measured"),
    )
    assert synthetic.crossing_markdown(crossings) in readme
    assert synthetic.epsilon_markdown(epsilons) in readme
    assert synthetic.crown_markdown(crowns) in readme
