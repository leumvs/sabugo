"""The JSON the API republishes to the browser, verbatim."""

from __future__ import annotations


from . import PIPELINE_VERSION
from .aggregate import HISTOGRAMS
from .export import globals_for


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word[:1].upper() + word[1:] for word in rest)


def result(
    file_name: str,
    region: str,
    roi_index: int,
    values: dict[str, object],
    threshold_value_used: int,
    pictures: dict[str, str | None],
    mode: str = "broken_roots",
) -> dict[str, object]:
    return {
        "roiIndex": roi_index,
        "roiName": region,
        "fileName": file_name,
        "thresholdValueUsed": threshold_value_used,
        "numSegments": int(values["num_segments"]),
        "metrics": {camel(key): values[key] for key in globals_for(mode)},
        "bins": {camel(name): list(values["histograms"][name]) for name in HISTOGRAMS},
        "segmentedImage": pictures.get("segmented"),
        "skeletonImage": pictures.get("skeleton"),
    }


def preview(
    file_name: str,
    region: str,
    roi_index: int,
    threshold_value_used: int,
    pictures: dict[str, str | None],
) -> dict[str, object]:
    """No `metrics` and no `bins`: the run stopped before anything was
    measured, and an empty table would read as a measurement of zero."""
    return {
        "roiIndex": roi_index,
        "roiName": region,
        "fileName": file_name,
        "thresholdValueUsed": threshold_value_used,
        "segmentedImage": pictures.get("segmented"),
        "skeletonImage": None,
    }


def document(results: list[dict[str, object]]) -> dict[str, object]:
    return {"pipelineVersion": PIPELINE_VERSION, "results": results}
