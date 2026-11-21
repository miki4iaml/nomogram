# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Monotonicity of a formulation in one input, proven by interval arithmetic.

:func:`monotonicity` tells whether the output of a formulation varies in
one direction with one of its inputs over a box of input values the
caller chooses. The derivative is bounded with the interval arithmetic of
mpmath (``mpmath.iv``), whose bounds are rigorous: on each sub-box where
the bounds of the derivative exclude zero, and those of the function are
finite (no pole), the sign is proven. The box is halved where the bounds
are too wide (geometrically where an interval spans decades), up to
:data:`BOX_BUDGET` sub-boxes. A point where the derivative has the
opposite sign refutes the claim.

The result is a property computed by nomogram, with its method and its
box: never a validity domain, which only a source or the physics states.
:func:`nomogram.inversion.invert` uses it to check that a formulation it
inverts numerically is monotonic over the interval searched.

A piecewise definition is split at the ends of its branches: each branch
is proven on its part of the box, and at each junction on the input the
value must not step back by more than :data:`JUNCTION_TOLERANCE` (the
rounding of its evaluation: a continuous junction evaluates equal only to
it); a larger step back refutes, and is measured. For an implicit
equation h(y, x) = 0, the derivative of the output is -h_x / h_y,
bounded over the whole box of the unknown and the inputs: that box holds
more than the solutions, so a change of sign there does not refute, and
the result is then unproven; a piecewise implicit equation is not tried.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import pairwise, product
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from nomogram.model import Formulation

__all__ = [
    "BOX_BUDGET",
    "JUNCTION_TOLERANCE",
    "Monotonicity",
    "monotonicity",
]

#: Sub-boxes examined before the proof is given up (unproven).
BOX_BUDGET = 2000

#: Relative step back allowed at a junction of a piecewise definition: the
#: rounding of its evaluation, by which a continuous junction differs.
JUNCTION_TOLERANCE = 1e-12

#: Relative width below which a sub-box is not halved again.
_RESOLUTION = 1e-9

#: How the proof is made, as :attr:`Monotonicity.method` says it.
_METHOD = "interval arithmetic (mpmath.iv) on the derivative"

Status = Literal["proven", "refuted", "unproven"]
Direction = Literal["increasing", "decreasing"]
Box = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Monotonicity:
    """Whether a formulation's output varies in one direction with an input.

    Computed by nomogram over a box the caller chose: a mathematical
    property of the expression there, not a validity domain.

    Attributes
    ----------
    status : {"proven", "refuted", "unproven"}
        ``"proven"`` when the output is strictly monotonic in the input
        over the whole box, in one direction for every value of the other
        inputs; ``"refuted"`` when the derivative has both signs, or a
        junction of a piecewise definition steps back; ``"unproven"``
        otherwise (bounds too wide within :data:`BOX_BUDGET` sub-boxes, a
        pole, a function the method cannot bound).
    direction : {"increasing", "decreasing"} or None
        The direction proven, or that of every branch when the only
        refutation is a step back at junctions; ``None`` otherwise.
    input : str
        The input in which monotonicity is examined.
    over : mapping of str to (float, float)
        The box, by identifier, in the units of the formulation; for an
        implicit equation it includes the interval of the unknown.
    method : str
        How the proof was made, and why it failed when it did.
    at : mapping of str to float
        Where a counterexample was found when refuted, by identifier.
    steps : mapping of float to float
        The junctions of a piecewise definition on the input where the
        value steps back against the direction of its branches by more
        than :data:`JUNCTION_TOLERANCE`: the largest step, relative to the
        value, by the input's value at the junction. The published
        coefficients of a standard atmosphere join its branches so, to
        about 1e-5.
    widths : mapping of float to float
        For each junction of ``steps``, the width of the interval of the
        input within which a value of the step is reached twice: the step
        divided by the smaller slope of the two branches there, in the
        input's unit, infinite where a branch is flat. The same step back
        weighs more where the slope is gentle: ITU-R P.835 steps back by
        9e-6 of its pressure at 11 km and 1.6e-5 at 71 km, 5.6 and 10.3 cm
        of altitude.
    """

    status: Status
    direction: Direction | None
    input: str
    over: Mapping[str, tuple[float, float]]
    method: str
    at: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    steps: Mapping[float, float] = field(default_factory=lambda: MappingProxyType({}))
    widths: Mapping[float, float] = field(default_factory=lambda: MappingProxyType({}))


def monotonicity(
    formulation: Formulation,
    input: str,
    over: Mapping[str, tuple[float, float]] | tuple[float, float],
    *,
    budget: int = BOX_BUDGET,
) -> Monotonicity:
    """Prove or refute that a formulation is monotonic in one input over a box.

    The function examined is the formulation's expression with its
    coefficients and constants, in its own units and scales, as
    :meth:`~nomogram.model.Formulation.evaluate` computes it before any
    conversion.

    Parameters
    ----------
    formulation : Formulation
        The formulation, explicit or implicit.
    input : str
        Identifier of the input.
    over : mapping of str to (float, float), or (float, float)
        The box: a finite interval for every input, in its unit; a pair
        alone for a formulation of one input. For an implicit equation,
        the interval of the output may be given too; it defaults to where
        the root is sought, which must then be finite.
    budget : int, optional
        Sub-boxes examined before giving up, for each branch.

    Returns
    -------
    Monotonicity
        The verdict, with its box and method.

    Raises
    ------
    ValueError
        If ``input`` is not an input of the formulation, an interval is
        missing, not finite or empty, or ``budget`` is not positive.
    """
    identifiers = [v.identifier for v in formulation.inputs]
    if input not in identifiers:
        msg = f"{formulation.key} has no input {input!r}"
        raise ValueError(msg)
    if budget < 1:
        msg = "budget must be positive"
        raise ValueError(msg)
    if not isinstance(over, Mapping):
        if len(identifiers) != 1:
            msg = f"{formulation.key} has several inputs: give an interval for each"
            raise ValueError(msg)
        over = {input: over}
    names = list(identifiers)
    output = formulation.output.identifier
    if formulation.implicit:
        names.insert(0, output)
        if output not in over:
            over = {**over, output: formulation._search_interval(None)}
    unknown = sorted(set(over) - set(names))
    if unknown:
        msg = f"{formulation.key} has no variable {', '.join(unknown)}"
        raise ValueError(msg)
    box = []
    for name in names:
        if name not in over:
            msg = f"{formulation.key}: give an interval for {name}"
            raise ValueError(msg)
        low, high = (float(v) for v in over[name])
        if not (math.isfinite(low) and math.isfinite(high) and low < high):
            msg = f"{formulation.key}: the interval of {name} must be finite and not empty"
            if name == output:
                msg += " (give the interval of the unknown in over)"
            raise ValueError(msg)
        box.append((low, high))
    status, sign, method, at, steps, widths = _prove(
        formulation, tuple(names), input, tuple(box), budget
    )
    return Monotonicity(
        status=status,
        direction=None if not sign else "increasing" if sign > 0 else "decreasing",
        input=input,
        over=MappingProxyType(dict(zip(names, box, strict=True))),
        method=method,
        at=MappingProxyType(dict(zip(names, at, strict=True)) if at else {}),
        steps=MappingProxyType(steps),
        widths=MappingProxyType(widths),
    )


Verdict = tuple[
    Status, int, str, tuple[float, ...] | None, dict[float, float], dict[float, float]
]


def _prove(
    formulation: Formulation,
    names: tuple[str, ...],
    input: str,
    box: Box,
    budget: int,
) -> Verdict:
    """The status, the sign of the branches, the method, a counterexample,
    and the steps back at junctions with their widths on the input."""
    import sympy

    from nomogram.expression import ExpressionError, _pieces

    pairs = [(c.identifier, c.value) for c in formulation.coefficients]
    pairs += [(k.identifier, k.value) for k in formulation.constants]
    values = {sympy.Symbol(name, real=True): value for name, value in pairs}
    symbols = tuple(sympy.Symbol(name, real=True) for name in names)
    variable = symbols[names.index(input)]
    if formulation.implicit:
        left, right = formulation.equation_members
        residual = (left - formulation._member_factor * right).xreplace(values)
        if residual.has(sympy.Piecewise):
            reason = "a piecewise implicit equation is not tried"
            return "unproven", 0, f"{_METHOD}: {reason}", None, {}, {}
        sign, _, reason = _sign_of(residual, symbols, variable, symbols[0], box, budget)
        if sign == 1 or sign == -1:
            method = f"{_METHOD} (-h_x / h_y, over the unknown too)"
            return "proven", sign, method, None, {}, {}
        # Over the unknown, the box holds more than the solutions: no refutation.
        reason = reason or "a change of sign over a box wider than the solutions"
        return "unproven", 0, f"{_METHOD}: {reason}", None, {}, {}
    expression = (
        formulation.sympy_expression.xreplace(values) * formulation.output_factor
    )
    nodes = sorted(
        {
            n
            for n in sympy.preorder_traversal(expression)
            if isinstance(n, sympy.Piecewise)
        },
        key=sympy.default_sort_key,
    )
    try:
        pieces = [_pieces(node, names) for node in nodes]
    except ExpressionError:
        reason = "a piecewise condition it cannot split"
        return "unproven", 0, f"{_METHOD}: {reason}", None, {}, {}
    # The ends of the branches inside the box, by variable.
    cuts: dict[Any, set[float]] = {s: set() for s in symbols}
    for branches in pieces:
        for piece in branches:
            k = symbols.index(piece.variable)
            for end in (piece.low, piece.high):
                end = float(end.xreplace(values))
                if box[k][0] < end < box[k][1]:
                    cuts[piece.variable].add(end)
    grids = [[box[k][0], *sorted(cuts[s]), box[k][1]] for k, s in enumerate(symbols)]
    signs: dict[int, tuple[float, ...]] = {}
    reasons = []
    smooth: dict[Box, Any] = {}
    for cell in product(*[list(pairwise(grid)) for grid in grids]):
        chosen = _branches(nodes, pieces, symbols, _middle(cell), values)
        if chosen is None:
            reason = "no branch holds in part of the box"
            return "unproven", 0, f"{_METHOD}: {reason}", None, {}, {}
        branch = expression
        # A definition nested in a branch is replaced once its parent is.
        for _ in range(len(nodes)):
            branch = branch.xreplace(chosen)
        smooth[cell] = branch
        sign, at, reason = _sign_of(branch, symbols, variable, None, cell, budget)
        if sign == 0:
            return "refuted", 0, f"{_METHOD}: the derivative changes sign", at, {}, {}
        if sign is None:
            reasons.append(reason)
            continue
        signs.setdefault(sign, _middle(cell))
        if len(signs) == 2:
            method = f"{_METHOD}: the derivative changes sign between branches"
            return "refuted", 0, method, signs[-sign], {}, {}
    if reasons:
        return "unproven", 0, f"{_METHOD}: {reasons[0]}", None, {}, {}
    (sign,) = signs
    k = symbols.index(variable)
    steps: dict[float, float] = {}
    widths: dict[float, float] = {}
    first: tuple[float, ...] | None = None
    for cut in grids[k][1:-1]:
        found = _junction(smooth, k, cut, sign, symbols, budget)
        if found is None:
            reason = f"the junction {input} = {cut!r} cannot be bounded"
            return "unproven", 0, f"{_METHOD}: {reason}", None, {}, {}
        step, at, width = found
        if step > 0:
            steps[cut], widths[cut] = step, width
            first = first or at
    if steps:
        method = (
            f"{_METHOD}: every branch is proven "
            f"{'increasing' if sign > 0 else 'decreasing'}, but the value steps "
            f"back at {len(steps)} junction(s)"
        )
        return "refuted", sign, method, first, steps, widths
    return "proven", sign, _METHOD, None, {}, {}


def _middle(cell: Box) -> tuple[float, ...]:
    """The centre of a box."""
    return tuple((low + high) / 2 for low, high in cell)


def _branches(
    nodes: list[Any],
    pieces: list[Any],
    symbols: tuple[Any, ...],
    middle: tuple[float, ...],
    values: Mapping[Any, float],
) -> dict[Any, Any] | None:
    """Each piecewise definition replaced by its branch at a point, or None."""
    chosen = {}
    for node, branches in zip(nodes, pieces, strict=True):
        for piece in branches:
            x = middle[symbols.index(piece.variable)]
            low = float(piece.low.xreplace(values))
            if low < x < float(piece.high.xreplace(values)):
                chosen[node] = piece.expression
                break
        else:
            return None
    return chosen


def _junction(
    smooth: Mapping[Box, Any],
    k: int,
    cut: float,
    sign: int,
    symbols: tuple[Any, ...],
    budget: int,
) -> tuple[float, tuple[float, ...], float] | None:
    """The largest relative step back at a junction on the input, 0 for none,
    with where it is and its width on the input; None when it cannot be
    bounded.

    A step back within :data:`JUNCTION_TOLERANCE` of the value counts as
    none: a continuous junction evaluates equal only to the rounding.
    """
    import sympy

    largest, width = 0.0, 0.0
    where: tuple[float, ...] = (cut,)
    for cell, before in smooth.items():
        if cell[k][1] != cut:
            continue
        after = next(
            e
            for c, e in smooth.items()
            if c[k][0] == cut
            and all(c[j] == cell[j] for j in range(len(cell)) if j != k)
        )
        point = {symbols[k]: sympy.Float(cut)}
        # Positive where the value goes the way of the branches.
        step = (sign * (after - before)).xreplace(point)
        size = abs(before.xreplace(point))
        others = tuple(c for j, c in enumerate(cell) if j != k)
        rest = tuple(s for j, s in enumerate(symbols) if j != k)
        margin = step + JUNCTION_TOLERANCE * size
        found, at, _ = _search(_interval_function(rest, (size, margin)), others, budget)
        if found == 1:
            continue
        if found is None and others:
            return None
        # The size of the step where it goes back, with the tight bounds of
        # a point.
        here = at if at is not None else _middle(others)
        exact = tuple((v, v) for v in here)
        low, _ = _enclosure(_interval_function(rest, (size, step)), exact)
        scale = _enclosure(_interval_function(rest, (size, size)), exact)[1]
        relative = -low / scale if scale > 0 else math.inf
        if relative > largest:
            largest, where = relative, (*here[:k], cut, *here[k:])
            width = -low / _slope((before, after), symbols, k, where)
    return largest, where, width


def _slope(
    sides: tuple[Any, Any], symbols: tuple[Any, ...], k: int, point: tuple[float, ...]
) -> float:
    """The smaller lower bound of the slopes of two branches at a point, in
    absolute value; 0 where one may be flat, or cannot be bounded."""
    exact = tuple((v, v) for v in point)
    smallest = math.inf
    for side in sides:
        derivative = _derivative(side, symbols[k], None)
        if derivative is None:
            return 0.0
        low, high = _enclosure(_interval_function(symbols, (side, derivative)), exact)
        smallest = min(smallest, low if low > 0 else -high if high < 0 else 0.0)
    return smallest


def _sign_of(
    expression: Any,
    symbols: tuple[Any, ...],
    variable: Any,
    unknown: Any,
    box: Box,
    budget: int,
) -> tuple[int | None, tuple[float, ...] | None, str]:
    """The sign of the derivative over the box: +1, -1, 0 (both, at a point), None.

    With ``unknown``, ``expression`` is the residual h of an implicit
    equation in that unknown, and the derivative of the solution is
    -h_x / h_y.
    """
    derivative = _derivative(expression, variable, unknown)
    if derivative is None:
        return None, None, "a function it cannot differentiate"
    if derivative == 0:
        return None, None, "a derivative identically zero"
    try:
        function = _interval_function(symbols, (expression, derivative))
    except (TypeError, ValueError, NameError, SyntaxError):
        return None, None, "a function it cannot bound"
    return _search(function, box, budget)


@lru_cache(maxsize=512)
def _derivative(expression: Any, variable: Any, unknown: Any) -> Any:
    """The derivative in ``variable``, -h_x / h_y with an ``unknown``, or None."""
    import sympy
    from sympy.core.function import AppliedUndef

    try:
        derivative = sympy.diff(expression, variable)
        if unknown is not None:
            derivative = -derivative / sympy.diff(expression, unknown)
    except (TypeError, ValueError, NotImplementedError):
        return None
    if derivative.has(sympy.Derivative) or derivative.atoms(AppliedUndef):
        return None
    return derivative


@lru_cache(maxsize=512)
def _interval_function(
    symbols: tuple[Any, ...], expressions: tuple[Any, ...]
) -> Callable[..., Any]:
    """The expressions as one function of intervals, returning a list.

    The first expression is the function, whose bounds must be finite; the
    last is the one whose sign is sought.
    """
    import sympy

    # Arguments renamed as nomogram.expression does, so that no identifier
    # (e, pi) can shadow a name of the generated code.
    renamed = [sympy.Symbol(f"_v_{s.name}", **s.assumptions0) for s in symbols]
    body = [e.xreplace(dict(zip(symbols, renamed, strict=True))) for e in expressions]
    return sympy.lambdify(renamed, body, modules=[_interval_namespace(), "mpmath"])  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def _interval_namespace() -> dict[str, Any]:
    """The functions of the expression syntax, on intervals."""
    import mpmath
    from mpmath import iv

    def increasing(function: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """An increasing function on intervals, its ends rounded outwards."""

        def bounded(value: Any) -> Any:
            value = iv.mpf(value)
            with mpmath.workprec(80):
                low = function(mpmath.mpf(float(value.a)))
                high = function(mpmath.mpf(float(value.b)))
            # 2**-50 is eight units in the last place of a double.
            return iv.mpf(
                [float(low - abs(low) * 2**-50), float(high + abs(high) * 2**-50)]
            )

        return bounded

    return {
        "mpf": lambda v: iv.mpf(mpmath.mpf(v)),
        "exp": iv.exp,
        "log": iv.log,
        "log10": iv.log10,
        "sqrt": iv.sqrt,
        "sin": iv.sin,
        "cos": iv.cos,
        "atan": increasing(mpmath.atan),
        "tanh": increasing(mpmath.tanh),
        "pi": iv.pi,
        "e": iv.e,
    }


def _enclosure(function: Callable[..., Any], box: Box) -> tuple[float, float]:
    """Bounds of the last value of the function over the box, (-inf, inf)
    where they cannot be computed or the bounds of the first are not finite."""
    from mpmath import iv

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            values = function(*[iv.mpf([low, high]) for low, high in box])
            first, last = iv.mpf(values[0]), iv.mpf(values[-1])
            ends = [float(first.a), float(first.b), float(last.a), float(last.b)]
    except (ValueError, ZeroDivisionError, OverflowError, TypeError, ArithmeticError):
        return -math.inf, math.inf
    if not all(math.isfinite(v) for v in ends[:2]) or any(math.isnan(v) for v in ends):
        return -math.inf, math.inf
    return ends[2], ends[3]


def _search(
    function: Callable[..., Any], box: Box, budget: int
) -> tuple[int | None, tuple[float, ...] | None, str]:
    """+1 or -1 when the last value keeps that sign over the box, 0 when it
    takes both (with a point of the sign found second), None when undecided,
    with why."""
    pending = [box]
    seen: dict[int, tuple[float, ...]] = {}
    examined, stuck = 0, ""
    while pending:
        current = pending.pop()
        examined += 1
        if examined > budget:
            return None, None, f"bounds too wide within {budget} sub-boxes"
        low, high = _enclosure(function, current)
        middle = _middle(current)
        if low > 0 or high < 0:
            seen.setdefault(1 if low > 0 else -1, middle)
        else:
            # The centre alone may show a sign the whole box does not.
            point_low, point_high = _enclosure(function, tuple((m, m) for m in middle))
            if point_low > 0 or point_high < 0:
                seen.setdefault(1 if point_low > 0 else -1, middle)
            widths = [(h - lo) / max(abs(lo), abs(h), 1.0) for lo, h in current]
            k = max(range(len(current)), key=widths.__getitem__)
            if widths[k] < _RESOLUTION:
                where = ", ".join(f"{m:.6g}" for m in middle)
                stuck = f"bounds too wide, or a pole, near {where}"
            else:
                pending.extend(_halves(current, k))
        if len(seen) == 2:
            return 0, list(seen.values())[1], ""
    if stuck or not seen:
        return None, None, stuck or "no sign"
    (sign,) = seen
    return sign, None, ""


def _halves(box: Box, k: int) -> tuple[Box, Box]:
    """Halve dimension k: geometrically where the interval spans decades of one sign."""
    low, high = box[k]
    if low > 0 and high / low > 10:
        middle = math.sqrt(low * high)
    elif high < 0 and low / high > 10:
        middle = -math.sqrt(low * high)
    else:
        middle = (low + high) / 2
    left, right = list(box), list(box)
    left[k], right[k] = (low, middle), (middle, high)
    return tuple(left), tuple(right)
