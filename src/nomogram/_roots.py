# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The root of an implicit equation, for each set of inputs, vectorised.

The unknown is sought in an interval the caller derives from objective
domains (VIM 2.48, note 1: h(Y, X1, ..., Xn) = 0, Y the output). The
residual h = left - right is sampled on a grid; each change of sign
between two finite samples, each exact zero and each edge of a region
where the residual is undefined gives a candidate; each candidate is
bisected down to adjacent floating-point numbers, and kept as a root only
where the residual has collapsed there, to a millionth of its largest
finite value at the ends of the bracket bisected: it stays as large
across a jump between pieces, and grows at a pole. The members' own
size plays no part, so that a member written 0 (h == 0) or computed by
cancellation of large terms does not hide a root. One root gives the
value; none, several, or a residual undefined inside a bracket give NaN,
with the reason.

Limits, by construction: two roots closer than the grid's step (a factor
of 10^(1/16) on a geometric grid, a 63rd of a finite interval on the
linear one) or a double root, without a change of sign, escape; on an
open interval, roots beyond 10^12 times the scale of the finite end are
not sought. A jump smaller than a millionth of the residual's change
across its bracket is taken for a root; a crossing with an infinite
slope, as steep as a cube root, may be taken for a jump where no float
gives an exact zero.

No dependency beyond numpy, no state: every function is pure.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

#: Samples per decade of the geometric grids.
SAMPLES_PER_DECADE = 16

#: Decades the geometric grids span, from an anchor, relative to its scale.
DECADES = (-12, 12)

#: Samples of the linear grid of a finite interval.
LINEAR_SAMPLES = 64

#: Largest number of residuals evaluated at once (rows times samples).
MAX_ELEMENTS = 1_000_000

#: How far the residual falls, from the ends of a bracket to a root.
COLLAPSE = 1e-6

#: What the search found, for each set of inputs.
ONE, NONE, SEVERAL, UNDETERMINED = 0, 1, 2, 3

_INT64_MIN = np.int64(-(2**63))

Members = Callable[..., tuple[Any, Any]]


def grid(low: float, high: float) -> np.ndarray:
    """Sample points of [low, high], ends included where finite.

    A linear grid and geometric grids anchored at each finite end (and at
    0 inside), offsets scaled by max(|anchor|, 1), so that roots near an
    end and roots of very different magnitudes are both reached; an open
    end is swept geometrically up to 10^12 times the scale of the anchor.
    """
    exponents = np.arange(
        DECADES[0], DECADES[1] + 1.0 / SAMPLES_PER_DECADE, 1.0 / SAMPLES_PER_DECADE
    )

    def geometric(anchor: float, direction: float) -> np.ndarray:
        return anchor + direction * max(abs(anchor), 1.0) * 10.0**exponents

    finite_low, finite_high = math.isfinite(low), math.isfinite(high)
    parts: list[np.ndarray] = []
    if finite_low:
        parts += [np.array([low]), geometric(low, 1.0)]
    if finite_high:
        parts += [np.array([high]), geometric(high, -1.0)]
    if finite_low and finite_high:
        parts.append(np.linspace(low, high, LINEAR_SAMPLES))
    if low < 0.0 < high:
        parts += [np.array([0.0]), geometric(0.0, 1.0), geometric(0.0, -1.0)]
    samples = np.unique(np.concatenate(parts))
    return samples[(samples >= low) & (samples <= high)]


def _key(x: np.ndarray) -> np.ndarray:
    """Floats as ordered integers: adjacent floats have adjacent keys."""
    i = np.asarray(x, dtype=np.float64).view(np.int64)
    return np.where(i < 0, _INT64_MIN - i, i)


def _value(key: np.ndarray) -> np.ndarray:
    i = np.where(key < 0, _INT64_MIN - key, key)
    return np.asarray(i, dtype=np.int64).view(np.float64)


def _midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The float halfway between a and b in the order of floats.

    Down to adjacent floats in at most 64 halvings, whatever the scale: a
    root of 1e-200 in [-1, 1] is reached as one of 1.
    """
    ka, kb = _key(a), _key(b)
    return _value((ka >> 1) + (kb >> 1) + (ka & kb & 1))


def _residual(members: Members, x: np.ndarray, args: list[Any]) -> np.ndarray:
    with np.errstate(all="ignore"):
        left, right = members(x, *args)
        residual: np.ndarray = np.asarray(left, dtype=float) - np.asarray(
            right, dtype=float
        )
    return residual


def _finite_size(h: np.ndarray) -> np.ndarray:
    """|h|, 0 where h is not finite."""
    return np.where(np.isfinite(h), np.abs(h), 0.0)


def _bisect(
    members: Members,
    a: np.ndarray,
    b: np.ndarray,
    args: list[Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bisect brackets [a, b] (h of opposite signs at the ends).

    Returns the root found in each, NaN where it is rejected (a pole, a
    jump), and whether the residual was undefined inside.
    """
    h_a = _residual(members, a, args)
    # The largest finite residual at the ends: a pole sampled exactly
    # gives no scale.
    start = np.maximum(_finite_size(h_a), _finite_size(_residual(members, b, args)))
    undefined = np.zeros(a.shape, dtype=bool)
    exact = np.zeros(a.shape, dtype=bool)
    # 64 halvings reach adjacent floats: the loop always ends by its break.
    for _ in range(66):  # pragma: no branch
        middle = _midpoint(a, b)
        active = (middle != a) & (middle != b) & ~exact & ~undefined
        if not active.any():
            break
        h_m = _residual(members, middle, args)
        # An infinite residual has a sign (a pole); NaN has none.
        undefined |= active & np.isnan(h_m)
        exact_here = active & (h_m == 0)
        exact |= exact_here
        a = np.where(exact_here, middle, a)
        b = np.where(exact_here, middle, b)
        same = active & ~np.isnan(h_m) & ~exact_here & (np.sign(h_m) == np.sign(h_a))
        a = np.where(same, middle, a)
        h_a = np.where(same, h_m, h_a)
        other = active & ~np.isnan(h_m) & ~exact_here & ~same
        b = np.where(other, middle, b)
    h_a = _residual(members, a, args)
    h_b = _residual(members, b, args)
    root = np.where(np.abs(h_a) <= np.abs(h_b), a, b)
    with np.errstate(invalid="ignore"):
        end = np.maximum(np.abs(h_a), np.abs(h_b))
    kept = exact | (end <= COLLAPSE * start)
    return np.where(kept & ~undefined, root, np.nan), kept, undefined


def _edges(
    members: Members, x_in: np.ndarray, x_out: np.ndarray, args: list[Any]
) -> np.ndarray:
    """The last point where the residual is defined, from x_in towards x_out."""
    for _ in range(66):  # pragma: no branch
        middle = _midpoint(np.minimum(x_in, x_out), np.maximum(x_in, x_out))
        active = (middle != x_in) & (middle != x_out)
        if not active.any():
            break
        defined = ~np.isnan(_residual(members, middle, args))
        x_in = np.where(active & defined, middle, x_in)
        x_out = np.where(active & ~defined, middle, x_out)
    return x_in


def solve(
    members: Members, inputs: list[Any], low: float, high: float
) -> tuple[np.ndarray, np.ndarray]:
    """The root of left(y, *inputs) = right(y, *inputs) in [low, high].

    Parameters
    ----------
    members : callable
        ``members(y, *inputs)`` gives the two members, broadcast like y
        and the inputs (rows of inputs against columns of samples).
    inputs : list of array_like
        The values of the inputs, broadcast together.
    low, high : float
        The interval searched, one end possibly infinite.

    Returns
    -------
    roots : numpy.ndarray
        The root for each set of inputs, NaN where there is not exactly one.
    status : numpy.ndarray of int
        :data:`ONE`, :data:`NONE`, :data:`SEVERAL` or :data:`UNDETERMINED`.
    """
    arrays = [np.asarray(v, dtype=float) for v in inputs]
    shape = np.broadcast_shapes(*(a.shape for a in arrays)) if arrays else ()
    flat = [np.broadcast_to(a, shape).reshape(-1) for a in arrays]
    count = int(np.prod(shape)) if shape else 1
    samples = grid(low, high)
    roots = np.full(count, np.nan)
    status = np.full(count, NONE, dtype=np.int64)
    if samples.size == 0:
        return roots.reshape(shape), status.reshape(shape)
    step = max(1, MAX_ELEMENTS // samples.size)
    for start in range(0, count, step):
        stop = min(start + step, count)
        rows = np.arange(start, stop)
        block = [a[rows] for a in flat]
        x = np.broadcast_to(samples, (rows.size, samples.size))
        h = _residual(members, x, [b[:, None] for b in block])
        # Defined where not NaN: an infinite residual keeps its sign.
        finite = ~np.isnan(h)
        zeros = finite & (h == 0)
        pair_finite = finite[:, :-1] & finite[:, 1:]
        change = pair_finite & (np.sign(h[:, :-1]) * np.sign(h[:, 1:]) < 0)
        edge = finite[:, :-1] != finite[:, 1:]
        candidate_rows, candidate_a, candidate_b = [], [], []
        r, j = np.nonzero(change)
        candidate_rows.append(r)
        candidate_a.append(samples[j])
        candidate_b.append(samples[j + 1])
        r, j = np.nonzero(edge)
        if r.size:
            # The residual becomes undefined between two samples: its last
            # defined point may lie beyond a root (sqrt(3 - y) = 0.1).
            inside = finite[r, j]
            x_in = np.where(inside, samples[j], samples[j + 1])
            x_out = np.where(inside, samples[j + 1], samples[j])
            args = [b[r] for b in block]
            x_edge = _edges(members, x_in, x_out, args)
            h_edge = _residual(members, x_edge, args)
            h_in = h[r, np.where(inside, j, j + 1)]
            # A sample already zero is counted as such, not again here.
            crossing = (
                ~np.isnan(h_edge)
                & (h_in != 0)
                & ((np.sign(h_edge) * np.sign(h_in) < 0) | (h_edge == 0))
            )
            candidate_rows.append(r[crossing])
            # A zero at the edge is a bracket of one point.
            low_end = np.where(h_edge == 0, x_edge, np.minimum(x_in, x_edge))
            high_end = np.where(h_edge == 0, x_edge, np.maximum(x_in, x_edge))
            candidate_a.append(low_end[crossing])
            candidate_b.append(high_end[crossing])
        rows_c = np.concatenate(candidate_rows)
        found = np.zeros(rows.size, dtype=np.int64)
        undetermined = np.zeros(rows.size, dtype=bool)
        value = np.full(rows.size, np.nan)
        zero_count = zeros.sum(axis=1)
        if rows_c.size:
            a = np.concatenate(candidate_a)
            b = np.concatenate(candidate_b)
            root, kept, undefined = _bisect(
                members, a, b, [blk[rows_c] for blk in block]
            )
            accepted = kept & ~undefined
            np.add.at(found, rows_c[accepted], 1)
            np.logical_or.at(undetermined, rows_c[undefined], True)
            value[rows_c[accepted]] = root[accepted]
        has_zero = zeros.any(axis=1)
        first_zero = samples[np.argmax(zeros, axis=1)]
        value = np.where(has_zero & (found == 0), first_zero, value)
        total = found + zero_count
        block_status = np.where(
            undetermined,
            UNDETERMINED,
            np.where(total == 0, NONE, np.where(total == 1, ONE, SEVERAL)),
        )
        status[rows] = block_status
        roots[rows] = np.where(block_status == ONE, value, np.nan)
    return roots.reshape(shape), status.reshape(shape)
