"""The client's copy of the diameter-class ramp, checked against this one.

The histogram in the browser and the coloured skeleton in the PNG beside it
have to be the same colour for the same class, or the figure and the number
disagree about the same pixel — which is the defect keeping `class_of` in one
place to avoid. The client cannot call OpenCV, so it carries a table; this is
what stops that table from drifting away in silence.
"""

import json
from pathlib import Path

import pytest

from imaging.render import class_colours

TABLE = Path(__file__).resolve().parents[2] / "web/src/lib/viridis.json"

# At most 11 inner boundaries, so at most 12 classes, and there is
# always at least one boundary.
CLASSES = range(2, 13)


@pytest.fixture(scope="module")
def table() -> dict:
    return json.loads(TABLE.read_text(encoding="utf-8"))


def test_the_table_covers_every_class_count_25_allows(table):
    assert sorted(int(key) for key in table) == list(CLASSES)


@pytest.mark.parametrize("classes", CLASSES)
def test_every_colour_matches_the_renderer(table, classes):
    # `class_colours` is BGR, straight out of OpenCV; the table is RGB hex.
    expected = ["#%02x%02x%02x" % (r, g, b) for b, g, r in class_colours(classes)]
    assert table[str(classes)] == expected


def test_the_ends_are_the_ends_of_viridis(table):
    """A guard against a table that matches a *different* colour map: dark
    purple at the thin end, yellow at the thick one, monotone in luminance."""
    for colours in table.values():
        assert colours[0] == "#440154"
        assert colours[-1] == "#fde725"
