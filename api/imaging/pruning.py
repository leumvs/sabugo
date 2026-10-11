"""Root pruning: remove spurs shorter than a threshold relative to the radius.

Translated and adapted from the pruning loop in `roottopology.cpp` of
RhizoVision Explorer, Copyright (C) Noble Research Institute, LLC, GPL-3.0.
"""

from __future__ import annotations

import numpy as np

from .segments import extract, simplified_length
from .skeleton import RING
from .topology import classify


def _is_simple(skeleton: np.ndarray, point: tuple[int, int]) -> bool:
    """One 0->1 transition around the ring: the foreground neighbours form a
    single run, so erasing the pixel cannot split the skeleton. An isolated
    pixel is not simple and `prune` removes it separately."""
    y, x = point
    height, width = skeleton.shape
    ring = [
        bool(skeleton[y + dy, x + dx])
        if 0 <= y + dy < height and 0 <= x + dx < width
        else False
        for dy, dx in RING
    ]
    return sum(not ring[t] and ring[(t + 1) % 8] for t in range(8)) == 1


def prune(
    skeleton: np.ndarray, dt: np.ndarray, threshold_px: float, max_passes: int = 20
) -> np.ndarray:
    """Drop the spurs skeletonization invents:

        length(branch -> tip) <= radius at the branch point + threshold

    The threshold is slack added to a radius, not a maximum length. Removal is
    a pixel peel and not a whole-segment erase, because these segments are not
    pixel-disjoint: a polyline can share an interior pixel with another.
    """
    height, width = skeleton.shape
    skeleton = skeleton.copy()

    for _ in range(max_passes):
        found = classify(skeleton)
        tip, branch = found["tip"], found["branch"]
        segments = extract(skeleton, tip | branch)

        # Judged against the topology the pass started with, all at once:
        # removing sequentially would let a branch losing one limb save its
        # sibling in the same pass.
        condemned = []
        for path in segments:
            head, tail = path[0], path[-1]
            if branch[head] and tip[tail]:
                root = head
            elif branch[tail] and tip[head]:
                root = tail
            else:
                continue  # tip-to-tip is a whole root; a cycle is no leaf
            if simplified_length(path) <= dt[root] + threshold_px:
                condemned.append(path)

        if not condemned:
            break

        # Peeling only simple pixels, re-checking as each one frees its
        # neighbour, takes the leaf to the branch and stops: a branch pixel is
        # never simple.
        candidates = {point for path in condemned for point in path}

        changed = True
        while changed:
            changed = False
            for point in list(candidates):
                if not skeleton[point]:
                    continue
                y, x = point
                y0, y1 = max(0, y - 1), min(height, y + 2)
                x0, x1 = max(0, x - 1), min(width, x + 2)
                isolated = int((skeleton[y0:y1, x0:x1] > 0).sum()) == 1
                if isolated or _is_simple(skeleton, point):
                    skeleton[point] = 0
                    candidates.discard(point)
                    changed = True

    return skeleton
