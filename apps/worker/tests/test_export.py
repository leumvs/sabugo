"""The features.csv layout and the CLI flags around it."""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
import pytest

from sabugo_worker import export
from sabugo_worker.args import diameter_ranges
from sabugo_worker.cli import main

# The export contract, spelled out rather than derived, so that renaming
# a column has to be a deliberate edit here: these headers are what makes a
# Sabugo sheet line up with a sheet from any of the tools it is compared against.
BROKEN_ROOT_HEADER = (
    "File.Name,Region.of.Interest,Number.of.Root.Tips,Number.of.Branch.Points,"
    "Total.Root.Length.mm,Branching.frequency.per.mm,Network.Area.mm2,"
    "Average.Diameter.mm,Median.Diameter.mm,Maximum.Diameter.mm,Perimeter.mm,"
    "Volume.mm3,Surface.Area.mm2,Computation.Time.s,"
    "Root.Length.Diameter.Range.1.mm,Root.Length.Diameter.Range.2.mm,"
    "Root.Length.Diameter.Range.3.mm,Projected.Area.Diameter.Range.1.mm2,"
    "Projected.Area.Diameter.Range.2.mm2,Projected.Area.Diameter.Range.3.mm2,"
    "Surface.Area.Diameter.Range.1.mm2,Surface.Area.Diameter.Range.2.mm2,"
    "Surface.Area.Diameter.Range.3.mm2,Volume.Diameter.Range.1.mm3,"
    "Volume.Diameter.Range.2.mm3,Volume.Diameter.Range.3.mm3"
).split(",")


def bar_image(path: Path, thickness: int = 20) -> None:
    image = np.full((80, 260), 255, np.uint8)
    image[30 : 30 + thickness, 30:230] = 0
    cv2.imwrite(str(path), image)


def test_the_broken_root_header_is_the_contract():
    assert export.columns([2.0, 5.0]) == BROKEN_ROOT_HEADER
    assert len(BROKEN_ROOT_HEADER) == 26  # 2 leading + 12 global + 4 histograms x 3


def test_the_whole_root_header_adds_twelve_globals():
    """38 instead of 26, and it drops the two that only a broken-roots run
    carries: branch points and their frequency."""
    whole = export.columns([2.0, 5.0], "whole_root")
    assert len(whole) == 38
    assert "Number.of.Branch.Points" not in whole
    assert "Branching.frequency.per.mm" not in whole


def test_column_count_follows_the_number_of_classes():
    assert len(export.columns([1.0])) == 2 + 12 + 4 * 2
    assert len(export.columns([1.0, 2.0, 4.0])) == 2 + 12 + 4 * 4


def test_computation_time_is_reported_in_seconds():
    values = {name: 1.0 for name in export.BROKEN_ROOT_COLUMNS}
    values["processing_time_ms"] = 2261.0
    values["histograms"] = {name: [0.0, 0.0, 0.0] for name in export.HISTOGRAM_COLUMNS}

    row = export.row("scan1.jpg", values, [2.0, 5.0])
    assert row["Computation.Time.s"] == "2.261000"
    assert row["File.Name"] == "scan1.jpg"
    assert row["Region.of.Interest"] == "Full"


def test_cli_writes_one_row_per_image(tmp_path):
    for name in ("a.png", "b.png"):
        bar_image(tmp_path / name)
    output = tmp_path / "features.csv"

    assert main([str(tmp_path), "--dpi", "254", "-o", str(output)]) == 0
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert [row["File.Name"] for row in rows] == ["a.png", "b.png"]
    assert {row["Region.of.Interest"] for row in rows} == {"Full"}
    assert float(rows[0]["Total.Root.Length.mm"]) > 0


def test_one_bad_image_does_not_take_the_batch_with_it(tmp_path):
    bar_image(tmp_path / "a.png")
    (tmp_path / "b.png").write_bytes(b"not an image at all")
    bar_image(tmp_path / "c.png")
    output = tmp_path / "features.csv"

    assert main([str(tmp_path), "--dpi", "254", "-o", str(output)]) == 1
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert [row["File.Name"] for row in rows] == ["a.png", "c.png"]


def test_a_second_run_replaces_the_file(tmp_path):
    bar_image(tmp_path / "a.png")
    output = tmp_path / "features.csv"
    for _ in range(2):
        main([str(tmp_path), "--dpi", "254", "-o", str(output)])
    assert len(output.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_dranges_changes_how_many_histogram_columns(tmp_path):
    bar_image(tmp_path / "a.png")
    output = tmp_path / "features.csv"
    main([str(tmp_path), "--dpi", "254", "--dranges", "1.5,3,4", "-o", str(output)])

    header = next(csv.reader(output.open(encoding="utf-8")))
    assert "Root.Length.Diameter.Range.4.mm" in header
    assert "Volume.Diameter.Range.4.mm3" in header
    assert len(header) == 2 + 12 + 4 * 4


@pytest.mark.parametrize(
    "text", ["2.0,5.0", "1", "0.1,0.2,0.3", "1,2,3,4,5,6,7,8,9,10,11"]
)
def test_dranges_accepts_valid_boundaries(text):
    assert diameter_ranges(text) == [float(x) for x in text.split(",")]


@pytest.mark.parametrize(
    "text",
    [
        "5.0,2.0",  # not increasing
        "2.0,2.0",  # not strictly
        "0,2",  # not greater than zero
        "-1",
        "",
        "two,five",
        "1,2,3,4,5,6,7,8,9,10,11,12",  # 12 boundaries is 13 classes
    ],
)
def test_dranges_rejects_what_2_5_forbids(text):
    with pytest.raises(argparse.ArgumentTypeError):
        diameter_ranges(text)
