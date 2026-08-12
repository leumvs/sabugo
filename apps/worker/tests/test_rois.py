"""Regions of interest."""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
import pytest

from sabugo_worker import Params
from sabugo_worker.analysis import regions
from sabugo_worker.args import read_annotations
from sabugo_worker.cli import main

ANNOTATION = """#ROI Name, Class Name, X Position, Y Position, Width, Height
roi_1, root, 10, 20, 30, 40
roi_2, root, 5, 5, 10, 10
"""


def bar_image(path: Path) -> None:
    image = np.full((200, 300), 255, np.uint8)
    image[40:60, 20:280] = 0
    image[140:150, 20:280] = 0
    cv2.imwrite(str(path), image)


def test_reads_the_rve_annotation_format(tmp_path):
    path = tmp_path / "rois.csv"
    path.write_text(ANNOTATION, encoding="utf-8")
    assert read_annotations(path) == [
        ("roi_1", 10, 20, 30, 40),
        ("roi_2", 5, 5, 10, 10),
    ]


def test_comments_and_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "rois.csv"
    path.write_text("# a comment\n\nroi_1, root, 1, 2, 3, 4\n", encoding="utf-8")
    assert read_annotations(path) == [("roi_1", 1, 2, 3, 4)]


def test_a_short_line_is_refused(tmp_path):
    path = tmp_path / "rois.csv"
    path.write_text("roi_1, root, 1, 2\n", encoding="utf-8")
    with pytest.raises(argparse.ArgumentTypeError):
        read_annotations(path)


def test_more_than_ten_rois_is_refused(tmp_path):
    path = tmp_path / "rois.csv"
    path.write_text(
        "".join(f"roi_{i}, root, 0, 0, 5, 5\n" for i in range(11)), encoding="utf-8"
    )
    with pytest.raises(argparse.ArgumentTypeError):
        read_annotations(path)


def test_without_rois_the_whole_image_is_the_region():
    image = np.zeros((10, 12), np.uint8)
    names = [name for name, _ in regions(image, Params())]
    assert names == ["Full"]
    assert regions(image, Params())[0][1].shape == image.shape


def test_a_roi_is_x_y_width_height_of_the_original_image():
    image = np.arange(200 * 300, dtype=np.uint8).reshape(200, 300)
    params = Params(rois=[("roi_1", 30, 20, 40, 50)])
    name, region = regions(image, params)[0]

    assert name == "roi_1"
    assert region.shape == (50, 40)
    assert np.array_equal(region, image[20:70, 30:70])


def test_a_roi_over_the_whole_image_measures_the_whole_image(tmp_path):
    bar_image(tmp_path / "bar.png")
    rois = tmp_path / "rois.csv"
    rois.write_text("whole, root, 0, 0, 300, 200\n", encoding="utf-8")

    plain, with_roi = tmp_path / "plain.csv", tmp_path / "roi.csv"
    main([str(tmp_path / "bar.png"), "--dpi", "254", "-o", str(plain)])
    main([str(tmp_path / "bar.png"), "--dpi", "254", "--roipath", str(rois),
          "-o", str(with_roi)])

    first = next(csv.DictReader(plain.open(encoding="utf-8")))
    second = next(csv.DictReader(with_roi.open(encoding="utf-8")))
    assert second["Region.of.Interest"] == "whole"
    assert first["Region.of.Interest"] == "Full"
    for column in ("Network.Area.mm2", "Total.Root.Length.mm", "Number.of.Root.Tips"):
        assert first[column] == second[column]


def test_one_row_per_roi_and_no_whole_image_row(tmp_path):
    bar_image(tmp_path / "bar.png")
    rois = tmp_path / "rois.csv"
    rois.write_text(
        "top, root, 0, 30, 300, 40\nbottom, root, 0, 130, 300, 40\n", encoding="utf-8"
    )
    output = tmp_path / "features.csv"
    assert main([str(tmp_path / "bar.png"), "--dpi", "254", "--roipath", str(rois),
                 "-o", str(output)]) == 0

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert [row["Region.of.Interest"] for row in rows] == ["top", "bottom"]
    assert float(rows[0]["Network.Area.mm2"]) > float(rows[1]["Network.Area.mm2"])


def test_an_empty_roi_fails_that_row_and_keeps_the_others(tmp_path):
    bar_image(tmp_path / "bar.png")
    rois = tmp_path / "rois.csv"
    rois.write_text(
        "empty, root, 0, 80, 100, 40\nreal, root, 0, 30, 300, 40\n", encoding="utf-8"
    )
    output = tmp_path / "features.csv"
    assert main([str(tmp_path / "bar.png"), "--dpi", "254", "--roipath", str(rois),
                 "-o", str(output)]) == 1

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert [row["Region.of.Interest"] for row in rows] == ["real"]
