# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Units of coefficients, inferred from the expression of a formulation.

The catalog states the units of variables, but often not those of
coefficients: in the Magnus form ``C * exp(A * t / (B + t))``, A, B and C
are given as plain numbers. Dimensional analysis settles them: the
argument of an exponential is a pure number, so B has the unit of t (a
temperature difference), A is a pure number, and C has the unit of the
result. :func:`infer_units` does this for any formulation.

The expression is read as SymPy builds it, as a tree. Each kind of node
brings a constraint:

- a variable, a constant or a coefficient with a declared unit has that
  unit (a Celsius temperature counts as a temperature difference, so that
  units can be multiplied: B + t gives B in degrees Celsius);
- a number is a pure number;
- the terms of a sum, and the sum, share one dimension;
- a product multiplies units; a power with a numerical exponent raises
  the unit to it;
- the argument of a function (exp, ln, log10), and the base and exponent
  of a power with a symbolic exponent, are pure numbers;
- both sides of the equation share one dimension.

A formulation with fixed units is a numerical value equation (VIM 1.25),
which allows two readings a quantity equation never gets:

- a quantity entirely known, found where a pure number is required, is
  its numerical value in its unit (T/K in ``ln(T)``, e_st/hPa in
  ``log10(e_st)``), unless a coefficient of unknown unit could carry the
  unit instead;
- a sum, or the equation itself, may join numerical values of variables
  (e_s/hPa equal to a bare exponential, ``t**2 + exp(t)``), as long as no
  coefficient takes part: a declared unit is a claim, and is checked.

Two methods solve the constraints. Local propagation runs first: each
coefficient whose unit follows from a single constraint gets it, with
that constraint recorded as the reason, and conflicts are reported where
they occur. Linear algebra (:func:`sympy.linsolve` on the exponents of
the base dimensions) settles whatever propagation leaves, which only
happens when several constraints must be solved together. The tests
check that both methods agree. In a formulation with fixed units, a
coefficient holds for the units the formulation is written with (hPa,
not Pa): linear algebra then solves the exponents of those units, and
leaves the coefficient undetermined when they do not fix its unit.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import sympy

from nomogram.expression import _relations
from nomogram.semantics import semantic_catalog
from nomogram.units import ureg

if TYPE_CHECKING:
    from nomogram.model import Formulation

__all__ = ["CoefficientUnit", "DimensionError", "infer_units", "unit_text"]

#: SI base unit of each pint base dimension, to write a unit found by
#: linear algebra.
_BASE_UNITS: Mapping[str, str] = {
    "[length]": "m",
    "[mass]": "kg",
    "[time]": "s",
    "[temperature]": "K",
    "[current]": "A",
    "[substance]": "mol",
    "[luminosity]": "cd",
}


class DimensionError(ValueError):
    """The units of a formulation contradict its expression."""


@dataclass(frozen=True)
class CoefficientUnit:
    """The unit of one coefficient, declared or inferred.

    Attributes
    ----------
    identifier : str
        The coefficient.
    unit : pint.Unit or None
        Its unit (dimensionless for a pure number); ``None`` when the
        expression does not determine it.
    origin : {"stated", "added", "inferred"} or None
        Where the unit comes from: stated by the source, added when the
        entry was written (a declared unit without basis counts as added),
        or inferred from the expression; ``None`` without a unit.
    reason : str or None
        For an inferred unit, the part of the expression it follows from.
    citation : str or None
        For a stated unit, the key of the source that states it.
    """

    identifier: str
    unit: Any
    origin: Literal["stated", "added", "inferred"] | None
    reason: str | None
    citation: str | None = None


def _pint(key: str) -> Any:
    """The pint unit of a catalog unit; a Celsius point counts as a difference."""
    expression = semantic_catalog().units[key].pint
    return ureg.Unit("delta_degC" if expression == "degC" else expression)


def unit_text(unit: Any) -> str:
    """A unit as text, with the symbols of the catalog where possible.

    A temperature difference in degrees Celsius is written °C, as the SI
    Brochure does, not pint's Δ°C. A pure number gives an empty string.
    """
    if unit is None or unit.dimensionless and unit == ureg.dimensionless:
        return ""
    for key, definition in semantic_catalog().units.items():
        if definition.symbol and key != "UNITLESS" and _pint(key) == unit:
            return definition.symbol
    return f"{unit:~P}".replace("Δ°C", "°C")


@dataclass
class _Context:
    """The state of one inference: known units and pending unknowns."""

    fixed_units: bool
    units: dict[str, Any]
    unknown: frozenset[str]
    coefficients: frozenset[str]
    reasons: dict[str, str]

    def involves(self, node: Any, names: frozenset[str]) -> bool:
        """Whether the dimension of a node involves one of ``names``.

        A function, or a power with a symbolic exponent, is a pure number
        whatever its argument; a sum takes the dimension of a term that
        does not involve them, when there is one.
        """
        if node.is_Symbol:
            return node.name in names
        if isinstance(node, sympy.Piecewise):
            return all(self.involves(e, names) for e, _ in node.args)
        if node.is_Number or node.is_NumberSymbol or isinstance(node, sympy.Function):
            return False
        if node.is_Pow:
            return bool(node.exp.is_Number) and self.involves(node.base, names)
        if node.is_Add:
            return all(self.involves(term, names) for term in node.args)
        return any(self.involves(arg, names) for arg in node.args)

    def depends(self, node: Any) -> bool:
        """Whether the dimension of a node depends on an unknown unit."""
        return self.involves(node, self.unknown)

    def numerical(self, constraint: _Constraint) -> bool:
        """Whether a constraint is read as one between numerical values.

        Only in a formulation with fixed units: a pure number may be a
        known quantity's numerical value (T/K in ``ln(T)``), and a sum or
        the equation may join numerical values of variables, as long as
        no coefficient is involved: a declared unit is a claim to check.
        """
        if not self.fixed_units:
            return False
        if constraint.kind == "pure":
            return not any(self.depends(node) for node in constraint.nodes)
        return not any(self.involves(n, self.coefficients) for n in constraint.nodes)

    def unit(self, node: Any) -> Any:
        """The unit of a node, or ``None`` while an unknown it needs is unsolved."""
        if node.is_Symbol:
            return self.units.get(node.name)
        if isinstance(node, sympy.Piecewise):
            # Its branches share one dimension (a constraint): any known one.
            known = (self.unit(e) for e, _ in node.args)
            return next((u for u in known if u is not None), None)
        if node.is_Number or node.is_NumberSymbol or isinstance(node, sympy.Function):
            return ureg.dimensionless
        if node.is_Pow:
            if not node.exp.is_Number:
                return ureg.dimensionless
            base = self.unit(node.base)
            return None if base is None else base ** float(node.exp)
        if node.is_Mul:
            result = ureg.dimensionless
            for factor in node.args:
                unit = self.unit(factor)
                if unit is None:
                    return None
                result = result * unit
            return result
        if node.is_Add:
            for term in node.args:
                unit = self.unit(term)
                if unit is not None:
                    return unit
            return None
        msg = f"unsupported node: {type(node).__name__}"  # pragma: no cover
        raise TypeError(msg)  # pragma: no cover

    def solve(self, node: Any, target: Any, reason: str) -> bool:
        """Give the unknowns of a node the units that make it ``target``.

        Called on nodes of unknown unit only. Returns whether something was
        solved; only a node with a single unknown path can be solved
        locally.
        """
        if node.is_Symbol:  # an unknown coefficient not solved yet
            self.units[node.name] = target
            self.reasons[node.name] = reason
            return True
        if node.is_Pow and node.exp.is_Number:
            return self.solve(node.base, target ** (1 / float(node.exp)), reason)
        if node.is_Mul:
            pending = [f for f in node.args if self.unit(f) is None]
            if len(pending) != 1:
                return False
            known = ureg.dimensionless
            for factor in node.args:
                if factor is not pending[0]:
                    known = known * self.unit(factor)
            return self.solve(pending[0], target / known, reason)
        if node.is_Add:
            return any(
                self.solve(term, target, reason)
                for term in node.args
                if self.unit(term) is None
            )
        if isinstance(node, sympy.Piecewise):
            return any(
                self.solve(e, target, reason)
                for e, _ in node.args
                if self.unit(e) is None
            )
        return False  # pragma: no cover - numbers and functions have a unit


@dataclass(frozen=True)
class _Constraint:
    """Nodes that must share a dimension, or be pure numbers."""

    kind: Literal["equal", "pure"]
    nodes: tuple[Any, ...]
    where: str


def _constraints(expr: Any) -> Iterator[_Constraint]:
    """The constraints of an expression tree, outermost first.

    The branches of a piecewise definition share one dimension, and so do
    both sides of each comparison of its conditions (T_ice < T gives T_ice
    the unit of T).
    """
    if isinstance(expr, sympy.Piecewise):
        branches = tuple(e for e, _ in expr.args)
        if len(branches) > 1:
            yield _Constraint("equal", branches, str(expr))
        for relation in _relations(expr):
            yield _Constraint("equal", (relation.lhs, relation.rhs), str(relation))
        for branch in branches:
            yield from _constraints(branch)
        return
    pure: list[Any] = []
    if isinstance(expr, sympy.Function):
        pure = list(expr.args)
    elif expr.is_Pow and not expr.exp.is_Number:
        pure = [expr.base, expr.exp]
    elif expr.is_Add:
        yield _Constraint("equal", tuple(expr.args), str(expr))
    for node in pure:
        yield _Constraint("pure", (node,), str(expr))
    for arg in expr.args:
        yield from _constraints(arg)


def _units_differ(a: Any, b: Any) -> bool:
    return bool(a.dimensionality != b.dimensionality)


def _propagate(context: _Context, constraints: list[_Constraint]) -> None:
    """Solve the constraints one at a time, until nothing changes."""
    changed = True
    while changed:
        changed = False
        for constraint in constraints:
            units = [context.unit(node) for node in constraint.nodes]
            target: Any
            if constraint.kind == "pure":
                target = ureg.dimensionless
            else:
                target = next((u for u in units if u is not None), None)
            if target is None:
                continue
            for node, unit in zip(constraint.nodes, units, strict=True):
                if unit is None and context.solve(node, target, constraint.where):
                    changed = True


def _check(context: _Context, constraints: list[_Constraint]) -> None:
    for constraint in constraints:
        units = [context.unit(node) for node in constraint.nodes]
        known = [u for u in units if u is not None]
        if constraint.kind == "pure":
            known.append(ureg.dimensionless)
        for unit in known[1:]:
            if _units_differ(unit, known[0]):
                parts = ", ".join(
                    f"{node} in {unit_text(u) or '1'}"
                    for node, u in zip(constraint.nodes, units, strict=True)
                    if u is not None
                )
                expected = (
                    " (a pure number is required)" if constraint.kind == "pure" else ""
                )
                msg = f"in {constraint.where}: {parts}{expected}"
                raise DimensionError(msg)


def _intermediates(
    formulation: Formulation, rename: Mapping[str, str], path: str
) -> Iterator[tuple[Any, Any, Any]]:
    """Each intermediate quantity of a formulation made of others.

    Yields a marker, the unit of the part's output and the part's
    expression, renamed into the outermost formulation (``rename`` maps the
    identifiers of ``formulation`` to it), for the parts and, recursively,
    the parts of the parts.
    """
    for part in formulation.parts:
        inner = part.formulation
        into = {
            name: rename.get(part.rename.get(name, name), part.rename.get(name, name))
            for name in inner.names
        }
        if part.computes is not None:
            piece = inner.sympy_expression.xreplace(
                {
                    sympy.Symbol(old, real=True): sympy.Symbol(new, real=True)
                    for old, new in into.items()
                    if old != new
                }
            )
            marker = sympy.Symbol(f"{path}{part.computes} ({inner.key})", real=True)
            yield marker, _pint(inner.output.unit), piece
        yield from _intermediates(inner, into, f"{path}{part.computes or inner.key}/")


def _setup(formulation: Formulation) -> tuple[_Context, list[_Constraint], Any]:
    units: dict[str, Any] = {}
    for variable in (formulation.output, *formulation.inputs):
        units[variable.identifier] = _pint(variable.unit)
    for constant in formulation.constants:
        units[constant.identifier] = _pint(constant.unit)
    unknown = []
    for coefficient in formulation.coefficients:
        if coefficient.unit is None:
            unknown.append(coefficient.identifier)
        else:
            units[coefficient.identifier] = _pint(coefficient.unit)
    # A formulation made of others keeps the units of its intermediate
    # quantities: each part's expression has the unit of the part's output,
    # and so do the parts of its parts, renamed into the formulation.
    # Each brings its own structure too: the expression of the formulation
    # may have simplified it away (a factor common to two calls).
    pieces = []
    for marker, unit, piece in _intermediates(formulation, {}, ""):
        units[marker.name] = unit
        pieces.append(_Constraint("equal", (marker, piece), f"{marker} = {piece}"))
        pieces.extend(_constraints(piece))
    coefficients = frozenset(c.identifier for c in formulation.coefficients)
    context = _Context(
        formulation.fixed_units, units, frozenset(unknown), coefficients, {}
    )
    expr = formulation.sympy_expression
    output = sympy.Symbol(formulation.output.identifier, real=True)
    candidates = [
        _Constraint("equal", (output, expr), f"{output} = {expr}"),
        *_constraints(expr),
        *pieces,
    ]
    constraints = [c for c in candidates if not context.numerical(c)]
    return context, constraints, expr


def _dimension(unit: Any) -> dict[str, Fraction]:
    return {
        name: Fraction(exponent).limit_denominator(1000)
        for name, exponent in unit.dimensionality.items()
    }


def _factors(unit: Any) -> dict[str, Fraction]:
    """A unit as the powers of the units it is written with.

    hPa/°C gives hectopascal to the power 1 and delta_degree_Celsius to
    the power -1: hPa and Pa are different factors, unlike dimensions.
    """
    items: Any = ureg.Quantity(1, unit).unit_items()
    return {
        name: Fraction(exponent).limit_denominator(1000) for name, exponent in items
    }


def _linear(
    formulation: Formulation, *, in_units: bool = False
) -> dict[str, dict[str, Fraction] | None]:
    """Dimensions of the coefficients of unknown unit, by linear algebra.

    Each unknown gets one exponent per base dimension; every constraint is
    linear in these exponents. A coefficient whose exponents are not all
    fixed maps to ``None``.

    With ``in_units``, the exponents are those of the units the
    formulation is written with (:func:`_factors`) instead of base
    dimensions: the unit a coefficient of a numerical value equation
    holds for. Units of the same dimension (hPa and Pa) are then distinct
    factors: constraints they satisfy only together have no solution, and
    every coefficient maps to ``None`` instead of raising; a solution may
    also mix them (hPa^0.5/Pa^0.5), which is the unit the numerical value
    holds for.
    """
    context, constraints, _ = _setup(formulation)
    basis = _factors if in_units else _dimension
    bases = sorted({name for unit in context.units.values() for name in basis(unit)})
    if not bases or not context.unknown:
        # Every unit is a number (per mille against per mille): so is each
        # coefficient. Or every unit is declared: nothing to solve.
        return {name: {} for name in sorted(context.unknown)}
    exponents = {
        (name, base): sympy.Symbol(f"x_{name}_{index}")
        for name in sorted(context.unknown)
        for index, base in enumerate(bases)
    }

    def vector(node: Any) -> dict[str, Any]:
        if node.is_Symbol:
            if node.name in context.unknown:
                return {b: exponents[node.name, b] for b in bases}
            dimension = basis(context.units[node.name])
            return {b: sympy.Rational(dimension.get(b, 0)) for b in bases}
        if isinstance(node, sympy.Piecewise):
            # Like a sum: a branch not depending on an unknown, if any.
            branches = [e for e, _ in node.args]
            fixed = [e for e in branches if not context.depends(e)]
            return vector(fixed[0] if fixed else branches[0])
        if node.is_Number or node.is_NumberSymbol or isinstance(node, sympy.Function):
            return dict.fromkeys(bases, sympy.Integer(0))
        if node.is_Pow:
            if not node.exp.is_Number:
                return dict.fromkeys(bases, sympy.Integer(0))
            power = sympy.nsimplify(node.exp)
            return {b: power * e for b, e in vector(node.base).items()}
        if node.is_Mul:
            total = dict.fromkeys(bases, sympy.Integer(0))
            for factor in node.args:
                for b, e in vector(factor).items():
                    total[b] += e
            return total
        # A sum takes the dimension of a term not depending on an unknown.
        fixed = [t for t in node.args if not context.depends(t)]
        return vector(fixed[0] if fixed else node.args[0])

    equations: list[Any] = []
    for constraint in constraints:
        vectors = [vector(node) for node in constraint.nodes]
        if constraint.kind == "pure":
            vectors.append(dict.fromkeys(bases, sympy.Integer(0)))
        for other in vectors[1:]:
            equations.extend(other[b] - vectors[0][b] for b in bases)
    unknowns = list(exponents.values())
    solutions = sympy.linsolve(equations, unknowns)
    if not solutions:
        if in_units:
            return dict.fromkeys(sorted(context.unknown))
        msg = f"{formulation.key}: the units contradict the expression"
        raise DimensionError(msg)
    (solution,) = solutions
    values = dict(zip(unknowns, solution, strict=True))
    result: dict[str, dict[str, Fraction] | None] = {}
    for name in sorted(context.unknown):
        found = [values[exponents[name, b]] for b in bases]
        if all(v.is_Number for v in found):
            result[name] = {
                b: Fraction(str(v)) for b, v in zip(bases, found, strict=True) if v != 0
            }
        else:
            result[name] = None
    return result


def _from_dimension(dimension: Mapping[str, Fraction]) -> Any:
    unit: Any = ureg.dimensionless
    for base, exponent in dimension.items():
        unit = unit * ureg.Unit(_BASE_UNITS[base]) ** float(exponent)
    return unit


def _from_factors(factors: Mapping[str, Fraction]) -> Any:
    unit: Any = ureg.dimensionless
    for name, exponent in factors.items():
        unit = unit * ureg.Unit(name) ** float(exponent)
    return unit


def _solved_together(
    formulation: Formulation, context: _Context
) -> dict[str, tuple[Any, str]]:
    """Units of the coefficients propagation leaves, found by linear algebra.

    A quantity equation gets them in SI base units. A numerical value
    equation (fixed units) holds its coefficients for the units it is
    written with, which a unit in SI base units would misstate (a value
    for hPa is not one for Pa): its units are solved over its own units,
    and a coefficient they do not determine stays undetermined, so that
    a declaration is asked for.
    """
    dimensions = _linear(formulation)
    written = _linear(formulation, in_units=True) if formulation.fixed_units else {}
    found = {}
    for name, dimension in dimensions.items():
        if name in context.units or dimension is None:
            continue
        if not formulation.fixed_units:
            found[name] = (_from_dimension(dimension), "several constraints together")
            continue
        factors = written.get(name)
        if factors is not None and _dimension(_from_factors(factors)) == dimension:
            found[name] = (_from_factors(factors), "several constraints together")
    return found


def infer_units(formulation: Formulation) -> Mapping[str, CoefficientUnit]:
    """The unit of each coefficient of a formulation, declared or inferred.

    Parameters
    ----------
    formulation : Formulation
        The formulation; for a formulation with fixed units, the units of
        its variables are the ones the coefficients hold for.

    Returns
    -------
    mapping of str to CoefficientUnit
        By coefficient identifier, in declaration order. An inferred unit
        is built from the units of the formulation (B of the Magnus form
        in degrees Celsius, C in hPa). One found by linear algebra only
        is written in SI base units for a quantity equation; for a
        formulation with fixed units, it is solved over the units the
        formulation is written with, and left undetermined (``None``)
        when they do not fix it.

    Raises
    ------
    DimensionError
        If a declared unit contradicts the expression; the message names
        the part of the expression where the conflict appears.
    """
    context, constraints, _ = _setup(formulation)
    _propagate(context, constraints)
    _check(context, constraints)
    if any(name not in context.units for name in context.unknown):
        for name, (unit, reason) in _solved_together(formulation, context).items():
            context.units[name] = unit
            context.reasons[name] = reason
        _check(context, constraints)
    result = {}
    for coefficient in formulation.coefficients:
        name = coefficient.identifier
        origin: Literal["stated", "added", "inferred"] | None = None
        if name not in context.unknown:
            basis = coefficient.unit_basis
            origin = (
                "stated" if basis is not None and basis.value == "stated" else "added"
            )
        elif name in context.units:
            origin = "inferred"
        citation = next(
            (c.reference for c in formulation.citations if name in c.units), None
        )
        result[name] = CoefficientUnit(
            name,
            context.units.get(name),
            origin,
            context.reasons.get(name),
            citation if origin == "stated" else None,
        )
    return MappingProxyType(result)
