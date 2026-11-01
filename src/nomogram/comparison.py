# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Comparing alternative formulations, and chaining them.

:func:`compare` evaluates formulations of the same quantity kind on the
same inputs and gives their relative deviation from a reference
formulation, in one vectorised pass: the comparison table of the
reference use case.

:func:`compose` feeds the output of formulations into the inputs of
another, for instance a saturation vapour pressure formulation into the
ideal gas mass concentration of water vapour, to compare HA = f(T, RH)
across vapour pressure formulations.

:func:`partial` fixes some inputs of a formulation, as
:func:`functools.partial` fixes arguments: the two levels of an
interpolation scheme, whose pressures share a kind with the target
pressure, so that the schemes compare along it.

Inputs are matched by quantity kind. The Celsius temperature and the
thermodynamic temperature are the only distinct kinds treated as the same
input: they are two expressions of one state, t = T - 273.15 K (SI
Brochure, section 2.3.1), and pint converts between them. A temperature
difference is never matched with either.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from nomogram.model import Basis, Outside, ScaleConversion, Variable
from nomogram.units import convert, is_offset_unit

__all__ = [
    "Comparison",
    "Composition",
    "Evaluable",
    "Partial",
    "compare",
    "compose",
    "feeds",
    "partial",
]

#: Kinds that express the same temperature state (SI Brochure 2.3.1).
TEMPERATURE_POINTS = frozenset({"ThermodynamicTemperature", "CelsiusTemperature"})


class Evaluable(Protocol):
    """What :func:`compare` and :func:`compose` need from a formulation."""

    @property
    def key(self) -> str: ...

    @property
    def output(self) -> Variable: ...

    @property
    def inputs(self) -> tuple[Variable, ...]: ...

    def evaluate(
        self,
        *,
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        **inputs: Any,
    ) -> Any: ...


def same_state(kind_a: str, kind_b: str) -> bool:
    """Whether two quantity kinds may feed the same input."""
    return kind_a == kind_b or {kind_a, kind_b} <= TEMPERATURE_POINTS


def feeds(output_kind: str, input_kind: str) -> bool:
    """Whether a result of one kind may feed an input of another.

    It may when the kinds are the same, or when the result's kind
    specializes the input's (QUDT ``specializationOf``, directly or not):
    a saturation vapour pressure is a vapour pressure. Never the other
    way round, and never a difference for a point, though QUDT makes a
    temperature difference a temperature.
    """
    from nomogram.catalog import catalog

    kinds = catalog().kinds
    kind = kinds.get(output_kind)
    target = kinds.get(input_kind)
    if kind is not None and target is not None and kind.delta and not target.delta:
        return False
    seen = set()
    while kind is not None and kind.name not in seen:
        if kind.name == input_kind:
            return True
        seen.add(kind.name)
        kind = kinds.get(kind.specialization_of or "")
    return output_kind == input_kind


def _may_feed(output_kind: str, input_kind: str) -> bool:
    """Whether a computed value may feed an input of a composition.

    As :func:`feeds`; or a temperature in the same state, in kelvins or in
    degrees Celsius; or the temperature of a point at which the receiving
    formulation is evaluated (a dew or frost point, a wet- or ice-bulb
    temperature), as a formulation of the catalog calling another may pass
    it.
    """
    from nomogram.catalog import _EVALUATION_POINTS

    return (
        feeds(output_kind, input_kind)
        or same_state(output_kind, input_kind)
        or input_kind in _EVALUATION_POINTS.get(output_kind, ())
    )


def _arguments(formulation: Evaluable, values: Mapping[str, Any]) -> dict[str, Any]:
    arguments = {}
    fed: dict[str, list[str]] = {}
    for variable in formulation.inputs:
        matches = [kind for kind in values if same_state(kind, variable.kind)]
        if len(matches) != 1:
            found = "none" if not matches else ", ".join(sorted(matches))
            msg = (
                f"{formulation.key}: input {variable.identifier} ({variable.kind}) "
                f"needs exactly one value of a matching kind; found: {found}"
            )
            raise ValueError(msg)
        arguments[variable.identifier] = values[matches[0]]
        fed.setdefault(matches[0], []).append(variable.identifier)
    for kind, names in fed.items():
        if len(names) > 1:
            # p, p_1 and p_2 all pressures: one value for all would compare
            # a degenerate formulation (an interpolation at its own levels).
            msg = (
                f"{formulation.key}: the value of {kind} would feed "
                f"{', '.join(names)}; fix all but one with "
                "nomogram.comparison.partial"
            )
            raise ValueError(msg)
    return arguments


@dataclass(frozen=True)
class Comparison:
    """Values of alternative formulations and their deviation from a reference.

    Attributes
    ----------
    reference : str
        Key of the reference formulation.
    inputs : mapping of str to pint.Quantity
        Input values, by quantity kind.
    values : mapping of str to pint.Quantity
        Result of each formulation, in the reference's output unit.
    relative_deviations : mapping of str to numpy.ndarray
        ``value / reference - 1`` for each formulation; NaN where either is
        outside its validity domain (with the default ``outside="nan"``).
        Values in a unit with an offset (a dew point in °C, a point of an
        interval scale) are divided in its absolute unit (K), where a
        ratio means something.
    formulations : mapping of str to Formulation or Composition
        The formulations compared, by key (labels, output variable).
    scale : {"convert", "ignore"}
        The ``scale`` of each evaluation. With ``"convert"`` (default),
        inputs and values are on the reference scale of their kind
        (ITS-90, Reference Salinity); with ``"ignore"``, each formulation
        took the inputs as they are, on whatever scale it was fitted on,
        and its values are on that scale.
    """

    reference: str
    inputs: Mapping[str, Any]
    values: Mapping[str, Any]
    relative_deviations: Mapping[str, Any]
    formulations: Mapping[str, Evaluable] = field(default_factory=dict, repr=False)
    scale: ScaleConversion = "convert"

    def max_abs_deviation(self) -> dict[str, float]:
        """Largest absolute relative deviation of each formulation (NaN ignored)."""
        result = {}
        for key, deviation in self.relative_deviations.items():
            finite = np.abs(np.asarray(deviation, dtype=float))
            finite = finite[np.isfinite(finite)]
            result[key] = float(finite.max()) if finite.size else float("nan")
        return result


def compare(
    formulations: Iterable[Evaluable],
    reference: Evaluable,
    inputs: Mapping[str, Any],
    *,
    outside: Outside = "nan",
    basis: Basis = "stated",
    scale: ScaleConversion = "convert",
) -> Comparison:
    """Compare formulations of one quantity kind against a reference.

    Parameters
    ----------
    formulations : iterable of Formulation or Composition
        The formulations to compare; the reference may be among them.
    reference : Formulation or Composition
        The formulation deviations are measured against.
    inputs : mapping of str to pint.Quantity
        One value per quantity kind, for example
        ``{"ThermodynamicTemperature": Q_(grid, "degC")}``; numpy arrays
        give the whole table in one pass.
    outside, basis, scale
        Passed to each evaluation (see
        :meth:`nomogram.model.Formulation.evaluate`). ``"nan"`` keeps
        each formulation to its own validity domains.

    Returns
    -------
    Comparison
        Values and relative deviations, by formulation key, with the scale
        mode used.

    Raises
    ------
    ValueError
        If a formulation computes another kind than the reference, an input
        cannot be matched to exactly one value, or one value would feed
        several inputs of a formulation (fix the others with :func:`partial`).
    """
    kind = reference.output.kind
    unit = None
    values: dict[str, Any] = {}
    candidates = [reference, *(f for f in formulations if f.key != reference.key)]
    for formulation in candidates:
        if formulation.output.kind != kind:
            msg = f"{formulation.key} computes {formulation.output.kind}, not {kind}"
            raise ValueError(msg)
        result = formulation.evaluate(
            outside=outside, basis=basis, scale=scale, **_arguments(formulation, inputs)
        )
        unit = unit or result.units
        values[formulation.key] = result.to(unit)
    # A ratio of points of an interval scale (degC) depends on its origin:
    # divide in the absolute unit (K).
    absolute = {
        key: value.to_base_units() if is_offset_unit(value.units) else value
        for key, value in values.items()
    }
    base = np.asarray(absolute[reference.key].magnitude, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        deviations = {
            key: np.asarray(value.magnitude, dtype=float) / base - 1.0
            for key, value in absolute.items()
        }
    compared = {f.key: f for f in candidates}
    return Comparison(
        reference.key, dict(inputs), values, deviations, compared, scale=scale
    )


@dataclass(frozen=True)
class Composition:
    """A formulation whose inputs are partly computed by other formulations.

    Attributes
    ----------
    outer : Formulation
        The formulation evaluated last.
    inner : mapping of str to Formulation
        For some inputs of ``outer``, by identifier, the formulation
        computing them.
    bind : mapping of str to str
        Inputs of inner formulations taken from inputs of ``outer``, by
        identifier (``{"t": "T"}``).
    label : str or None
        What the composition computes, for legends; the key otherwise.
    """

    outer: Evaluable
    inner: Mapping[str, Evaluable]
    bind: Mapping[str, str]
    label: str | None = None

    @property
    def key(self) -> str:
        """``outer[input=inner,...]``, for example ``ha[e_s=sonntag1990]``."""
        parts = ",".join(f"{k}={f.key}" for k, f in sorted(self.inner.items()))
        return f"{self.outer.key}[{parts}]"

    @property
    def output(self) -> Variable:
        """The output of the outer formulation."""
        return self.outer.output

    @property
    def inputs(self) -> tuple[Variable, ...]:
        """Inputs to supply: those of ``outer`` not computed, then unbound inner ones."""
        own = tuple(v for v in self.outer.inputs if v.identifier not in self.inner)
        names = {v.identifier for v in own}
        extra = []
        for formulation in self.inner.values():
            for variable in formulation.inputs:
                if (
                    variable.identifier not in self.bind
                    and variable.identifier not in names
                ):
                    extra.append(variable)
                    names.add(variable.identifier)
        return own + tuple(extra)

    def evaluate(
        self,
        *,
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        **inputs: Any,
    ) -> Any:
        """Evaluate inner formulations, then the outer one.

        Parameters are those of :meth:`nomogram.model.Formulation.evaluate`;
        ``inputs`` are given by the identifiers of :attr:`inputs`.
        """
        computed = dict(inputs)
        for identifier, formulation in self.inner.items():
            arguments = {
                v.identifier: inputs[self.bind.get(v.identifier, v.identifier)]
                for v in formulation.inputs
            }
            computed[identifier] = formulation.evaluate(
                outside=outside, basis=basis, scale=scale, **arguments
            )
        outer_arguments = {
            v.identifier: computed[v.identifier] for v in self.outer.inputs
        }
        return self.outer.evaluate(
            outside=outside, basis=basis, scale=scale, **outer_arguments
        )


def compose(
    outer: Evaluable,
    inner: Mapping[str, Evaluable],
    bind: Mapping[str, str] | None = None,
    *,
    label: str | None = None,
) -> Composition:
    """Feed the outputs of formulations into the inputs of another.

    Parameters
    ----------
    outer : Formulation
        The formulation evaluated last.
    inner : mapping of str to Formulation
        For some inputs of ``outer``, by identifier, the formulation that
        computes them; its output kind must be the input's kind or a
        specialization of it (see :func:`feeds`), a temperature in the
        same state (kelvins and degrees Celsius), or the temperature of a
        point at which ``outer`` is evaluated: a dew point feeds the
        temperature of a saturation vapour pressure.
    bind : mapping of str to str, optional
        Inputs of inner formulations to take from inputs of ``outer``, by
        identifier, for example ``{"t": "T"}``: the binding is declared,
        never guessed, and both kinds must express the same state.
    label : str, optional
        What the composition computes, for the legends of plots; its key
        otherwise.

    Returns
    -------
    Composition
        Evaluable like a formulation.

    Raises
    ------
    ValueError
        If an identifier is unknown or kinds do not match.
    """
    bind = dict(bind or {})
    outer_inputs = {v.identifier: v for v in outer.inputs}
    for identifier, formulation in inner.items():
        target = outer_inputs.get(identifier)
        if target is None:
            msg = f"{outer.key} has no input {identifier!r}"
            raise ValueError(msg)
        if not _may_feed(formulation.output.kind, target.kind):
            msg = (
                f"{formulation.key} computes {formulation.output.kind}, "
                f"but {identifier} is {target.kind}"
            )
            raise ValueError(msg)
    inner_inputs = {v.identifier: v for f in inner.values() for v in f.inputs}
    for source, target_name in bind.items():
        variable = inner_inputs.get(source)
        target = outer_inputs.get(target_name)
        if variable is None or target is None or target_name in inner:
            msg = f"cannot bind {source!r} to {target_name!r}"
            raise ValueError(msg)
        if not same_state(variable.kind, target.kind):
            msg = f"cannot bind {source} ({variable.kind}) to {target_name} ({target.kind})"
            raise ValueError(msg)
    return Composition(outer, dict(inner), bind, label)


@dataclass(frozen=True)
class Partial:
    """A formulation some of whose inputs are fixed.

    Attributes
    ----------
    formulation : Formulation or Composition
        The formulation evaluated.
    values : mapping of str to pint.Quantity
        The fixed inputs, by identifier.
    label : str
        What it computes, for legends: the label of the formulation unless
        another is given, which legends then show instead of a citation.
    """

    formulation: Evaluable
    values: Mapping[str, Any]
    label: str = ""
    named: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        # Named by a label of its own only: one equal to the formulation's,
        # as dataclasses.replace passes it back, names nothing.
        default = str(getattr(self.formulation, "label", None) or self.formulation.key)
        object.__setattr__(self, "named", bool(self.label) and self.label != default)
        if not self.label:
            object.__setattr__(self, "label", default)

    @property
    def key(self) -> str:
        """The formulation's key and the values fixed, ``key(p_1=850 hPa, ...)``."""
        fixed = ", ".join(f"{name}={value:~P}" for name, value in self.values.items())
        return f"{self.formulation.key}({fixed})"

    @property
    def citations(self) -> tuple[Any, ...]:
        """The citations of the formulation, for legends; none once named."""
        if self.named:
            return ()
        return tuple(getattr(self.formulation, "citations", ()))

    @property
    def output(self) -> Variable:
        """The output of the formulation."""
        return self.formulation.output

    @property
    def inputs(self) -> tuple[Variable, ...]:
        """The inputs left to supply."""
        return tuple(
            v for v in self.formulation.inputs if v.identifier not in self.values
        )

    def evaluate(
        self,
        *,
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        **inputs: Any,
    ) -> Any:
        """Evaluate the formulation with the fixed values and those given.

        Parameters are those of :meth:`nomogram.model.Formulation.evaluate`;
        ``inputs`` are given by the identifiers of :attr:`inputs`.
        """
        return self.formulation.evaluate(
            outside=outside, basis=basis, scale=scale, **self.values, **inputs
        )


def partial(formulation: Evaluable, /, *, label: str = "", **values: Any) -> Partial:
    """Fix some inputs of a formulation, as :func:`functools.partial` does.

    :func:`compare` matches inputs by quantity kind: an interpolation
    scheme, whose levels ``p_1`` and ``p_2`` are pressures like the target
    ``p``, compares along ``p`` once its levels are fixed.

    Parameters
    ----------
    formulation : Formulation or Composition
        The formulation.
    label : str, optional
        What it computes, for the legends of plots; the label of the
        formulation otherwise.
    **values
        The fixed inputs, by identifier, for example
        ``p_1=Q_(850, "hPa")``.

    Returns
    -------
    Partial
        Evaluable like a formulation, on the inputs left.

    Raises
    ------
    ValueError
        If an identifier is not an input of the formulation, or a value is
        not a quantity of the dimension of its input.
    """
    import pint

    from nomogram.semantics import semantic_catalog

    inputs = {v.identifier: v for v in formulation.inputs}
    unknown = sorted(set(values) - set(inputs))
    if unknown:
        msg = f"{formulation.key} has no input {', '.join(unknown)}"
        raise ValueError(msg)
    units = semantic_catalog().units
    for name, value in values.items():
        unit = inputs[name].unit
        try:
            convert(value, units[unit].pint)
        except (TypeError, pint.DimensionalityError) as exc:
            msg = f"{formulation.key}: {name} needs a quantity convertible to {unit}"
            raise ValueError(msg) from exc
    return Partial(formulation, dict(values), label)
