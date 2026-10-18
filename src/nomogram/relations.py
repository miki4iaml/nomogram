# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Verification of the relations between formulations stated by sources.

A relation of the catalog is a claim made by a source; :func:`verify`
checks it and returns a :class:`Verdict`:

- an **equivalence** is proved with SymPy: coefficients become exact
  rationals, the object's inputs are replaced as the relation says
  (``given``), and the difference must simplify to zero. If it does not,
  a numerical counterexample refutes the claim; without one, the
  equivalence is left unproven (equivalence of transcendental
  expressions is undecidable in general);
- an **approximation** is checked on a dense grid of the domain the
  source states: the maximum relative deviation found is compared with
  the stated one. The verdict says whether it is reproduced (to the
  precision published), held (smaller) or exceeded (larger); it is a
  check on points, never a proof.

Deviations nomogram computes without a source are observations, given by
:func:`nomogram.comparison.compare`; they never become relations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import sympy

from nomogram.comparison import same_state
from nomogram.expression import parse_expression
from nomogram.model import Formulation, Relation, RelationKind
from nomogram.units import Q_

if TYPE_CHECKING:
    from nomogram.catalog import Catalog

__all__ = ["BUDGET", "Verdict", "match_inputs", "per_axis", "verify"]

#: Relative difference below which two values are taken as equal, when
#: looking for a counterexample to an equivalence.
EQUALITY_TOLERANCE = 1e-9

#: Random samples looking for a counterexample to an equivalence.
SAMPLES = 200

Status = Literal["proven", "refuted", "unproven", "reproduced", "held", "exceeded"]


@dataclass(frozen=True)
class Verdict:
    """The outcome of verifying a relation.

    Attributes
    ----------
    status : str
        ``"proven"``, ``"refuted"`` or ``"unproven"`` for an equivalence;
        ``"reproduced"``, ``"held"`` or ``"exceeded"`` for an
        approximation.
    method : str
        How it was verified.
    value : float or None
        For an approximation, the maximum relative deviation found, in
        percent.
    at : mapping of str to float
        Where that maximum lies, or where a counterexample was found, by
        input identifier of the subject.
    detail : str or None
        The simplified difference of an equivalence that is not proven.
    """

    status: Status
    method: str
    value: float | None = None
    at: Mapping[str, float] = MappingProxyType({})
    detail: str | None = None


def _decimals(value: float) -> int:
    text = repr(value)
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


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
) -> Verdict:
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
        values = np.abs(ratio - 1) * 100
        return np.where(np.isfinite(values), values, -np.inf)

    def grid(lower: Any, upper: Any, count: int) -> Any:
        axes = [np.linspace(a, b, count) for a, b in zip(lower, upper, strict=True)]
        mesh = np.meshgrid(*axes, indexing="ij")
        return np.stack([m.ravel() for m in mesh], axis=1)

    count = per_axis(len(names), budget)
    first = grid(low, high, count)
    values = deviation(first)
    evaluations = len(first)
    best_points = first[np.argsort(values)[::-1][:CANDIDATES]]
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
            local_values = deviation(local)
            evaluations += len(local)
            centre = local[int(np.argmax(local_values))]
            half = half * 2 / (zoom - 1)
        value = float(deviation(centre[None, :])[0])
        if value > found:
            found, where = value, centre
    at = MappingProxyType({n: float(x) for n, x in zip(names, where, strict=True)})
    claimed = float(relation.accuracy or 0.0)
    tolerance = 0.5 * 10.0 ** -_decimals(claimed)
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
    return Verdict(status, method, found, at)


def _rational(formulation: Formulation) -> Any:
    """The expression with exact coefficients and constants."""
    expr = parse_expression(formulation.expression, formulation.names)
    pairs = [(c.identifier, c.value) for c in formulation.coefficients]
    pairs += [(k.identifier, k.value) for k in formulation.constants]
    values = {
        sympy.Symbol(name, real=True): sympy.Rational(repr(value))
        for name, value in pairs
    }
    return expr.xreplace(values)


def _equivalence(
    relation: Relation, subject: Formulation, other: Formulation, points: int
) -> Verdict:
    names = [v.identifier for v in subject.inputs]
    left = _rational(subject)
    right = _rational(other)
    replacements = {
        sympy.Symbol(identifier, real=True): parse_expression(source, names)
        for identifier, source in relation.given.items()
    }
    difference = sympy.nsimplify(left - right.xreplace(replacements), rational=True)
    simplified = sympy.simplify(difference)
    method = "symbolic difference simplified with SymPy, exact rationals"
    if simplified == 0:
        return Verdict("proven", method)
    # Look for a counterexample on positive values, or on the stated domain.
    symbols = sorted(simplified.free_symbols | left.free_symbols, key=lambda s: s.name)
    random = np.random.default_rng(0)
    for _ in range(points):
        sample = {
            s: (
                random.uniform(*relation.bounds[s.name])
                if s.name in relation.bounds
                else random.uniform(0.5, 2.0)
            )
            for s in symbols
        }
        scale = abs(float(left.xreplace(sample))) or 1.0
        gap = abs(float(simplified.xreplace(sample)))
        if gap > EQUALITY_TOLERANCE * scale:
            at = MappingProxyType({s.name: float(v) for s, v in sample.items()})
            return Verdict(
                "refuted",
                method + "; numerical counterexample",
                None,
                at,
                str(simplified),
            )
    return Verdict(
        "unproven", method + "; no counterexample found", detail=str(simplified)
    )


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
        :func:`per_axis`; ``docs/verification.md`` says how far the
        result can be trusted with the number of inputs).

    Returns
    -------
    Verdict
        The status, the method and what was found.
    """
    subject = catalog.formulations[relation.subject]
    other = catalog.formulations[relation.object]
    if relation.kind is RelationKind.APPROXIMATES:
        return _approximation(relation, subject, other, budget)
    return _equivalence(relation, subject, other, SAMPLES)
