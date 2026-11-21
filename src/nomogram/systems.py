# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Systems of equations: several unknowns, solved together.

A :class:`System` is a multivariate measurement model (JCGM 102:2011, 3.8;
VIM 2.48, note 2): several equations, each given by a formulation of the
catalog, coupled through their variables. Its equations are listed in the
order the source computes them. An **unknown** is a variable that an
equation reads before the equation that gives it, in that order: what the
source iterates on. The other variables the equations give are
**intermediate**, computed from the unknowns and the inputs; the variables
no equation gives are the **inputs** of the system.

:meth:`System.evaluate` solves it for each set of inputs:

- ``method="newton"`` (default): Newton's method on the residuals of the
  unknowns, x - g(x) for an explicit equation, h for an implicit one (an
  implicit equation joins the unknowns of Newton's method even where it
  gives an intermediate variable), damped by a backtracking line search
  (Armijo) and vectorised over the values given. The Jacobian is exact: the
  chain rule assembles it from the partial derivatives of each formulation,
  which SymPy derives and which are compiled once. A set of values
  converges when every residual, relative to the size of its terms (the
  values on each side, and the first-order contribution of each variable),
  is below :data:`TOLERANCE`, or below :data:`FLOOR` where no step lowers
  it further, at the rounding of its terms. The unknown of an implicit
  equation stays where :meth:`~nomogram.model.Formulation.evaluate` seeks
  its root (the physical domains on its output and the bounds of its
  kind). Without convergence, with a singular Jacobian or a residual
  undefined, its results are NaN and a :class:`ConvergenceWarning` counts
  the sets of values by reason. Newton's method finds a solution near its
  start, the first guess the source prescribes: converged, never proven
  unique (JCGM 102:2011, 6.3.1.2, note: solved numerically "starting from
  an approximation").
- ``method="fixed-point"``: the passes the source iterates, from its
  first guess, each equation in turn taking the latest values, an implicit
  equation solved for its root at each pass; the result is the source's
  own procedure, and its residual is reported (:attr:`Solution.residual`),
  not tested.

Units, conventional scales and validity domains follow
:meth:`~nomogram.model.Formulation.evaluate`: each formulation takes its
values in its own units and on its own scale, and gives its result on the
reference scale of its kind. The domains of every equation apply to the
inputs of the system before it is solved, and once solved to every value
each equation takes and gives, unknowns and intermediate variables
included: a set of values outside one of them is NaN with
``outside="nan"``, for every variable, the equations being coupled. An
equation may follow the source's own practice instead (``Equation.outside``,
``"ignore"`` where the source takes a value beyond a domain).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from types import MappingProxyType
from typing import Any, Literal

import numpy as np

from nomogram.expression import compile_numeric, parse_expression
from nomogram.model import (
    Basis,
    Formulation,
    OutOfDomainError,
    Outside,
    RootWarning,
    ScaleConversion,
    ValidityWarning,
    Variable,
    _check_given,
    _check_options,
    _flag_beyond,
    _on_scale,
    _to_reference,
)
from nomogram.semantics import semantic_catalog
from nomogram.units import Q_, convert

__all__ = [
    "CONVERGED",
    "FLOOR",
    "ITERATED",
    "MAX_ITERATIONS",
    "NOT_CONVERGED",
    "OUTSIDE",
    "SINGULAR",
    "STATUS",
    "TOLERANCE",
    "UNDEFINED",
    "ConvergenceWarning",
    "Equation",
    "Solution",
    "System",
]

#: Largest residual of a converged set of values, relative to the size of
#: its terms.
TOLERANCE = 1e-12

#: Largest relative residual accepted where no step lowers it further: the
#: rounding of terms that nearly cancel.
FLOOR = 1e-8

#: Newton steps, by default, before a set of values is not converged.
MAX_ITERATIONS = 50

#: Status of a set of values, in :attr:`Solution.status`.
CONVERGED, NOT_CONVERGED, SINGULAR, UNDEFINED, ITERATED, OUTSIDE = range(6)

#: Names of the statuses, by code.
STATUS = (
    "converged",
    "not converged",
    "singular",
    "undefined",
    "iterated",
    "inputs outside a domain",
)

#: Sufficient decrease of the line search (Armijo).
_ARMIJO = 1e-4

#: Halvings of a Newton step before the line search gives up.
_HALVINGS = 40

#: Condition number, after equilibration, beyond which a Jacobian is
#: singular.
_SINGULAR = 1e14

Method = Literal["newton", "fixed-point"]


class ConvergenceWarning(UserWarning):
    """A system was not solved for some sets of values: NaN there.

    Newton's method did not converge, met a singular Jacobian, a residual
    undefined (a value beyond the domain of a function), or a first guess
    outside where the root of an implicit equation is sought.
    """


@dataclass(frozen=True)
class Equation:
    """An equation of a system: a formulation, its variables named in the system.

    Attributes
    ----------
    formulation : Formulation
        The formulation; its output is the variable the equation gives.
    bind : mapping of str to str
        Names in the system of the formulation's variables, by identifier;
        a variable not listed keeps its identifier.
    outside : {"nan", "warn", "raise", "ignore"} or None
        The source's own practice for the domains of this equation, in
        place of the option of :meth:`System.evaluate`: ``"ignore"`` where
        the source takes a value beyond them (and says so). ``None``
        follows the option.
    """

    formulation: Formulation
    bind: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    outside: Outside | None = None

    def __post_init__(self) -> None:
        identifiers = {v.identifier for v in self.formulation.inputs}
        identifiers.add(self.formulation.output.identifier)
        unknown = sorted(set(self.bind) - identifiers)
        if unknown:
            msg = f"{self.formulation.key} has no variable {', '.join(unknown)}"
            raise ValueError(msg)
        if self.outside is not None:
            _check_options(self.outside, "stated", "convert")
        object.__setattr__(self, "bind", MappingProxyType(dict(self.bind)))

    def name(self, identifier: str) -> str:
        """The name in the system of a variable of the formulation."""
        return self.bind.get(identifier, identifier)

    @property
    def output(self) -> str:
        """The name of the variable the equation gives."""
        return self.name(self.formulation.output.identifier)

    @property
    def reads(self) -> tuple[str, ...]:
        """The names of the variables the equation takes, in order."""
        return tuple(self.name(v.identifier) for v in self.formulation.inputs)


@dataclass(frozen=True)
class Solution:
    """The solution of a system for each set of values given.

    Attributes
    ----------
    values : mapping of str to pint.Quantity
        Every variable the system gives, unknowns and intermediate ones,
        in the unit of the formulation that gives it; NaN where the set of
        values was not solved, or lies outside a domain.
    status : numpy.ndarray of int
        For each set of values, one of :data:`CONVERGED`,
        :data:`NOT_CONVERGED`, :data:`SINGULAR`, :data:`UNDEFINED`
        (Newton's method), :data:`ITERATED` (the passes of a fixed point),
        or :data:`OUTSIDE` (inputs outside a domain, not solved);
        :data:`STATUS` names them.
    residual : numpy.ndarray of float
        The largest residual left, relative to the size of its terms.
    iterations : numpy.ndarray of int
        Newton steps, or passes of the fixed point.
    method : str
        ``"newton"`` or ``"fixed-point"``.
    """

    values: Mapping[str, Any]
    status: Any
    residual: Any
    iterations: Any
    method: str

    def __getitem__(self, name: str) -> Any:
        """The values of a variable, by name."""
        return self.values[name]


@dataclass(frozen=True)
class System:
    """Equations solved together for their unknowns.

    Attributes
    ----------
    key, label : str
        Identification.
    equations : tuple of Equation
        In the order the source computes them, which defines the unknowns
        (read before they are given) and the passes of the fixed point.
    start : mapping of str to str
        The first guess of each unknown, an expression of the inputs in the
        catalog syntax (a number alone, or ``0.035 * U``), in the unit of
        the formulation that gives the unknown, the inputs in the units of
        the first formulation that takes each; a number is taken as its
        text.
    iterations : int or None
        The passes of the fixed point the source iterates, if it says.
    note : str
        Free text.
    """

    key: str
    label: str
    equations: tuple[Equation, ...]
    start: Mapping[str, str]
    iterations: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "equations", tuple(self.equations))
        if not self.equations:
            msg = f"{self.key}: a system needs equations"
            raise ValueError(msg)
        given: dict[str, int] = {}
        for i, equation in enumerate(self.equations):
            if equation.output in given:
                msg = f"{self.key}: two equations give {equation.output}"
                raise ValueError(msg)
            given[equation.output] = i
        if not self.unknowns:
            msg = (
                f"{self.key}: no equation reads a variable before another gives "
                "it: a composition, not a system"
            )
            raise ValueError(msg)
        self._check_links()
        start: dict[str, str] = {}
        given_start: Mapping[str, object] = self.start
        for name, text in given_start.items():
            if isinstance(text, str):
                start[name] = text
            elif isinstance(text, int | float) and not isinstance(text, bool):
                start[name] = repr(float(text))
            else:
                msg = f"{self.key}: the first guess of {name} is not an expression"
                raise TypeError(msg)
        object.__setattr__(self, "start", MappingProxyType(start))
        missing = sorted(set(self.unknowns) - set(self.start))
        extra = sorted(set(self.start) - set(self.unknowns))
        if missing or extra:
            msg = (
                f"{self.key}: a first guess for each unknown "
                f"({', '.join(self.unknowns)}); missing: {', '.join(missing) or 'none'}"
                f", not an unknown: {', '.join(extra) or 'none'}"
            )
            raise ValueError(msg)
        for name in self.unknowns:
            self._first_guess(name)
        if self.iterations is not None and self.iterations < 1:
            msg = f"{self.key}: iterations must be positive"
            raise ValueError(msg)

    def _check_links(self) -> None:
        """Each variable given feeds each equation that takes it: a kind it
        may feed, in a unit of the same dimension."""
        from pint.errors import DimensionalityError

        from nomogram.comparison import _may_feed

        units = semantic_catalog().units
        for equation in self.equations:
            for v in equation.formulation.inputs:
                name = equation.name(v.identifier)
                if name not in self._giver:
                    continue
                source = self.variable(name)
                where = f"{self.key}: {name} given as {source.kind}"
                if not _may_feed(source.kind, v.kind):
                    msg = f"{where} cannot feed {v.kind} in {equation.formulation.key}"
                    raise ValueError(msg)
                try:
                    convert(Q_(1.0, units[source.unit].pint), units[v.unit].pint)
                except DimensionalityError as error:
                    msg = (
                        f"{where} in {source.unit}, taken in {v.unit} by "
                        f"{equation.formulation.key}"
                    )
                    raise ValueError(msg) from error

    @cached_property
    def _giver(self) -> Mapping[str, int]:
        """The equation that gives each variable, by name."""
        return MappingProxyType({e.output: i for i, e in enumerate(self.equations)})

    @cached_property
    def unknowns(self) -> tuple[str, ...]:
        """The variables read before they are given, in order of reading."""
        given: set[str] = set()
        found: list[str] = []
        for equation in self.equations:
            for name in equation.reads:
                if name in self._giver and name not in given and name not in found:
                    found.append(name)
            given.add(equation.output)
        return tuple(found)

    @cached_property
    def intermediates(self) -> tuple[str, ...]:
        """The variables given and not unknowns, in the order of the equations."""
        return tuple(e.output for e in self.equations if e.output not in self.unknowns)

    @cached_property
    def inputs(self) -> tuple[str, ...]:
        """The variables no equation gives, in order of reading."""
        found: list[str] = []
        for equation in self.equations:
            for name in equation.reads:
                if name not in self._giver and name not in found:
                    found.append(name)
        return tuple(found)

    @cached_property
    def outputs(self) -> tuple[str, ...]:
        """Every variable the system gives, in the order of the equations."""
        return tuple(e.output for e in self.equations)

    def variable(self, name: str) -> Variable:
        """The variable of a name: as its equation gives it, or as first taken.

        Raises
        ------
        KeyError
            If no equation gives or takes it.
        """
        if name in self._giver:
            return self.equations[self._giver[name]].formulation.output
        for equation in self.equations:
            for v in equation.formulation.inputs:
                if equation.name(v.identifier) == name:
                    return v
        msg = f"{self.key} has no variable {name!r}"
        raise KeyError(msg)

    def _first_guess(self, name: str) -> Any:
        """The compiled first guess of an unknown, a function of the inputs."""
        try:
            expression = parse_expression(self.start[name], self.inputs)
        except ValueError as error:
            msg = f"{self.key}: the first guess of {name}: {error}"
            raise ValueError(msg) from error
        return compile_numeric(expression, self.inputs)

    def evaluate(
        self,
        *,
        method: Method = "newton",
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        start: Mapping[str, Any] | None = None,
        iterations: int | None = None,
        **inputs: Any,
    ) -> Solution:
        """Solve the system on pint quantities.

        Parameters
        ----------
        method : {"newton", "fixed-point"}
            Newton's method (default), or the passes of the fixed point the
            source iterates.
        outside, basis, scale
            As for :meth:`~nomogram.model.Formulation.evaluate`, for the
            domains of every equation and the conventional scales of its
            variables.
        start : mapping of str to pint.Quantity, optional
            First guesses replacing the source's, by unknown, in the shape
            of the inputs or broadcast to it.
        iterations : int, optional
            The most Newton steps (default :data:`MAX_ITERATIONS`), or the
            passes of the fixed point (default :attr:`iterations`).
        **inputs : pint.Quantity
            One quantity per input of the system, by name.

        Returns
        -------
        Solution
            The values of every variable the system gives, with the status
            of each set of values.

        Raises
        ------
        TypeError
            If an input is missing or unexpected.
        ValueError
            If an option is not one of its values, a first guess is not of
            an unknown or not in the shape of the inputs, or the passes of
            a fixed point are not known.
        OutOfDomainError
            With ``outside="raise"``, if a value lies outside a domain.
        """
        _check_options(outside, basis, scale)
        if method not in ("newton", "fixed-point"):
            msg = f"method: expected newton or fixed-point, not {method!r}"
            raise ValueError(msg)
        expected = set(self.inputs)
        if set(inputs) != expected:
            missing = ", ".join(sorted(expected - set(inputs))) or "none"
            unexpected = ", ".join(sorted(set(inputs) - expected)) or "none"
            msg = f"{self.key}: missing inputs: {missing}; unexpected: {unexpected}"
            raise TypeError(msg)
        start = dict(start or {})
        wrong = sorted(set(start) - set(self.unknowns))
        if wrong:
            msg = f"{self.key}: not an unknown: {', '.join(wrong)}"
            raise ValueError(msg)
        if iterations is not None and iterations < 1:
            msg = "iterations must be positive"
            raise ValueError(msg)
        passes = iterations if iterations is not None else self.iterations
        if method == "fixed-point" and passes is None:
            msg = f"{self.key}: the source states no passes; give iterations"
            raise ValueError(msg)
        run = _Run(self, inputs, scale, outside)
        skip = run.outside_inputs(outside, basis)
        first = run.first_guess(start)
        if method == "newton":
            found = run.newton(first, iterations or MAX_ITERATIONS, skip)
        else:
            assert passes is not None
            found = run.fixed_point(first, passes, skip)
        return run.solution(found, method, outside, basis)


class _Found:
    """What a method found: the unknowns of Newton's method, the status,
    residual and steps of each set of values, and, for a fixed point, the
    values of its last pass."""

    def __init__(
        self,
        x: Any,
        status: Any,
        residual: Any,
        steps: Any,
        known: dict[str, Any] | None = None,
        seen: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self.x, self.status, self.residual, self.steps = x, status, residual, steps
        self.known, self.seen = known, seen


class _Run:
    """One evaluation of a system: its inputs as each equation takes them."""

    def __init__(
        self,
        system: System,
        inputs: Mapping[str, Any],
        scale: ScaleConversion,
        outside: Outside,
    ) -> None:
        self.system = system
        self.scale = scale
        units = semantic_catalog().units
        constants: list[dict[str, Any]] = []
        arrays: list[Any] = []
        for equation in system.equations:
            formulation = equation.formulation
            taken: dict[str, Any] = {}
            beyond = []
            for v in formulation.inputs:
                name = equation.name(v.identifier)
                if name not in inputs:
                    continue
                if scale == "ignore":
                    _check_given(formulation.key, v, inputs[name])
                taken[v.identifier], failed = _on_scale(v, inputs[name], scale)
                if failed is not None and v.scale is not None:
                    beyond.append((v.identifier, v.scale, failed))
                arrays.append(taken[v.identifier])
            if scale == "convert":
                _flag_beyond(formulation.key, beyond, equation.outside or outside)
            constants.append(taken)
        self.shape = np.broadcast_shapes(*(np.shape(a) for a in arrays))
        self.size = int(np.prod(self.shape, dtype=int))
        self.constants = [
            {k: np.broadcast_to(a, self.shape).reshape(-1) for k, a in taken.items()}
            for taken in constants
        ]
        # Inputs that are NaN (or beyond a scale conversion): NaN results,
        # silently, as a formulation gives.
        self.blank = np.zeros(self.size, dtype=bool)
        for taken in self.constants:
            for value in taken.values():
                self.blank |= ~np.isfinite(value)
        # The inputs in the units of the first formulation that takes each,
        # for the first guesses.
        self.inputs = {
            name: np.broadcast_to(
                np.asarray(
                    convert(
                        inputs[name], units[system.variable(name).unit].pint
                    ).magnitude,
                    dtype=float,
                ),
                self.shape,
            ).reshape(-1)
            for name in system.inputs
        }
        # The unknowns of Newton's method: those of the system, then the
        # outputs of implicit equations, solved with them rather than for
        # their roots at every step.
        self.unknowns = system.unknowns + tuple(
            e.output
            for e in system.equations
            if e.formulation.implicit and e.output not in system.unknowns
        )
        self.computed = tuple(n for n in system.intermediates if n not in self.unknowns)
        self.links = {
            (i, v.identifier): _link(
                system.variable(equation.name(v.identifier)), v, scale
            )
            for i, equation in enumerate(system.equations)
            for v in equation.formulation.inputs
            if equation.name(v.identifier) in system._giver
        }
        self.backs = [
            _back(equation.formulation.output, scale) for equation in system.equations
        ]

    def outside_inputs(self, outside: Outside, basis: Basis) -> Any:
        """Where the inputs of the system lie outside a domain of an equation
        that takes them, before solving: raised, or not solved with
        ``outside="nan"``, as :meth:`Formulation.evaluate` does for an
        implicit equation."""
        mask = np.zeros(self.size, dtype=bool)
        for i, equation in enumerate(self.system.equations):
            rule = equation.outside or outside
            formulation = equation.formulation
            given = self.constants[i]
            if rule not in ("nan", "raise") or not given or formulation.parts:
                continue
            if formulation.branches:
                continue
            here = np.broadcast_to(formulation._outside(given, basis), mask.shape)
            if rule == "raise" and here.any():
                message = formulation._outside_message(here, given, basis)
                raise OutOfDomainError(f"{self.system.key}: {message}")
            mask |= here
        return mask

    def first_guess(self, start: Mapping[str, Any]) -> Any:
        """The first guesses, one column per unknown of Newton's method; an
        implicit equation's output from its root at the first guesses."""
        system = self.system
        units = semantic_catalog().units
        arguments = [self.inputs[name] for name in system.inputs]
        known: dict[str, Any] = {}
        for name in system.unknowns:
            if name in start:
                # Given in the shape of the inputs.
                unit = units[system.variable(name).unit].pint
                value = np.asarray(convert(start[name], unit).magnitude, dtype=float)
                try:
                    column = np.broadcast_to(value, self.shape).reshape(-1)
                except ValueError as error:
                    msg = f"{system.key}: the first guess of {name} is not in the shape of the inputs"
                    raise ValueError(msg) from error
            else:
                # Computed from the inputs, already flat.
                with np.errstate(all="ignore"):
                    value = np.asarray(
                        system._first_guess(name)(*arguments), dtype=float
                    )
                column = np.broadcast_to(value, (self.size,))
            known[name] = column
        if len(self.unknowns) > len(system.unknowns):
            rows = np.arange(self.size)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RootWarning)
                for name in system.intermediates:
                    known[name] = self.apply(system._giver[name], known, None, rows)[0]
        return np.stack([known[name] for name in self.unknowns], axis=1)

    def apply(
        self,
        i: int,
        known: Mapping[str, Any],
        gradients: Mapping[str, Any] | None,
        rows: Any,
    ) -> tuple[Any, Any, dict[str, Any], Any]:
        """An equation on the values known: its result as the system holds
        it (on the reference scale), its gradient in the unknowns, the values
        it takes and gives as the formulation does, and the size of its
        first-order terms (with the gradient)."""
        equation = self.system.equations[i]
        formulation = equation.formulation
        taken, slopes = self._taken(i, known, rows)
        with np.errstate(all="ignore"):
            raw = np.broadcast_to(
                np.asarray(formulation._raw(taken), dtype=float), rows.shape
            )
        result, back = self.backs[i](raw)
        gradient = size = None
        if gradients is not None:
            # An implicit equation never reaches here: it is an unknown.
            n = len(self.unknowns)
            gradient = np.zeros((rows.size, n))
            partial = self._partials(formulation, taken, rows.size)
            size = np.zeros(rows.size)
            for v in formulation.inputs:
                magnitude = np.abs(taken[v.identifier])
                if v.identifier in slopes:
                    name = equation.name(v.identifier)
                    term = partial[v.identifier] * slopes[v.identifier]
                    gradient += term[:, None] * gradients[name]
                    magnitude = _held(magnitude, slopes[v.identifier], known[name])
                size = size + np.abs(partial[v.identifier]) * magnitude
            gradient *= back[:, None]
            size = size * np.abs(back)
        return result, gradient, {**taken, formulation.output.identifier: raw}, size

    def _taken(
        self, i: int, known: Mapping[str, Any], rows: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """The values an equation takes, in its units and scales, and their
        slopes against the values the system holds."""
        equation = self.system.equations[i]
        taken: dict[str, Any] = {}
        slopes: dict[str, Any] = {}
        for v in equation.formulation.inputs:
            if v.identifier in self.constants[i]:
                taken[v.identifier] = self.constants[i][v.identifier][rows]
            else:
                value, slope = self.links[(i, v.identifier)](
                    known[equation.name(v.identifier)]
                )
                taken[v.identifier], slopes[v.identifier] = value, slope
        return taken, slopes

    def _arguments(
        self, formulation: Formulation, taken: Mapping[str, Any]
    ) -> list[Any]:
        arguments = [taken[v.identifier] for v in formulation.inputs]
        arguments += [c.value for c in formulation.coefficients]
        arguments += [k.value for k in formulation.constants]
        return arguments

    def _partials(
        self, formulation: Formulation, taken: Mapping[str, Any], size: int
    ) -> dict[str, Any]:
        """The partial derivatives of an explicit formulation, in its units."""
        identifiers = tuple(v.identifier for v in formulation.inputs)
        functions = _derivatives(
            formulation.sympy_expression, formulation.names, identifiers
        )
        arguments = self._arguments(formulation, taken)
        with np.errstate(all="ignore"):
            return {
                identifier: np.broadcast_to(
                    np.asarray(function(*arguments), dtype=float)
                    * formulation.output_factor,
                    (size,),
                )
                for identifier, function in zip(identifiers, functions, strict=True)
            }

    def _members_derivatives(
        self, formulation: Formulation, y: Any, taken: Mapping[str, Any], size: int
    ) -> tuple[Any, dict[str, Any]]:
        """The derivatives of the residual h of an implicit formulation, in
        its output and in each input, in its units."""
        left, right = formulation.equation_members
        residual = left - formulation._member_factor * right
        output = formulation.output.identifier
        names = (output, *formulation.names)
        identifiers = tuple(v.identifier for v in formulation.inputs)
        functions = _derivatives(residual, names, (output, *identifiers))
        arguments = [y, *self._arguments(formulation, taken)]
        with np.errstate(all="ignore"):
            values = [
                np.broadcast_to(np.asarray(f(*arguments), dtype=float), (size,))
                for f in functions
            ]
        return values[0], dict(zip(identifiers, values[1:], strict=True))

    def state(self, x: Any, rows: Any, jacobian: bool) -> tuple[Any, ...]:
        """At x: the residuals of the unknowns, the size of their terms, the
        Jacobian if asked, whether each implicit unknown lies where its root
        is sought, every variable as the system holds it, and the values
        each equation takes and gives."""
        n = len(self.unknowns)
        known: dict[str, Any] = {}
        gradients: dict[str, Any] | None = {} if jacobian else None
        for k, name in enumerate(self.unknowns):
            known[name] = x[:, k]
            if gradients is not None:
                unit = np.zeros((rows.size, n))
                unit[:, k] = 1.0
                gradients[name] = unit
        seen: dict[int, dict[str, Any]] = {}
        giver = self.system._giver
        for name in self.computed:
            known[name], gradient, seen[giver[name]], _ = self.apply(
                giver[name], known, gradients, rows
            )
            if gradients is not None:
                gradients[name] = gradient
        residual = np.empty((rows.size, n))
        terms = np.empty((rows.size, n))
        inside = np.ones(rows.size, dtype=bool)
        matrix = np.zeros((rows.size, n, n)) if jacobian else None
        for k, name in enumerate(self.unknowns):
            i = giver[name]
            if self.system.equations[i].formulation.implicit:
                h, size, row, seen[i], here = self._implicit(
                    i, k, x[:, k], known, gradients, rows
                )
                residual[:, k], terms[:, k] = h, size
                inside &= here
            else:
                given, gradient, seen[i], size = self.apply(i, known, gradients, rows)
                residual[:, k] = x[:, k] - given
                terms[:, k] = np.maximum(np.abs(x[:, k]), np.abs(given))
                row = None
                if gradient is not None:
                    terms[:, k] = np.maximum(terms[:, k], size)
                    row = -gradient
                    row[:, k] += 1.0
            if matrix is not None:
                matrix[:, k, :] = row
        return residual, terms, matrix, inside, known, seen

    def _implicit(
        self,
        i: int,
        k: int,
        value: Any,
        known: Mapping[str, Any],
        gradients: Mapping[str, Any] | None,
        rows: Any,
    ) -> tuple[Any, Any, Any, dict[str, Any], Any]:
        """The residual h of an implicit equation whose output is unknown k,
        the size of its terms, its row of the Jacobian, the values it takes
        and gives, and whether the unknown lies where its root is sought."""
        equation = self.system.equations[i]
        formulation = equation.formulation
        taken, slopes = self._taken(i, known, rows)
        output = formulation.output
        y, y_slope = _link(output, output, self.scale)(value)
        left, right = formulation._members_functions
        arguments = [y, *self._arguments(formulation, taken)]
        with np.errstate(all="ignore"):
            first = np.broadcast_to(
                np.asarray(left(*arguments), dtype=float), rows.shape
            )
            second = formulation._member_factor * np.broadcast_to(
                np.asarray(right(*arguments), dtype=float), rows.shape
            )
        size = np.maximum(np.abs(first), np.abs(second))
        row = None
        if gradients is not None:
            h_y, h_x = self._members_derivatives(formulation, y, taken, rows.size)
            row = np.zeros((rows.size, len(self.unknowns)))
            row[:, k] += h_y * y_slope
            linear = np.abs(h_y) * _held(np.abs(y), y_slope, value)
            for v in formulation.inputs:
                magnitude = np.abs(taken[v.identifier])
                if v.identifier in slopes:
                    name = equation.name(v.identifier)
                    term = h_x[v.identifier] * slopes[v.identifier]
                    row += term[:, None] * gradients[name]
                    magnitude = _held(magnitude, slopes[v.identifier], known[name])
                linear = linear + np.abs(h_x[v.identifier]) * magnitude
            size = np.maximum(size, linear)
        low, high = formulation._search_interval(None)
        inside = (y >= low) & (y <= high)
        return first - second, size, row, {**taken, output.identifier: y}, inside

    def newton(self, first: Any, most: int, skip: Any) -> _Found:
        """Damped Newton's method from the first guesses, row by row."""
        x = first.copy()
        size = x.shape[0]
        status = np.full(size, NOT_CONVERGED)
        left = np.full(size, np.nan)
        steps = np.zeros(size, dtype=int)
        status[skip] = OUTSIDE
        status[~skip & (self.blank | ~np.isfinite(x).all(axis=1))] = UNDEFINED
        active = np.flatnonzero(status == NOT_CONVERGED)
        for step in range(most + 1):
            if not active.size:
                break
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RootWarning)
                residual, terms, matrix, inside = self.state(x[active], active, True)[
                    :4
                ]
            if step == 0:
                # A first guess outside where an implicit equation's root is
                # sought gives no solution there.
                status[active[~inside]] = UNDEFINED
                residual, terms, matrix = (
                    residual[inside],
                    terms[inside],
                    matrix[inside],
                )
                active = active[inside]
                if not active.size:
                    break
            error = _relative(residual, terms).max(axis=1)
            done = np.isfinite(error) & (error <= TOLERANCE)
            status[active[done]] = CONVERGED
            left[active] = error
            steps[active] = step
            finite = np.isfinite(error) & np.isfinite(matrix).all(axis=(1, 2))
            status[active[~done & ~finite]] = UNDEFINED
            keep = ~done & finite
            if step == most or not keep.any():
                break
            rows, matrix = active[keep], matrix[keep]
            residual, terms = residual[keep], terms[keep]
            singular = ~(_condition(matrix) < _SINGULAR)
            status[rows[singular]] = SINGULAR
            rows, matrix = rows[~singular], matrix[~singular]
            residual, terms = residual[~singular], terms[~singular]
            if not rows.size:
                break
            delta = np.linalg.solve(matrix, -residual[..., None])[..., 0]
            accepted = self._line_search(x, rows, delta, residual, terms)
            stalled = rows[~accepted]
            status[stalled[left[stalled] <= FLOOR]] = CONVERGED
            active = rows[accepted]
        return _Found(x, status, left, steps)

    def _line_search(
        self, x: Any, rows: Any, delta: Any, residual: Any, terms: Any
    ) -> Any:
        """Halve each Newton step until it lowers the scaled residual enough
        (Armijo) and keeps each implicit unknown where its root is sought;
        update x where it does. Which rows moved."""
        safe = np.where(terms > 0, terms, 1.0)
        merit = 0.5 * np.sum((residual / safe) ** 2, axis=1)
        factor = np.ones(rows.size)
        accepted = np.zeros(rows.size, dtype=bool)
        start = x[rows]
        for _ in range(_HALVINGS):
            todo = np.flatnonzero(~accepted)
            if not todo.size:
                break
            trial = start[todo] + factor[todo, None] * delta[todo]
            with np.errstate(all="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore", RootWarning)
                found, _, _, inside = self.state(trial, rows[todo], jacobian=False)[:4]
                value = 0.5 * np.sum((found / safe[todo]) ** 2, axis=1)
            good = (
                inside
                & np.isfinite(value)
                & (value <= (1.0 - 2.0 * _ARMIJO * factor[todo]) * merit[todo])
            )
            x[rows[todo[good]]] = trial[good]
            accepted[todo[good]] = True
            factor[todo[~good]] /= 2.0
        return accepted

    def fixed_point(self, first: Any, passes: int, skip: Any) -> _Found:
        """The passes of the source: each equation in turn, the latest values;
        the values of the last pass, as the source gives them."""
        system = self.system
        rows = np.arange(self.size)
        known = {name: first[:, k] for k, name in enumerate(system.unknowns)}
        seen: dict[int, dict[str, Any]] = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RootWarning)
            for _ in range(passes):
                for i, equation in enumerate(system.equations):
                    known[equation.output], _, seen[i], _ = self.apply(
                        i, known, None, rows
                    )
            x = np.stack([known[name] for name in self.unknowns], axis=1)
            residual, terms = self.state(x, rows, jacobian=True)[:2]
        left = _relative(residual, terms).max(axis=1)
        status = np.where(np.isfinite(x).all(axis=1), ITERATED, UNDEFINED)
        status[self.blank] = UNDEFINED
        status[skip] = OUTSIDE
        return _Found(x, status, left, np.full(self.size, passes), known, seen)

    def solution(
        self, found: _Found, method: str, outside: Outside, basis: Basis
    ) -> Solution:
        """The values of every variable, NaN where not solved or outside."""
        system = self.system
        rows = np.arange(self.size)
        status = found.status
        if found.known is None or found.seen is None:
            with np.errstate(all="ignore"):
                known, seen = self.state(found.x, rows, jacobian=False)[4:]
        else:
            known, seen = found.known, found.seen
        solved = (status == CONVERGED) | (status == ITERATED)
        reported = ~solved & (status != OUTSIDE) & ~self.blank
        if reported.any():
            counts = [
                f"{int((reported & (status == code)).sum())} {STATUS[code]}"
                for code in (NOT_CONVERGED, SINGULAR, UNDEFINED)
                if (reported & (status == code)).any()
            ]
            message = f"{system.key}: not solved for {', '.join(counts)}; NaN there"
            warnings.warn(message, ConvergenceWarning, stacklevel=3)
        masked = ~solved
        for i, equation in enumerate(system.equations):
            rule = equation.outside or outside
            if rule == "ignore":
                continue
            formulation = equation.formulation
            mask = np.broadcast_to(formulation.outside_mask(seen[i], basis), rows.shape)
            mask = mask & solved
            if not mask.any():
                continue
            message = formulation._outside_message(mask, seen[i], basis)
            if rule == "raise":
                raise OutOfDomainError(f"{system.key}: {message}")
            if rule == "warn":
                warnings.warn(f"{system.key}: {message}", ValidityWarning, stacklevel=3)
            else:
                masked |= mask
        units = semantic_catalog().units
        values = {}
        for name in system.outputs:
            value = np.where(masked, np.nan, known[name]).reshape(self.shape)
            magnitude = value.item() if value.ndim == 0 else value
            values[name] = Q_(magnitude, units[system.variable(name).unit].pint)

        def shaped(array: Any) -> Any:
            array = np.asarray(array).reshape(self.shape)
            return array.item() if array.ndim == 0 else array

        return Solution(
            values=MappingProxyType(values),
            status=shaped(status),
            residual=shaped(found.residual),
            iterations=shaped(found.steps),
            method=method,
        )


def _relative(residual: Any, terms: Any) -> Any:
    """Residuals relative to the size of their terms; 0 where both are 0."""
    with np.errstate(all="ignore"):
        relative = np.abs(residual) / terms
    return np.where((terms == 0) & (residual == 0), 0.0, relative)


def _held(magnitude: Any, slope: Any, held: Any) -> Any:
    """The size of a value taken, at least that of the value held before
    its conversion: a value in degC converted from about 273 K is rounded at
    the scale of 273 K, which bounds what a residual can resolve."""
    return np.maximum(magnitude, np.abs(slope * held))


def _condition(matrix: Any) -> Any:
    """The condition number of each Jacobian once its rows and columns are
    scaled to a largest entry of 1, so that the units of the unknowns and of
    the residuals do not change it; infinite for a row or column of zeros."""
    scaled = np.array(matrix, dtype=float)
    for axis in (2, 1):
        largest = np.abs(scaled).max(axis=axis, keepdims=True)
        scaled = scaled / np.where(largest > 0, largest, 1.0)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.linalg.cond(scaled)


def _slope(function: Callable[[Any], Any], value: Any, converted: Any) -> Any:
    """The slope of a conversion: a central difference, one-sided where the
    other side leaves the bounds of the conversion."""
    step = 1e-6 * np.maximum(np.abs(value), 1.0)
    above, below = function(value + step), function(value - step)
    central = (above - below) / (2.0 * step)
    forward = (above - converted) / step
    backward = (converted - below) / step
    return np.where(
        np.isfinite(central), central, np.where(np.isfinite(forward), forward, backward)
    )


def _link(
    source: Variable, target: Variable, scale: ScaleConversion
) -> Callable[[Any], Any]:
    """From a value held in the unit of ``source``, on the reference scale,
    to the value ``target`` takes, in its unit and on its scale, with the
    slope of the conversion."""
    unit = semantic_catalog().units[source.unit].pint

    def convert_to(value: Any) -> Any:
        return _on_scale(target, Q_(value, unit), scale)[0]

    if scale != "convert" or target.scale is None or target.scale.is_reference:
        # A unit conversion is affine.
        zero, one = convert_to(np.array(0.0)), convert_to(np.array(1.0))
        slope = float(one - zero)

        def affine(value: Any) -> Any:
            converted = convert_to(value)
            return converted, np.full(np.shape(converted), slope)

        return affine

    def on_scale(value: Any) -> Any:
        converted = convert_to(value)
        return converted, _slope(convert_to, value, converted)

    return on_scale


def _back(output: Variable, scale: ScaleConversion) -> Callable[[Any], Any]:
    """From a result on the scale of a formulation to the reference scale,
    with the slope of the conversion."""
    if scale != "convert" or output.scale is None or output.scale.is_reference:
        return lambda value: (value, np.ones(np.shape(value)))

    def convert_back(value: Any) -> Any:
        return _to_reference(output, value, scale)[0]

    def to_reference(value: Any) -> Any:
        converted = convert_back(value)
        return converted, _slope(convert_back, value, converted)

    return to_reference


@lru_cache(maxsize=1024)
def _derivatives(
    expression: Any, names: tuple[str, ...], identifiers: tuple[str, ...]
) -> tuple[Callable[..., Any], ...]:
    """The partial derivatives of an expression, compiled, one per identifier."""
    import sympy

    return tuple(
        compile_numeric(
            sympy.diff(expression, sympy.Symbol(identifier, real=True)), names
        )
        for identifier in identifiers
    )
