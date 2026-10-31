# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Verification of the relations between formulations stated by sources.

A relation of the catalog is a claim made by a source; :func:`verify`
checks it and returns a :class:`Verdict`:

- an **equivalence** is proved with SymPy: coefficients become exact
  rationals, each result is brought into the output unit of the subject,
  the object's inputs are replaced as the relation says (``given``) or
  by the subject inputs that feed them, converted by a factor where
  their units differ (hPa fed by Pa), and the difference must simplify
  to zero. If
  it does not, a numerical counterexample refutes the claim; without
  one, the equivalence is left unproven (equivalence of transcendental
  expressions is undecidable in general). Between formulations on
  different conventional scales, evaluated with conversion, it is
  unverified: the expressions cannot tell;
- an **approximation** is checked on a dense grid of the domain the
  source states: the maximum relative deviation found is compared with
  the stated one. The verdict says whether it is reproduced (to the
  precision published), held (smaller) or exceeded (larger); it is a
  check on points, never a proof. Points where the deviation is not
  finite are not compared, and the verdict says so; it is unverified
  when no point is left.

- a **proportionality** is proved like an equivalence, on the ratio of
  the two sides, which must simplify to a constant: the factor. If it
  does not, the ratio is sampled on the bounds: it holds when it varies
  no more than the rounding of the printed coefficients allows (half a
  unit of the last digit of each, through its effect on the ratio), and
  the verdict says what the factor is the ratio of, whether the two are
  even equal to the printed precision, and whether a shift or a factor
  of an input with a conventional scale would make them equal (a matter
  of scale rather than of coefficients).

A relation without a citation is computed by nomogram: an equivalence or
a proportionality it proves or holds. Deviations nomogram computes
without a source are observations, given by
:func:`nomogram.comparison.compare`; they never become relations.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import sympy

from nomogram.comparison import same_state
from nomogram.expression import (
    MAX_SOURCE_LENGTH,
    Piecewise,
    compile_numeric,
    parse_expression,
)
from nomogram.model import (
    CheckCase,
    ConstantNature,
    CrossCheck,
    Formulation,
    PhysicalConstant,
    Relation,
    RelationKind,
    Variable,
)
from nomogram.units import Q_, is_offset_unit

if TYPE_CHECKING:
    from nomogram.catalog import Catalog

__all__ = [
    "BUDGET",
    "VERIFIER",
    "Replay",
    "Verdict",
    "fingerprint",
    "form",
    "load_registry",
    "match_inputs",
    "per_axis",
    "record",
    "replay",
    "report",
    "signature",
    "verdict",
    "verify",
]

#: Relative difference below which two values are taken as equal, when
#: looking for a counterexample to an equivalence.
EQUALITY_TOLERANCE = 1e-9

#: Random samples looking for a counterexample to an equivalence.
SAMPLES = 200

Status = Literal[
    "proven", "refuted", "unproven", "reproduced", "held", "exceeded", "unverified"
]


@dataclass(frozen=True)
class Verdict:
    """The outcome of verifying a relation.

    Attributes
    ----------
    status : str
        ``"proven"``, ``"refuted"`` or ``"unproven"`` for an equivalence;
        ``"proven"``, ``"held"`` (to the printed precision of the
        coefficients) or ``"refuted"`` for a proportionality;
        ``"reproduced"``, ``"held"`` or ``"exceeded"`` for an
        approximation; ``"unverified"`` when the claim cannot be checked
        as it stands (an equivalence between formulations on different
        conventional scales, evaluated with conversion; an approximation
        whose deviation is finite nowhere on its domain), the method
        saying why.
    method : str
        How it was verified.
    value : float or None
        For an approximation, the maximum relative deviation found, in
        percent; for a proportionality, the factor; ``None`` when it is
        unverified or refuted.
    at : mapping of str to float
        Where that maximum lies, or where a counterexample was found, by
        input identifier of the subject.
    detail : str or None
        The simplified difference of an equivalence that is not proven;
        for a proportionality, what explains the factor, or the ratio when
        refuted.
    """

    status: Status
    method: str
    value: float | None = None
    at: Mapping[str, float] = MappingProxyType({})
    detail: str | None = None


def _printed_step(value: float) -> float:
    """Half a unit of the last significant digit: the rounding a value may hide.

    Read from the shortest text of the value, in any notation: 5.9e-06
    hides 5e-08, 6.112 hides 5e-04. The catalog keeps no text of its
    numbers, so an integral value is read without trailing zeros: 2.501e6
    hides 500, 72 hides 0.5.
    """
    digits = Decimal(repr(float(value)))
    if digits == digits.to_integral_value():
        digits = digits.normalize()
    exponent = digits.as_tuple().exponent
    return 0.5 * 10.0 ** int(exponent)


def _constant_step(constant: PhysicalConstant) -> float:
    """The rounding a constant may hide: none when exact, else its printed digits."""
    if constant.nature is ConstantNature.EXACT:
        return 0.0
    if constant.printed is not None:
        return 0.5 * 10.0 ** int(Decimal(constant.printed).as_tuple().exponent)
    return _printed_step(constant.value)


#: Evaluations of the first grid of an approximation, all in one
#: vectorised pass.
BUDGET = 200_000

#: Points per axis at most: a step of 0.01 degC over -40..50 degC.
MAX_PER_AXIS = 9001

#: Best points of the grid around which the maximum is refined.
CANDIDATES = 5

#: Zoom steps of the refinement at most, points of each step, and the
#: fraction of the domain at which it stops.
ZOOMS = 8
ZOOM_POINTS = 2_000
RESOLUTION = 1e-9


def _canonical(formulation: Formulation, *, keep_coefficients: bool) -> str:
    """The expression with canonical input names, as SymPy writes it.

    Inputs are renamed by quantity kind and unit; when several share both,
    every order is tried and the smallest text kept, so that the result
    does not depend on the identifiers chosen by the source.
    """
    expr = _numbers(formulation, keep_coefficients=keep_coefficients)
    groups = _input_groups(formulation)
    texts: list[str] = []
    for orders in itertools.product(
        *(itertools.permutations(groups[k]) for k in sorted(groups))
    ):
        renaming = {}
        for index, name in enumerate(n for order in orders for n in order):
            renaming[sympy.Symbol(name, real=True)] = sympy.Symbol(f"x{index}")
        texts.append(str(sympy.srepr(expr.xreplace(renaming))))
    return _head(formulation, keep_coefficients=keep_coefficients) + "|" + min(texts)


def _numbers(formulation: Formulation, *, keep_coefficients: bool) -> Any:
    """The expression, its coefficients and constants as exact rationals or ``c``."""
    expr = formulation.sympy_expression
    if keep_coefficients:
        pairs = [(c.identifier, c.value) for c in formulation.coefficients]
        pairs += [(k.identifier, k.value) for k in formulation.constants]
        return expr.xreplace(
            {sympy.Symbol(n, real=True): sympy.Rational(repr(v)) for n, v in pairs}
        )
    names = [c.identifier for c in formulation.coefficients]
    names += [k.identifier for k in formulation.constants]
    return expr.xreplace({sympy.Symbol(n, real=True): sympy.Symbol("c") for n in names})


#: Relative gap under which two shapes are alike (:func:`_alike`).
SHAPE_TOLERANCE = 1e-6


def _shape(formulation: Formulation) -> Any:
    """A fingerprint that does not depend on the names of the inputs.

    The values of the formulation for every order of distinct probe values
    among the inputs of one kind and unit, sorted: cheap where the
    signature rewrites the expression for every order. Two writings of
    one formulation round differently, so shapes compare within a
    tolerance (:func:`_alike`); alike ones still need their signatures
    compared.
    """
    groups = _input_groups(formulation)
    function = compile_numeric(formulation.sympy_expression, formulation.names)
    fixed = [c.value for c in formulation.coefficients]
    fixed += [float(k.value) for k in formulation.constants]
    position = {v.identifier: i for i, v in enumerate(formulation.inputs)}
    values = []
    with np.errstate(all="ignore"):
        for orders in itertools.product(
            *(itertools.permutations(groups[g]) for g in sorted(groups))
        ):
            arguments = [0.0] * len(position)
            for index, order in enumerate(orders):
                for rank, name in enumerate(order):
                    arguments[position[name]] = 250.0 + 10.0 * (rank + 1) + 3.0 * index
            try:
                value = float(function(*arguments, *fixed))
            except (ArithmeticError, TypeError, ValueError):
                value = float("nan")
            values.append(value)
    return np.sort(np.array(values))


def _alike(shape: Any, other: Any) -> bool:
    """Whether two shapes of formulations of one head may be one formulation.

    Alike within :data:`SHAPE_TOLERANCE`, relative: two writings of one
    expression round differently, by a few ulps, more where terms cancel
    at the probe values. Beyond, they are taken as two formulations: a
    cancellation that loses more than six digits at every probe value
    would hide a duplicate from this prefilter.
    """
    return bool(
        shape.shape == other.shape
        and np.allclose(shape, other, rtol=SHAPE_TOLERANCE, atol=0.0, equal_nan=True)
    )


def _input_groups(formulation: Formulation) -> dict[tuple[str, str], list[str]]:
    """The identifiers of the inputs, by quantity kind and unit."""
    groups: dict[tuple[str, str], list[str]] = {}
    for variable in formulation.inputs:
        groups.setdefault((variable.kind, variable.unit), []).append(
            variable.identifier
        )
    return groups


def _head(formulation: Formulation, *, keep_coefficients: bool = True) -> str:
    """What two writings of one formulation share before their expression.

    The kind and unit of the output and of the inputs, and the values and
    units of the coefficients and constants: cheap to compute, so that the
    canonical expression is needed only where heads meet.
    """
    groups = _input_groups(formulation)
    parts = [
        formulation.output.kind,
        formulation.output.unit,
        str(formulation.fixed_units),
    ]
    parts += [
        f"{kind} {unit} x{len(groups[(kind, unit)])}" for kind, unit in sorted(groups)
    ]
    if keep_coefficients:
        # The units of coefficients and constants set the factor that brings
        # a quantity equation into its output unit.
        units = [f"{c.value!r} {c.unit}" for c in formulation.coefficients]
        units += [f"{k.value!r} {k.unit}" for k in formulation.constants]
        parts.append(" ".join(sorted(units)))
    return "|".join(parts)


def signature(formulation: Formulation) -> str:
    """A fingerprint of a formulation: equal for two writings of the same one.

    Same quantity kinds and units, same expression once inputs are named
    canonically and coefficients written as exact rationals (6.112 and
    6.1120 are the same number); SymPy's own simplifications apply (a
    coefficient C gives ``exp(ln(C) + x) = C * exp(x)``). Two forms equal
    only after further algebra (``A * t / (B + t)`` and
    ``A - A * B / (B + t)``) have different signatures.
    """
    text = _canonical(formulation, keep_coefficients=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def form(formulation: Formulation) -> str:
    """A fingerprint of the form alone: coefficients and constants left aside.

    Equal for the Magnus forms of Sonntag, Bolton or Alduchov and Eskridge,
    which differ only by their coefficients.
    """
    text = _canonical(formulation, keep_coefficients=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def match_inputs(subject: Formulation, other: Formulation) -> dict[str, str]:
    """Which input of the subject feeds each input of the object.

    By identifier first, then by quantity kind when a single input of the
    subject has a matching kind (a Celsius temperature feeds a
    thermodynamic one). An input left without match is absent from the
    result.
    """
    names = {v.identifier: v for v in subject.inputs}
    matched = {}
    for variable in other.inputs:
        if variable.identifier in names:
            matched[variable.identifier] = variable.identifier
            continue
        candidates = [
            v.identifier for v in subject.inputs if same_state(v.kind, variable.kind)
        ]
        if len(candidates) == 1:
            matched[variable.identifier] = candidates[0]
    return matched


def per_axis(dimensions: int, budget: int = BUDGET) -> int:
    """Points per axis of the first grid, for a number of input variables."""
    return int(min(MAX_PER_AXIS, max(5, int(budget ** (1 / dimensions) + 1e-9))))


def _approximation(
    relation: Relation, subject: Formulation, other: Formulation, budget: int
) -> tuple[Verdict, float]:
    """The verdict on an approximation, and the share of the grid compared.

    Points where the deviation is not finite (a formulation undefined
    there, or beyond the bounds of a scale conversion) are not compared;
    the method says so when there are some.
    """
    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    names = [v.identifier for v in subject.inputs]
    low = np.array([relation.bounds[n][0] for n in names])
    high = np.array([relation.bounds[n][1] for n in names])

    feeds = match_inputs(subject, other)

    def deviation(points: Any) -> Any:
        """Relative deviation in percent at points (one row per point)."""
        arguments: dict[str, Any] = {
            v.identifier: Q_(points[:, i], units[v.unit].pint)
            for i, v in enumerate(subject.inputs)
        }
        mine = subject.evaluate(outside="ignore", scale=relation.scale, **arguments)
        theirs = other.evaluate(
            outside="ignore",
            scale=relation.scale,
            **{name: arguments[source] for name, source in feeds.items()},
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.asarray(mine.magnitude) / np.asarray(
                theirs.to(mine.units).magnitude
            )
        return np.abs(ratio - 1) * 100

    def ranked(values: Any) -> Any:
        """Deviations to rank: a point not compared ranks last."""
        return np.where(np.isfinite(values), values, -np.inf)

    def grid(lower: Any, upper: Any, count: int) -> Any:
        axes = [np.linspace(a, b, count) for a, b in zip(lower, upper, strict=True)]
        mesh = np.meshgrid(*axes, indexing="ij")
        return np.stack([m.ravel() for m in mesh], axis=1)

    count = per_axis(len(names), budget)
    first = grid(low, high, count)
    values = deviation(first)
    evaluations = len(first)
    compared = np.isfinite(values)
    share = float(np.mean(compared))
    if not compared.any():
        method = (
            f"no point of a grid of {count} points per axis ({len(names)} "
            "input(s)) where both formulations give a finite value; "
            f"scale {relation.scale}"
        )
        return Verdict("unverified", method), share
    order = np.argsort(ranked(values))[::-1][:CANDIDATES]
    best_points = first[order[compared[order]]]
    step = (high - low) / (count - 1)
    zoom = max(3, int(ZOOM_POINTS ** (1 / len(names)) + 1e-9))
    found, where = -np.inf, best_points[0]
    for centre in best_points:
        half = step.copy()
        span = np.where(high > low, high - low, 1.0)
        for _ in range(ZOOMS):
            if np.max(half / span) <= RESOLUTION:
                break
            local = grid(
                np.maximum(low, centre - half), np.minimum(high, centre + half), zoom
            )
            local_values = ranked(deviation(local))
            evaluations += len(local)
            best = int(np.argmax(local_values))
            if np.isfinite(local_values[best]):
                centre = local[best]
            half = half * 2 / (zoom - 1)
        value = float(deviation(centre[None, :])[0])
        if value > found:
            found, where = value, centre
    at = MappingProxyType({n: float(x) for n, x in zip(names, where, strict=True)})
    claimed = float(relation.accuracy or 0.0)
    tolerance = _printed_step(claimed)
    if abs(found - claimed) <= tolerance:
        status: Status = "reproduced"
    elif found < claimed:
        status = "held"
    else:
        status = "exceeded"
    resolution = float(np.max(half / span))
    method = (
        f"maximum relative deviation: grid of {count} points per axis "
        f"({len(names)} input(s)), refined around the {CANDIDATES} best points "
        f"down to {resolution:.1e} of the domain; {evaluations} evaluations; "
        f"scale {relation.scale}"
    )
    if share < 1:
        method += (
            f"; deviation finite on {100 * share:.4g} % of the grid only, "
            "the other points not compared"
        )
    return Verdict(status, method, found, at), share


def _exact(value: float) -> Any:
    """A float as the simplest rational within its rounding (0.001, not 0.0010...02).

    A factor between units computed in floating point is a ratio of small
    integers or powers of ten; the first rational close enough is it.
    """
    exact = Fraction(repr(value))
    for digits in range(1, 19):
        found = exact.limit_denominator(10**digits)
        if abs(found - exact) <= 1e-13 * abs(exact):
            return sympy.Rational(found.numerator, found.denominator)
    return sympy.Rational(exact.numerator, exact.denominator)


def _unit_factor(source: str, target: str) -> Any:
    """The exact factor bringing a value from one unit of the catalog into another.

    Raises
    ------
    ValueError
        When no factor does: the dimensions differ, or a unit carries an
        offset (``DEG_C``). That conversion is affine, and its origin
        (0 degC at 273.15 or 273.16 K) is what a relation states with
        ``given``.
    """
    if source == target:
        return sympy.Integer(1)
    from pint.errors import DimensionalityError

    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    start, end = units[source].pint, units[target].pint
    if is_offset_unit(start) or is_offset_unit(end):
        msg = f"{source} and {target} differ by an offset"
        raise ValueError(msg)
    try:
        return _exact(float(Q_(1.0, start).to(end).magnitude))
    except DimensionalityError:
        msg = f"{source} and {target} have different dimensions"
        raise ValueError(msg) from None


def _rational(formulation: Formulation) -> Any:
    """The result in the output unit, with exact numbers, coefficients and constants.

    A quantity equation gives its result in the units of its inputs, which
    :attr:`~nomogram.model.Formulation.output_factor` brings into the
    output unit (1 for fixed units): the factor is part of the result.
    """
    expr = parse_expression(
        formulation.expression,
        formulation.names,
        exact=True,
        limit=formulation._source_limit,
    )
    pairs = [(c.identifier, c.value) for c in formulation.coefficients]
    pairs += [(k.identifier, k.value) for k in formulation.constants]
    values = {
        sympy.Symbol(name, real=True): sympy.Rational(repr(value))
        for name, value in pairs
    }
    return _exact(formulation.output_factor) * expr.xreplace(values)


def _scale_name(variable: Variable) -> str:
    return "no scale" if variable.scale is None else variable.scale.key


def _scale_differences(
    relation: Relation, subject: Formulation, other: Formulation
) -> list[str]:
    """Where the object and the subject feeding it are on different scales.

    The reference scale of a kind and no scale are evaluated alike
    (without conversion), so they count as the same.
    """

    def key(variable: Variable) -> str | None:
        scale = variable.scale
        return None if scale is None or scale.is_reference else scale.key

    names = {v.identifier: v for v in subject.inputs}
    matched = match_inputs(subject, other)
    found = []
    if key(subject.output) != key(other.output):
        found.append(
            f"output on {_scale_name(subject.output)} and {_scale_name(other.output)}"
        )
    for variable in other.inputs:
        if variable.identifier in relation.given:
            expr = parse_expression(relation.given[variable.identifier], sorted(names))
            sources = sorted(s.name for s in expr.free_symbols)
        else:
            sources = (
                [matched[variable.identifier]] if variable.identifier in matched else []
            )
        found += [
            f"{variable.identifier} on {_scale_name(variable)} fed by {s} on "
            f"{_scale_name(names[s])}"
            for s in sources
            if key(names[s]) != key(variable)
        ]
    return found


def _real(expr: Any, sample: Mapping[Any, float]) -> float | None:
    """The value of an expression at a sample, ``None`` unless real and finite."""
    try:
        value = complex(expr.xreplace(sample))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(value.real) and math.isfinite(value.imag)):
        return None
    if abs(value.imag) > EQUALITY_TOLERANCE * max(abs(value.real), 1.0):
        return None
    return value.real


def _same_conditions(left: Any, right: Any) -> bool:
    """Whether two piecewise definitions have the same conditions, in order."""
    return (
        isinstance(left, sympy.Piecewise)
        and isinstance(right, sympy.Piecewise)
        and [c for _, c in left.args] == [c for _, c in right.args]
    )


def _written(subject: Formulation, other: Formulation) -> bool:
    """Whether both expressions are of a written length, which SymPy simplifies.

    SymPy's simplification has no bound on its cost: an expression longer
    than a written one (a derived formulation) is decided on samples.
    """
    return max(len(subject.expression), len(other.expression)) <= MAX_SOURCE_LENGTH


def _difference(left: Any, right: Any, *, simplify: bool = True) -> Any:
    """The difference of two expressions, simplified where it surely ends.

    Piecewise definitions with the same conditions are compared branch by
    branch; otherwise their difference is not simplified (SymPy would
    combine the conditions, at a cost without bound), and the search for a
    counterexample on samples decides. So it goes with ``simplify=False``,
    for expressions longer than a written one.
    """
    if _same_conditions(left, right):
        branches = [
            _difference(a, b, simplify=simplify)
            for (a, _), (b, _) in zip(left.args, right.args, strict=True)
        ]
        if all(branch == 0 for branch in branches):
            return sympy.Integer(0)
        conditions = [c for _, c in left.args]
        return Piecewise(*zip(branches, conditions, strict=True))
    difference = sympy.nsimplify(left - right, rational=True)
    if not simplify or left.has(sympy.Piecewise) or right.has(sympy.Piecewise):
        return difference
    return sympy.simplify(difference)


def _sides(
    relation: Relation, subject: Formulation, other: Formulation
) -> tuple[Any, Any, dict[Any, Any]]:
    """The subject and the object, fed by the subject, and the replacements made.

    The object is brought into the units of the subject: its result into
    the output unit of the subject, and each input fed by a subject input
    in another unit receives it converted (``p`` in hPa fed by ``P`` in
    Pa becomes ``P / 100``). The loader has checked that a factor gives
    each of these conversions.
    """
    names = [v.identifier for v in subject.inputs]
    units = {v.identifier: v.unit for v in subject.inputs}
    replacements = {
        sympy.Symbol(identifier, real=True): parse_expression(source, names, exact=True)
        for identifier, source in relation.given.items()
    }
    # An input of the object fed by a subject input of another identifier
    # (Q fed by P, the only pressure of the subject) takes its symbol.
    feeds = match_inputs(subject, other)
    for variable in other.inputs:
        source = feeds.get(variable.identifier)
        if source is None or variable.identifier in relation.given:
            continue
        factor = _unit_factor(units[source], variable.unit)
        if variable.identifier != source or factor != 1:
            replacements[sympy.Symbol(variable.identifier, real=True)] = (
                factor * sympy.Symbol(source, real=True)
            )
    output = _unit_factor(other.output.unit, subject.output.unit)
    right = output * _rational(other).xreplace(replacements)
    return _rational(subject), right, replacements


def _equivalence(
    relation: Relation, subject: Formulation, other: Formulation, points: int
) -> Verdict:
    method = "symbolic difference simplified with SymPy, exact rationals"
    differences = _scale_differences(relation, subject, other)
    if differences and relation.scale == "convert":
        return Verdict(
            "unverified",
            "an equivalence is proved on the expressions as written, which "
            "evaluated with conversion of conventional scales needs the same "
            f'scales: {"; ".join(differences)}; state scale = "ignore" to '
            "compare the expressions as written",
        )
    if differences:
        method += f"; scales ignored: {'; '.join(differences)}"
    left, right, _ = _sides(relation, subject, other)
    if left.has(sympy.Piecewise) or right.has(sympy.Piecewise):
        method += (
            "; piecewise definitions compared branch by branch"
            if _same_conditions(left, right)
            else "; piecewise definitions not simplified, compared on samples"
        )
    written = _written(subject, other)
    if not written:
        method = method.replace("simplified with SymPy", "compared on samples")
        method += "; an expression longer than a written one is not simplified"
    simplified = _difference(left, right, simplify=written)
    if simplified == 0:
        return Verdict("proven", method)
    # Look for a counterexample on positive values, or on the stated domain,
    # where both sides are real: outside, the formulations mean nothing.
    symbols = sorted(simplified.free_symbols | left.free_symbols, key=lambda s: s.name)
    random = np.random.default_rng(0)
    valid = 0
    for _ in range(points):
        sample = {
            s: (
                random.uniform(*relation.bounds[s.name])
                if s.name in relation.bounds
                else random.uniform(0.5, 2.0)
            )
            for s in symbols
        }
        value = _real(left, sample)
        gap = _real(simplified, sample)
        if value is None or gap is None:
            continue
        valid += 1
        if abs(gap) > EQUALITY_TOLERANCE * (abs(value) or 1.0):
            at = MappingProxyType({s.name: float(v) for s, v in sample.items()})
            return Verdict(
                "refuted",
                method + "; numerical counterexample",
                None,
                at,
                str(simplified),
            )
    if valid == points:
        method += "; no counterexample found"
    elif valid == 0:
        method += f"; no counterexample: none of {points} samples is real and finite"
    else:
        method += (
            f"; no counterexample found among the {valid} of {points} samples "
            "real and finite"
        )
    return Verdict("unproven", method, detail=str(simplified))


#: Share of the variation of a ratio, or of its distance from 1, that moving
#: one coefficient within its rounding may leave: a rest of second order.
UNEXPLAINED = 1e-3


def _sensitivities(
    formulation: Formulation, replacements: Mapping[Any, Any], sign: int
) -> list[tuple[str, Any, float]]:
    """For each coefficient and constant, d(sign * ln f)/dc and its printed step."""
    expr = formulation.sympy_expression.xreplace(replacements)
    pairs = [
        (c.identifier, c.value, _printed_step(c.value))
        for c in formulation.coefficients
    ]
    pairs += [(k.identifier, k.value, _constant_step(k)) for k in formulation.constants]
    values = {
        sympy.Symbol(name, real=True): sympy.Rational(repr(value))
        for name, value, _ in pairs
    }
    found = []
    for name, value, step in pairs:
        derivative = sign * sympy.diff(sympy.log(expr), sympy.Symbol(name, real=True))
        label = f"{name} of {formulation.key} ({value!r})"
        found.append((label, derivative.xreplace(values), step))
    return found


def _samples(
    relation: Relation, subject: Formulation, points: int
) -> tuple[list[Any], list[Any]]:
    """The input symbols of the subject, and random points of the bounds."""
    symbols = [sympy.Symbol(v.identifier, real=True) for v in subject.inputs]
    random = np.random.default_rng(0)
    return symbols, [random.uniform(*relation.bounds[s.name], points) for s in symbols]


def _absorbed(target: Any, effect: Any, step: float) -> Any:
    """What is left of ``target`` once a coefficient moves within its rounding.

    The move is the least-squares one along ``effect``, the change of the
    log ratio per unit of the coefficient, held within plus or minus
    ``step``.
    """
    norm = float(effect @ effect)
    move = 0.0 if norm == 0 else float(np.clip(-(target @ effect) / norm, -step, step))
    return target + move * effect


def _ratio_check(
    relation: Relation,
    subject: Formulation,
    other: Formulation,
    catalog: Catalog,
    left: Any,
    right: Any,
    replacements: Mapping[Any, Any],
    points: int,
) -> tuple[Status, float | None, str, Mapping[str, float], float]:
    """The ratio on samples of the bounds, against the printed precision.

    The ratio holds as constant when moving one printed coefficient within
    its rounding (half a unit of its last digit) takes its variation away,
    to a rest of second order (:data:`UNEXPLAINED`); the verdict names the
    finest such coefficient. The two are equal to the printed precision
    when such a move takes the ratio to 1. Points where a side is zero or
    not finite are left aside; a ratio that changes sign is refuted.
    Returns the status, the factor, what explains it (or why it is
    refuted), where it strays most, and the share of the samples compared.
    """
    symbols, columns = _samples(relation, subject, points)
    function = sympy.lambdify(symbols, left / right, "numpy")
    with np.errstate(all="ignore"):
        ratios = np.broadcast_to(np.asarray(function(*columns), dtype=float), (points,))
    usable = np.isfinite(ratios) & (ratios != 0)
    share = float(np.mean(usable))
    if not usable.any():
        return "unverified", None, "", MappingProxyType({}), share
    ratios = ratios[usable]
    columns = [c[usable] for c in columns]

    def where(index: int) -> Mapping[str, float]:
        return MappingProxyType(
            {s.name: float(c[index]) for s, c in zip(symbols, columns, strict=True)}
        )

    signs = np.sign(ratios)
    if (signs != signs[0]).any():
        return (
            "refuted",
            None,
            "the ratio changes sign",
            where(int(np.argmax(signs != signs[0]))),
            share,
        )
    logs = np.log(np.abs(ratios))
    middle = float(np.median(logs))
    factor = float(signs[0]) * math.exp(middle)
    spread = float(logs.max() - logs.min())
    residual = float(np.abs(logs - middle).max())
    centred = logs - logs.mean()
    explaining: list[tuple[float, str]] = []
    equalling: list[tuple[float, str]] = []
    sensitivities = _sensitivities(subject, {}, 1) + _sensitivities(
        other, replacements, -1
    )
    for label, derivative, step in sensitivities:
        if step == 0:
            continue
        function = sympy.lambdify(symbols, derivative, "numpy")
        with np.errstate(all="ignore"):
            values = np.broadcast_to(
                np.asarray(function(*columns), dtype=float), logs.shape
            )
        # Where the sensitivity is not finite, it tells nothing.
        values = np.where(np.isfinite(values), values, 0.0)
        rest = _absorbed(centred, values - values.mean(), step)
        if float(rest.max() - rest.min()) <= max(
            UNEXPLAINED * spread, EQUALITY_TOLERANCE
        ):
            explaining.append((float(values.max() - values.min()) * step, label))
        rest = _absorbed(logs, values, step)
        if float(np.abs(rest).max()) <= max(
            UNEXPLAINED * abs(middle), EQUALITY_TOLERANCE
        ):
            equalling.append((float(np.abs(values).max()) * step, label))
    held = spread <= EQUALITY_TOLERANCE or bool(explaining)
    if not held:
        worst = int(np.argmax(np.abs(logs - middle)))
        return "refuted", None, "", where(worst), share
    text, ratio_of = _factor_text(factor, subject, other, spread)
    parts = [text]
    if explaining:
        allowance, label = min(explaining)
        parts.append(
            f"the ratio varies by {spread:.2g}, which the rounding of {label} "
            f"explains (up to {allowance:.2g})"
        )
    else:
        parts.append(
            f"the ratio varies by {spread:.2g} only, within the precision of "
            "the computation"
        )
    # A factor that is the ratio of two coefficients is explained by theirs
    # first.
    equal = min([e for e in equalling if e[1] in ratio_of] or equalling, default=None)
    if equal is not None:
        parts.append(
            f"equivalent to the printed precision: |ln factor| = "
            f"{abs(middle):.2g}, which the rounding of {equal[1]} explains "
            f"(up to {equal[0]:.2g})"
        )
    parts.append(_scale_text(subject, catalog, symbols, columns, left, right, residual))
    return "held", factor, "; ".join(parts), MappingProxyType({}), share


def _factor_text(
    factor: float, subject: Formulation, other: Formulation, spread: float = 0.0
) -> tuple[str, tuple[str, ...]]:
    """The factor, its deviation, and the two coefficients it is the ratio of.

    A proven factor is constant; a sampled one is the median of a ratio
    that varies by ``spread``, and it is the ratio of two coefficients
    only within their printed rounding. Two equal coefficients give no
    factor. A coefficient of the object is brought into the output unit of
    the subject (611.21 Pa is 6.1121 hPa).
    """
    deviation = f"{100 * abs(1 - factor):.2g} %"
    text = (
        f"factor {factor:.8g}, a constant relative deviation of {deviation}"
        if not spread
        else f"factor {factor:.8g}, the median of the sampled ratio, a relative "
        f"deviation of {deviation}"
    )
    unit = float(_unit_factor(other.output.unit, subject.output.unit))
    converted = (
        "" if unit == 1 else f", {other.output.unit} brought into {subject.output.unit}"
    )

    def values(formulation: Formulation) -> list[tuple[str, float]]:
        pairs = [(c.identifier, c.value) for c in formulation.coefficients]
        return pairs + [(k.identifier, k.value) for k in formulation.constants]

    for (a, x), (b, y) in itertools.product(values(subject), values(other)):
        if not x or not y or x == y * unit:
            continue
        allowed = (
            max(1e-9, _printed_step(x) / abs(x) + _printed_step(y) / abs(y))
            if spread
            else 1e-9
        )
        if abs(x / (y * unit) - factor) <= allowed * abs(factor):
            labels = (f"{a} of {subject.key} ({x!r})", f"{b} of {other.key} ({y!r})")
            found = (
                f"{text}, the ratio of {a} of {subject.key} to {b} of "
                f"{other.key} ({x!r} / {y!r}{converted})"
            )
            return found, labels
    return text, ()


def _scale_windows(
    variable: Variable, values: Any, catalog: Catalog
) -> tuple[float, float]:
    """How far the catalog's scales move an input, as a shift and as a factor.

    The largest difference, over the samples, between a value on a scale
    applying to the input and the same value on the reference scale: as a
    shift in the unit of the input, and as a relative factor. A temperature
    may also be shifted by 0.01 K, a Celsius origin written 273.16 K.
    """
    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    unit = units[variable.unit].pint
    shift = factor = 0.0
    for scale in catalog.scales.values():
        if scale.is_reference or not scale.convertible or scale.unit is None:
            continue
        if not scale.applies_to(variable.kind, catalog.kinds):
            continue
        own = units[scale.unit].pint
        on_reference = scale.to_reference(Q_(values, unit).to(own).magnitude)
        back = Q_(on_reference, own).to(unit).magnitude
        with np.errstate(all="ignore"):
            moved = np.abs(back - values)
            scaled = np.abs(back / values - 1)
        if np.isfinite(moved).any():
            shift = max(shift, float(np.nanmax(moved)))
        if np.isfinite(scaled).any():
            factor = max(factor, float(np.nanmax(scaled)))
    if Q_(1.0, unit).dimensionality == Q_(1.0, "K").dimensionality:
        kelvin = Q_(1.0, unit).to("K").magnitude - Q_(0.0, unit).to("K").magnitude
        shift += 0.01 / kelvin
    return shift, factor


def _scale_text(
    subject: Formulation,
    catalog: Catalog,
    symbols: list[Any],
    columns: list[Any],
    left: Any,
    right: Any,
    tolerance: float,
) -> str:
    """Whether a shift or a factor on an input with a conventional scale explains it.

    A formulation read on another scale (0 degC at 273.16 K, IPTS-68, a
    salinity scale) differs by a shift or a factor of an input: if one
    makes the two formulations equal as closely as the proportionality
    does (``tolerance``, its largest residual), the factor may come from
    the scale rather than a coefficient. Only shifts and factors the
    catalog's scales can produce over the samples are tried
    (:func:`_scale_windows`). When the object is proportional to a power of
    an input, a factor of that input is a factor of the result, which tells
    nothing: only its shift is tried.
    """
    candidates = [
        (i, v)
        for i, v in enumerate(subject.inputs)
        if any(s.applies_to(v.kind, catalog.kinds) for s in catalog.scales.values())
    ]
    if not candidates:
        return "no input with a conventional scale"
    found = []
    blind = []
    shift = sympy.Symbol("_shift", real=True)
    for index, variable in candidates:
        x = symbols[index]
        most, factor = _scale_windows(variable, columns[index], catalog)
        moves = [("a shift", x + shift, -most, most)] if most else []
        if sympy.simplify(x * sympy.diff(sympy.log(right), x)).free_symbols:
            if factor:
                moves.append(("a factor", x * shift, 1 - factor, 1 + factor))
        else:
            blind.append(variable.identifier)
        for name, image, low, high in moves:
            moved = sympy.lambdify(
                [*symbols, shift], left / right.xreplace({x: image}), "numpy"
            )

            def worst(value: float, moved: Any = moved) -> float:
                with np.errstate(all="ignore"):
                    logs = np.log(
                        np.abs(np.asarray(moved(*columns, value), dtype=float))
                    )
                logs = logs[np.isfinite(logs)]
                return float(np.abs(logs).max()) if logs.size else math.inf

            best = _golden(worst, low, high)
            if worst(best) <= max(tolerance, EQUALITY_TOLERANCE):
                found.append(
                    f"equal to it with {name} of {variable.identifier} "
                    f"({best:.6g}): the factor may come from the scale of "
                    f"{variable.identifier}, not a coefficient"
                )
    notes = [
        f"a factor of {name} cannot be told from a coefficient, the object "
        f"being proportional to a power of {name}"
        for name in blind
    ]
    if found:
        return "; ".join(found + notes)
    names = ", ".join(v.identifier for _, v in candidates)
    within = "within what the catalog's scales give"
    if not blind:
        return (
            f"no shift nor factor of {names} {within} makes them as close: "
            "not a matter of scale"
        )
    factors = ", ".join(
        v.identifier for _, v in candidates if v.identifier not in blind
    )
    tried = f"no shift of {names}" + (f" nor factor of {factors}" if factors else "")
    return "; ".join([f"{tried} {within} makes them as close", *notes])


def _golden(function: Any, low: float, high: float, steps: int = 80) -> float:
    """The minimum of a unimodal function on an interval (golden-section search)."""
    ratio = (math.sqrt(5) - 1) / 2
    a, b = low, high
    c, d = b - ratio * (b - a), a + ratio * (b - a)
    fc, fd = function(c), function(d)
    for _ in range(steps):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = function(c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = function(d)
    return (a + b) / 2


def _proportionality(
    relation: Relation,
    subject: Formulation,
    other: Formulation,
    catalog: Catalog,
    points: int,
) -> Verdict:
    method = "symbolic ratio simplified with SymPy, exact rationals"
    differences = _scale_differences(relation, subject, other)
    if differences and relation.scale == "convert":
        return Verdict(
            "unverified",
            "a proportionality is proved on the expressions as written, which "
            "evaluated with conversion of conventional scales needs the same "
            f'scales: {"; ".join(differences)}; state scale = "ignore" to '
            "compare the expressions as written",
        )
    if differences:
        method += f"; scales ignored: {'; '.join(differences)}"
    left, right, replacements = _sides(relation, subject, other)
    ratio = sympy.nsimplify(left / right, rational=True)
    if _written(subject, other):
        ratio = sympy.simplify(ratio)
    else:
        method = method.replace("simplified with SymPy", "not simplified")
        method += ", an expression longer than a written one"
    if not ratio.free_symbols:
        factor = float(ratio)
        detail, _ = _factor_text(factor, subject, other)
        symbols, columns = _samples(relation, subject, points)
        scale = _scale_text(
            subject, catalog, symbols, columns, left, right, EQUALITY_TOLERANCE
        )
        return Verdict("proven", method, factor, detail=f"{detail}; {scale}")
    method += (
        f"; not constant: ratio sampled at {points} points of the bounds, "
        "against the rounding of the printed coefficients"
    )
    status, sampled, detail, at, share = _ratio_check(
        relation, subject, other, catalog, left, right, replacements, points
    )
    if share < 1:
        method += (
            f"; ratio finite and non-zero on {100 * share:.4g} % of the samples "
            "only, the others not compared"
        )
    if status == "unverified":
        return Verdict("unverified", method)
    if status == "held":
        return Verdict("held", method, sampled, detail=detail)
    if detail:
        method += f"; {detail}"
    return Verdict("refuted", method, None, at, str(ratio))


def verify(relation: Relation, catalog: Catalog, *, budget: int = BUDGET) -> Verdict:
    """Verify a relation stated by a source.

    Parameters
    ----------
    relation : Relation
        The relation, from ``catalog.relations``.
    catalog : Catalog
        The catalog holding its two formulations.
    budget : int, optional
        Evaluations of the first grid of an approximation (see
        :func:`per_axis`; ``docs/relation-verdicts.md`` says how far
        the result can be trusted with the number of inputs).

    Returns
    -------
    Verdict
        The status, the method and what was found.
    """
    subject = catalog.formulations[relation.subject]
    other = catalog.formulations[relation.object]
    if relation.kind is RelationKind.APPROXIMATES:
        return _approximation(relation, subject, other, budget)[0]
    if relation.kind is RelationKind.PROPORTIONAL:
        return _proportionality(relation, subject, other, catalog, SAMPLES)
    return _equivalence(relation, subject, other, SAMPLES)


def _valid_extent(formulation: Formulation) -> dict[str, tuple[float, float]]:
    """Per input, where a formulation is stated valid, within its physical domains.

    The extent of the domains its sources state (:func:`_stated_extent`),
    narrowed by every physical domain, which always applies; infinite on
    a side nothing bounds.
    """
    extent = dict(_stated_extent(formulation))
    for domain in formulation.physical_domains:
        for name, (low, high) in domain.bounds.items():
            old_low, old_high = extent.get(name, (-math.inf, math.inf))
            extent[name] = (max(old_low, low), min(old_high, high))
    return extent


def _common_bounds(
    subject: Formulation, other: Formulation
) -> dict[str, tuple[float, float]] | None:
    """A domain where both formulations are valid, on the subject's inputs.

    Both are stated valid there (a domain stated by one side serves when
    the other states none), within the physical domains of both; ``None``
    when that domain is empty, or unbounded on a side.
    """
    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    feeds = {source: name for name, source in match_inputs(subject, other).items()}
    own_extent = _on_reference(subject, _valid_extent(subject))
    other_extent = _on_reference(other, _valid_extent(other))
    if own_extent is None or other_extent is None:
        return None
    bounds = {}
    for variable in subject.inputs:
        low, high = own_extent.get(variable.identifier, (-math.inf, math.inf))
        name = feeds.get(variable.identifier)
        if name is not None and name in other_extent:
            unit = next(v.unit for v in other.inputs if v.identifier == name)
            converted = Q_(np.array(other_extent[name]), units[unit].pint).to(
                units[variable.unit].pint
            )
            low = max(low, float(converted.magnitude[0]))
            high = min(high, float(converted.magnitude[1]))
        if not (math.isfinite(low) and math.isfinite(high) and low < high):
            return None
        bounds[variable.identifier] = (low, high)
    return bounds


def _on_reference(
    formulation: Formulation, extent: Mapping[str, tuple[float, float]]
) -> dict[str, tuple[float, float]] | None:
    """An extent of a formulation's inputs, carried to their reference scales.

    Domains are stated on the scale a formulation was fitted on, while a
    comparison takes its inputs on the reference scale (ITS-90, Reference
    Salinity); values that do not convert are left out. ``None`` when no
    value of an input's extent converts. A scale nomogram cannot convert is
    left as it is: :func:`report` says why such a pair is not compared.
    """
    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    carried = dict(extent)
    for variable in formulation.inputs:
        scale = variable.scale
        if (
            variable.identifier not in extent
            or scale is None
            or scale.is_reference
            or not scale.convertible
        ):
            continue
        own, table = units[variable.unit].pint, units[str(scale.unit)].pint
        on_scale = Q_(np.array(extent[variable.identifier]), own).to(table)
        interval = scale.interval_to_reference(*on_scale.magnitude)
        if interval is None:
            return None
        back = Q_(np.array(interval), table).to(own).magnitude
        carried[variable.identifier] = (float(back[0]), float(back[1]))
    return carried


def _stated_extent(formulation: Formulation) -> dict[str, tuple[float, float]]:
    """Per input, the extent of the domains a formulation's sources state.

    Domains of one citation apply together, citations combine by union: the
    extent is the smallest interval holding that union, infinite on a side
    a citation leaves open.
    """
    boxes = []
    for citation in formulation.citations:
        if not citation.domains:
            continue
        box: dict[str, tuple[float, float]] = {}
        for domain in citation.domains:
            for name, (low, high) in domain.bounds.items():
                old_low, old_high = box.get(name, (-math.inf, math.inf))
                box[name] = (max(old_low, low), min(old_high, high))
        boxes.append(box)
    names = {name for box in boxes for name in box}
    whole = (-math.inf, math.inf)
    return {
        name: (
            min(box.get(name, whole)[0] for box in boxes),
            max(box.get(name, whole)[1] for box in boxes),
        )
        for name in sorted(names)
    }


def _beyond_parts(formulation: Formulation) -> list[str]:
    """Where the sources of a composed formulation state more than those of its parts.

    A domain stated for the composed formulation replaces those stated for
    its parts; for a formulation calling others, both hold (see
    :meth:`~nomogram.model.Formulation.outside_mask`). A disagreement is
    pointed out, never smoothed.
    """
    own = _stated_extent(formulation)
    if not own:
        return []
    inputs = {v.identifier for v in formulation.inputs}
    lines = []
    for part in formulation.parts:
        key = part.formulation.key
        for name, (low, high) in _stated_extent(part.formulation).items():
            identifier = part.rename.get(name, name)
            if identifier not in inputs:
                lines.append(
                    f"  domain stated for {key} on {name}, a computed value, "
                    "replaced by the composed formulation's"
                )
                continue
            ours = own.get(identifier, (-math.inf, math.inf))
            if ours[0] < low or ours[1] > high:
                lines.append(
                    f"  stated domain beyond that of {key} on {identifier}: "
                    f"[{ours[0]:g}, {ours[1]:g}] against [{low:g}, {high:g}]"
                )
    return lines


@dataclass(frozen=True)
class Replay:
    """A case of a cross-check, computed again by nomogram.

    Attributes
    ----------
    case : CheckCase
        The case, with the value of the other implementation.
    value : float
        The value nomogram computes, in the unit of the formulation's
        output.
    deviation : float
        Relative deviation from the recorded value (absolute when it is 0).
    """

    case: CheckCase
    value: float
    deviation: float

    @property
    def agrees(self) -> bool:
        """Whether the deviation is within the case's tolerance."""
        return self.deviation <= self.case.rtol


def replay(check: CrossCheck, catalog: Catalog) -> tuple[Replay, ...]:
    """Compute again the cases of a cross-check.

    Each formulation is evaluated as written: inputs in its units, no
    scale conversion and no validity domain, as an implementation of the
    printed equation computes it.

    Parameters
    ----------
    check : CrossCheck
        The cross-check, from ``catalog.cross_checks``.
    catalog : Catalog
        The catalog holding its formulations.

    Returns
    -------
    tuple of Replay
        One per case, in order.
    """
    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    results = []
    for case in check.cases:
        formulation = catalog.formulations[case.formulation]
        inputs: dict[str, Any] = {
            v.identifier: Q_(case.inputs[v.identifier], units[v.unit].pint)
            for v in formulation.inputs
        }
        found = formulation.evaluate(outside="ignore", scale="ignore", **inputs)
        value = float(found.magnitude)
        deviation = (
            abs(value / case.value - 1) if case.value != 0 else abs(value - case.value)
        )
        results.append(Replay(case, value, deviation))
    return tuple(results)


def report(catalog: Catalog, keys: Iterable[str], *, budget: int = 20_000) -> str:
    """Observations on formulations, against the others of the same kind.

    For each formulation: those of the same form, and the maximum relative
    deviation observed against each other
    formulation of the same output kind on the domain where both are
    stated valid. These are observations, never claims: only a relation
    with a citation states an approximation or an equivalence.

    A pair is not compared, and a line says why, when a variable is on a
    scale nomogram cannot convert (Absolute Salinity) or when no point of
    the common domain gives a finite value; when only some points do, the
    line gives the share compared.

    Parameters
    ----------
    catalog : Catalog
        The catalog holding the formulations.
    keys : iterable of str
        The formulations to report on.
    budget : int, optional
        Evaluations of the first grid of each comparison.

    Returns
    -------
    str
        The report, as plain text.
    """
    lines = []
    for key in keys:
        formulation = catalog.formulations[key]
        lines.append(f"{key} ({formulation.output.kind})")
        lines += _beyond_parts(formulation)
        shape = form(formulation)
        others = [
            f
            for f in catalog.formulations.values()
            if f.key != key and f.output.kind == formulation.output.kind
        ]
        # Identical formulations never reach a report: loading refuses them.
        alike = [f.key for f in others if form(f) == shape]
        if alike:
            lines.append(f"  same form, other coefficients: {', '.join(alike)}")
        for other in others:
            bounds = _common_bounds(formulation, other)
            if bounds is None or len(match_inputs(formulation, other)) != len(
                other.inputs
            ):
                continue
            blocked = _unconvertible(formulation) + _unconvertible(other)
            if blocked:
                lines.append(
                    f"  not compared with {other.key}: nomogram holds no "
                    f"conversion of {', '.join(sorted(set(blocked)))} to the "
                    "reference scale"
                )
                continue
            probe = Relation(
                key="observation",
                kind=RelationKind.APPROXIMATES,
                subject=key,
                object=other.key,
                citation="",
                accuracy=0.0,
                bounds=MappingProxyType(bounds),
            )
            verdict, share = _approximation(probe, formulation, other, budget)
            if verdict.value is None:
                lines.append(
                    f"  not compared with {other.key}: no point of the common "
                    "domain where both give a finite value"
                )
                continue
            place = ", ".join(f"{n} = {v:.6g}" for n, v in verdict.at.items())
            partial = (
                f" (finite on {100 * share:.4g} % of the common domain only)"
                if share < 1
                else ""
            )
            note = (
                "  (numerically identical: an equivalence to state?)"
                if verdict.value < 1e-9
                else ""
            )
            lines.append(
                f"  observed max deviation from {other.key}: "
                f"{verdict.value:.4g} % at {place}{partial}{note}"
            )
    return "\n".join(lines) + "\n"


def _unconvertible(formulation: Formulation) -> list[str]:
    """Scales of a formulation's variables that nomogram cannot convert."""
    return [
        v.scale.key
        for v in (formulation.output, *formulation.inputs)
        if v.scale is not None and not v.scale.is_reference and not v.scale.convertible
    ]


#: Version of the verification method. Increase it when a change of the
#: method may change a verdict: every recorded verdict is then redone.
VERIFIER = 3

#: The registry of the bundled catalog, generated, never edited by hand.
REGISTRY = "verifications.json"


def _conversion_chain(scale: Any) -> list[Any]:
    """A conversion by expression and the scales it goes through.

    Empty for a table converting straight to the reference scale, so that
    existing fingerprints stay valid.
    """
    found: list[Any] = []
    while scale is not None and scale.conversion is not None:
        found.append(
            [scale.key, scale.conversion, list(scale.bounds or ()), scale.unit]
        )
        scale = scale.base
    if found and scale is not None and scale.points:
        found.append(
            [scale.key, list(scale.points), list(scale.difference), scale.unit]
        )
    return found


def fingerprint(relation: Relation, catalog: Catalog, *, budget: int = BUDGET) -> str:
    """A fingerprint (SHA-256) of everything a verdict depends on.

    The relation as written, the signatures of its two formulations, the
    conventional scales of their variables, the budget of the check and
    the version of the method: if any changes, the fingerprint changes and
    a recorded verdict no longer applies.
    """
    subject = catalog.formulations[relation.subject]
    other = catalog.formulations[relation.object]
    scales = sorted(
        (
            f.key,
            v.identifier,
            v.scale.key,
            list(v.scale.points),
            list(v.scale.difference),
            *_conversion_chain(v.scale),
        )
        for f in (subject, other)
        for v in (f.output, *f.inputs)
        if v.scale is not None
    )
    # The detail names coefficients and formulations, and weighs the scales
    # of the catalog applying to the inputs (_scale_text).
    names = [
        (f.key, c.identifier, c.value) for f in (subject, other) for c in f.coefficients
    ]
    names += [
        (f.key, k.identifier, k.value) for f in (subject, other) for k in f.constants
    ]
    applying = sorted(
        (
            v.identifier,
            s.key,
            list(s.points),
            list(s.difference),
            *_conversion_chain(s),
        )
        for v in subject.inputs
        for s in catalog.scales.values()
        if s.applies_to(v.kind, catalog.kinds)
    )
    content = {
        "verifier": VERIFIER,
        "budget": budget,
        "keys": [relation.subject, relation.object],
        "names": names,
        "applying": applying,
        "kind": relation.kind.value,
        "accuracy": relation.accuracy,
        "at": sorted(relation.at.items()),
        "bounds": sorted((k, list(v)) for k, v in relation.bounds.items()),
        "given": sorted(relation.given.items()),
        "scale": relation.scale,
        "subject": signature(subject),
        "object": signature(other),
        "scales": scales,
    }
    text = json.dumps(content, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _to_json(key: str, found: Verdict) -> dict[str, Any]:
    return {
        "relation": key,
        "status": found.status,
        "method": found.method,
        "value": found.value,
        "at": dict(found.at),
        "detail": found.detail,
    }


def _from_json(item: Mapping[str, Any]) -> Verdict:
    return Verdict(
        status=item["status"],
        method=item["method"],
        value=item["value"],
        at=MappingProxyType(dict(item["at"])),
        detail=item["detail"],
    )


def _registry_path() -> Path:
    return Path(str(files("nomogram") / "data" / "catalog" / REGISTRY))


@lru_cache(maxsize=8)
def _read_registry(path: str) -> Mapping[str, Verdict]:
    if not Path(path).exists():
        return MappingProxyType({})
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return MappingProxyType({k: _from_json(v) for k, v in data["verdicts"].items()})


def load_registry(path: str | os.PathLike[str] | None = None) -> Mapping[str, Verdict]:
    """Recorded verdicts, by fingerprint: the bundled registry by default."""
    return _read_registry(
        os.fspath(path) if path is not None else str(_registry_path())
    )


def verdict(
    relation: Relation,
    catalog: Catalog,
    *,
    registry: str | os.PathLike[str] | None = None,
    budget: int = BUDGET,
) -> Verdict:
    """The verdict on a relation: recorded when it still applies, computed otherwise.

    Parameters
    ----------
    relation, catalog, budget
        As for :func:`verify`.
    registry : path-like, optional
        A registry written by :func:`record`; the bundled one by default.

    Returns
    -------
    Verdict
        Read from the registry when its fingerprint matches, so that
        nothing is recomputed; computed by :func:`verify` otherwise.
    """
    recorded = load_registry(registry).get(
        fingerprint(relation, catalog, budget=budget)
    )
    return (
        recorded if recorded is not None else verify(relation, catalog, budget=budget)
    )


def record(
    catalog: Catalog,
    path: str | os.PathLike[str] | None = None,
    *,
    budget: int = BUDGET,
) -> tuple[int, int]:
    """Write the registry of the verdicts on every relation of a catalog.

    Verdicts whose fingerprint is already recorded are reused; the others
    are computed; entries matching no relation any more are dropped. The
    continuous integration recomputes every verdict and compares it with
    the bundled registry: it has the last word.

    Parameters
    ----------
    catalog : Catalog
        The catalog whose relations are verified.
    path : path-like, optional
        The registry file; the bundled one by default.
    budget : int, optional
        As for :func:`verify`.

    Returns
    -------
    (int, int)
        Verdicts computed, verdicts reused.
    """
    target = Path(os.fspath(path)) if path is not None else _registry_path()
    existing = _read_registry(str(target))
    verdicts = {}
    computed = reused = 0
    for key in sorted(catalog.relations):
        relation = catalog.relations[key]
        print_key = fingerprint(relation, catalog, budget=budget)
        found = existing.get(print_key)
        if found is None:
            found = verify(relation, catalog, budget=budget)
            computed += 1
        else:
            reused += 1
        verdicts[print_key] = _to_json(key, found)
    content = {"verifier": VERIFIER, "verdicts": dict(sorted(verdicts.items()))}
    target.write_text(
        json.dumps(content, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _read_registry.cache_clear()
    return computed, reused
