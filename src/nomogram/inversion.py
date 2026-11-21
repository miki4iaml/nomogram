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
over a search interval, once the formulation is proven monotonic there
(:func:`nomogram.monotonicity.monotonicity`), or found so on samples when
no proof concludes; it is refused where the formulation is not.

A piecewise definition is inverted branch by branch, **provided each
branch is strictly monotonic on its interval** (nomogram proves it by
interval arithmetic, or checks it on samples when no proof concludes; a
constant branch is not):
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

from nomogram._roots import COLLAPSE, grid
from nomogram.expression import (
    PIECEWISE,
    ExpressionError,
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
    RootWarning,
    ScaleConversion,
    UnitBasis,
    ValidityDomain,
    ValidityWarning,
    Variable,
    _beyond_kind,
    _check_given,
    _check_options,
    _flag_beyond,
)
from nomogram.monotonicity import Monotonicity, monotonicity
from nomogram.semantics import semantic_catalog
from nomogram.units import Q_, convert

__all__ = [
    "DEW_POINT_SEARCH_CELSIUS",
    "STEP_BACK_TOLERANCE",
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

#: Largest step back at a junction of a piecewise definition, relative to
#: the value, that a numerical inverse accepts unless ``step_back`` says
#: otherwise: a target within the step has two solutions, either side of
#: the junction, and the one found is either. The published coefficients
#: of the standard atmospheres join their branches to about 1e-5.
STEP_BACK_TOLERANCE = 1e-4

#: Points of the linear grid on which a numerical inverse is checked when
#: no proof of its monotonicity concludes, besides the grid of the solver
#: of implicit equations (geometric near each end and around 0).
_SAMPLES = 2001

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

        def _print_Exp1(self, _node: Any) -> str:
            # Euler's number, printed E by SymPy, a name the syntax lacks.
            return "exp(1)"

    return str(Printer().doprint(expr))


def _check(
    formulation: Formulation, solve_for: str, output: Variable, input: Variable
) -> None:
    if formulation.implicit:
        msg = (
            f"{formulation.key}: an implicit equation is solved for its output, "
            "not inverted"
        )
        raise InversionError(msg)
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
    """Intersection of the stated domains on the input, if any and finite.

    An open end (a domain from 0 to inf) cannot be searched: the caller
    gives the interval then.
    """
    stated = [
        d.bounds[solve_for]
        for d in formulation.domains
        if d.basis.value == "stated" and solve_for in d.bounds
    ]
    if not stated:
        return None
    low, high = max(low for low, _ in stated), min(high for _, high in stated)
    if not (np.isfinite(low) and np.isfinite(high)):
        return None
    return low, high


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
    z = sympy.Dummy("z", real=True)
    try:
        lhs = sympy.expand_log(sympy.log(expr), force=True)
        if lhs.count(x) > SYMBOLIC_MAX_OCCURRENCES:
            return None
        # ln f(x) = k + g(x): solve g(x) = z, then z = ln(y) - k, combined
        # into one logarithm (ln(e/C) for the Magnus form).
        constant, varying = lhs.as_independent(x, as_Add=True)
        # Each solution is checked numerically below: SymPy's own check,
        # which simplifies every candidate, took up to 20 s for nothing.
        solutions = sympy.solve(varying - z, x, check=False)
        rhs = sympy.logcombine(sympy.log(y) - constant, force=True)
        solutions = [s.xreplace({z: rhs}) for s in solutions]
    except (NotImplementedError, RecursionError):
        # No algorithm, or one that recurses without end (the dew point of
        # metpy171_dew_point, after 7 s): the numerical inverse takes over.
        return None
    shift = _offset(formulation.inputs[0].unit, output.unit)
    coefficients = list(formulation.coefficients)
    # The offset's name must not be one of the formulation's.
    offset_name = _OFFSET
    while offset_name in formulation.names:
        offset_name += "_"
    if shift:
        coefficients.append(
            Coefficient(
                offset_name,
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
            offset = sympy.Symbol(offset_name, real=True)
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


def _branch_direction(
    formulation: Formulation,
    solve_for: str,
    low: float,
    high: float,
    inside: Any,
    forward: Any,
) -> int | None:
    """+1 or -1 when a branch is strictly monotonic, None otherwise.

    Proven by interval arithmetic over the branch's interval, or over the
    span of its samples where an end is infinite; checked on the samples
    when no proof concludes.
    """
    start = low if np.isfinite(low) else float(inside[0])
    stop = high if np.isfinite(high) else float(inside[-1])
    if start < stop:
        verdict = monotonicity(formulation, solve_for, (start, stop))
        if verdict.status == "proven":
            return 1 if verdict.direction == "increasing" else -1
        if verdict.status == "refuted":
            return None
    steps = np.diff(forward(inside))
    if np.all(steps > 0):
        return 1
    if np.all(steps < 0):
        return -1
    return None


def _checked_monotonicity(
    formulation: Formulation,
    solve_for: str,
    interval: tuple[float, float],
    step_back: float | None,
) -> Monotonicity:
    """The monotonicity of the source over the search interval, or an error.

    Proven, or refuted by steps back at junctions only, none beyond
    :data:`STEP_BACK_TOLERANCE` of the value, or none wider than
    ``step_back`` on the input; otherwise checked on samples, which a step
    back beyond the rounding refutes, as does a sample where the source is
    undefined.

    Raises
    ------
    InversionError
        If the source is not monotonic over the interval, or undefined at
        one of its ends or of the samples.
    """
    low, high = interval
    where = f"over [{low!r}, {high!r}]"
    ends = _forward(formulation)(np.array(interval, dtype=float))
    if not np.isfinite(ends).all():
        msg = (
            f"{formulation.key} is undefined at an end of the search interval "
            f"{where}: give a search interval where it is defined"
        )
        raise InversionError(msg)
    verdict = monotonicity(formulation, solve_for, interval)
    if verdict.direction is not None:
        limit = STEP_BACK_TOLERANCE if step_back is None else step_back
        measure = verdict.steps if step_back is None else verdict.widths
        beyond = {cut: value for cut, value in measure.items() if value > limit}
        if not beyond:
            return verdict
        junction = max(beyond, key=beyond.__getitem__)
        if step_back is None:
            msg = (
                f"{formulation.key} steps back by {beyond[junction]:.3g} of its "
                f"value at {solve_for} = {junction!r}, beyond STEP_BACK_TOLERANCE; "
                f"step_back accepts it by its width on {solve_for}, "
                f"{verdict.widths[junction]:.3g}"
            )
        else:
            msg = (
                f"{formulation.key} steps back at {solve_for} = {junction!r}: a "
                f"target within the step has two solutions up to "
                f"{beyond[junction]:.3g} apart, beyond step_back = {step_back!r}"
            )
        raise InversionError(msg)
    if verdict.status == "refuted":
        at = ", ".join(f"{k} = {v!r}" for k, v in verdict.at.items())
        msg = (
            f"{formulation.key} is not monotonic in {solve_for} {where} "
            f"({verdict.method}, at {at}): give a search interval where it is"
        )
        raise InversionError(msg)
    points = np.union1d(grid(low, high), np.linspace(low, high, _SAMPLES))
    values = _forward(formulation)(points)
    undefined = int(np.sum(~np.isfinite(values)))
    if undefined:
        msg = (
            f"{formulation.key} is undefined at {undefined} of {points.size} "
            f"samples {where}: give a search interval where it is defined"
        )
        raise InversionError(msg)
    overall = np.sign(values[-1] - values[0])
    noise = 1e-9 * float(np.max(np.abs(values)))
    if overall != 0 and not np.any(overall * np.diff(values) < -noise):
        method = f"{verdict.method}; monotonic on {points.size} samples"
        return replace(verdict, method=method)
    msg = (
        f"{formulation.key} is not monotonic in {solve_for} {where} on "
        f"{points.size} samples: give a search interval where it is"
    )
    raise InversionError(msg)


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

    Each branch must be strictly monotonic on its interval (proven, or
    checked on samples, see :func:`_branch_direction`) and have a
    closed-form inverse; the inverse takes the image
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
    # The catalog checked that every condition bounds an input alone, but
    # a formulation called may bound an expression passed to it.
    try:
        pieces = _pieces(nodes[0], [solve_for])
    except ExpressionError:
        return None
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
        direction = _branch_direction(
            formulation, solve_for, low, high, inside, forward
        )
        if direction is None:
            return None
        found = _closed_form(formulation, branch, solve_for, output, input, inside)
        if found is None:
            return None
        source, coefficients = found
        ends: list[tuple[float, bool] | None] = []
        for end, closed in ((low, piece.low_closed), (high, piece.high_closed)):
            image = float(forward(np.array(end))) if np.isfinite(end) else np.inf
            ends.append((image, closed) if np.isfinite(image) else None)
        lower, upper = ends if direction > 0 else ends[::-1]
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
    # Each branch is monotonic, and the images do not overlap.
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
    shift = _offset(formulation.inputs[0].unit, output.unit)

    def carried(domains: tuple[ValidityDomain, ...]) -> tuple[ValidityDomain, ...]:
        return _carried_domains(
            domains, formulation, input.identifier, output.identifier, forward, shift
        )

    return Formulation(
        key=key,
        label=label,
        output=output,
        inputs=(input,),
        coefficients=tuple(coefficients),
        constants=formulation.constants,
        expression=source,
        fixed_units=formulation.fixed_units,
        physical_domains=carried(formulation.physical_domains),
        citations=tuple(
            replace(
                citation,
                domains=carried(citation.domains),
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
    source: Formulation,
    input_identifier: str,
    output_identifier: str,
    forward: Any,
    shift: float,
) -> tuple[ValidityDomain, ...]:
    """The domains of the source, carried onto its inverse.

    The interval of the solved input becomes that of the inverse's output
    (shifted from K to degC or back when its unit changes); its image
    through the function, when both its ends are finite, and a bound on the
    source's output become an interval of the inverse's input. A tolerance
    goes with the bound of its variable (a difference, unchanged by the
    shift); the image of an interval takes none.
    """
    solve_for = source.inputs[0].identifier
    carried = []
    for domain in domains:
        bounds: dict[str, tuple[float, float]] = {}
        tolerance: dict[str, tuple[float, float]] = {}
        if solve_for in domain.bounds:
            low, high = domain.bounds[solve_for]
            bounds[output_identifier] = (low + shift, high + shift)
            if solve_for in domain.tolerance:
                tolerance[output_identifier] = domain.tolerance[solve_for]
            if np.isfinite(low) and np.isfinite(high):
                ends = sorted(float(v) for v in forward(np.array([low, high])))
                bounds[input_identifier] = (ends[0], ends[1])
        if source.output.identifier in domain.bounds:
            low, high = domain.bounds[source.output.identifier]
            ends_tolerance = domain.tolerance.get(source.output.identifier, (0.0, 0.0))
            if input_identifier in bounds:
                image = bounds[input_identifier]
                # The tolerance of an end goes only where the source's bound wins.
                ends_tolerance = (
                    ends_tolerance[0] if low >= image[0] else 0.0,
                    ends_tolerance[1] if high <= image[1] else 0.0,
                )
                low, high = max(low, image[0]), min(high, image[1])
            bounds[input_identifier] = (low, high)
            if any(ends_tolerance):
                tolerance[input_identifier] = ends_tolerance
        if not bounds:
            continue
        criterion = (
            f"Carried by inversion from {source.key}: "
            f"{domain.criterion or 'no criterion'}"
        )
        carried.append(
            ValidityDomain(
                domain.basis,
                MappingProxyType(bounds),
                criterion,
                domain.reference,
                MappingProxyType(tolerance),
            )
        )
    return tuple(carried)


@dataclass(frozen=True)
class NumericalInverse:
    """The inverse of a formulation, solved numerically.

    Evaluable like a formulation (see :func:`nomogram.comparison.compare`
    and :func:`~nomogram.comparison.compose`). :func:`invert` builds it
    only for a source monotonic over the search interval: proven, or
    found so on samples when no proof concludes (``monotonicity``). Values
    outside its image give NaN: beyond the images of the ends of the
    search interval, and within a gap where the source jumps forward at a
    junction, which a :class:`~nomogram.model.RootWarning` reports. Results
    outside the source's validity domains follow the ``outside`` option. Where a piecewise source steps back at a junction
    (``monotonicity.steps``, as far as :func:`invert` accepts), a target
    within the step has two solutions on either side of the junction, at
    most ``monotonicity.widths`` apart, and the one found is either; the
    bisection follows the direction proven. Where the source is constant
    on part of the interval (a constant branch), a target equal to that
    value has a whole interval of solutions, of which the bisection gives
    the end where the values below the target stop: the lower end of the
    plateau for an increasing source, the upper end for a decreasing one,
    and, where no value lies below the target (the plateau holds the
    minimum of the image), the end of the search interval on that side,
    an answer that depends on the interval searched.

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
    references : tuple of str
        The references of the source.
    monotonicity : Monotonicity or None
        The monotonicity of the source over the search interval, as
        :func:`invert` checked it; ``None`` for an inverse built directly,
        whose monotonicity nobody checked.
    """

    key: str
    label: str
    output: Variable
    input: Variable
    source: Formulation
    search: tuple[float, float]
    derivation: Derivation
    references: tuple[str, ...] = field(default=())
    monotonicity: Monotonicity | None = None

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
        ends = forward(np.array(self.search))
        # The direction proven, which steps back at junctions may hide from
        # the ends alone.
        direction = self.monotonicity.direction if self.monotonicity else None
        increasing = (
            direction == "increasing" if direction is not None else ends[1] > ends[0]
        )
        for _ in range(100):
            middle = (low + high) / 2
            below = forward(middle) < target
            go_up = below if increasing else ~below
            low = np.where(go_up, middle, low)
            high = np.where(go_up, high, middle)
        solved = (low + high) / 2
        # Only between the images of the ends, in the order of the direction,
        # is a solution bracketed; and not where the source jumps forward
        # between the two last points, as large a change between adjacent
        # floats as the solver of implicit equations takes for a jump.
        first, last = ends if increasing else ends[::-1]
        with np.errstate(invalid="ignore"):
            jump = np.abs(forward(high) - forward(low))
        gap = jump > COLLAPSE * abs(float(last - first))
        beyond = (target < first) | (target > last) | ~np.isfinite(target)
        within = gap & ~beyond
        if within.any():
            import warnings

            message = (
                f"{self.key}: NaN for {int(within.sum())} within a gap of the "
                f"image of {self.source.key}, which jumps forward at a "
                f"junction: no value of {source_input.identifier} gives them"
            )
            warnings.warn(message, RootWarning, stacklevel=2)
        solved = np.where(beyond | gap, np.nan, solved)
        given = {source_input.identifier: solved, self.source.output.identifier: target}
        mask = self.source.outside_mask(given, basis)
        # The bounds of the kinds of its own variables, which may be
        # narrower than those of the source's: as a closed form would apply.
        mask = (
            mask
            | _beyond_kind(self.input, target)
            | _beyond_kind(self.output, solved, source_input.unit)
        )
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
    step_back: float | None = None,
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
        interchangeable for the temperature of a numerical value
        equation, while a quantity equation keeps the unit of x).
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
        defaults to the source's stated validity domain. The source must
        be monotonic over it.
    step_back : float, optional
        For a numerical inverse of a piecewise definition that steps back
        at a junction: the largest width accepted, in x's unit, of the
        interval of x within which a target in the step has two solutions
        (``monotonicity.widths``), the step divided by the slope there.
        By default, a step back is accepted up to
        :data:`STEP_BACK_TOLERANCE` of the value.

    Returns
    -------
    Formulation or NumericalInverse
        A formulation when a closed form was found; its ``derivation``
        records the source and the method.

    Raises
    ------
    InversionError
        If the formulation cannot be inverted as asked, or, numerically,
        is not monotonic over the search interval (a derivative that
        changes sign there, proven or found on samples, or a piecewise
        definition that steps back at a junction beyond what is accepted),
        or if ``step_back`` is negative.
    """
    _check(formulation, solve_for, output, input)
    if step_back is not None and not step_back >= 0:
        msg = f"step_back must be positive or zero, not {step_back!r}"
        raise InversionError(msg)
    from nomogram.catalog import catalog

    # The bounds of their kinds, as the catalog gives them to its variables,
    # unless the caller gives some.
    output = replace(
        output, kind_bounds=output.kind_bounds or catalog().bounds_of(output.kind)
    )
    input = replace(
        input, kind_bounds=input.kind_bounds or catalog().bounds_of(input.kind)
    )
    source_input = formulation.inputs[0]
    output = replace(
        output,
        # A quantity equation gives x in its own unit, which pint converts.
        unit=output.unit if formulation.fixed_units else source_input.unit,
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
            f"{formulation.key} states no finite validity domain on {solve_for}: "
            "give a search interval for numerical inversion"
        )
        raise InversionError(msg)
    low, high = float(interval[0]), float(interval[1])
    if not (np.isfinite(low) and np.isfinite(high) and low < high):
        msg = f"the search interval must be finite and increasing, not {interval}"
        raise InversionError(msg)
    return NumericalInverse(
        key=key,
        label=label,
        output=output,
        input=input,
        source=formulation,
        search=(low, high),
        derivation=Derivation(formulation.key, "numerical inversion", solve_for),
        references=formulation.references,
        monotonicity=_checked_monotonicity(
            formulation, solve_for, (low, high), step_back
        ),
    )


def dew_point(
    formulation: Formulation,
    *,
    method: Method = "auto",
    search: tuple[float, float] | None = None,
    step_back: float | None = None,
) -> Formulation | NumericalInverse:
    """The dew point formulation obtained by inverting a saturation vapour pressure.

    Parameters
    ----------
    formulation : Formulation
        A saturation vapour pressure formulation e_s = f(T).
    method, search, step_back
        As for :func:`invert`. Without a stated validity domain, numerical
        inversion searches :data:`DEW_POINT_SEARCH_CELSIUS`.

    Returns
    -------
    Formulation or NumericalInverse
        t_d = g(e), with e a vapour pressure (in the unit of e_s) and t_d
        a dew point temperature in degC, or in the unit of the
        temperature for a quantity equation.
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
        step_back=step_back,
    )
