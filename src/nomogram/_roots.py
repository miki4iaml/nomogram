# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The root of an implicit equation, for each set of inputs, vectorised.

The unknown is sought in an interval the caller derives from objective
domains (VIM 2.48, note 1: h(Y, X1, ..., Xn) = 0, Y the output). The
residual h = left - right is sampled on a grid; each change of sign
between two finite samples, each exact zero and each edge of a region
where the residual is undefined gives a candidate; each candidate's
bracket is narrowed down to adjacent floating-point numbers by
Chandrupatla's method (Chandrupatla, T. R., 1997, A new hybrid
quadratic/bisection algorithm for finding the zero of a nonlinear
function without using derivatives, Advances in Engineering Software
28(3), 145-149, doi:10.1016/S0965-9978(96)00051-8): inverse quadratic
interpolation where it is safe, halving otherwise, in the order of floats
rather than at the arithmetic middle. A candidate is kept as a root only
where the residual has collapsed there, to a millionth of its largest
finite value at the ends of the bracket: it stays as large across a jump
between pieces, and grows at a pole, which any bracketing method
otherwise converges to. The members' own
size plays no part, so that a member written 0 (h == 0) or computed by
cancellation of large terms does not hide a root. One root gives the
value; none, several, or a residual undefined inside a bracket give NaN,
with the reason.

Limits, by construction: two roots closer than the grid's step (a factor
of 10^(1/16) on a geometric grid, a 63rd of a finite interval on the
linear one) or a double root, without a change of sign, escape; on an
open interval, roots beyond 10^12 times the scale of the finite end are
not sought, nor, at the edge of a region where the residual is undefined,
a root closer to that edge than the grids' resolution (10^-12 times the
scale max(|x|, 1)), nor a root closer than about 10^-9 of its value to a
finite end of the interval, whose bracket is too narrow there for the
test of a jump below. A jump smaller than a millionth of the residual's change
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

#: The finest offset of the grids, relative to the scale max(|x|, 1).
RESOLUTION = 10.0 ** DECADES[0]

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


def _narrow(
    members: Members,
    low: np.ndarray,
    high: np.ndarray,
    h_low: np.ndarray,
    h_high: np.ndarray,
    args: list[Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Narrow brackets [low, high] down to adjacent floats (Chandrupatla, 1997).

    ``h_low`` and ``h_high``, the residuals at the ends, have opposite signs
    (or the bracket is one point, a zero). Each step tries an inverse
    quadratic interpolation through the last three points, where
    Chandrupatla's criterion holds it safe, and halves the bracket in the
    order of floats otherwise (:func:`_midpoint`): halving is forced after
    two interpolations that did not halve the bracket, so that adjacent
    floats are reached within about three times 64 steps. Only the brackets
    still open are evaluated at each step.

    Returns the root found in each, NaN where it is rejected (a pole, a
    jump), and whether the residual was undefined inside.
    """
    # The largest finite residual at the ends: a pole sampled exactly
    # gives no scale.
    start = np.maximum(_finite_size(h_low), _finite_size(h_high))
    # The ends of each bracket once closed, and why it closed.
    end_a, end_b = high.copy(), low.copy()
    end_fa, end_fb = h_high.copy(), h_low.copy()
    undefined = np.zeros(low.shape, dtype=bool)
    exact = np.zeros(low.shape, dtype=bool)
    # The brackets still open: Chandrupatla's points, a the newest, b the
    # other end of the bracket, c the previous a.
    index = np.arange(low.size)
    a, b, c = high.copy(), low.copy(), high.copy()
    fa, fb, fc = h_high.copy(), h_low.copy(), h_high.copy()
    interpolate = np.zeros(low.shape, dtype=bool)
    t = np.full(low.shape, 0.5)
    slow = np.zeros(low.shape, dtype=np.int64)
    lower, upper = np.minimum(a, b), np.maximum(a, b)
    middle = _midpoint(lower, upper)
    open_ = (middle != lower) & (middle != upper)
    for _ in range(4 * 66):  # pragma: no branch
        if not open_.all():
            # Close the brackets done: adjacent floats, an exact zero, or a
            # residual undefined inside.
            done = index[~open_]
            end_a[done], end_b[done] = a[~open_], b[~open_]
            end_fa[done], end_fb[done] = fa[~open_], fb[~open_]
            index, a, b, c = index[open_], a[open_], b[open_], c[open_]
            fa, fb, fc = fa[open_], fb[open_], fc[open_]
            interpolate, t, slow = interpolate[open_], t[open_], slow[open_]
            lower, upper, middle = lower[open_], upper[open_], middle[open_]
        if not index.size:
            break
        with np.errstate(all="ignore"):
            trial = a + t * (b - a)
        use = interpolate & (slow < 2) & (trial > lower) & (trial < upper)
        x = np.where(use, trial, middle)
        fx = _residual(members, x, [v[index] for v in args])
        # An infinite residual has a sign (a pole); NaN has none.
        nan = np.isnan(fx)
        undefined[index[nan]] = True
        zero = fx == 0
        exact[index[zero]] = True
        moved = ~nan & ~zero
        same = moved & (np.sign(fx) == np.sign(fa))
        other = moved & ~same
        width = upper - lower
        # Same sign as a: c takes a. Otherwise c takes b, and b takes a.
        c = np.where(same, a, np.where(other, b, c))
        fc = np.where(same, fa, np.where(other, fb, fc))
        b = np.where(other, a, np.where(zero, x, b))
        fb = np.where(other, fa, np.where(zero, 0.0, fb))
        a = np.where(nan, a, x)
        fa = np.where(nan, fa, fx)
        halved = np.abs(b - a) <= 0.5 * width
        slow = np.where(moved & use & ~halved, slow + 1, np.where(moved, 0, slow))
        with np.errstate(all="ignore"):
            xi = (a - b) / (c - b)
            phi = (fa - fb) / (fc - fb)
            interpolate = (phi**2 < xi) & ((1 - phi) ** 2 < 1 - xi)
            t = fa / (fb - fa) * fc / (fb - fc) + (c - a) / (b - a) * fa / (
                fc - fa
            ) * fb / (fc - fb)
        interpolate &= np.isfinite(t)
        lower, upper = np.minimum(a, b), np.maximum(a, b)
        middle = _midpoint(lower, upper)
        open_ = moved & (middle != lower) & (middle != upper)
    root = np.where(np.abs(end_fa) <= np.abs(end_fb), end_a, end_b)
    with np.errstate(invalid="ignore"):
        end = np.maximum(np.abs(end_fa), np.abs(end_fb))
    kept = exact | (end <= COLLAPSE * start)
    return np.where(kept & ~undefined, root, np.nan), kept, undefined


def _edges(
    members: Members, x_in: np.ndarray, x_out: np.ndarray, args: list[Any]
) -> np.ndarray:
    """The last point where the residual is defined, from x_in towards x_out.

    Sought to the resolution of the grids, 10^-12 times max(|x|, 1), not
    to adjacent floats: closer to a pole, an overflowing expression gives
    noise, whose sign is no crossing (IFS 3.25 as L tends to 0).
    """
    for _ in range(66):  # pragma: no branch
        middle = _midpoint(np.minimum(x_in, x_out), np.maximum(x_in, x_out))
        scale = np.maximum(np.maximum(np.abs(x_in), np.abs(x_out)), 1.0)
        wide = np.abs(x_out - x_in) > RESOLUTION * scale
        active = (middle != x_in) & (middle != x_out) & wide
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
        # The residuals at the ends, taken from the grid where they were.
        candidate_ha, candidate_hb = [], []
        r, j = np.nonzero(change)
        candidate_rows.append(r)
        candidate_a.append(samples[j])
        candidate_b.append(samples[j + 1])
        candidate_ha.append(h[r, j])
        candidate_hb.append(h[r, j + 1])
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
            at_zero = h_edge == 0
            edge_first = x_edge < x_in
            low_end = np.where(at_zero, x_edge, np.minimum(x_in, x_edge))
            high_end = np.where(at_zero, x_edge, np.maximum(x_in, x_edge))
            h_low = np.where(at_zero, 0.0, np.where(edge_first, h_edge, h_in))
            h_high = np.where(at_zero, 0.0, np.where(edge_first, h_in, h_edge))
            candidate_a.append(low_end[crossing])
            candidate_b.append(high_end[crossing])
            candidate_ha.append(h_low[crossing])
            candidate_hb.append(h_high[crossing])
        rows_c = np.concatenate(candidate_rows)
        found = np.zeros(rows.size, dtype=np.int64)
        undetermined = np.zeros(rows.size, dtype=bool)
        value = np.full(rows.size, np.nan)
        zero_count = zeros.sum(axis=1)
        if rows_c.size:
            a = np.concatenate(candidate_a)
            b = np.concatenate(candidate_b)
            root, kept, undefined = _narrow(
                members,
                a,
                b,
                np.concatenate(candidate_ha),
                np.concatenate(candidate_hb),
                [blk[rows_c] for blk in block],
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
