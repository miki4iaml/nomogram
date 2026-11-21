# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Monin-Obukhov similarity: profile functions from gradient functions, and back.

The gradient function φ(ζ) of a quantity gives its gradient in the
surface layer, its profile function ψ(ζ) the integrated profile (Paulson,
1970): ψ(ζ) = ∫₀^ζ (1 - φ(x)) / x dx, and back, φ(ζ) = 1 - ζ dψ/dζ.

:func:`profile_function` integrates a gradient function of the stability
parameter in closed form with SymPy, its coefficients and numbers taken
as exact fractions. A piecewise definition is integrated branch by
branch, each from the end of its interval nearest 0, where the branch
next to it ends; its branches must follow one another without gap. φ
must tend to 1 at 0 on each side, or the integral diverges there. The
closed form must hold in the syntax of expressions, and its values are
checked against a numerical quadrature (mpmath) in each branch, within
the domains the source states; otherwise the derivation is refused (no
numerical fallback). The domains the source states on the stability
parameter bound the derived function as they are; where one does not
hold the point the integral starts from (0, or the junction of a
branch), the note of the derived function says that the integral takes
φ outside it on the way.

:func:`gradient_function` differentiates a profile function, its
coefficients kept by name.

Both give an ordinary :class:`~nomogram.model.Formulation`, with an
expression, its LaTeX in any notation, a
:class:`~nomogram.model.Derivation` recording the source and the method,
and the citations of the source with their domains on the stability
parameter and their assumptions, but without the equation number, the
accuracy and the note they give of the source. A source defined by
branches gives a derived formulation by branches, each with the domains
of its own.
"""

from __future__ import annotations

import math
from dataclasses import replace
from fractions import Fraction
from functools import lru_cache
from itertools import pairwise
from types import MappingProxyType
from typing import Any

import numpy as np

from nomogram.expression import PIECEWISE, ExpressionError, _pieces, parse_expression
from nomogram.inversion import _source
from nomogram.model import (
    Branch,
    Citation,
    Derivation,
    Formulation,
    ValidityDomain,
    Variable,
)

__all__ = [
    "STABILITY",
    "DerivationError",
    "gradient_function",
    "profile_function",
]

#: The kind of the input of a gradient or profile function, or a kind
#: specializing it.
STABILITY = "StabilityParameter"

#: The profile function of each kind of gradient function, with the
#: identifier of its output by default; and back.
_PROFILE_OF = MappingProxyType(
    {
        "GradientFunctionForMomentum": ("ProfileFunctionForMomentum", "Psi_M"),
        "GradientFunctionForHeat": ("ProfileFunctionForHeat", "Psi_H"),
    }
)
_GRADIENT_OF = MappingProxyType(
    {
        "ProfileFunctionForMomentum": ("GradientFunctionForMomentum", "Phi_M"),
        "ProfileFunctionForHeat": ("GradientFunctionForHeat", "Phi_H"),
    }
)

#: Distances from the end of a branch, relative to max(1, |end|), at which
#: a branch of infinite extent is checked.
_REACH = (0.01, 0.1, 1.0, 10.0)

#: Agreement asked of a closed form with the quadrature, relative to
#: max(1, |ψ|).
_AGREEMENT = 1e-9


class DerivationError(ValueError):
    """A formulation cannot be derived as asked."""


def profile_function(
    gradient: Formulation,
    *,
    output: Variable | None = None,
    key: str | None = None,
    label: str | None = None,
) -> Formulation:
    """The profile function of a gradient function, ψ(ζ) = ∫₀^ζ (1 - φ(x)) / x dx.

    Parameters
    ----------
    gradient : Formulation
        An explicit gradient function of one input, the stability
        parameter, which tends to 1 at 0.
    output : Variable, optional
        The profile function's output; by default the profile function
        for momentum (``Psi_M``) or heat (``Psi_H``), after the kind of the
        gradient function.
    key, label : str, optional
        Identification; derived from the source otherwise.

    Returns
    -------
    Formulation
        ψ in closed form, its ``derivation`` recording the source and the
        method ``"integration"``. A domain of the source without the point
        its integral starts from (0, or the junction of a branch) is
        carried as it is, and the note says that the integral takes φ
        outside it.

    Raises
    ------
    DerivationError
        If the gradient function is implicit, not of the stability
        parameter alone, does not tend to 1 at 0, has branches with a gap
        between them, has no closed-form integral in the syntax of
        expressions, or one that departs from the quadrature; or if no
        output is given for a kind without a default.
    """
    import sympy

    zeta = _single_input(gradient, "a gradient function")
    output = _output(gradient, output, _PROFILE_OF, "profile function")
    phi = _exact(gradient)
    z = sympy.Symbol(zeta.identifier, real=True)
    names = (zeta.identifier,)
    if phi.has(sympy.Piecewise) and not isinstance(phi, sympy.Piecewise):
        msg = f"{gradient.key}: a piecewise definition inside an expression is not integrated"
        raise DerivationError(msg)
    if isinstance(phi, sympy.Piecewise):
        branches = _integrated_pieces(gradient, phi, z, names)
    else:
        _tends_to_one(gradient, phi, z, "+-")
        psi = _integral(gradient, phi, z, sympy.Integer(0), sympy.Integer(0))
        branches = [
            _Piece(phi, -math.inf, math.inf, 0.0, _text(gradient, psi, names), None)
        ]
    _check(gradient, branches, zeta)
    key = key or f"{gradient.key}_profile_function"
    label = label or f"Profile function of: {gradient.label}"
    note = (
        f"Derived by nomogram from {gradient.key}: psi(zeta) = integral from 0 to "
        "zeta of (1 - phi(x)) / x dx, in closed form by SymPy, the coefficients "
        "taken as exact fractions."
    )
    if len(branches) == 1:
        text = branches[0].text
    else:
        text = (
            f"{PIECEWISE}({', '.join(f'({b.text}, {b.condition})' for b in branches)})"
        )
    if not gradient.branches:
        return _derived(
            gradient,
            output,
            text,
            key,
            label,
            "integration",
            note,
            start=0.0,
            coefficients=False,
        )
    # Each branch keeps the domains and assumptions of its own.
    derived_branches = [
        Branch(
            _derived(
                branch.formulation,
                output,
                piece.text,
                f"{key}_{i + 1}",
                f"{label} ({branch.condition})",
                "integration",
                note,
                start=piece.start,
                coefficients=False,
            ),
            branch.condition,
        )
        for i, (branch, piece) in enumerate(
            zip(gradient.branches, sorted(branches, key=lambda p: p.index), strict=True)
        )
    ]
    whole = _derived(
        gradient,
        output,
        text,
        key,
        label,
        "integration",
        note,
        start=None,
        coefficients=False,
    )
    return replace(
        whole, branches=tuple(derived_branches), citations=(), physical_domains=()
    )


def gradient_function(
    profile: Formulation,
    *,
    output: Variable | None = None,
    key: str | None = None,
    label: str | None = None,
) -> Formulation:
    """The gradient function of a profile function, φ(ζ) = 1 - ζ dψ/dζ.

    Parameters
    ----------
    profile : Formulation
        An explicit profile function of one input, the stability
        parameter.
    output : Variable, optional
        The gradient function's output; by default the gradient function
        for momentum (``Phi_M``) or heat (``Phi_H``), after the kind of the
        profile function.
    key, label : str, optional
        Identification; derived from the source otherwise.

    Returns
    -------
    Formulation
        φ, its ``derivation`` recording the source and the method
        ``"differentiation"``; the coefficients of the source keep their
        names.

    Raises
    ------
    DerivationError
        If the profile function is implicit, not of the stability
        parameter alone, or holds a piecewise definition inside an
        expression; or if no output is given for a kind without a default.
    """
    import sympy

    zeta = _single_input(profile, "a profile function")
    output = _output(profile, output, _GRADIENT_OF, "gradient function")
    z = sympy.Symbol(zeta.identifier, real=True)
    psi = profile.sympy_expression
    factor = profile.output_factor
    if psi.has(sympy.Piecewise) and not isinstance(psi, sympy.Piecewise):
        msg = f"{profile.key}: a piecewise definition inside an expression is not differentiated"
        raise DerivationError(msg)

    def derivative(expr: Any) -> str:
        scaled = expr if factor == 1 else expr * factor
        return _source(1 - z * sympy.diff(scaled, z))

    if isinstance(psi, sympy.Piecewise):
        texts = [
            f"({derivative(piece.expression)}, {_condition(piece, zeta.identifier)})"
            for piece in _split(profile, psi, (zeta.identifier,))
        ]
        text = f"{PIECEWISE}({', '.join(texts)})"
    else:
        text = derivative(psi)
    return _derived(
        profile,
        output,
        text,
        key or f"{profile.key}_gradient_function",
        label or f"Gradient function of: {profile.label}",
        "differentiation",
        f"Derived by nomogram from {profile.key}: phi(zeta) = 1 - zeta dpsi/dzeta.",
        start=None,
        coefficients=True,
    )


class _Piece:
    """A branch of a derivation: its integrand φ, its interval, where its
    integral starts, its closed form, its condition (``None`` alone) and
    its place among the branches of the source."""

    def __init__(
        self,
        phi: Any,
        low: float,
        high: float,
        start: float,
        text: str,
        condition: str | None,
        index: int = 0,
    ) -> None:
        self.phi, self.low, self.high, self.start = phi, low, high, start
        self.text, self.condition, self.index = text, condition, index


def _single_input(formulation: Formulation, what: str) -> Variable:
    from nomogram.comparison import feeds

    if formulation.implicit:
        msg = f"{formulation.key}: an implicit equation is not {what} to derive from"
        raise DerivationError(msg)
    if len(formulation.inputs) != 1:
        msg = f"{formulation.key}: {what} takes one input, the stability parameter"
        raise DerivationError(msg)
    zeta = formulation.inputs[0]
    if not feeds(zeta.kind, STABILITY):
        msg = (
            f"{formulation.key}: {what} is of the stability parameter, not of "
            f"{zeta.identifier} ({zeta.kind})"
        )
        raise DerivationError(msg)
    return zeta


def _output(
    source: Formulation,
    output: Variable | None,
    defaults: MappingProxyType[str, tuple[str, str]],
    what: str,
) -> Variable:
    if output is None:
        if source.output.kind not in defaults:
            msg = f"{source.key} computes {source.output.kind}: give the output of its {what}"
            raise DerivationError(msg)
        kind, identifier = defaults[source.output.kind]
        output = Variable(identifier, kind, "UNITLESS", what.capitalize())
    if output.identifier == source.inputs[0].identifier:
        msg = f"{source.key}: the output of its {what} cannot be named after its input"
        raise DerivationError(msg)
    return output


def _exact(formulation: Formulation) -> Any:
    """The expression with its coefficients, constants and numbers as exact
    fractions: SymPy integrates rationals where floats derail it."""
    import sympy

    def exact(value: float) -> Any:
        # The simplest fraction the float stands for (10/13 for
        # 0.7692307692307693, 47/10 for 4.7), else its decimal.
        fraction = Fraction(float(value)).limit_denominator(10**8)
        if abs(float(fraction) - value) <= 1e-15 * abs(value):
            return sympy.Rational(fraction.numerator, fraction.denominator)
        return sympy.Rational(repr(float(value)))

    pairs = [(c.identifier, c.value) for c in formulation.coefficients]
    pairs += [(k.identifier, k.value) for k in formulation.constants]
    values = {sympy.Symbol(name, real=True): exact(value) for name, value in pairs}
    expr = formulation.sympy_expression.xreplace(values)
    expr = expr.xreplace({f: exact(float(f)) for f in expr.atoms(sympy.Float)})
    factor = exact(formulation.output_factor)
    return expr if factor == 1 else expr * factor


def _tends_to_one(source: Formulation, phi: Any, z: Any, sides: str) -> None:
    """φ tends exactly to 1 at 0 from each side asked, or the integral of
    (1 - φ(x)) / x diverges there."""
    import sympy

    for side in sides:
        try:
            limit = sympy.limit(phi, z, 0, dir=side)
        except (NotImplementedError, ValueError, TypeError) as error:
            msg = f"{source.key}: no limit of its gradient function at 0 ({error})"
            raise DerivationError(msg) from error
        if limit != 1:
            msg = (
                f"{source.key} tends to {limit} at {z} = 0 from the {side} side: the "
                "integral of (1 - phi(x)) / x diverges unless phi tends to 1 there"
            )
            raise DerivationError(msg)


def _integral(source: Formulation, phi: Any, z: Any, start: Any, offset: Any) -> Any:
    """offset + ∫_start^z (1 - phi(x)) / x dx, in closed form, or an error."""
    import sympy
    from sympy.polys.polyerrors import BasePolynomialError

    try:
        found = _integrate(phi, z, start)
    except (
        NotImplementedError,
        ValueError,
        TypeError,
        RecursionError,
        BasePolynomialError,
    ) as error:
        msg = f"{source.key}: SymPy finds no closed-form integral ({error})"
        raise DerivationError(msg) from error
    if found.has(sympy.Integral):
        msg = f"{source.key}: SymPy finds no closed-form integral"
        raise DerivationError(msg)
    return offset + found


@lru_cache(maxsize=256)
def _integrate(phi: Any, z: Any, start: Any) -> Any:
    """∫_start^z (1 - phi(x)) / x dx by SymPy: costly and deterministic."""
    import sympy

    x = sympy.Dummy("x", real=True)
    integrand = (1 - phi.xreplace({z: x})) / x
    return sympy.integrate(integrand, (x, start, z), conds="none")


def _text(source: Formulation, psi: Any, names: tuple[str, ...]) -> str:
    """The closed form in the syntax of expressions, simplified until it is
    one, or an error."""
    import sympy

    attempts = [lambda e: e, sympy.gammasimp]
    if not psi.has(sympy.exp_polar):
        # A form on complex branches (roots of unity) stays one: simplify
        # would only take long.
        attempts.append(sympy.simplify)
    complex_form = False
    for attempt in attempts:
        try:
            candidate = attempt(psi)
        except (NotImplementedError, ValueError, TypeError, RecursionError):
            continue
        if candidate.has(sympy.I, sympy.exp_polar):
            complex_form = True
            continue
        if candidate.has(sympy.zoo, sympy.nan, sympy.oo):
            continue
        text = _source(candidate)
        try:
            parse_expression(text, names, limit=None)
        except (ExpressionError, ValueError):
            continue
        return text
    if complex_form:
        msg = f"{source.key}: SymPy writes the closed form with complex numbers"
    else:
        msg = f"{source.key}: the closed form holds functions outside the syntax of expressions"
    raise DerivationError(msg)


def _split(source: Formulation, expr: Any, names: tuple[str, ...]) -> Any:
    try:
        return _pieces(expr, names)
    except ExpressionError as error:
        msg = f"{source.key}: {error}"
        raise DerivationError(msg) from error


def _bound(value: Any) -> str:
    """A bound of a condition: a number as Python writes it, else as text."""
    return repr(float(value)) if value.is_number else _source(value)


def _infinite(value: Any) -> bool:
    return bool(value.is_number and math.isinf(float(value)))


def _condition(piece: Any, identifier: str) -> str:
    """The condition of a branch, as an interval of the input, a bound
    possibly a coefficient."""
    text = identifier
    if not _infinite(piece.low):
        text = f"{_bound(piece.low)} {'<=' if piece.low_closed else '<'} {text}"
    if not _infinite(piece.high):
        text = f"{text} {'<=' if piece.high_closed else '<'} {_bound(piece.high)}"
    return text


def _integrated_pieces(
    source: Formulation, phi: Any, z: Any, names: tuple[str, ...]
) -> list[_Piece]:
    """Each branch integrated from the end of its interval nearest 0, where
    the branch next to it ends, in order of the intervals."""
    import sympy

    found = _split(source, phi, names)
    order = sorted(range(len(found)), key=lambda i: float(found[i].low))
    pieces = [found[i] for i in order]
    for before, after in pairwise(pieces):
        # A point left out between two strict conditions (zeta < 0, zeta > 0)
        # changes no integral; a gap or an overlap would.
        if before.high != after.low or (before.high_closed and after.low_closed):
            msg = (
                f"{source.key}: its branches do not follow one another at "
                f"{z} = {after.low} (a gap or an overlap)"
            )
            raise DerivationError(msg)
    near = [i for i, p in enumerate(pieces) if bool(p.low <= 0) and bool(p.high >= 0)]
    if not near:
        msg = f"{source.key}: no branch holds the stability parameter 0"
        raise DerivationError(msg)
    for i in near:
        # From each side of 0 its branch holds.
        sides = ("-" if bool(pieces[i].low < 0) else "") + (
            "+" if bool(pieces[i].high > 0) else ""
        )
        _tends_to_one(source, pieces[i].expression, z, sides)
    first = min(near)
    integrals: dict[int, Any] = {}
    starts: dict[int, Any] = {}
    # Outwards from 0: leftwards from the first branch holding 0, then
    # rightwards from the next one.
    for i in [*range(first, -1, -1), *range(first + 1, len(pieces))]:
        piece = pieces[i]
        if bool(piece.low <= 0) and bool(piece.high >= 0):
            start, offset = sympy.Integer(0), sympy.Integer(0)
        elif bool(piece.high <= 0):
            start = piece.high
            offset = integrals[i + 1].xreplace({z: start})
        else:
            start = piece.low
            offset = integrals[i - 1].xreplace({z: start})
        starts[i] = start
        integrals[i] = _integral(source, piece.expression, z, start, offset)
    return [
        _Piece(
            piece.expression,
            float(piece.low),
            float(piece.high),
            float(starts[i]),
            _text(source, integrals[i], names),
            _condition(piece, names[0]),
            order[i],
        )
        for i, piece in enumerate(pieces)
    ]


def _check(source: Formulation, branches: list[_Piece], zeta: Variable) -> None:
    """Each branch of the closed form against a quadrature of (1 - φ(x)) / x
    from 0, at points inside it and within the domains the source states,
    if any; each branch they reach checked at one point at least."""
    import mpmath
    import sympy

    from nomogram.expression import compile_numeric

    z = sympy.Symbol(zeta.identifier, real=True)
    # Renamed as nomogram.expression does, so that the identifier (e, pi)
    # cannot shadow a name of the generated code.
    renamed = sympy.Symbol(f"_v_{zeta.identifier}", real=True)
    names = (zeta.identifier,)
    functions = [
        (
            b,
            sympy.lambdify(
                renamed, ((1 - b.phi) / z).xreplace({z: renamed}), modules="mpmath"
            ),
            compile_numeric(parse_expression(b.text, names, limit=None), names),
        )
        for b in branches
    ]

    def integrand(x: Any) -> Any:
        value = float(x)
        for branch, function, _ in functions:
            if branch.low <= value <= branch.high:
                return function(x)
        return mpmath.nan

    bounds = [
        d.bounds[zeta.identifier] for d in source.domains if zeta.identifier in d.bounds
    ]
    junctions = sorted({b.low for b in branches} | {b.high for b in branches})
    for branch, _, closed in functions:
        points = _points_inside(branch.low, branch.high, bounds)
        if not points:
            continue  # the domains leave the branch out
        checked = 0
        for point in points:
            if point == 0 or not _regular(source, zeta, point):
                continue
            between = [j for j in junctions if min(0, point) < j < max(0, point)]
            path = [0.0, *sorted(between, reverse=point < 0), point]
            try:
                value, error = mpmath.quad(integrand, path, error=True)
            except (ValueError, ZeroDivisionError, TypeError):
                continue
            quadrature = float(value)
            if not float(error) <= _AGREEMENT * max(1.0, abs(quadrature)):
                continue  # the quadrature itself is not sure there
            with np.errstate(all="ignore"):
                found = float(np.asarray(closed(np.array(point))))
            if not abs(found - quadrature) <= _AGREEMENT * max(1.0, abs(quadrature)):
                msg = (
                    f"{source.key}: the closed form gives {found!r} at "
                    f"{zeta.identifier} = {point!r}, the quadrature {quadrature!r}"
                )
                raise DerivationError(msg)
            checked += 1
        if not checked:
            msg = (
                f"{source.key}: no point to check the closed form at on "
                f"[{branch.low!r}, {branch.high!r}]"
            )
            raise DerivationError(msg)


def _points_inside(
    low: float, high: float, bounds: list[tuple[float, float]]
) -> list[float]:
    """Points inside a branch, within the stated domains if any."""
    if math.isfinite(low) and math.isfinite(high):
        candidates = [float(v) for v in np.linspace(low, high, 7)[1:-1]]
    else:
        end = low if math.isfinite(low) else high if math.isfinite(high) else 0.0
        scale = max(1.0, abs(end))
        steps = [end + r * scale for r in _REACH] + [end - r * scale for r in _REACH]
        candidates = [p for p in steps if low < p < high]
    if bounds:
        candidates = [p for p in candidates if any(a <= p <= b for a, b in bounds)]
        for a, b in bounds:
            inner = (max(a, low), min(b, high))
            if inner[0] < inner[1] and all(map(math.isfinite, inner)):
                candidates += [
                    float(v) for v in np.linspace(inner[0], inner[1], 5)[1:-1]
                ]
    return candidates


def _regular(source: Formulation, zeta: Variable, point: float) -> bool:
    """Whether φ stays finite and bounded from 0 to the point: no pole on the
    way (the gradient function of SHEBA for heat has two at zeta < 0)."""
    path = np.linspace(0.0, point, 2001)
    with np.errstate(all="ignore"):
        phi = np.asarray(source._raw({zeta.identifier: path}), dtype=float)
    # The value at 0 itself may be undefined (conditions strict on both
    # sides): its limit was checked.
    inner = phi[1:]
    if not np.isfinite(inner).all():
        return False
    ends = max(1.0, abs(float(inner[0])), abs(float(inner[-1])))
    return bool(np.max(np.abs(inner)) <= 1e3 * ends)


def _carried(
    domains: tuple[ValidityDomain, ...], identifier: str
) -> tuple[ValidityDomain, ...]:
    """The domains of the source on the stability parameter, its output left
    out: they bound the input of the derived function as the source states
    them (see :func:`_beyond_start`)."""
    carried = []
    for domain in domains:
        if identifier not in domain.bounds:
            continue
        low, high = domain.bounds[identifier]
        tolerance = {k: v for k, v in domain.tolerance.items() if k == identifier}
        carried.append(
            ValidityDomain(
                domain.basis,
                MappingProxyType({identifier: (low, high)}),
                domain.criterion,
                domain.reference,
                MappingProxyType(tolerance),
            )
        )
    return tuple(carried)


def _beyond_start(source: Formulation, start: float) -> str:
    """What the note says of each domain of the source without the point its
    integral starts from: the integral takes φ outside it, between its end
    nearest the start and the start."""
    zeta = source.inputs[0].identifier
    remarks = []
    for domain in source.domains:
        if zeta not in domain.bounds:
            continue
        low, high = domain.bounds[zeta]
        if low <= start <= high:
            continue
        end = high if high < start else low
        remarks.append(
            f" The domain [{low!r}, {high!r}] of {source.key} does not hold "
            f"{zeta} = {start!r}: the integral also takes its gradient function "
            f"between {end!r} and {start!r}, outside it."
        )
    return "".join(remarks)


def _cited(citation: Citation, source: Formulation, keep_units: bool) -> Citation:
    """A citation of the source, as the derived formulation keeps it: its
    domains on the stability parameter and its assumptions, not what it
    says of the source alone (equation number, accuracy, note, the symbol
    of its output)."""
    zeta = source.inputs[0].identifier
    notation = citation.notation
    if notation is not None:
        notation = replace(
            notation,
            symbols=MappingProxyType(
                {
                    k: v
                    for k, v in notation.symbols.items()
                    if k != source.output.identifier
                }
            ),
        )
    return replace(
        citation,
        equation=None,
        notation=notation,
        domains=_carried(citation.domains, zeta),
        units=citation.units if keep_units else MappingProxyType({}),
        scales=MappingProxyType({}),
        accuracy=None,
        note=f"Of {source.key}, from which nomogram derived this formulation.",
    )


def _derived(
    source: Formulation,
    output: Variable,
    text: str,
    key: str,
    label: str,
    method: str,
    note: str,
    *,
    start: float | None,
    coefficients: bool,
) -> Formulation:
    zeta = source.inputs[0]
    if start is not None:
        note += _beyond_start(source, start)
    return Formulation(
        key=key,
        label=label,
        output=output,
        inputs=(zeta,),
        coefficients=source.coefficients if coefficients else (),
        constants=source.constants if coefficients else (),
        expression=text,
        fixed_units=True,
        physical_domains=_carried(source.physical_domains, zeta.identifier),
        citations=tuple(_cited(c, source, coefficients) for c in source.citations),
        note=note,
        matches=(),
        derivation=Derivation(source.key, method, None),
    )
