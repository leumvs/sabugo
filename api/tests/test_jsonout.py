import csv
import io

import pytest

from imaging import PIPELINE_VERSION, export
from imaging.jsonout import camel
from services.processing import analyse_upload


def test_camel_case_of_metric_names():
    assert camel("total_root_length") == "totalRootLength"
    assert camel("processing_time_ms") == "processingTimeMs"
    assert camel("width_to_depth_ratio") == "widthToDepthRatio"
    assert camel("volume") == "volume"


@pytest.mark.parametrize("mode", ["broken_roots", "whole_root"])
def test_json_and_csv_describe_the_same_run(job_factory, mode):
    document, table = analyse_upload(job_factory(params={"mode": mode}), 100)
    assert document["pipelineVersion"] == PIPELINE_VERSION
    [entry] = document["results"]
    assert entry["roiIndex"] == -1
    assert entry["roiName"] == "Full"
    assert entry["fileName"] == "bar.png"
    assert entry["thresholdValueUsed"] == 200
    assert entry["numSegments"] >= 1
    assert set(entry["metrics"]) == {camel(key) for key in export.globals_for(mode)}
    cells = next(csv.DictReader(io.StringIO(table)))
    for key, column in export.globals_for(mode).items():
        value = entry["metrics"][camel(key)]
        if key == "processing_time_ms":
            value /= 1000
        assert float(cells[column]) == pytest.approx(value, abs=5e-7)
    assert entry["segmentedImage"].startswith("data:image/png;base64,")
    assert entry["skeletonImage"].startswith("data:image/png;base64,")
    assert "segmentedImagePath" not in entry
    assert "skeletonImagePath" not in entry


def test_one_bin_per_diameter_class(job_factory):
    document, _ = analyse_upload(job_factory(params={"diameter_ranges_mm": [0.5, 1.0, 2.0]}), 100)
    bins = document["results"][0]["bins"]
    assert set(bins) == {"rootLength", "projectedArea", "surfaceArea", "volume"}
    assert all(len(values) == 4 for values in bins.values())


def test_display_options_change_pictures_without_changing_measurements(job_factory):
    plain, _ = analyse_upload(job_factory(), 100)
    for options in ({"show_medial_axis": False}, {"show_medial_axis_diameter": False},
                    {"medial_axis_width": 9}, {"show_contours": True},
                    {"show_convex_hull": True}, {"show_dist_map": True}):
        changed, _ = analyse_upload(job_factory(params=options), 100)
        first, second = plain["results"][0], changed["results"][0]
        assert first["skeletonImage"] != second["skeletonImage"]
        for key, value in first["metrics"].items():
            if key != "processingTimeMs":
                assert value == second["metrics"][key]
