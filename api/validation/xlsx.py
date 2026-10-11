"""Read one sheet of an .xlsx with the standard library.

The competitors' numbers ship as a workbook and are read exactly once, so
this is a few lines of zipfile and ElementTree instead of a dependency.
"""

from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree

NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _column(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group()
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index - 1


def sheet_names(path) -> list[str]:
    with zipfile.ZipFile(path) as book:
        root = ElementTree.fromstring(book.read("xl/workbook.xml"))
        return [s.get("name") for s in root.iter(f"{NAMESPACE}sheet")]


def rows(path, sheet: str) -> list[list[str]]:
    """Every row of `sheet` as strings, blanks included so columns line up."""
    with zipfile.ZipFile(path) as book:
        names = sheet_names(path)
        index = names.index(sheet) + 1
        shared = [
            "".join(t.text or "" for t in item.iter(f"{NAMESPACE}t"))
            for item in ElementTree.fromstring(
                book.read("xl/sharedStrings.xml")
            ).iter(f"{NAMESPACE}si")
        ] if "xl/sharedStrings.xml" in book.namelist() else []

        table = []
        root = ElementTree.fromstring(book.read(f"xl/worksheets/sheet{index}.xml"))
        for row in root.iter(f"{NAMESPACE}row"):
            cells: dict[int, str] = {}
            for cell in row.iter(f"{NAMESPACE}c"):
                value = cell.find(f"{NAMESPACE}v")
                if value is None or value.text is None:
                    continue
                text = value.text
                if cell.get("t") == "s":
                    text = shared[int(text)]
                cells[_column(cell.get("r"))] = text
            table.append(
                [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []
            )
        return table
