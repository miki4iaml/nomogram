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

from nomogram.comparison import compare
from nomogram.expression import parse_expression
from nomogram.model import Formulation, Relation, RelationKind
from nomogram.units import Q_

if TYPE_CHECKING:
    from nomogram.catalog import Catalog

__all__ = ["Verdict", "verify"]

#: Relative difference below which two values are taken as equal, when
#: looking for a counterexample to an equivalence.
EQUALITY_TOLERANCE = 1e-9

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


def _grid(
    subject: Formulation, bounds: Mapping[str, tuple[float, float]], points: int
) -> dict[str, Any]:
    """One array per input of the subject, spanning the stated domain."""
    names = [v.identifier for v in subject.inputs]
    per_axis = max(2, round(points ** (1 / len(names))))
    axes = [np.linspace(*bounds[name], per_axis) for name in names]
    return dict(zip(names, np.meshgrid(*axes, indexing="ij"), strict=True))


def _approximation(
    relation: Relation, subject: Formulation, other: Formulation, points: int
) -> Verdict:
    from nomogram.semantics import semantic_catalog

    units = semantic_catalog().units
    grid = _grid(subject, relation.bounds, points)
    inputs = {
        v.kind: Q_(grid[v.identifier], units[v.unit].pint) for v in subject.inputs
    }
    comparison = compare(
        [subject], other, inputs, outside="ignore", scale=relation.scale
    )
    deviation = np.abs(np.asarray(comparison.relative_deviations[subject.key])) * 100
    index = np.unravel_index(int(np.nanargmax(deviation)), deviation.shape)
    found = float(deviation[index])
    at = MappingProxyType({name: float(values[index]) for name, values in grid.items()})
    claimed = float(relation.accuracy or 0.0)
    tolerance = 0.5 * 10.0 ** -_decimals(claimed)
    if abs(found - claimed) <= tolerance:
        status: Status = "reproduced"
    elif found < claimed:
        status = "held"
    else:
        status = "exceeded"
    method = (
        f"maximum relative deviation on {deviation.size} points, scale {relation.scale}"
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


def verify(relation: Relation, catalog: Catalog, *, points: int = 9001) -> Verdict:
    """Verify a relation stated by a source.

    Parameters
    ----------
    relation : Relation
        The relation, from ``catalog.relations``.
    catalog : Catalog
        The catalog holding its two formulations.
    points : int, optional
        Number of points of the grid (approximation), or of random
        samples looking for a counterexample (equivalence).

    Returns
    -------
    Verdict
        The status, the method and what was found.
    """
    subject = catalog.formulations[relation.subject]
    other = catalog.formulations[relation.object]
    if relation.kind is RelationKind.APPROXIMATES:
        return _approximation(relation, subject, other, points)
    return _equivalence(relation, subject, other, min(points, 200))
