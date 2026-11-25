# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Formulations derived by differentiation.

:func:`derivative` differentiates an explicit formulation with respect to
one of its inputs, at a given order, with SymPy: the slope of a saturation
vapour pressure curve, de_s/dT, from a formulation of e_s. The derivative
is an ordinary :class:`~nomogram.model.Formulation`:

- it keeps the inputs of its source, with their units and scales, and the
  coefficients and constants its expression still uses, under their names;
- its expression is the closed form :func:`sympy.diff` gives, without
  further simplification, and its LaTeX derives from it in any notation;
- the source is its part: the domains of the source, physical and stated,
  and the bounds of its kinds apply to the values the derivative receives,
  as for a composition;
- its :class:`~nomogram.model.Derivation` records the source, the method
  ``"differentiation"``, the input and the order; with no citation of its
  own, it is derived by nomogram.

A source defined by pieces is differentiated piece by piece, each under
its condition; a piecewise definition inside an expression is refused, and
so is an implicit equation. A source that holds only in its units (fixed
units) gives a derivative in the unit of its output divided by that of the
input, to the order, nothing being converted: hPa/K from a saturation
vapour pressure in hPa and a temperature in kelvins. A quantity equation
gives it in any unit of that dimension.

A catalog entry derives a formulation so (see the catalog guide)::

    [formulations.sonntag1990_slope]
    label = "Slope of the Sonntag (1990) saturation vapour pressure over water"
    derivative = { of = "sonntag1990", with_respect_to = "T" }
    output = { identifier = "de_s", kind = "...", unit = "HectoPA-PER-K", description = "..." }
"""

from __future__ import annotations

import math
import operator
from typing import TYPE_CHECKING, Any, SupportsIndex

if TYPE_CHECKING:
    from collections.abc import Mapping

    from nomogram.model import Formulation, Variable
    from nomogram.semantics import QuantityKind

__all__ = ["derivative"]


def derivative(
    formulation: Formulation,
    with_respect_to: str,
    output: Variable,
    *,
    order: SupportsIndex = 1,
    key: str | None = None,
    label: str | None = None,
    kinds: Mapping[str, QuantityKind] | None = None,
) -> Formulation:
    """The derivative of a formulation with respect to one of its inputs.

    Parameters
    ----------
    formulation : Formulation
        An explicit formulation.
    with_respect_to : str
        Identifier of the input the derivative is taken with respect to.
    output : Variable
        The derivative's output: its identifier, quantity kind and unit,
        which no rule derives from those of the source.
    order : int, default 1
        Order of the derivative, a whole number of 1 or more (an int, or
        numpy's).
    key, label : str, optional
        Identification; derived from the source otherwise.
    kinds : mapping of str to QuantityKind, optional
        The quantity kinds against which the unit of ``output`` is checked
        to apply to its kind; those of the bundled catalog by default.

    Returns
    -------
    Formulation
        The derivative, its source as its part, its derivation recording
        the source, the method ``"differentiation"``, the input and the
        order.

    Raises
    ------
    ~nomogram.similarity.DerivationError
        If the formulation is implicit or holds a piecewise definition
        inside an expression; if ``with_respect_to`` is not one of its
        inputs; if the order is not a whole number of 1 or more; if the
        unit of ``output`` is unknown, does not apply to its kind, or does
        not have the dimension of the source's output divided by that of
        the input, to the order; or, for a formulation that holds only in
        its units, if it is not that unit itself.
    """
    import sympy

    from nomogram.expression import PIECEWISE, ExpressionError, _pieces
    from nomogram.inversion import _source
    from nomogram.model import Derivation, Formulation, Part
    from nomogram.similarity import DerivationError, _condition

    try:
        whole = operator.index(order)  # an int, or numpy's
    except TypeError:
        whole = 0
    if isinstance(order, bool) or whole < 1:
        msg = (
            f"{formulation.key}: the order of a derivative is a whole number "
            f"of 1 or more, not {order!r}"
        )
        raise DerivationError(msg)
    order = whole
    if formulation.implicit:
        msg = f"{formulation.key}: an implicit equation is not differentiated"
        raise DerivationError(msg)
    inputs = {v.identifier: v for v in formulation.inputs}
    if with_respect_to not in inputs:
        msg = f"{formulation.key} has no input {with_respect_to!r}"
        raise DerivationError(msg)
    _check_unit(formulation, inputs[with_respect_to], output, order, kinds)

    symbol = sympy.Symbol(with_respect_to, real=True)
    expr = formulation.sympy_expression
    if isinstance(expr, sympy.Piecewise):
        try:
            pieces = _pieces(expr, tuple(inputs))
        except (
            ExpressionError
        ) as error:  # pragma: no cover - the catalog refuses such a condition first
            msg = f"{formulation.key}: {error}"
            raise DerivationError(msg) from error
        derived = [sympy.diff(p.expression, symbol, order) for p in pieces]
        # The bounds of the conditions are written again: a coefficient or a
        # constant bounding a piece stays declared.
        bounds = [
            end
            for p in pieces
            for end in (p.low, p.high)
            if hasattr(end, "free_symbols")
        ]
        if any(d.has(sympy.Piecewise) for d in derived):
            msg = f"{formulation.key}: a piecewise definition inside an expression is not differentiated"
            raise DerivationError(msg)
        branches = [
            f"({_source(d)}, {_condition(p, p.variable.name)})"
            for d, p in zip(derived, pieces, strict=True)
        ]
        text = f"{PIECEWISE}({', '.join(branches)})"
    else:
        if expr.has(sympy.Piecewise):
            msg = f"{formulation.key}: a piecewise definition inside an expression is not differentiated"
            raise DerivationError(msg)
        derived = [sympy.diff(expr, symbol, order)]
        bounds = []
        text = _source(derived[0])
    used = {s.name for d in (*derived, *bounds) for s in d.free_symbols}

    of = formulation.output.identifier
    leibniz = (
        f"d{of}/d{with_respect_to}"
        if order == 1
        else f"d^{order} {of}/d{with_respect_to}^{order}"
    )
    suffix = "" if order == 1 else f"_{order}"
    return Formulation(
        key=key or f"{formulation.key}_derivative_{with_respect_to}{suffix}",
        label=label
        or f"Derivative of order {order} of: {formulation.label}, with respect to {with_respect_to}",
        output=output,
        inputs=formulation.inputs,
        coefficients=tuple(c for c in formulation.coefficients if c.identifier in used),
        constants=tuple(k for k in formulation.constants if k.identifier in used),
        expression=text,
        fixed_units=formulation.fixed_units,
        physical_domains=(),
        citations=(),
        note=f"Derived by nomogram from {formulation.key}: {leibniz}.",
        matches=(),
        derivation=Derivation(
            formulation.key,
            "differentiation",
            with_respect_to=with_respect_to,
            order=order,
        ),
        parts=(Part(formulation, None),),
    )


def _check_unit(
    source: Formulation,
    variable: Variable,
    output: Variable,
    order: int,
    kinds: Mapping[str, QuantityKind] | None,
) -> None:
    """Refuse a unit of the derivative of another dimension, or, for a
    source in fixed units, other than the unit of its output divided by
    that of the input, to the order: its numbers are computed so."""
    from nomogram.dimensions import _pint
    from nomogram.similarity import DerivationError

    if kinds is None:
        from nomogram.catalog import catalog

        kinds = catalog().kinds
    kind = kinds.get(output.kind)
    if kind is None or output.unit not in kind.applicable_units:
        msg = f"{output.identifier}: {output.unit} does not apply to {output.kind}"
        raise DerivationError(msg)
    expected = _pint(source.output.unit) / _pint(variable.unit) ** order
    given = _pint(output.unit)
    if expected.dimensionality != given.dimensionality:
        msg = (
            f"{source.key}: the derivative of {source.output.identifier} with "
            f"respect to {variable.identifier} is in {expected:~P}, a "
            f"dimension {output.unit} does not have"
        )
        raise DerivationError(msg)
    factor: Any = (1 * expected).to(given).magnitude
    if source.fixed_units and not math.isclose(factor, 1.0, rel_tol=1e-12):
        msg = (
            f"{source.key} holds only in its units: its derivative is "
            f"computed in {expected:~P}, not in {output.unit}"
        )
        raise DerivationError(msg)
