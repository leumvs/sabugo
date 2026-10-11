from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveNumber = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class AnalysisParams(BaseModel):
    model_config = ConfigDict(strict=True)
    mode: Literal["broken_roots", "whole_root"] = "broken_roots"
    threshold_method: Literal["manual", "otsu"] = "manual"
    threshold_value: int = Field(default=200, ge=0, le=255)
    invert_image: bool = False
    keep_largest: bool = True
    filter_background_noise: bool = False
    max_background_noise_mm2: PositiveNumber = 1.0
    filter_foreground_noise: bool = False
    max_foreground_noise_mm2: PositiveNumber = 1.0
    enable_edge_smoothing: bool = False
    edge_smoothing_threshold: PositiveNumber = 2.0
    enable_root_pruning: bool = False
    root_pruning_threshold: int = Field(default=5, ge=0)
    diameter_ranges_mm: list[PositiveNumber] = Field(default_factory=lambda: [2.0, 5.0], min_length=1, max_length=11)
    show_medial_axis: bool = True
    medial_axis_width: int = Field(default=3, ge=1, le=20)
    show_medial_axis_diameter: bool = True
    show_contours: bool = False
    contour_width: int = Field(default=1, ge=1, le=20)
    show_convex_hull: bool = False
    show_holes: bool = False
    show_dist_map: bool = False

    @field_validator("diameter_ranges_mm")
    @classmethod
    def increasing(cls, values: list[float]) -> list[float]:
        if any(b <= a for a, b in zip(values, values[1:])):
            raise ValueError("diameter_ranges_must_be_strictly_increasing")
        return values


class Roi(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str = Field(min_length=1, max_length=64)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Accepted(BaseModel):
    id: UUID
    status: Literal["pending"] = "pending"
    queuePosition: int = Field(ge=0)
    queuedAt: datetime


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: dict | None = None


class PreviewResult(BaseModel):
    roiIndex: int
    roiName: str
    fileName: str
    thresholdValueUsed: int
    segmentedImage: str
    skeletonImage: None = None


class AnalysisResult(PreviewResult):
    numSegments: int
    metrics: dict[str, float]
    bins: dict[str, list[float]]
    skeletonImage: str


class AnalysisDocument(BaseModel):
    pipelineVersion: str
    results: list[AnalysisResult | PreviewResult]
