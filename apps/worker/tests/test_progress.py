"""The NDJSON progress stream the API turns into `progress` events."""

import json
from pathlib import Path

import cv2
import numpy as np

from sabugo_worker.cli import main
from sabugo_worker.progress import Progress

ANNOTATION = """#ROI Name, Class Name, X Position, Y Position, Width, Height
roi_1, root, 10, 10, 280, 80
roi_2, root, 10, 120, 280, 60
"""


def bar_image(path: Path) -> None:
    image = np.full((200, 300), 255, np.uint8)
    image[40:60, 20:280] = 0
    image[140:150, 20:280] = 0
    cv2.imwrite(str(path), image)


def run(tmp_path, capsys, *extra):
    image = tmp_path / "bar.png"
    bar_image(image)
    assert main([str(image), "--dpi", "300", "--progress", *extra]) == 0
    return [json.loads(line) for line in capsys.readouterr().err.splitlines()]


def test_nothing_is_written_unless_asked(tmp_path, capsys):
    image = tmp_path / "bar.png"
    bar_image(image)
    assert main([str(image), "--dpi", "300"]) == 0
    assert capsys.readouterr().err == ""


def test_every_line_is_json_with_a_stage_and_a_percent(tmp_path, capsys):
    events = run(tmp_path, capsys)
    assert events
    for event in events:
        assert event["stage"] in Progress.STAGES
        assert 0 < event["percent"] <= 100


def test_the_percent_never_goes_backwards(tmp_path, capsys):
    """Two regions run one after the other, and the second must not restart
    the bar — the client draws this number directly."""
    rois = tmp_path / "rois.csv"
    rois.write_text(ANNOTATION, encoding="utf-8")
    percents = [e["percent"] for e in run(tmp_path, capsys, "--roipath", str(rois))]

    assert percents == sorted(percents)
    assert percents[-1] >= 95.0


def test_each_region_names_itself(tmp_path, capsys):
    rois = tmp_path / "rois.csv"
    rois.write_text(ANNOTATION, encoding="utf-8")
    events = run(tmp_path, capsys, "--roipath", str(rois))

    named = {event["region"] for event in events}
    assert {"roi_1", "roi_2"} <= named


def test_pruning_only_reports_when_it_runs(tmp_path, capsys):
    assert "prune" not in {e["stage"] for e in run(tmp_path, capsys)}
    assert "prune" in {e["stage"] for e in run(tmp_path, capsys, "--prune")}


def test_the_report_on_stdout_stays_clean(tmp_path, capsys):
    """stdout is what the validation parses. A progress
    line landing there would be read as a metric."""
    image = tmp_path / "bar.png"
    bar_image(image)
    assert main([str(image), "--dpi", "300", "--progress"]) == 0

    captured = capsys.readouterr()
    assert "stage" not in captured.out
    assert "total_root_length" in captured.out
