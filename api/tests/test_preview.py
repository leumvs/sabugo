from imaging import analysis
from imaging import pipeline
from services.processing import analyse_upload


def test_preview_segments_without_measuring(job_factory, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("skeletonize ran during a preview")

    monkeypatch.setattr(analysis, "skeletonize", refuse)
    monkeypatch.setattr(pipeline, "_distance_transform", refuse)
    document, csv = analyse_upload(job_factory(preview=True), 100)
    [entry] = document["results"]
    assert entry["segmentedImage"].startswith("data:image/png;base64,")
    assert entry["thresholdValueUsed"] == 200
    assert entry["roiName"] == "Full"
    assert entry["skeletonImage"] is None
    assert "metrics" not in entry and "bins" not in entry
    assert csv == ""


def test_preview_has_one_result_per_roi(job_factory):
    rois = [{"name": name, "x": 0, "y": y, "width": 300, "height": 40}
            for name, y in (("top", 30), ("bottom", 130))]
    document, _ = analyse_upload(job_factory(preview=True, rois=rois), 100)
    assert [entry["roiName"] for entry in document["results"]] == ["top", "bottom"]
    assert [entry["roiIndex"] for entry in document["results"]] == [0, 1]
