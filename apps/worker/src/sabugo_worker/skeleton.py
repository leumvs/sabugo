"""Skeletonization: ridge detection, steepest ascent and Guo-Hall thinning.

Translated and adapted from `cvutil/cvutil_bwskel.cpp` (`location::isridge`,
`bwskel_helper::bwskel`) of cvutil, Copyright (C) Noble Research Institute,
LLC, GPL-3.0. The C++ is scalar and AVX2; this is the same logic vectorized
over NumPy.
"""

from __future__ import annotations

import cv2
import numpy as np

# The eight neighbours as (row, col): right, upper-right, top, upper-left, left,
# lower-left, bottom, lower-right. Odd positions orthogonal, even diagonal,
# and the opposite of N[t] is N[t + 4].
RING = ((0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1))

def _neighbour(
    padded: np.ndarray, shape: tuple[int, int], step: int, direction: int, pad: int = 2
):
    dr, dc = RING[direction]
    row, col = pad + step * dr, pad + step * dc
    return padded[row : row + shape[0], col : col + shape[1]]


def detect_ridges(mask: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """The tests below are in the order `isridge` applies them, and the order
    is load-bearing: the first two return early."""
    shape = mask.shape
    distance = np.pad(dt, 2)
    binary = np.pad(mask, 2) != 0
    centre = dt

    d = [_neighbour(distance, shape, 1, t) for t in range(8)]
    d2 = [_neighbour(distance, shape, 2, t) for t in range(8)]
    b = [_neighbour(binary, shape, 1, t) for t in range(8)]

    # 1. strictly greater than two opposite neighbours, any one of the 4 axes
    ridge = np.zeros(shape, bool)
    for t in range(4):
        ridge |= (d[t] < centre) & (d[t + 4] < centre)

    # 2. plateau: one side equal, the opposite smaller, and the second layer
    #    beyond the equal side smaller too
    for t in range(8):
        ridge |= (d[t] == centre) & (d[(t + 4) % 8] < centre) & (d2[t] < centre)

    # 4. and 5. connectivity-preserving pixels are ridges even where the
    #    distance map does not peak: a pixel whose removal would disconnect
    #    the neighbourhood is skeleton by definition
    connectivity_8, connectivity_4 = _connectivity(b)

    ridge |= (connectivity_8 > 1) | (connectivity_4 > 1)
    return np.where(ridge & (centre > 0), 255, 0).astype(np.uint8)


def _connectivity(b: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    connectivity_8 = np.zeros(b[0].shape, np.uint8)
    connectivity_4 = np.zeros(b[0].shape, np.uint8)
    for t in range(0, 8, 2):
        i1, i2, i3 = b[t], b[t + 1], b[(t + 2) % 8]
        connectivity_8 += (~i1 & (i2 | i3)).view(np.uint8)
        connectivity_4 += (i1 & ~(i2 & i3)).view(np.uint8)
    return connectivity_8, connectivity_4


def component_count(mask: np.ndarray) -> int:
    return cv2.connectedComponents(mask, connectivity=8)[0] - 1


def _ridge_neighbourhood(ridge: np.ndarray):
    shape = ridge.shape
    padded = np.pad(ridge, 2) != 0
    r = [_neighbour(padded, shape, 1, t) for t in range(8)]
    count = sum(x.view(np.uint8) for x in r)
    pairs = sum((r[t] & r[(t + 1) % 8]).view(np.uint8) for t in range(8))
    triples = sum(
        (r[t] & r[(t + 1) % 8] & r[(t + 2) % 8]).view(np.uint8) for t in range(8)
    )
    return count, pairs, triples


def ridge_endpoints(ridge: np.ndarray) -> np.ndarray:
    count, pairs, triples = _ridge_neighbourhood(ridge)
    is_end = (
        (count <= 1)
        | ((count == 2) & (pairs == 1))
        | ((count == 3) & (triples == 1))
    )
    return (ridge != 0) & is_end


def climb_starts(mask: np.ndarray, dt: np.ndarray, ridge: np.ndarray) -> np.ndarray:
    """A fragment end climbs only where the tissue still goes uphill:

    - `P >= nrv1`: no ridge neighbour is higher;
    - `P <= nrv2`: some free neighbour is at least as high, so there is
      somewhere to climb to. A root tip fails this — its free neighbours are
      background at distance 0.
    """
    shape = ridge.shape
    ridge_pad = np.pad(ridge, 2) != 0
    mask_pad = np.pad(mask, 2) != 0
    dt_pad = np.pad(dt, 2)
    r = [_neighbour(ridge_pad, shape, 1, t) for t in range(8)]
    b = [_neighbour(mask_pad, shape, 1, t) for t in range(8)]
    d = [_neighbour(dt_pad, shape, 1, t) for t in range(8)]

    nrv1 = np.full(shape, -1.0, np.float32)
    nrv2 = np.full(shape, -1.0, np.float32)
    for t in range(8):
        free = ~r[t] & ~r[(t + 1) % 8] & ~r[(t + 7) % 8]
        np.maximum(nrv1, d[t], out=nrv1, where=r[t])
        np.maximum(nrv2, d[t], out=nrv2, where=free)

    neighbours = sum(x.view(np.uint8) for x in r)
    connectivity_8, connectivity_4 = _connectivity(b)
    interior = (
        (sum(x.view(np.uint8) for x in b) >= 5)
        | (neighbours == 0)
        | (
            (np.maximum(connectivity_8, connectivity_4) > 1)
            & (neighbours >= 1)
            & (neighbours <= 3)
        )
    )
    is_end = ridge_endpoints(ridge)
    return (
        (ridge != 0)
        & (dt >= nrv1)
        & (dt <= nrv2)
        & ((is_end & interior) | (~is_end & (neighbours == 2)))
    )


def _fragment_owners(fragment_of: np.ndarray, part_of: np.ndarray, pieces: int) -> np.ndarray:
    on = fragment_of > 0
    owners = np.zeros(pieces, np.int32)
    owners[fragment_of[on]] = part_of[on]
    return owners[1:]


def _fragmented_components(
    ridge: np.ndarray, part_of: np.ndarray, parts: int
) -> np.ndarray:
    _, fragment_of = cv2.connectedComponents(np.ascontiguousarray(ridge), connectivity=8)
    on_ridge = ridge != 0
    seen = np.unique(np.stack([part_of[on_ridge], fragment_of[on_ridge]]), axis=1)
    fragmented = np.bincount(seen[0], minlength=parts) > 1
    fragmented[0] = False
    return fragmented


def steepest_ascent(
    mask: np.ndarray, dt: np.ndarray, ridge: np.ndarray, max_passes: int = 10
) -> np.ndarray:
    """Each fragment end climbs the steepest slope until it touches another
    fragment, and the climb becomes skeleton. Runs until the fragment count
    stops falling."""
    height, width = mask.shape
    stride = width + 4
    foreground = np.pad(mask, 2).ravel() != 0
    distance = np.pad(dt, 2).ravel()
    skeleton = np.pad(ridge, 2)

    offsets = [dr * stride + dc for dr, dc in RING]
    second = [2 * o for o in offsets]
    # tie-break by slope, so a diagonal candidate pays its sqrt(2)
    lengths = [2.0 * np.hypot(dr, dc) for dr, dc in RING]
    limit = height * width
    parts, part_of = cv2.connectedComponents(mask, connectivity=8)
    previous = component_count(ridge)
    # Ends that climbed back onto their own fragment: they would do it again.
    hopeless: set[int] = set()

    for _ in range(max_passes):
        current = skeleton[2:-2, 2:-2]
        # Only components whose ridge is still in pieces climb: ungated, every
        # root tip climbs too and grows a duplicate branch.
        broken = _fragmented_components(current, part_of, parts)
        if not broken.any():
            break

        neighbours, _, _ = _ridge_neighbourhood(current)
        junction = np.pad(neighbours > 1, 2).ravel()
        is_ridge = skeleton.ravel() != 0
        flat = skeleton.ravel()

        # The source relabels after every climb, not every pass, which is what
        # stops both ends of a gap bridging it and leaving a sliver the thinning
        # keeps as a loop. Relabelling per climb is not affordable; the
        # union-find below has the same effect.
        pieces, fragment_of = cv2.connectedComponents(current, connectivity=8)
        fragment = np.pad(fragment_of, 2).ravel()
        joined = list(range(pieces))
        left = np.bincount(
            _fragment_owners(fragment_of, part_of, pieces), minlength=parts
        )

        def group(piece: int) -> int:
            while joined[piece] != piece:
                joined[piece] = joined[joined[piece]]
                piece = joined[piece]
            return piece

        starts = climb_starts(mask, dt, current) & broken[part_of]
        for start in np.flatnonzero(np.pad(starts, 2).ravel()):
            point = int(start)
            owner = part_of.ravel()[
                (point // stride - 2) * width + (point % stride - 2)
            ]
            if left[owner] <= 1 or point in hopeless:
                continue  # already in one piece, or a climb that leads nowhere
            source = group(int(fragment[point]))
            bridged, returned = False, False
            visited = {point}
            visited.update(point + o for o in offsets if is_ridge[point + o])
            for _step in range(limit):
                best, tied = -1.0, []
                for k, offset in enumerate(offsets):
                    candidate = point + offset
                    if not foreground[candidate] or candidate in visited:
                        continue
                    value = distance[candidate]
                    if value > best:
                        best, tied = value, [k]
                    elif value == best:
                        tied.append(k)
                if not tied:
                    break
                if len(tied) > 1:
                    tied.sort(key=lambda k: distance[point + second[k]] / lengths[k])
                point += offsets[tied[-1]]
                visited.add(point)
                flat[point] = 255
                if is_ridge[point] and junction[point]:
                    reached = group(int(fragment[point]))
                    if reached != source:
                        joined[reached] = source
                        left[owner] -= 1
                        bridged = True
                    else:
                        returned = True
                    break

            # It would climb again next pass. The strand it drew stays:
            # erasing it opens stubs.
            if returned:
                hopeless.add(int(start))

        ridge = skeleton[2:-2, 2:-2].copy()
        remaining = component_count(ridge)
        if remaining >= previous:
            break
        previous = remaining

    return skeleton[2:-2, 2:-2]


FILL_PINHOLES = True


def _fill_pinholes(ridge: np.ndarray) -> np.ndarray:
    """Closes the 1-px indentation the thinning would otherwise keep as a
    loop. Over the largest component only, as the source does.
    """
    count, labels = cv2.connectedComponents(ridge, connectivity=8)
    if count <= 1:
        return ridge
    largest = 1 + int(np.argmax(np.bincount(labels.ravel())[1:]))

    shape = ridge.shape
    padded = np.pad(ridge, 2) != 0
    on = padded[2:-2, 2:-2] & (labels == largest)
    fill = np.zeros_like(padded)
    for n in range(0, 8, 2):  # orthogonal directions only
        neighbour = _neighbour(padded, shape, 1, n)
        diag_a = _neighbour(padded, shape, 1, (n + 1) % 8)
        diag_b = _neighbour(padded, shape, 1, (n + 7) % 8)
        beyond = _neighbour(padded, shape, 2, n)
        pt = on & ~neighbour & diag_a & diag_b & beyond
        dr, dc = RING[n]  # the fill lands on the empty neighbour, pt + N[n]
        fill[2 + dr : 2 + dr + shape[0], 2 + dc : 2 + dc + shape[1]] |= pt
    out = ridge.copy()
    out[fill[2:-2, 2:-2]] = 255
    return out


def skeletonize(mask: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """Guo-Hall runs on the connected ridge, not the mask. Padded first: the
    thinning treats a border pixel differently from one with background around
    it, and the bbox crop puts the object against the border."""
    connected = steepest_ascent(mask, dt, detect_ridges(mask, dt))
    if FILL_PINHOLES:
        connected = _fill_pinholes(connected)
    padded = cv2.copyMakeBorder(connected, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    thinned = cv2.ximgproc.thinning(padded, thinningType=cv2.ximgproc.THINNING_GUOHALL)
    return np.ascontiguousarray(thinned[1:-1, 1:-1])
