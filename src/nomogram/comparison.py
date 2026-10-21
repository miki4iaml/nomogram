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

__all__ = ["Comparison", "Composition", "Evaluable", "compare", "compose", "feeds"]

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
    way round.
    """
    from nomogram.catalog import catalog

    kinds = catalog().kinds
    kind = kinds.get(output_kind)
    seen = set()
    while kind is not None and kind.name not in seen:
        if kind.name == input_kind:
            return True
        seen.add(kind.name)
        kind = kinds.get(kind.specialization_of or "")
    return output_kind == input_kind


def _arguments(formulation: Evaluable, values: Mapping[str, Any]) -> dict[str, Any]:
    arguments = {}
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
        If a formulation computes another kind than the reference, or an
        input cannot be matched to exactly one value.
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
    base = np.asarray(values[reference.key].magnitude, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        deviations = {
            key: np.asarray(value.magnitude, dtype=float) / base - 1.0
            for key, value in values.items()
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
    """

    outer: Evaluable
    inner: Mapping[str, Evaluable]
    bind: Mapping[str, str]

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
) -> Composition:
    """Feed the outputs of formulations into the inputs of another.

    Parameters
    ----------
    outer : Formulation
        The formulation evaluated last.
    inner : mapping of str to Formulation
        For some inputs of ``outer``, by identifier, the formulation that
        computes them; its output kind must be the input's kind or a
        specialization of it (see :func:`feeds`).
    bind : mapping of str to str, optional
        Inputs of inner formulations to take from inputs of ``outer``, by
        identifier, for example ``{"t": "T"}``: the binding is declared,
        never guessed, and both kinds must express the same state.

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
        if not feeds(formulation.output.kind, target.kind):
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
    return Composition(outer, dict(inner), bind)
