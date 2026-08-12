"""Skeleton topology: tips, branch points and overlap points.

Translated and adapted from `getroottopology()` in `roottopology.cpp` of
RhizoVision Explorer, Copyright (C) Noble Research Institute, LLC, GPL-3.0.
The C++ walks the skeleton contour pixel by pixel; this classifies every
skeleton pixel at once, which is the same classification.
"""

from __future__ import annotations

import numpy as np

from .skeleton import RING, _neighbour

# The ring pairs that must both be background for the nsum == 6 exclusion, as
# 0-based indices into RING. Verbatim from the source.
_DEGENERATE_PAIRS = (
    (0, 4),
    (2, 6),
    (0, 1),
    (0, 7),
    (2, 1),
    (6, 7),
    (2, 3),
    (6, 5),
    (4, 3),
    (4, 5),
)


def classify(skeleton: np.ndarray) -> dict[str, np.ndarray]:
    """Not the naive "1 neighbour is a tip, 3 or more is a branch": the
    staircase artefacts break that rule, so the tests below run on the ring of
    eight neighbours and their adjacency."""
    shape = skeleton.shape
    padded = np.pad(skeleton, 1) != 0
    n = [_neighbour(padded, shape, 1, t, pad=1) for t in range(8)]
    on = skeleton != 0

    total = sum(x.view(np.uint8) for x in n)

    # a tip is one neighbour, or two that sit next to each other in the ring
    adjacent = np.zeros(shape, bool)
    for t in range(8):
        adjacent |= n[t] & n[(t + 1) % 8]
    tip = on & ((total == 1) | ((total == 2) & adjacent))

    # crossing number: transitions around the ring, three of them is a fork
    crossings = sum((n[t] & ~n[(t + 1) % 8]).view(np.uint8) for t in range(8))

    # or a contiguous run of three starting on an orthogonal neighbour
    run_of_three = np.zeros(shape, bool)
    for t in (0, 2, 4, 6):
        run_of_three |= n[t] & n[(t + 1) % 8] & n[(t + 2) % 8]

    degenerate = np.zeros(shape, bool)
    for a, b in _DEGENERATE_PAIRS:
        degenerate |= ~n[a] & ~n[b]

    # two roots crossing: four neighbours, all orthogonal or all diagonal
    overlap = on & ~tip & (total == 4) & (
        (n[0] & n[2] & n[4] & n[6]) | (n[1] & n[3] & n[5] & n[7])
    )

    branch = (
        on
        & ~tip
        & (
            (crossings == 3)
            | ((total >= 4) & (total < 7) & run_of_three & ~((total == 6) & degenerate))
            | overlap
        )
    )
    return {"tip": tip, "branch": branch, "overlap": overlap}
