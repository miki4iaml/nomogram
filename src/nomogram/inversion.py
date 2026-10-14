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

Temperatures stay on ITS-90 at both ends: an inverse of a formulation
fitted on another scale converts its result back.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

import numpy as np

from nomogram.expression import compile_numeric, parse_expression
from nomogram.model import (
    Basis,
    Coefficient,
    Derivation,
    Formulation,
    OutOfDomainError,
    Outside,
    ScaleConversion,
    ValidityDomain,
    ValidityWarning,
    Variable,
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

#: Name of the offset coefficient added when the result changes from K to
#: degC (t = T - T0, SI Brochure, section 2.3.1).
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


def _forward(formulation: Formulation) -> Any:
    """The formulation's numeric function of its single input, in its units."""
    function = compile_numeric(formulation.sympy_expression, formulation.names)
    fixed = [c.value for c in formulation.coefficients] + [
        k.value for k in formulation.constants
    ]
    factor = formulation.output_factor

    def forward(x: Any) -> Any:
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            return np.asarray(function(x, *fixed), dtype=float) * factor

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

    x = sympy.Symbol(solve_for, real=True)
    y = sympy.Symbol(input.identifier, positive=True)
    lhs = sympy.expand_log(sympy.log(formulation.sympy_expression), force=True)
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
            Coefficient(_OFFSET, -shift, "K", "t = T - T0 (SI Brochure, section 2.3.1)")
        )
    names = (
        [input.identifier]
        + [c.identifier for c in coefficients]
        + [k.identifier for k in formulation.constants]
    )
    forward = _forward(formulation)
    targets = forward(samples)
    for solution in solutions:
        expr = solution
        if shift:
            expr = expr - sympy.Symbol(_OFFSET, real=True)
        source = _source(expr)
        try:
            parsed = parse_expression(source, names)
        except ValueError:
            continue
        values = [c.value for c in coefficients] + [
            k.value for k in formulation.constants
        ]
        with np.errstate(invalid="ignore", divide="ignore"):
            back = np.asarray(
                compile_numeric(parsed, tuple(names))(targets, *values), dtype=float
            )
        if np.allclose(back, samples + shift, rtol=1e-9, atol=1e-9):
            return Formulation(
                key=key,
                label=label,
                output=output,
                inputs=(input,),
                coefficients=tuple(coefficients),
                constants=formulation.constants,
                expression=source,
                fixed_units=formulation.fixed_units,
                domains=_carried_domains(
                    formulation, solve_for, input.identifier, forward
                ),
                accuracy=formulation.accuracy,
                references=formulation.references,
                note=f"Derived by symbolic inversion of {formulation.key}.",
                matches=(),
                derivation=Derivation(formulation.key, "symbolic inversion", solve_for),
            )
    return None


def _carried_domains(
    formulation: Formulation, solve_for: str, identifier: str, forward: Any
) -> tuple[ValidityDomain, ...]:
    """The domains on the input, carried through the function onto its output."""
    carried = []
    for domain in formulation.domains:
        if solve_for not in domain.bounds:
            continue
        low, high = domain.bounds[solve_for]
        ends = sorted(float(v) for v in forward(np.array([low, high])))
        criterion = f"Carried by inversion from {formulation.key}: {domain.criterion or 'no criterion'}"
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
        """Solve for the output, by vectorised bisection."""
        if set(inputs) != {self.input.identifier}:
            msg = f"{self.key}: expected the input {self.input.identifier}"
            raise TypeError(msg)
        units = semantic_catalog().units
        source_input = self.source.inputs[0]
        target = np.asarray(
            convert(
                inputs[self.input.identifier], units[self.input.unit].pint
            ).magnitude,
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
        scale_of_source = source_input.temperature_scale
        if scale == "convert" and scale_of_source is not None and scale_of_source.t90:
            celsius = scale_of_source.to_its90(convert(quantity, "degC").magnitude)
            quantity = Q_(celsius, "degC")
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
        inversion; the others force one method.
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
        temperature_scale=source_input.temperature_scale,
        scale_basis=source_input.scale_basis,
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
