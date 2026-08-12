"""`--preview`: the mask and nothing else — RVE's "Preview segmented image"."""

import json
from pathlib import Path

import cv2
import numpy as np

from sabugo_worker import analysis
from sabugo_worker.cli import main


def bar_image(path: Path) -> None:
    image = np.full((200, 300), 255, np.uint8)
    image[40:60, 20:280] = 0
    image[140:150, 20:280] = 0
    cv2.imwrite(str(path), image)


def run(tmp_path: Path, *extra: str) -> dict:
    bar_image(tmp_path / "bar.png")
    payload = tmp_path / "preview.json"
    assert main([str(tmp_path / "bar.png"), "--dpi", "254", "--preview", "--segment",
                 "--json", str(payload), *extra]) == 0
    return json.loads(payload.read_text(encoding="utf-8"))


def test_it_writes_the_mask_and_reports_the_threshold(tmp_path):
    entry = run(tmp_path)["results"][0]
    assert Path(entry["segmentedImagePath"]).name == "bar_seg.png"
    assert Path(entry["segmentedImagePath"]).exists()
    assert entry["thresholdValueUsed"] == 200
    assert entry["roiName"] == "Full"


def test_it_measures_nothing(tmp_path):
    entry = run(tmp_path)["results"][0]
    assert "metrics" not in entry
    assert "bins" not in entry
    assert entry["skeletonImagePath"] is None


def test_feature_is_ignored_and_no_csv_is_written(tmp_path):
    run(tmp_path, "--feature")
    assert not (tmp_path / "bar_feat.png").exists()
    assert list(tmp_path.glob("*.csv")) == []


def test_the_skeleton_is_never_built(tmp_path, monkeypatch):

    def refuse(*_args, **_kwargs):
        raise AssertionError("skeletonize ran during a preview")

    monkeypatch.setattr(analysis, "skeletonize", refuse)
    run(tmp_path)


def test_one_entry_per_roi(tmp_path):
    rois = tmp_path / "rois.csv"
    rois.write_text(
        "top, root, 0, 30, 300, 40\nbottom, root, 0, 130, 300, 40\n", encoding="utf-8"
    )
    results = run(tmp_path, "--roipath", str(rois))["results"]
    assert [entry["roiName"] for entry in results] == ["top", "bottom"]
    assert [entry["roiIndex"] for entry in results] == [0, 1]
