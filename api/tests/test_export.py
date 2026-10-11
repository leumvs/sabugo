"""The features.csv column contract."""


import numpy as np
import pytest

from imaging import export

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
