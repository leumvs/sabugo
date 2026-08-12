"""The JSON the API republishes as the `completed` event."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from sabugo_worker import PIPELINE_VERSION, export
from sabugo_worker.cli import main
from sabugo_worker.jsonout import camel

ANNOTATION = """#ROI Name, Class Name, X Position, Y Position, Width, Height
roi_1, root, 10, 10, 280, 80
roi_2, root, 10, 120, 280, 60
"""


def bar_image(path: Path) -> None:
    image = np.full((200, 300), 255, np.uint8)
    image[40:60, 20:280] = 0
    image[140:150, 20:280] = 0
    cv2.imwrite(str(path), image)


def run(tmp_path, *extra):
    image = tmp_path / "bar.png"
    bar_image(image)
    out = tmp_path / "out.json"
    assert main([str(image), "--dpi", "300", "--json", str(out), *extra]) == 0
    return json.loads(out.read_text(encoding="utf-8"))


def test_camel_case_of_every_metric_name():
    assert camel("total_root_length") == "totalRootLength"
    assert camel("processing_time_ms") == "processingTimeMs"
    assert camel("width_to_depth_ratio") == "widthToDepthRatio"
    assert camel("volume") == "volume"


def test_the_document_carries_the_pipeline_version_once(tmp_path):
    document = run(tmp_path)
    assert document["pipelineVersion"] == PIPELINE_VERSION
    assert len(document["results"]) == 1


def test_the_whole_image_is_roi_index_minus_one(tmp_path):
    [entry] = run(tmp_path)["results"]
    assert entry["roiIndex"] == -1
    assert entry["roiName"] == "Full"


def test_every_metric_of_the_mode_is_present_in_camel_case(tmp_path):
    [entry] = run(tmp_path)["results"]
    assert set(entry["metrics"]) == {
        camel(key) for key in export.BROKEN_ROOT_COLUMNS
    }
    assert entry["thresholdValueUsed"] == 200
    assert entry["numSegments"] >= 1


def test_whole_root_drops_the_two_broken_root_metrics(tmp_path):
    [entry] = run(tmp_path, "--mode", "whole_root")["results"]
    assert set(entry["metrics"]) == {camel(key) for key in export.WHOLE_ROOT_COLUMNS}
    assert "numBranchPoints" not in entry["metrics"]
    assert "branchingFrequency" not in entry["metrics"]
    assert "solidity" in entry["metrics"]


def test_one_bin_per_diameter_class(tmp_path):
    [entry] = run(tmp_path, "--dranges", "0.5,1.0,2.0")["results"]
    assert set(entry["bins"]) == {"rootLength", "projectedArea", "surfaceArea", "volume"}
    for values in entry["bins"].values():
        assert len(values) == 4


def test_processing_time_stays_in_milliseconds(tmp_path):
    """The CSV column is seconds; the JSON is not, and the two are read
    by different consumers that would both look plausible if this flipped."""
    [entry] = run(tmp_path)["results"]
    assert entry["metrics"]["processingTimeMs"] > 1.0


def test_the_json_and_the_csv_describe_the_same_run(tmp_path):
    """Two renderings of one result. Nothing forces them to agree except this.

    `export.py` owns which metrics exist per mode and `jsonout.py` reads that
    same map, so a divergence here means one of them stopped reading it.
    """
    image = tmp_path / "bar.png"
    bar_image(image)
    out, table = tmp_path / "out.json", tmp_path / "features.csv"
    assert main([str(image), "--dpi", "300", "--json", str(out), "-o", str(table)]) == 0

    [entry] = json.loads(out.read_text(encoding="utf-8"))["results"]
    header, row = table.read_text(encoding="utf-8").splitlines()
    cells = dict(zip(header.split(","), row.split(",")))

    for key, column in export.BROKEN_ROOT_COLUMNS.items():
        value = entry["metrics"][camel(key)]
        if key == "processing_time_ms":
            value /= 1000.0  # the column is seconds
        assert float(cells[column]) == pytest.approx(value, abs=5e-7)


def test_the_picture_paths_are_reported_not_guessed(tmp_path):
    document = run(tmp_path, "--segment", "--feature", "--fsuffix", "_custom")
    [entry] = document["results"]
    assert Path(entry["segmentedImagePath"]).exists()
    assert Path(entry["skeletonImagePath"]).name.endswith("_custom.png")


def test_pictures_not_asked_for_are_null(tmp_path):
    [entry] = run(tmp_path)["results"]
    assert entry["segmentedImagePath"] is None
    assert entry["skeletonImagePath"] is None


def test_one_entry_per_roi_and_no_full_row(tmp_path):
    rois = tmp_path / "rois.csv"
    rois.write_text(ANNOTATION, encoding="utf-8")
    document = run(tmp_path, "--roipath", str(rois))

    assert [entry["roiIndex"] for entry in document["results"]] == [0, 1]
    assert [entry["roiName"] for entry in document["results"]] == ["roi_1", "roi_2"]
