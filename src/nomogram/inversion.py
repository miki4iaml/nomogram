# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Inverting formulations: closed form by symbolic computation, or numerically.

A formulation y = f(x) of one input can be inverted into x = g(y). For
the dew point, the saturation vapour pressure e_s = f(t) becomes
t_d = g(e): the temperature at which a vapour pressure e saturates.

:func:`invert` first looks for a closed form with SymPy, after taking the
logarithm of both sides (which turns the usual exponential forms into
rational equations). The closed form becomes an ordinary
:class:`~nomogram.model.Formulation`, with an expression in the catalog
syntax, LaTeX in any notation, validity domains carried through the
function, and a :class:`~nomogram.model.Derivation` recording its
origin. When there is none, or when the unknown appears more than
:data:`SYMBOLIC_MAX_OCCURRENCES` times (to keep the search short), the
result is a :class:`NumericalInverse`, solved by vectorised bisection
over a search interval.

A piecewise definition is inverted branch by branch, **provided each
branch is strictly monotonic on its interval** (nomogram checks it on
samples; a constant branch is not):
each branch then needs a closed form, and the images of the intervals,
which become the conditions of the inverse, must not overlap. Otherwise
the inverse is numerical.

Values stay on the reference scales of their kinds at both ends (ITS-90
for temperatures, Reference Salinity for salinities): the inverse takes
its input on the scale of the source's output, and converts its result
back from the scale of the source's input.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from nomogram.expression import (
    PIECEWISE,
    _pieces,
    compile_numeric,
    parse_expression,
)
from nomogram.model import (
    Basis,
    Coefficient,
    Derivation,
    Formulation,
    OutOfDomainError,
    Outside,
    ScaleConversion,
    UnitBasis,
    ValidityDomain,
    ValidityWarning,
    Variable,
    _check_given,
    _check_options,
    _flag_beyond,
)
from nomogram.semantics import semantic_catalog
from nomogram.units import Q_, convert

__all__ = [
    "DEW_POINT_SEARCH_CELSIUS",
    "SYMBOLIC_MAX_OCCURRENCES",
    "InversionError",
    "NumericalInverse",
    "dew_point",
    "invert",
]

#: Above this many occurrences of the unknown (after taking logarithms),
#: no closed form is sought: SymPy would search for long and find none.
SYMBOLIC_MAX_OCCURRENCES = 3

#: Interval searched by :func:`dew_point` when the formulation states no
#: validity domain, in degC: a search interval, not a validity domain.
DEW_POINT_SEARCH_CELSIUS = (-100.0, 100.0)

#: Name of the offset coefficient, 273.15 K, added when the result changes
#: from K to degC or back (t = T - T0, SI Brochure, section 2.3.1).
_OFFSET = "T_celsius_zero"

Method = Literal["auto", "symbolic", "numerical"]


class InversionError(ValueError):
    """The formulation cannot be inverted as asked."""


def _source(expr: Any) -> str:
    """The catalog-syntax source of a SymPy expression (``ln`` for ``log``)."""
    from sympy.printing.str import StrPrinter

    class Printer(StrPrinter):  # type: ignore[misc]
        def _print_log(self, node: Any) -> str:
            return f"ln({self._print(node.args[0])})"

    return str(Printer().doprint(expr))


def _check(
    formulation: Formulation, solve_for: str, output: Variable, input: Variable
) -> None:
    if len(formulation.inputs) != 1:
        msg = f"{formulation.key}: only formulations of one input can be inverted"
        raise InversionError(msg)
    if formulation.inputs[0].identifier != solve_for:
        msg = f"{formulation.key} has no input {solve_for!r}"
        raise InversionError(msg)
    if input.unit != formulation.output.unit:
        msg = (
            f"the new input must keep the unit of {formulation.key}'s output "
            f"({formulation.output.unit}), the unit its coefficients hold in"
        )
        raise InversionError(msg)
    from nomogram.catalog import catalog

    kinds = catalog().kinds
    for variable in (output, input):
        kind = kinds.get(variable.kind)
        if kind is None or variable.unit not in kind.applicable_units:
            msg = f"{variable.identifier}: {variable.unit} does not apply to {variable.kind}"
            raise InversionError(msg)
    if (
        formulation.inputs[0].kind == "TemperatureDifference"
        or output.kind == "TemperatureDifference"
    ):
        msg = "inverting temperature differences is not supported"
        raise InversionError(msg)


def _forward(formulation: Formulation, expr: Any = None) -> Any:
    """The formulation's numeric function of its single input, in its units.

    ``expr`` replaces the formulation's expression (a branch of it).
    """
    source = formulation.sympy_expression if expr is None else expr
    function = compile_numeric(source, formulation.names)
    fixed = [c.value for c in formulation.coefficients] + [
        k.value for k in formulation.constants
    ]
    factor = formulation.output_factor

    def forward(x: Any) -> Any:
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            result = np.asarray(function(x, *fixed), dtype=float) * factor
        # A constant (a branch of a piecewise definition) gives one number
        # whatever the shape of x.
        return np.broadcast_to(result, np.shape(x))

    return forward


def _bounds(formulation: Formulation, solve_for: str) -> tuple[float, float] | None:
    """Intersection of the stated domains on the input, if any."""
    stated = [
        d.bounds[solve_for]
        for d in formulation.domains
        if d.basis.value == "stated" and solve_for in d.bounds
    ]
    if not stated:
        return None
    return max(low for low, _ in stated), min(high for _, high in stated)


def _offset(source_unit: str, target_unit: str) -> float:
    """What to add to the solved value to express it in the target unit."""
    if source_unit == target_unit:
        return 0.0
    if (source_unit, target_unit) == ("K", "DEG_C"):
        return -273.15
    if (source_unit, target_unit) == ("DEG_C", "K"):
        return 273.15
    msg = f"cannot express a result solved in {source_unit} in {target_unit}"
    raise InversionError(msg)


def _closed_form(
    formulation: Formulation,
    expr: Any,
    solve_for: str,
    output: Variable,
    input: Variable,
    samples: Any,
) -> tuple[str, list[Coefficient]] | None:
    """A closed-form inverse of ``expr``, as source text, checked on samples.

    Returns the source and the coefficients it uses (those of the
    formulation, plus the offset when the result changes from K to degC
    or back).
    """
    import sympy

    x = sympy.Symbol(solve_for, real=True)
    y = sympy.Symbol(input.identifier, positive=True)
    lhs = sympy.expand_log(sympy.log(expr), force=True)
    if lhs.count(x) > SYMBOLIC_MAX_OCCURRENCES:
        return None
    # ln f(x) = k + g(x): solve g(x) = z, then z = ln(y) - k, combined
    # into one logarithm (ln(e/C) for the Magnus form).
    constant, varying = lhs.as_independent(x, as_Add=True)
    z = sympy.Dummy("z", real=True)
    try:
        solutions = sympy.solve(varying - z, x)
    except NotImplementedError:
        return None
    rhs = sympy.logcombine(sympy.log(y) - constant, force=True)
    solutions = [s.subs(z, rhs) for s in solutions]
    shift = _offset(formulation.inputs[0].unit, output.unit)
    coefficients = list(formulation.coefficients)
    if shift:
        coefficients.append(
            Coefficient(
                _OFFSET,
                abs(shift),
                "K",
                "t = T - T0 (SI Brochure, section 2.3.1)",
                UnitBasis.ADDED,
            )
        )
    names = (
        [input.identifier]
        + [c.identifier for c in coefficients]
        + [k.identifier for k in formulation.constants]
    )
    targets = _forward(formulation, expr)(samples)
    values = [c.value for c in coefficients] + [k.value for k in formulation.constants]
    for solution in solutions:
        found = solution
        if shift:
            # t = T - T0 from K to degC, T = t + T0 from degC to K.
            offset = sympy.Symbol(_OFFSET, real=True)
            found = found + offset if shift > 0 else found - offset
        source = _source(found)
        try:
            parsed = parse_expression(source, names)
        except ValueError:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            back = np.asarray(
                compile_numeric(parsed, tuple(names))(targets, *values), dtype=float
            )
        if np.allclose(back, samples + shift, rtol=1e-9, atol=1e-9):
            return source, coefficients
    return None


def _branch_samples(low: float, high: float, samples: Any) -> Any:
    """Points inside the interval of a branch, near the given samples."""
    first, last = float(np.min(samples)), float(np.max(samples))
    width = max(last - first, 1.0)
    start = low if np.isfinite(low) else min(first, high - width)
    stop = high if np.isfinite(high) else max(last, low + width)
    return np.linspace(start, stop, 51)[1:-1]


def _image_condition(
    variable: str,
    lower: tuple[float, bool] | None,
    upper: tuple[float, bool] | None,
) -> str:
    """The condition of an inverse branch: the image of the interval."""
    if lower and upper:
        return (
            f"{lower[0]!r} {'<=' if lower[1] else '<'} {variable} "
            f"{'<=' if upper[1] else '<'} {upper[0]!r}"
        )
    if lower:
        return f"{variable} {'>=' if lower[1] else '>'} {lower[0]!r}"
    assert upper is not None
    return f"{variable} {'<=' if upper[1] else '<'} {upper[0]!r}"


def _closed_form_of_pieces(
    formulation: Formulation,
    solve_for: str,
    output: Variable,
    input: Variable,
    samples: Any,
) -> tuple[str, list[Coefficient]] | None:
    """A closed-form inverse of a piecewise definition, branch by branch.

    Each branch must be strictly monotonic on its interval (checked on
    samples) and have a closed-form inverse; the inverse takes the image
    of each interval as its condition, and the images must not overlap.
    One piecewise definition only: with several, ``None``.
    """
    import sympy

    expr = formulation.sympy_expression
    nodes = [
        n for n in sympy.preorder_traversal(expr) if isinstance(n, sympy.Piecewise)
    ]
    if len(nodes) != 1:
        return None
    # The catalog checked that every condition bounds the input alone.
    pieces = _pieces(nodes[0], [solve_for])
    pairs = [(c.identifier, c.value) for c in formulation.coefficients]
    pairs += [(k.identifier, k.value) for k in formulation.constants]
    values = {sympy.Symbol(name, real=True): value for name, value in pairs}
    texts, spans = [], []
    coefficients: list[Coefficient] = []
    for piece in pieces:
        branch = expr.xreplace({nodes[0]: piece.expression})
        low = float(piece.low.xreplace(values))
        high = float(piece.high.xreplace(values))
        inside = _branch_samples(low, high, samples)
        forward = _forward(formulation, branch)
        steps = np.diff(forward(inside))
        if not (np.all(steps > 0) or np.all(steps < 0)):
            return None
        found = _closed_form(formulation, branch, solve_for, output, input, inside)
        if found is None:
            return None
        source, coefficients = found
        ends: list[tuple[float, bool] | None] = []
        for end, closed in ((low, piece.low_closed), (high, piece.high_closed)):
            image = float(forward(np.array(end))) if np.isfinite(end) else np.inf
            ends.append((image, closed) if np.isfinite(image) else None)
        lower, upper = ends if steps[0] > 0 else ends[::-1]
        if lower is None and upper is None:
            return None
        texts.append(f"({source}, {_image_condition(input.identifier, lower, upper)})")
        spans.append(
            (
                lower[0] if lower else -np.inf,
                not (lower and lower[1]),
                upper[0] if upper else np.inf,
                bool(upper and upper[1]),
            )
        )
    spans.sort()
    for (_, _, top, top_closed), (bottom, bottom_open, _, _) in pairwise(spans):
        if top > bottom or (top == bottom and top_closed and not bottom_open):
            return None
    # Each branch was checked on its samples, and the images do not overlap.
    return f"{PIECEWISE}({', '.join(texts)})", coefficients


def _symbolic(
    formulation: Formulation,
    solve_for: str,
    output: Variable,
    input: Variable,
    key: str,
    label: str,
    samples: Any,
) -> Formulation | None:
    import sympy

    if formulation.sympy_expression.has(sympy.Piecewise):
        found = _closed_form_of_pieces(formulation, solve_for, output, input, samples)
    else:
        found = _closed_form(
            formulation,
            formulation.sympy_expression,
            solve_for,
            output,
            input,
            samples,
        )
    if found is None:
        return None
    source, coefficients = found
    forward = _forward(formulation)
    return Formulation(
        key=key,
        label=label,
        output=output,
        inputs=(input,),
        coefficients=tuple(coefficients),
        constants=formulation.constants,
        expression=source,
        fixed_units=formulation.fixed_units,
        physical_domains=_carried_domains(
            formulation.physical_domains,
            formulation.key,
            solve_for,
            input.identifier,
            forward,
        ),
        citations=tuple(
            replace(
                citation,
                domains=_carried_domains(
                    citation.domains,
                    formulation.key,
                    solve_for,
                    input.identifier,
                    forward,
                ),
                # The output carries the scale of the solved variable.
                scales=MappingProxyType({}),
            )
            for citation in formulation.citations
        ),
        note=f"Derived by symbolic inversion of {formulation.key}.",
        matches=(),
        derivation=Derivation(formulation.key, "symbolic inversion", solve_for),
    )


def _carried_domains(
    domains: tuple[ValidityDomain, ...],
    source: str,
    solve_for: str,
    identifier: str,
    forward: Any,
) -> tuple[ValidityDomain, ...]:
    """The domains on the input, carried through the function onto its output."""
    carried = []
    for domain in domains:
        if solve_for not in domain.bounds:
            continue
        low, high = domain.bounds[solve_for]
        ends = sorted(float(v) for v in forward(np.array([low, high])))
        criterion = (
            f"Carried by inversion from {source}: {domain.criterion or 'no criterion'}"
        )
        carried.append(
            ValidityDomain(
                domain.basis,
                {identifier: (ends[0], ends[1])},
                criterion,
                domain.reference,
            )
        )
    return tuple(carried)


@dataclass(frozen=True)
class NumericalInverse:
    """The inverse of a formulation, solved numerically.

    Evaluable like a formulation (see :func:`nomogram.comparison.compare`
    and :func:`~nomogram.comparison.compose`). The source is assumed
    monotonic over the search interval; values outside its image give
    NaN, and results outside the source's validity domains follow the
    ``outside`` option.

    Attributes
    ----------
    key, label : str
        Identification.
    output, input : Variable
        The solved variable and the new input.
    source : Formulation
        The formulation inverted.
    search : tuple of float
        Interval of the source's input searched, in its unit.
    derivation : Derivation
        Origin, with ``method="numerical inversion"``.
    """

    key: str
    label: str
    output: Variable
    input: Variable
    source: Formulation
    search: tuple[float, float]
    derivation: Derivation
    references: tuple[str, ...] = field(default=())

    @property
    def inputs(self) -> tuple[Variable, ...]:
        """The single input, as for a formulation."""
        return (self.input,)

    def evaluate(
        self,
        *,
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        **inputs: Any,
    ) -> Any:
        """Solve for the output, by vectorised bisection.

        Parameters
        ----------
        outside : {"nan", "warn", "raise", "ignore"}
            Behaviour outside the validity domains of the source, and
            beyond a scale conversion (NaN whatever the option), as for
            :meth:`~nomogram.model.Formulation.evaluate`.
        basis : {"stated", "physical", "all"}
            Which domains of the source apply.
        scale : {"convert", "ignore"}
            With ``"convert"`` (default), the input is taken on the
            reference scale of its kind and converted to the scale of the
            source's output, and the result converted from the scale of
            the source's input to the reference scale; ``"ignore"`` uses
            values as they are.
        **inputs : pint.Quantity
            The one input, by identifier.

        Returns
        -------
        pint.Quantity
            The result, in the output unit; NaN where the input is beyond
            the image of the search interval.

        Raises
        ------
        TypeError
            If the input is missing or unexpected.
        ValueError
            If ``outside``, ``basis`` or ``scale`` is not one of its values.
        OutOfDomainError
            With ``outside="raise"``, if a result is outside a domain, or
            a value beyond a scale conversion.
        ScaleConversionError
            With ``scale="convert"``, if a scale cannot be converted; with
            ``scale="ignore"``, if the input is not written as its scale
            writes it: with a unit on a scale of numbers (Practical
            Salinity), bare on a scale in per mille (Knudsen salinity).
        """
        _check_options(outside, basis, scale)
        if set(inputs) != {self.input.identifier}:
            msg = f"{self.key}: expected the input {self.input.identifier}"
            raise TypeError(msg)
        units = semantic_catalog().units
        source_input = self.source.inputs[0]
        given = inputs[self.input.identifier]
        if scale == "ignore":
            _check_given(self.key, self.input, given)
        target_scale = self.input.scale
        if (
            scale == "convert"
            and target_scale is not None
            and not target_scale.is_reference
        ):
            # The target is given on the reference scale: the source computes
            # on its own.
            target_scale.check_convertible()
            table = units[str(target_scale.unit)].pint
            on_scale, failed = target_scale.from_reference(
                convert(given, table).magnitude
            )
            _flag_beyond(
                self.key, [(self.input.identifier, target_scale, failed)], outside
            )
            given = Q_(on_scale, table)
        target = np.asarray(
            convert(given, units[self.input.unit].pint).magnitude,
            dtype=float,
        )
        forward = _forward(self.source)
        low = np.full(target.shape, self.search[0])
        high = np.full(target.shape, self.search[1])
        increasing = forward(np.array(self.search[1])) > forward(
            np.array(self.search[0])
        )
        for _ in range(100):
            middle = (low + high) / 2
            below = forward(middle) < target
            go_up = below if increasing else ~below
            low = np.where(go_up, middle, low)
            high = np.where(go_up, high, middle)
        solved = (low + high) / 2
        ends = forward(np.array(self.search))
        unreachable = (
            (target < ends.min()) | (target > ends.max()) | ~np.isfinite(target)
        )
        solved = np.where(unreachable, np.nan, solved)
        mask = self.source.outside_mask({source_input.identifier: solved}, basis)
        if mask.any() and outside != "ignore":
            message = f"{self.key}: {int(mask.sum())} value(s) outside the {basis} domain of {self.source.key}"
            if outside == "raise":
                raise OutOfDomainError(message)
            if outside == "warn":
                import warnings

                warnings.warn(message, ValidityWarning, stacklevel=2)
            else:
                solved = np.where(mask, np.nan, solved)
        quantity = Q_(solved, units[source_input.unit].pint)
        scale_of_source = source_input.scale
        if (
            scale == "convert"
            and scale_of_source is not None
            and not scale_of_source.is_reference
        ):
            scale_of_source.check_convertible()
            table = units[str(scale_of_source.unit)].pint
            on_scale = convert(quantity, table).magnitude
            on_reference = scale_of_source.to_reference(on_scale)
            failed = np.isnan(on_reference) & ~np.isnan(on_scale)
            _flag_beyond(
                self.key, [(self.output.identifier, scale_of_source, failed)], outside
            )
            quantity = Q_(on_reference, table)
        result = np.asarray(
            convert(quantity, units[self.output.unit].pint).magnitude, dtype=float
        )
        magnitude = result.item() if result.ndim == 0 else result
        return Q_(magnitude, units[self.output.unit].pint)


def invert(
    formulation: Formulation,
    solve_for: str,
    *,
    output: Variable,
    input: Variable,
    key: str | None = None,
    label: str | None = None,
    method: Method = "auto",
    search: tuple[float, float] | None = None,
) -> Formulation | NumericalInverse:
    """Invert a formulation of one input.

    Parameters
    ----------
    formulation : Formulation
        The formulation y = f(x).
    solve_for : str
        Identifier of its input x, which becomes the output.
    output : Variable
        The new output (x's identifier, kind and unit; K and degC are
        interchangeable for temperatures).
    input : Variable
        The new input, in the unit of the formulation's output.
    key, label : str, optional
        Identification of the result; derived from the source otherwise.
    method : {"auto", "symbolic", "numerical"}
        ``"auto"`` tries a closed form, then falls back to numerical
        inversion; the others force one method. A piecewise definition
        has a closed form only if each branch is strictly monotonic on
        its interval, has a closed form itself, and the images of the
        intervals do not overlap.
    search : (float, float), optional
        Interval of x searched by numerical inversion, in x's unit;
        defaults to the source's stated validity domain.

    Returns
    -------
    Formulation or NumericalInverse
        A formulation when a closed form was found; its ``derivation``
        records the source and the method.

    Raises
    ------
    InversionError
        If the formulation cannot be inverted as asked.
    """
    _check(formulation, solve_for, output, input)
    source_input = formulation.inputs[0]
    output = replace(
        output,
        scale=source_input.scale,
        scale_basis=source_input.scale_basis,
    )
    # The new input is on the scale of the source's output, if any.
    input = replace(
        input,
        scale=formulation.output.scale,
        scale_basis=formulation.output.scale_basis,
    )
    key = key or f"{formulation.key}_inverse"
    label = label or f"Inverse of: {formulation.label}"
    interval = search or _bounds(formulation, solve_for)
    if method != "numerical":
        if interval is not None:
            samples = np.linspace(interval[0], interval[1], 7)[1:-1]
        else:
            # Ordinary temperatures, to pick the right branch of a solution.
            samples = np.array([5.0, 20.0, 35.0]) + (
                273.15 if source_input.unit == "K" else 0.0
            )
        closed = _symbolic(formulation, solve_for, output, input, key, label, samples)
        if closed is not None:
            return closed
        if method == "symbolic":
            msg = f"{formulation.key}: no closed form found for {solve_for}"
            if f"{PIECEWISE}(" in formulation.expression:
                msg += (
                    " (a piecewise definition needs each branch strictly "
                    "monotonic on its interval, with a closed form, and images "
                    "that do not overlap)"
                )
            raise InversionError(msg)
    if interval is None:
        msg = (
            f"{formulation.key} states no validity domain on {solve_for}: "
            "give a search interval for numerical inversion"
        )
        raise InversionError(msg)
    return NumericalInverse(
        key=key,
        label=label,
        output=output,
        input=input,
        source=formulation,
        search=(float(interval[0]), float(interval[1])),
        derivation=Derivation(formulation.key, "numerical inversion", solve_for),
        references=formulation.references,
    )


def dew_point(
    formulation: Formulation,
    *,
    method: Method = "auto",
    search: tuple[float, float] | None = None,
) -> Formulation | NumericalInverse:
    """The dew point formulation obtained by inverting a saturation vapour pressure.

    Parameters
    ----------
    formulation : Formulation
        A saturation vapour pressure formulation e_s = f(T).
    method, search
        As for :func:`invert`. Without a stated validity domain, numerical
        inversion searches :data:`DEW_POINT_SEARCH_CELSIUS`.

    Returns
    -------
    Formulation or NumericalInverse
        t_d = g(e), with e a vapour pressure (in the unit of e_s) and t_d
        a dew point temperature in degC.
    """
    temperature = formulation.inputs[0]
    if search is None and _bounds(formulation, temperature.identifier) is None:
        # A search interval only, not a validity domain.
        search = DEW_POINT_SEARCH_CELSIUS
        if temperature.unit == "K":
            search = (search[0] + 273.15, search[1] + 273.15)
    return invert(
        formulation,
        temperature.identifier,
        output=Variable("t_d", "DewPointTemperature", "DEG_C", "Dew point temperature"),
        input=Variable(
            "e", "VapourPressure", formulation.output.unit, "Vapour pressure"
        ),
        key=f"{formulation.key}_dew_point",
        label=f"Dew point, inverse of: {formulation.label}",
        method=method,
        search=search,
    )
