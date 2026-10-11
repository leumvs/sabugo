"""The segmented mask, and the skeleton coloured by diameter class."""

from __future__ import annotations

import cv2
import numpy as np

from .aggregate import class_of

BACKGROUND = (255, 255, 255)
ROOT = (60, 60, 60)  # the segmented image: dark on white
ROOT_UNDER_SKELETON = (215, 215, 215)  # light, so the colours read over it
HOLE = (235, 206, 135)  # the gaps the network closes around
HULL = (0, 140, 255)
CONTOUR = (120, 60, 60)
PEN = 3
CONTOUR_WIDTH = 1


def class_colours(classes: int) -> list[tuple[int, int, int]]:
    """Viridis sampled at one point per diameter class, as BGR."""
    positions = np.linspace(0, 255, classes, dtype=np.uint8).reshape(1, -1)
    ramp = cv2.applyColorMap(positions, cv2.COLORMAP_VIRIDIS)[0]
    return [tuple(int(channel) for channel in colour) for colour in ramp]


def segmented(mask: np.ndarray) -> np.ndarray:
    picture = np.full((*mask.shape, 3), BACKGROUND, np.uint8)
    picture[mask > 0] = ROOT
    return picture


def overlay_holes(picture: np.ndarray, mask: np.ndarray) -> None:
    filled = mask.copy()
    cv2.floodFill(filled, np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), np.uint8), (0, 0), 255)
    picture[(filled == 0)] = HOLE


def overlay_hull(picture: np.ndarray, mask: np.ndarray, width: int = 2) -> None:
    points = cv2.findNonZero(mask)
    if points is not None:
        cv2.polylines(picture, [cv2.convexHull(points)], True, HULL, width)


def overlay_contour(picture: np.ndarray, mask: np.ndarray, width: int = CONTOUR_WIDTH) -> None:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(picture, contours, -1, CONTOUR, width)


def distance_map(dt: np.ndarray, mask: np.ndarray) -> np.ndarray:
    picture = np.full((*mask.shape, 3), BACKGROUND, np.uint8)
    maximum = dt.max()
    if maximum > 0:
        scaled = np.clip(dt / maximum * 255.0, 0, 255).astype(np.uint8)
        picture[mask > 0] = cv2.applyColorMap(scaled, cv2.COLORMAP_VIRIDIS)[mask > 0]
    return picture


def skeleton_picture(
    mask: np.ndarray,
    dt: np.ndarray,
    skeleton: np.ndarray,
    mm_per_px: float,
    diameter_ranges_mm: list[float],
    pen: int = PEN,
    holes: bool = False,
    hull: bool = False,
    contour: bool = False,
    contour_width: int = CONTOUR_WIDTH,
    show_distance_map: bool = False,
    medial_axis: bool = True,
    colour_by_class: bool = True,
) -> np.ndarray:
    """The skeleton over the mask, one colour per diameter class. The class
    comes from `class_of`, the same function the histograms use."""
    if show_distance_map:
        picture = distance_map(dt, mask)
    else:
        picture = np.full((*mask.shape, 3), BACKGROUND, np.uint8)
        picture[mask > 0] = ROOT_UNDER_SKELETON

    # What is behind first, medial axis last.
    if holes:
        overlay_holes(picture, mask)
    if hull:
        overlay_hull(picture, mask)
    if contour:
        overlay_contour(picture, mask, contour_width)

    on = skeleton != 0
    if not medial_axis or not on.any():
        return picture

    kernel = np.ones((pen, pen), np.uint8)
    if not colour_by_class:
        picture[cv2.dilate(on.astype(np.uint8) * 255, kernel) > 0] = ROOT
        return picture

    colours = class_colours(len(diameter_ranges_mm) + 1)
    where = class_of(dt[on], mm_per_px, diameter_ranges_mm)
    coordinates = np.nonzero(on)
    for index, colour in enumerate(colours):
        layer = np.zeros(mask.shape, np.uint8)
        layer[tuple(coordinate[where == index] for coordinate in coordinates)] = 255
        if layer.any():
            picture[cv2.dilate(layer, kernel) > 0] = colour
    return picture
