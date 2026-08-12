"""Polylines between notable points of the skeleton, and their length.

The length part is translated from `getrootlength_new()` in
`rootsegmentprop.cpp` of RhizoVision Explorer, Copyright (C) Noble Research
Institute, LLC, GPL-3.0.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .skeleton import RING

# Roughly 1/sqrt(2), the offset one staircase step makes against its own line.
# Pruning measures a spur with it too, so changing it moves the tip and branch
# counts along with the length.
SIMPLIFY_EPSILON = 0.71


def extract(skeleton: np.ndarray, nodes: np.ndarray) -> list[list[tuple[int, int]]]:
    """Insertion order is row-major over the nodes, then `RING` order over
    their neighbours. Pruning walks segments in container order with no sort,
    so a different order here changes the tip and branch counts."""
    skel = np.pad(skeleton, 1) != 0
    node = np.pad(nodes, 1) != 0
    walked = np.zeros_like(skel)
    segments: list[list[tuple[int, int]]] = []
    joined: set[tuple[int, int, int, int]] = set()

    def neighbours(point):
        y, x = point
        return [(y + dy, x + dx) for dy, dx in RING if skel[y + dy, x + dx]]

    def follow(start, first, closes=False):
        """Neighbours that end the walk are taken first: under
        8-connectivity a pixel one step short of a branch point often touches
        two of its arms, and taking the ordinary one swallows the next
        segment."""

        def ends(p):
            return node[p] or (closes and p == start)

        path, previous, current = [start], start, first
        while True:
            path.append(current)
            if ends(current):
                return path
            walked[current] = True
            ahead = [
                p
                for p in neighbours(current)
                if p != previous and (ends(p) or not walked[p])
            ]
            if not ahead:
                return path
            ahead.sort(key=lambda p: not ends(p))
            previous, current = current, ahead[0]

    for point in map(tuple, np.argwhere(node)):
        steps = neighbours(point)
        if not steps:
            segments.append([point])  # isolated pixel: a segment of zero length
            continue
        for step in steps:
            if node[step]:
                edge = (*min(point, step), *max(point, step))
                if edge in joined:
                    continue
                joined.add(edge)
                segments.append([point, step])
            elif not walked[step]:
                segments.append(follow(point, step))

    # A component with no node at all is a closed loop.
    for point in map(tuple, np.argwhere(skel & ~node & ~walked)):
        if walked[point]:
            continue
        walked[point] = True
        around = neighbours(point)
        segments.append(follow(point, around[0], closes=True) if around else [point])

    return [[(y - 1, x - 1) for y, x in path] for path in segments]


def stepwise_length(path: list[tuple[int, int]]) -> float:
    """The chain code: 1 per orthogonal step, sqrt(2) per diagonal one. Not
    what the pipeline reports — only `validation/synthetic.py` calls it."""
    return sum(
        math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])
    )


def _simplify(path: list[tuple[int, int]], epsilon: float) -> np.ndarray:
    points = np.array(path, np.int32).reshape(-1, 1, 2)
    return cv2.approxPolyDP(points, epsilon, False).reshape(-1, 2)


def simplified_length(
    path: list[tuple[int, int]], epsilon: float = SIMPLIFY_EPSILON
) -> float:
    """Douglas-Peucker, then the euclidean length of what is left."""
    if len(path) < 2:
        return 0.0
    simplified = _simplify(path, epsilon)
    return float(
        np.hypot(*np.diff(simplified, axis=0).T).sum() if len(simplified) > 1 else 0.0
    )


def simplified_scales(
    path: list[tuple[int, int]], epsilon: float = SIMPLIFY_EPSILON
) -> np.ndarray:
    """One factor per step, so the simplification lands on pixels and can fill
    a histogram. Summing the scaled steps returns the simplified length
    exactly, which keeps `total_root_length` the sum of its bins."""
    steps = np.diff(np.array(path, np.float64), axis=0)
    walk = np.hypot(steps[:, 0], steps[:, 1])
    scales = np.ones(len(walk))
    if len(walk) == 0:
        return scales

    kept, vertex = [], 0
    simplified = _simplify(path, epsilon)
    for index, point in enumerate(path):
        if vertex < len(simplified) and point == tuple(simplified[vertex]):
            kept.append(index)
            vertex += 1

    for start, end in zip(kept, kept[1:]):
        staircase = walk[start:end].sum()
        if staircase:
            scales[start:end] = math.dist(path[start], path[end]) / staircase
    return scales


def lengths(segments: list[list[tuple[int, int]]], mm_per_px: float) -> dict[str, float]:
    """`total_root_length` is not here: it is the sum of the root length
    histogram `aggregate` produces."""
    return {"num_segments": float(len(segments))}
