# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Formula model: formulations, their variables, coefficients and sources.

A *formulation* is one author's way of computing a quantity kind (the
Magnus form with Sonntag's 1990 coefficients, for instance). Its
mathematical content is an expression written once (see
:mod:`nomogram.expression`); everything around it is traced: variables
with their quantity kind and unit, empirical coefficients, physical
constants, objective validity domains, accuracy and references.

Two kinds of formulas are told apart by ``fixed_units``:

- *fixed units*: the coefficients only hold in the declared units (the
  Magnus form takes t in degC and gives hPa). Coefficients are never
  converted; inputs are converted to the declared unit **and scale**
  before evaluation (a Fahrenheit point becomes a Celsius point), which
  makes the formula usable from any unit;
- otherwise, a quantity equation whose dimensional homogeneity is checked
  when the catalog is loaded.

Validity domains are objective only: physical, or stated by the author or
the cited publication, each with its criterion and reference. What to do
outside them is a parameter of :meth:`Formulation.evaluate`; by default
the result is NaN there. See ``docs/rosetta.md`` for the vocabulary.
"""

from __future__ import annotations

import datetime
import math
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property, lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, get_args

import numpy as np
import sympy

from nomogram.expression import (
    MAX_SOURCE_LENGTH,
    ExpressionError,
    _opaque_calls,
    _relations,
    _split_equation,
    _variants,
    compile_numeric,
    parse_expression,
)
from nomogram.semantics import ExternalMatch, KindBounds, _cf_names, semantic_catalog
from nomogram.units import Q_, convert

if TYPE_CHECKING:
    from nomogram.dimensions import CoefficientUnit
    from nomogram.display import Rendering
    from nomogram.semantics import QuantityKind

__all__ = [
    "Assumption",
    "AssumptionStatus",
    "Branch",
    "Call",
    "CheckCase",
    "Citation",
    "Coefficient",
    "ConstantNature",
    "ConventionalScale",
    "CrossCheck",
    "Derivation",
    "DomainBasis",
    "Formulation",
    "FormulationNature",
    "Notation",
    "OutOfDomainError",
    "Part",
    "PhysicalConstant",
    "Reference",
    "ReferenceStatus",
    "Relation",
    "RelationKind",
    "RootWarning",
    "ScaleBasis",
    "ScaleConversionError",
    "TradeMeaning",
    "TradeTerm",
    "UnitBasis",
    "ValidityDomain",
    "ValidityWarning",
    "Variable",
]

#: What :meth:`Formulation.evaluate` does with values outside the domains.
Outside = Literal["nan", "warn", "raise", "ignore"]
#: Which validity domains :meth:`Formulation.evaluate` applies.
Basis = Literal["stated", "physical", "all"]

#: Whether :meth:`Formulation.evaluate` converts temperatures between scales.
ScaleConversion = Literal["convert", "ignore"]

#: Relative tolerance at domain bounds, for rounding in unit conversions.
BOUND_TOLERANCE = 1e-9


def _check_options(outside: Any, basis: Any, scale: Any) -> None:
    """Refuse an evaluation option outside its allowed values (a typo).

    Raises
    ------
    ValueError
        If ``outside``, ``basis`` or ``scale`` is not one of its values.
    """
    for name, value, allowed in (
        ("outside", outside, get_args(Outside)),
        ("basis", basis, get_args(Basis)),
        ("scale", scale, get_args(ScaleConversion)),
    ):
        if value not in allowed:
            msg = f"{name}: expected one of {', '.join(allowed)}, not {value!r}"
            raise ValueError(msg)


def _flag_beyond(
    key: str, beyond: list[tuple[str, ConventionalScale, Any]], outside: Outside
) -> None:
    """Report values a scale conversion could not convert, as ``outside`` says.

    Such values are NaN whatever the option, since they have no value on
    the other scale: ``"raise"`` raises, ``"warn"`` warns, ``"nan"`` and
    ``"ignore"`` leave the NaN silently.

    Parameters
    ----------
    key : str
        Key of the formulation, for the message.
    beyond : list of (str, ConventionalScale, numpy.ndarray of bool)
        Identifier of the variable, scale converted, and where the
        conversion failed.
    outside : {"nan", "warn", "raise", "ignore"}
        As for :meth:`Formulation.evaluate`.

    Raises
    ------
    OutOfDomainError
        With ``outside="raise"``, if a value could not be converted.
    """
    found = [
        f"{int(np.sum(mask))} value(s) of {identifier} beyond the conversion "
        f"of scale {scale.key}"
        for identifier, scale, mask in beyond
        if np.any(mask)
    ]
    if not found or outside not in ("raise", "warn"):
        return
    message = f"{key}: {'; '.join(found)} (NaN there)"
    if outside == "raise":
        raise OutOfDomainError(message)
    warnings.warn(message, ValidityWarning, stacklevel=3)


def _check_search(key: str, search: Any) -> tuple[float, float]:
    """``search=`` as two numbers, ``low < high``, either end possibly infinite.

    Raises
    ------
    ValueError
        Otherwise: an interval reversed, empty or NaN, or not a pair.
    """
    try:
        low, high = (float(end) for end in search)
    except (TypeError, ValueError):
        low = high = math.nan
    if not low < high:
        msg = f"{key}: search= takes two numbers, low < high, not {search!r}"
        raise ValueError(msg)
    return low, high


def _check_given(key: str, variable: Variable, value: Any) -> None:
    """Refuse a value taken as given that is not written as its scale writes it.

    A scale of numbers (Practical Salinity, S_P = 35) takes a bare number:
    in per mille or in g/kg the value would be read a thousand times
    smaller. A scale of dimensionless quantities (Knudsen salinity, in per
    mille) takes a quantity with its unit: a bare number would be read as a
    fraction, a thousand times larger. Either way without error, hence the
    refusal.

    Raises
    ------
    ScaleConversionError
        If the value is not written as its scale writes it.
    """
    scale = variable.scale
    if scale is None or scale.unit is None:
        return
    # pint's own ``unitless`` holds for per mille: only a bare number has
    # no unit items.
    items = getattr(value, "unit_items", None)
    bare = items is None or not dict(items())
    where = f"{key}: {variable.identifier} is taken as given on {scale.label}"
    if scale.unit == "UNITLESS":
        if bare:
            return
        msg = (
            f"{where}, whose values are numbers: give it without a unit, not in "
            f"{format(value.units, '~P')}"
        )
        raise ScaleConversionError(msg)
    unit = semantic_catalog().units[scale.unit]
    if bare and Q_(1, unit.pint).dimensionless:
        msg = f"{where}, in {unit.symbol}: give it with its unit, not as a bare number"
        raise ScaleConversionError(msg)


class ReferenceStatus(Enum):
    """Whether a reference has been checked against its source."""

    VERIFIED = "verified"
    TO_CONFIRM = "to-confirm"


class DomainBasis(Enum):
    """Ground of a validity domain."""

    #: Where the underlying physics holds.
    PHYSICAL = "physical"
    #: Range stated by the author or the cited publication.
    STATED = "stated"


class ValidityWarning(UserWarning):
    """A formulation was evaluated outside its validity domain."""


class OutOfDomainError(ValueError):
    """A formulation was evaluated outside its validity domain."""


class RootWarning(UserWarning):
    """An implicit equation has no root, or several, where it is solved.

    The value is NaN there: no root in the interval searched (the domains
    of the output and the bounds of its kind, or ``search=``), several
    roots (a domain to narrow), or a residual undefined inside the bracket
    of a root.
    """


@dataclass(frozen=True)
class Reference:
    """A bibliographic source.

    Attributes
    ----------
    key : str
        Catalog key, for example ``"sonntag1990"``.
    authors : str
        Authors, as cited.
    year : int or None
        Year of publication.
    title : str
        Title.
    container : str or None
        Journal, book or series.
    doi : str or None
        DOI, which takes precedence over any other identifier.
    url : str or None
        Address of the source when there is no DOI, or beside a DOI the
        address of a freely readable copy.
    status : ReferenceStatus
        Whether the details were checked against the source.
    note : str or None
        What remains to confirm, or any remark.
    matches : tuple of ExternalMatch
        Links to external vocabularies (a Wikidata item...).
    """

    key: str
    authors: str
    year: int | None
    title: str
    container: str | None
    doi: str | None
    url: str | None
    status: ReferenceStatus
    note: str | None
    matches: tuple[ExternalMatch, ...]


class UnitBasis(Enum):
    """Where the declared unit of a coefficient comes from."""

    #: Stated by the source.
    STATED = "stated"
    #: Added when the entry was written; the note says why. Only for a
    #: unit the expression does not determine (see
    #: :mod:`nomogram.dimensions`): a unit that can be inferred is not
    #: declared.
    ADDED = "added"


class ScaleBasis(Enum):
    """How the conventional scale of a variable is known."""

    #: Stated by the source.
    STATED = "stated"
    #: Inferred from the publication date only: the scale in force then.
    #: Weak, since new scales took years to be applied (ITS-90 included).
    INFERRED_FROM_DATE = "inferred-from-date"
    #: Inferred from numerical evidence, for instance the agreement with a
    #: formulation on a known scale; the evidence goes in the note.
    INFERRED_FROM_NUMBERS = "inferred-from-numbers"


@dataclass(frozen=True)
class ConventionalScale:
    """A conventional reference scale: a quantity-value scale defined by formal agreement.

    The term is that of the VIM (JCGM 200:2012, 1.29). The international
    temperature scales are examples: formulations were fitted to
    temperatures on the scale in force at the time (IPTS-68, ITS-48...),
    and salinity scales followed one another the same way (Knudsen, PSS-78,
    Reference Salinity). Each quantity kind has one reference scale
    (ITS-90 for temperatures, Reference Salinity for salinities); inputs
    are taken on it and converted to the scale of the formulation before
    evaluation, and results converted back.

    Attributes
    ----------
    key : str
        Catalog key, for example ``"ipts68"``.
    label : str
        Name of the scale.
    kinds : tuple of str
        Quantity kinds the scale applies to.
    reference_scale : str or None
        Key of the reference scale of these kinds; ``None`` for the
        reference scale itself.
    unit : str or None
        QUDT name of the unit of the conversion (table or expression);
        ``None`` for a reference scale, and possibly for a scale without
        conversion.
    points : tuple of float
        Values on the reference scale where the difference is tabulated;
        empty without a table.
    difference : tuple of float
        Value on the reference scale minus value on this scale, at those
        points.
    reference : str or None
        Key of the source of the scale or of its table.
    symbol : str or None
        Short name, for example ``"ITS-90"``.
    subscript : str or None
        Subscript that marks a quantity on this scale, for example
        ``"90"`` (the ITS-90 writes t90 and T90).
    base : ConventionalScale or None
        For a conversion by expression, the scale it leads to; ``None``
        when it leads to the reference scale. Chains end on the reference
        scale (Knudsen salinity to Cox salinity, then to Reference
        Salinity).
    conversion : str or None
        The value on ``base`` (or on the reference scale) as an expression
        of ``x``, the value on this scale, both in ``unit``, for example
        ``"35.16504 / 35 * x"``; ``None`` for a table or no conversion.
    bounds : (float, float) or None
        Values on this scale where the conversion holds; NaN beyond.
    convertible : bool
        ``False`` when the conversion needs data nomogram does not hold
        (Absolute Salinity needs the anomaly of its location): values on
        such a scale are taken as given, ``scale="ignore"``.
    matches : tuple of ExternalMatch
        Links to the CF standard names of quantities on this scale
        (``sea_water_practical_salinity``), each with its SKOS relation and
        the date it was checked.
    note : str or None
        Remark: disagreements between sources on the conversion, its
        domain...
    """

    key: str
    label: str
    kinds: tuple[str, ...]
    reference_scale: str | None
    unit: str | None
    points: tuple[float, ...]
    difference: tuple[float, ...]
    reference: str | None
    symbol: str | None = None
    subscript: str | None = None
    base: ConventionalScale | None = None
    conversion: str | None = None
    bounds: tuple[float, float] | None = None
    convertible: bool = True
    matches: tuple[ExternalMatch, ...] = ()
    note: str | None = None

    @property
    def cf_standard_names(self) -> tuple[str, ...]:
        """The CF standard names the scale is linked to (see ``matches``)."""
        return _cf_names(self.matches)

    @property
    def is_reference(self) -> bool:
        """Whether this is the reference scale of its kinds."""
        return self.reference_scale is None

    def applies_to(self, kind: str, kinds: Mapping[str, QuantityKind]) -> bool:
        """Whether the scale applies to a kind: one of its kinds or a specialization.

        A difference is never on a conventional scale, though QUDT makes a
        temperature difference a temperature.

        Parameters
        ----------
        kind : str
            The name of the quantity kind.
        kinds : mapping of str to QuantityKind
            The kinds of the catalog, through which specializations are
            followed (a frost point is a temperature).

        Returns
        -------
        bool
        """
        start = kinds.get(kind)
        if start is not None and start.delta:
            return False
        seen: set[str] = set()
        while kind not in seen:
            if kind in self.kinds:
                return True
            seen.add(kind)
            found = kinds.get(kind)
            if found is None or found.specialization_of is None:
                return False
            kind = found.specialization_of
        return False

    def check_convertible(self) -> None:
        """Raise :class:`ScaleConversionError` if nomogram cannot convert.

        Raises
        ------
        ScaleConversionError
            For a scale whose conversion needs data nomogram does not hold.
        """
        if not self.convertible:
            msg = (
                f"{self.key}: nomogram holds no conversion to the reference "
                f"scale {self.reference_scale}; give values on this scale and "
                'evaluate with scale="ignore"'
            )
            raise ScaleConversionError(msg)

    @cached_property
    def _expression(self) -> Any:
        assert self.conversion is not None
        return parse_expression(self.conversion, ["x"])

    @cached_property
    def _forward_function(self) -> Callable[..., Any]:
        return compile_numeric(self._expression, ("x",))

    @cached_property
    def _inverse_function(self) -> Callable[..., Any] | None:
        """The inverse when SymPy finds a single one; ``None`` otherwise."""
        expr = self._expression
        x = next(iter(expr.free_symbols), sympy.Symbol("x", real=True))
        y = sympy.Symbol("y", real=True)
        try:
            found = sympy.solve(sympy.Eq(y, expr), x)
        except (NotImplementedError, ValueError, TypeError, RecursionError):
            # The conversion is then inverted numerically.
            return None
        return compile_numeric(found[0], ("y",)) if len(found) == 1 else None

    def _outside(self, values: Any) -> Any:
        if self.bounds is None:
            return np.zeros(np.shape(values), dtype=bool)
        low, high = self.bounds
        margin = BOUND_TOLERANCE * max(abs(low), abs(high), 1.0)
        with np.errstate(invalid="ignore"):
            return (values < low - margin) | (values > high + margin)

    def _forward(self, values: Any) -> Any:
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            result = np.asarray(self._forward_function(values), dtype=float)
        return np.broadcast_to(result, np.shape(values)).astype(float)

    def from_reference(self, values: Any) -> tuple[Any, Any]:
        """Values on this scale, from values on the reference scale.

        Parameters
        ----------
        values : array_like
            Values on the reference scale, in the unit of the table.

        Returns
        -------
        (numpy.ndarray, numpy.ndarray of bool)
            The values on this scale (linear interpolation of the table, or
            the inverse of the conversion through the chain of scales), and
            where they fall outside the table or the bounds (NaN there).

        Raises
        ------
        ScaleConversionError
            For a scale nomogram cannot convert.
        """
        values = np.asarray(values, dtype=float)
        if self.is_reference:
            return values, np.zeros(values.shape, dtype=bool)
        self.check_convertible()
        if self.conversion is None:
            outside = (values < self.points[0]) | (values > self.points[-1])
            shift = np.interp(values, self.points, self.difference)
            return np.where(outside, np.nan, values - shift), outside
        on_base, outside = (
            (values, np.zeros(values.shape, dtype=bool))
            if self.base is None
            else self.base.from_reference(values)
        )
        inverse = self._inverse_function
        if inverse is not None:
            with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
                found = np.asarray(inverse(on_base), dtype=float)
            found = np.broadcast_to(found, on_base.shape).astype(float)
        else:
            # Conversions are close to the identity: fixed-point iteration,
            # kept only where it converged.
            found = on_base.copy()
            with np.errstate(invalid="ignore", over="ignore"):
                for _ in range(50):
                    found = found - (self._forward(found) - on_base)
                residual = np.abs(self._forward(found) - on_base)
                converged = residual <= 1e-9 * np.maximum(1.0, np.abs(on_base))
            outside = outside | ~converged
        outside = outside | np.isnan(found) | self._outside(found)
        return np.where(outside, np.nan, found), outside

    def to_reference(self, values: Any) -> Any:
        """Values on the reference scale, from values on this scale.

        A table is inverted by fixed-point iteration (the differences are
        small and vary slowly); a conversion by expression is applied, then
        that of its base. NaN beyond the table or the bounds.

        Raises
        ------
        ScaleConversionError
            For a scale nomogram cannot convert.
        """
        values = np.asarray(values, dtype=float)
        if self.is_reference:
            return values
        self.check_convertible()
        if self.conversion is None:
            on_reference = self._through_table(values)
            outside = (on_reference < self.points[0]) | (on_reference > self.points[-1])
            return np.where(outside, np.nan, on_reference)
        on_base = np.where(self._outside(values), np.nan, self._forward(values))
        return on_base if self.base is None else self.base.to_reference(on_base)

    def interval_to_reference(
        self, low: float, high: float
    ) -> tuple[float, float] | None:
        """An interval of values on this scale, carried to the reference scale.

        Conversions increase: each end is converted, an infinite end staying
        infinite, and the part beyond the conversion table or the bounds of
        the conversion, which has no value on the reference scale, is left
        out.

        Parameters
        ----------
        low, high : float
            Ends of the interval on this scale, in the unit of the scale.

        Returns
        -------
        (float, float) or None
            The interval on the reference scale, in the same unit; ``None``
            when no value of it converts.

        Raises
        ------
        ScaleConversionError
            For a scale nomogram cannot convert.
        """
        self.check_convertible()
        ends = np.array([low, high], dtype=float)
        finite = np.isfinite(ends)
        converted = np.where(
            finite, self._unbounded_to_reference(np.where(finite, ends, 0.0)), ends
        )
        floor, ceiling = self._reference_extent
        low, high = max(float(converted[0]), floor), min(float(converted[1]), ceiling)
        return (low, high) if low < high else None

    def _through_table(self, values: Any) -> Any:
        """Values on the reference scale, by the table, extended beyond it."""
        on_reference = values
        for _ in range(4):
            on_reference = values + np.interp(
                on_reference, self.points, self.difference
            )
        return on_reference

    def _unbounded_to_reference(self, values: Any) -> Any:
        """:meth:`to_reference` extended beyond the table and the bounds."""
        if self.is_reference:
            return values
        if self.conversion is None:
            return self._through_table(values)
        on_base = self._forward(values)
        return (
            on_base if self.base is None else self.base._unbounded_to_reference(on_base)
        )

    @cached_property
    def _reference_extent(self) -> tuple[float, float]:
        """Values on the reference scale that convert to this scale.

        The range of a table; the bounds of a conversion carried to the
        reference scale, within the extent of its base; infinite on a side
        nothing bounds.
        """
        if self.is_reference:
            return (-np.inf, np.inf)
        if self.conversion is None:
            return (self.points[0], self.points[-1])
        low, high = (
            (-np.inf, np.inf) if self.base is None else self.base._reference_extent
        )
        if self.bounds is not None:
            ends = self._unbounded_to_reference(np.array(self.bounds, dtype=float))
            low, high = max(low, float(ends[0])), min(high, float(ends[1]))
        return (float(low), float(high))


class ScaleConversionError(ValueError):
    """A value cannot be converted between conventional scales."""


class RelationKind(Enum):
    """What a relation between two formulations states.

    An equivalence is the narrowest: a proportionality of factor 1. An
    approximation is on another axis, a bounded deviation; a
    proportionality of factor k implies a constant relative deviation
    of |1 - k|.
    """

    #: The subject equals the object, possibly given substitutions.
    EQUIVALENT = "equivalent"
    #: The subject approximates the object within a stated deviation.
    APPROXIMATES = "approximates"
    #: The subject equals the object times a constant factor, possibly
    #: given substitutions (Murray 1967 and Tetens 1930, whose constants
    #: C differ).
    PROPORTIONAL = "proportional"

    @property
    def broader(self) -> RelationKind | None:
        """The looser kind it implies: an equivalence is a proportionality."""
        return RelationKind.PROPORTIONAL if self is RelationKind.EQUIVALENT else None


@dataclass(frozen=True)
class Relation:
    """A relation between two formulations, as a source states it or nomogram proves it.

    A relation is a claim, cited, which nomogram verifies
    (:func:`nomogram.relations.verify`); or, without a citation, an
    equivalence or a proportionality nomogram computes and proves, exactly
    or to the printed precision of the coefficients. Deviations nomogram
    computes are observations (:func:`nomogram.comparison.compare`).

    Attributes
    ----------
    key : str
        Catalog key.
    kind : RelationKind
        Equivalence or approximation.
    subject, object : str
        Keys of the two formulations.
    citation : str or None
        Key of the source that states the relation; ``None`` for a
        relation computed by nomogram (see :attr:`computed`).
    accuracy : float or None
        For an approximation, the maximum relative deviation the source
        states, in percent.
    at : mapping of str to float
        Where the source places that maximum, by input identifier of the
        subject.
    bounds : mapping of str to (float, float)
        Domain over which the source states it, by input identifier of the
        subject, in the input's unit.
    given : mapping of str to str
        For an equivalence or a proportionality, inputs of the object
        expressed with those of the subject (``{"P_d": "P - e"}``); the
        expression may convert a unit (``{"t": "T - 273.16"}``).
    scale : {"convert", "ignore"}
        How the formulations are evaluated for the claim: with conversion
        of conventional scales, or as given, each on its own scale.
    note : str or None
        Remark.
    """

    key: str
    kind: RelationKind
    subject: str
    object: str
    citation: str | None
    accuracy: float | None = None
    at: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    bounds: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    given: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    scale: ScaleConversion = "convert"
    note: str | None = None

    @property
    def computed(self) -> bool:
        """Whether nomogram computes it, no source stating it."""
        return self.citation is None


@dataclass(frozen=True)
class CheckCase:
    """One value of a formulation, as another implementation computes it.

    Attributes
    ----------
    formulation : str
        Key of the formulation.
    inputs : mapping of str to float
        Input values, by identifier, in the units of the formulation's
        inputs; the formulation is evaluated as written (no scale
        conversion, no validity domain).
    value : float
        The value the other implementation gives, in the unit of the
        formulation's output.
    call : str or None
        How the value was obtained from the other implementation.
    rtol : float
        Relative tolerance of the agreement.
    """

    formulation: str
    inputs: Mapping[str, float]
    value: float
    call: str | None = None
    rtol: float = 1e-12


@dataclass(frozen=True)
class CrossCheck:
    """Formulations checked against another implementation, on given points.

    A cross-check records values computed once with software outside
    nomogram (not a dependency); the tests replay the cases against the
    catalog, so that a change of a formulation cannot go unnoticed. It is
    an observation, never a source.

    Attributes
    ----------
    key : str
        Catalog key.
    implementation : str
        Name of the other implementation.
    version : str
        Its version, release or commit, as run.
    checked : datetime.date
        Date of the check.
    cases : tuple of CheckCase
        The values compared.
    url : str or None
        Where the implementation lives.
    note : str or None
        Remark (workarounds, known differences).
    """

    key: str
    implementation: str
    version: str
    checked: datetime.date
    cases: tuple[CheckCase, ...]
    url: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Derivation:
    """How a formulation was derived from others.

    Attributes
    ----------
    source : str
        Key of the formulation it derives from; for a composition, the
        formulation evaluated last; for branches, the first branch; for
        calls, the first formulation called.
    method : str
        ``"symbolic inversion"`` (closed form found by SymPy),
        ``"numerical inversion"``, ``"composition"``, ``"branches"`` or
        ``"calls"``.
    solved_for : str or None
        For an inversion, identifier of the source's input that became the
        output.
    parts : mapping of str to str
        For a composition, the formulation computing each input of the
        source it replaces: input identifier to formulation key. For
        branches, the formulation used under each condition. For calls,
        the formulation of each call, by the call as written
        (``"e_w(p=p, t=t_d)"``).
    """

    source: str
    method: str
    solved_for: str | None = None
    parts: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class Variable:
    """A variable of a formulation: identifier, quantity kind and unit.

    A variable has no external link of its own: it inherits the links of
    its quantity kind.

    Attributes
    ----------
    identifier : str
        Semantic identifier used in the expression, for example ``"t"``.
    kind : str
        Name of its quantity kind.
    unit : str
        QUDT name of the unit the formulation works in.
    description : str
        What the variable is, in a few words.
    scale : ConventionalScale or None
        The conventional scale of the value: for an input, the one the
        formulation was fitted on (a temperature scale, a salinity
        scale); for an output, the one it gives values on. ``None`` when
        unknown or not applicable.
    scale_basis : ScaleBasis or None
        How that scale is known.
    kind_bounds : KindBounds or None
        The bounds its quantity kind admits by definition, declared or
        inherited (see :class:`~nomogram.semantics.KindBounds`), set when
        the catalog is loaded; they apply to its values whatever the
        domains selected, a value on a conventional scale other than the
        reference one being carried to the reference scale first.
    """

    identifier: str
    kind: str
    unit: str
    description: str
    scale: ConventionalScale | None = None
    scale_basis: ScaleBasis | None = None
    kind_bounds: KindBounds | None = None

    def bounds_in_unit(self) -> tuple[float, float] | None:
        """The bounds of its kind in its unit, or ``None`` when none apply.

        None for a variable without bounds, or on a conventional scale
        other than the reference one: a Practical Salinity of 35 is no
        mass fraction, and the scale has its own bounds.
        """
        if self.kind_bounds is None:
            return None
        if self.scale is not None and not self.scale.is_reference:
            return None
        bounds = self.kind_bounds
        return _converted_bounds(bounds.low, bounds.high, bounds.unit, self.unit)


def _beyond(value: Any, low: float, high: float) -> Any:
    """Where values lie beyond a closed interval, its finite ends rounded.

    The tolerance :data:`BOUND_TOLERANCE` lets a value converted between
    units through at a bound; NaN is never beyond.
    """
    finite = [abs(b) for b in (low, high) if math.isfinite(b)]
    margin = BOUND_TOLERANCE * max([*finite, 1.0])
    value = np.asarray(value, dtype=float)
    return (value < low - margin) | (value > high + margin)


def _beyond_kind(variable: Variable, values: Any, unit: str | None = None) -> Any:
    """Where values, in ``unit`` (the variable's by default), lie beyond its kind's bounds."""
    value = np.asarray(values, dtype=float)
    bounds = variable.kind_bounds
    if bounds is None:
        return np.zeros(value.shape, dtype=bool)
    low, high = _converted_bounds(
        bounds.low, bounds.high, bounds.unit, unit or variable.unit
    )
    return _beyond(value, low, high)


@lru_cache(maxsize=256)
def _converted_bounds(
    low: float, high: float, unit: str, target: str
) -> tuple[float, float]:
    """Bounds converted between units, offsets included (0 K is -273.15 degC)."""
    units = semantic_catalog().units
    source, to = units[unit].pint, units[target].pint
    ends = []
    for end in (low, high):
        if math.isinf(end):
            ends.append(end)
        else:
            ends.append(float(Q_(end, source).to(to).magnitude))
    return ends[0], ends[1]


def _kind_bounds_on_scale(variable: Variable) -> tuple[float, float] | None:
    """The bounds of a variable's kind in its unit, on its conventional scale.

    On a scale other than the reference one, each finite end is carried
    from the reference scale onto it; an end beyond the conversion is kept
    as it is, as :meth:`Formulation._beyond_kinds` compares it, which
    bounds holding on every scale (0 K) do rightly.
    """
    bounds = variable.kind_bounds
    if bounds is None:
        return None
    raw = _converted_bounds(bounds.low, bounds.high, bounds.unit, variable.unit)
    scale = variable.scale
    if scale is None or scale.is_reference or not scale.convertible:
        return raw
    units = semantic_catalog().units
    table = variable.unit if scale.unit is None else str(scale.unit)
    reference = _converted_bounds(bounds.low, bounds.high, bounds.unit, table)
    ends = []
    for end, kept in zip(reference, raw, strict=True):
        if not math.isfinite(end):
            ends.append(kept)
            continue
        with np.errstate(invalid="ignore"):
            on_scale, _ = scale.from_reference(np.asarray(end, dtype=float))
        value = float(
            convert(
                Q_(float(on_scale), units[table].pint), units[variable.unit].pint
            ).magnitude
        )
        ends.append(kept if math.isnan(value) else value)
    return ends[0], ends[1]


def _same_unit(unit: Any, other: Any) -> bool:
    """Whether two units give one number to a value: same factor, no offset."""
    from nomogram.units import is_offset_unit

    if unit == other:
        return True
    if is_offset_unit(unit) or is_offset_unit(other):
        return False
    return bool(Q_(1.0, unit).to(other).magnitude == 1.0)


def _coherent(unit: Any) -> bool:
    """Whether a unit is coherent with the SI base units: factor 1, no offset (Pa, K)."""
    return _same_unit(unit, Q_(1.0, unit).to_base_units().units)


def _check_sums(key: str, expr: Any, unit_of: Callable[[Any], Any]) -> None:
    """Refuse a sum whose terms are in two units of one dimension.

    The numeric function adds the numbers: 1500 Pa + 15 hPa would give
    1515 Pa. The terms of a sum share their unit; a unit with an offset
    (degC) is shared only with itself.

    Raises
    ------
    DimensionError
        At the first such sum.
    """
    from nomogram.dimensions import DimensionError

    for node in sympy.preorder_traversal(expr):
        if not isinstance(node, sympy.Add):
            continue
        first, *others = (unit_of(term) for term in node.args)
        for unit in others:
            if not _same_unit(unit, first):
                msg = (
                    f"{key}: {node} adds {first:~P} and {unit:~P}: write the "
                    "terms of a sum in one unit"
                )
                raise DimensionError(msg)


@dataclass(frozen=True)
class Coefficient:
    """An empirical coefficient of a formulation (the A, B, C of Magnus).

    Attributes
    ----------
    identifier : str
        Identifier used in the expression.
    value : float
        Value, as published.
    unit : str or None
        QUDT name of its declared unit; ``None`` when the unit is left to
        inference (:func:`nomogram.dimensions.infer_units`). In a
        fixed-units formulation coefficients are numbers tied to the units
        of the variables, never converted.
    note : str or None
        Remark.
    unit_basis : UnitBasis or None
        Where the declared unit comes from; ``None`` without a declared
        unit.
    """

    identifier: str
    value: float
    unit: str | None
    note: str | None
    unit_basis: UnitBasis | None = None


class ConstantNature(Enum):
    """How the value of a physical constant is known."""

    #: Fixed by definition, without uncertainty: the defining constants of
    #: the SI, whose numerical values "have no uncertainty" (SI Brochure,
    #: 9th ed., 2.2), and constants derived from them alone (CODATA
    #: "exact"; QUDT ``qudt:exactConstant``).
    EXACT = "exact"
    #: Attributed by agreement for a given purpose (VIM 2.12, conventional
    #: quantity value): the standard acceleration of free fall, or a value a
    #: source adopts for its formulas.
    CONVENTIONAL = "conventional"
    #: Representing a measurement result (VIM 2.10, measured quantity
    #: value), with its standard uncertainty when the source gives it.
    MEASURED = "measured"


class FormulationNature(Enum):
    """What makes a formulation hold, when no fit nor model does."""

    #: True by definition (the definition of a quantity, cited to a text
    #: that defines it): it holds without a validity domain.
    DEFINITION = "definition"
    #: An exact consequence of definitions (the latent heat of fusion as
    #: that of sublimation minus that of vaporization).
    IDENTITY = "identity"


@dataclass(frozen=True)
class PhysicalConstant:
    """A constant with a metrological status, and its source.

    Attributes
    ----------
    key : str
        Catalog key, for example ``"R_v_iapws95"``: several sources may
        give different values for the same constant.
    identifier : str
        Identifier used in expressions, for example ``"R_v"``.
    value : float
        Value in ``unit``.
    unit : str
        QUDT name of the unit.
    description : str
        What the constant is.
    reference : str
        Key of the source.
    matches : tuple of ExternalMatch
        Links to external vocabularies.
    nature : ConstantNature or None
        How the value is known; ``None`` when not stated (a catalog file
        may leave it out; every constant of the bundled catalog states it).
    uncertainty : float or None
        Standard uncertainty in ``unit``, as the source gives it; ``None``
        when exact or not given.
    conditions : str or None
        The conditions the value holds in, when it depends on them (a
        latent heat at 0 degC).
    printed : str or None
        The value as the source prints it, when written as text in the
        catalog to keep significant trailing zeros (``"287.0500"``).
    definition : str or None
        The formula giving the value from other constants, in the
        restricted syntax of expressions (``"R_d / R_v"``), when the source
        states one. The value used stays the one printed; the catalog
        checks that it agrees with the formula.
    components : tuple of str
        Keys of the constants the definition uses (``constants`` in a
        catalog file).
    tolerance : float or None
        How far the printed value may depart from the definition, in
        ``unit``, when the source departs from its own formula; ``note``
        then says by how much and why.
    note : str or None
        Remark.
    """

    key: str
    identifier: str
    value: float
    unit: str
    description: str
    reference: str
    matches: tuple[ExternalMatch, ...]
    nature: ConstantNature | None = None
    uncertainty: float | None = None
    conditions: str | None = None
    printed: str | None = None
    definition: str | None = None
    components: tuple[str, ...] = ()
    tolerance: float | None = None
    note: str | None = None


@dataclass(frozen=True)
class ValidityDomain:
    """An objective validity domain of a formulation.

    Attributes
    ----------
    basis : DomainBasis
        Physical, or stated by the author or the cited publication.
    bounds : mapping of str to (float, float)
        Closed interval per input identifier, in the input's unit, and of
        the output when the domain bounds it, in the output's unit; one end
        may be infinite (``(0, inf)``).
    criterion : str or None
        What the domain guarantees, for example a maximum deviation from
        a reference formulation.
    reference : str or None
        Key of the source of the domain.
    """

    basis: DomainBasis
    bounds: Mapping[str, tuple[float, float]]
    criterion: str | None
    reference: str | None


@dataclass(frozen=True)
class Notation:
    """How a convention writes identifiers: identifier to LaTeX symbol.

    Attributes
    ----------
    key : str
        Catalog key, for example ``"wmo"``.
    label : str
        Name of the convention.
    symbols : mapping of str to str
        LaTeX symbol per identifier; identifiers not listed keep their
        default rendering.
    reference : str or None
        Key of the source of the convention.
    """

    key: str
    label: str
    symbols: Mapping[str, str]
    reference: str | None


@dataclass(frozen=True)
class Citation:
    """One appearance of a formulation in a source, and what the source states.

    A formulation is written once; each source that gives it is a
    citation, with the symbols it uses and what it states about the
    formulation. Validity domains of different citations combine by union
    by default: a value is inside if one source says so.

    Attributes
    ----------
    reference : str
        Key of the source.
    equation : str or None
        Equation number in the source, as printed.
    notation : Notation or None
        The symbols the source uses, coefficients included.
    domains : tuple of ValidityDomain
        Validity domains the source states (basis ``stated``); they apply
        together.
    units : mapping of str to str
        Units the source states for coefficients, by identifier (QUDT
        names).
    scales : mapping of str to ConventionalScale
        Conventional reference scales the source states for the inputs
        and the output, by identifier.
    accuracy : str or None
        Accuracy the source claims, as stated.
    note : str or None
        Remark on this citation.
    assumptions : tuple of str
        Assumptions the source states for the formula, as stated.
    """

    reference: str
    equation: str | None = None
    notation: Notation | None = None
    domains: tuple[ValidityDomain, ...] = ()
    units: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    scales: Mapping[str, ConventionalScale] = field(
        default_factory=lambda: MappingProxyType({})
    )
    accuracy: str | None = None
    note: str | None = None
    assumptions: tuple[str, ...] = ()


class AssumptionStatus(Enum):
    """How an assumption of a formulation is known."""

    #: Stated by the source that gives the formula (in its citation).
    STATED = "stated"
    #: Stated by another source, about the formula (a review, a guide).
    STATED_BY_OTHER = "stated-by-other"
    #: Deduced from the form of the formula, its coefficients or its kinds.
    DEDUCED = "deduced"
    #: Suspected, not established: to be checked.
    SUSPECTED = "suspected"


@dataclass(frozen=True)
class Assumption:
    """An assumption under which a formulation holds.

    Attributes
    ----------
    text : str
        The assumption.
    status : AssumptionStatus
        How it is known.
    reference : str or None
        Key of the source that states it; ``None`` when deduced or
        suspected.
    """

    text: str
    status: AssumptionStatus
    reference: str | None = None


@dataclass(frozen=True)
class TradeMeaning:
    """One meaning of an ambiguous trade term.

    Attributes
    ----------
    community : str
        Who uses the term with this meaning.
    kind : str
        Name of the quantity kind it then denotes.
    definition : str
        The meaning, in plain words.
    sources : tuple of str
        Keys of the references documenting this use.
    """

    community: str
    kind: str
    definition: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class TradeTerm:
    """A term whose meaning depends on the trade: never a quantity kind itself.

    Attributes
    ----------
    key : str
        Catalog key.
    term : str
        The term, for example ``"absolute humidity"``.
    language : str
        Language code, for example ``"en"``.
    meanings : tuple of TradeMeaning
        Its meanings, each pointing to an unambiguous quantity kind.
    matches : tuple of ExternalMatch
        Links to external vocabularies.
    """

    key: str
    term: str
    language: str
    meanings: tuple[TradeMeaning, ...]
    matches: tuple[ExternalMatch, ...]


@dataclass(frozen=True)
class Part:
    """A formulation within a composed one, and how its inputs are fed.

    Attributes
    ----------
    formulation : Formulation
        The part.
    computes : str or None
        Identifier of the outer formulation's input it computes; ``None``
        for the outer formulation itself.
    rename : mapping of str to str
        Its identifiers taken under another in the formulation made of it,
        by its own identifier: inputs bound (``bind``) or passed as
        arguments, and, for a formulation called, its coefficients and
        constants renamed.
    arguments : mapping of str to str
        For a formulation called, the expressions passed to its inputs, by
        their identifiers (``{"zeta": "z_s / L"}``): expressions of the
        inputs, coefficients and constants of the calling formulation,
        substituted for those inputs.
    """

    formulation: Formulation
    computes: str | None
    rename: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    arguments: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class Branch:
    """A formulation a piecewise formulation uses on an interval of its input.

    Attributes
    ----------
    formulation : Formulation
        The formulation used there, with its own validity domains and
        sources.
    condition : str
        Where it is used: an interval of the input, in the catalog syntax
        (``"T <= 273.16"``).
    """

    formulation: Formulation
    condition: str


@dataclass(frozen=True)
class Call:
    """A formulation called in the expression of another, with its arguments.

    Attributes
    ----------
    alias : str
        The name the expression calls it by (``e_w``).
    formulation : Formulation
        The formulation called, with its own validity domains and sources.
    arguments : mapping of str to str
        For each of its inputs, by identifier and in the order of its
        inputs, what the calling formulation passes to it: one of its
        inputs (``{"p": "p", "t": "t_d"}``), or an expression of its
        inputs, coefficients and constants, as normalized text
        (``{"zeta": "z_s / L"}``).
    """

    alias: str
    formulation: Formulation
    arguments: Mapping[str, str]


@dataclass(frozen=True)
class Formulation:
    """One author's way of computing a quantity kind.

    Attributes
    ----------
    key : str
        Catalog key, for example ``"sonntag1990"``.
    label : str
        Name of the formulation.
    output : Variable
        The computed variable; its kind groups alternative formulations.
    inputs : tuple of Variable
        Input variables, in the order of the numeric function.
    coefficients : tuple of Coefficient
        Empirical coefficients.
    constants : tuple of PhysicalConstant
        Physical constants used.
    expression : str
        The expression, in restricted Python syntax.
    fixed_units : bool
        Whether the formulation only holds in its declared units.
    physical_domains : tuple of ValidityDomain
        Physical validity domains (basis ``physical``); the domains stated
        by sources belong to their citations.
    citations : tuple of Citation
        The sources that give the formulation, and what each states.
    note : str or None
        Remark.
    matches : tuple of ExternalMatch
        Links to external vocabularies (Wikidata item of the formula...).
    derivation : Derivation or None
        For a formulation derived from another one (see
        :mod:`nomogram.inversion`), how it was derived.
    family : str or None
        Name of the catalog family it belongs to, set when the catalog is
        loaded (the file it comes from).
    keywords : tuple of str
        Keywords for discovery and search; several per formulation,
        unlike the family.
    parts : tuple of Part
        For a composed formulation, its parts: the inner formulations,
        then the outer one. Their validity domains apply to the values
        each part receives (see :meth:`outside_mask`).
    branches : tuple of Branch
        For a formulation defined by pieces taken from other formulations,
        those formulations, each with its condition; the expression is
        the piecewise definition they make. The validity domains of each
        apply where its condition holds.
    calls : tuple of Call
        For a formulation whose expression calls others, every call, in
        order of appearance (two identical calls are both kept; they make
        one part). ``expression`` is then the expression with each call
        developed: the coefficients of each formulation called under an
        identifier qualified by the formulation that defines them, a
        constant under its identifier, or qualified by its key when
        another constant has that identifier. ``written`` keeps the
        expression as written.
    written : str or None
        The expression as written, with its calls; ``None`` without calls.
    nature : FormulationNature or None
        For a definition or an identity, which; ``None`` for a formula a
        source gives (a fit, a model).
    conditions : str or None
        Conditions under which it holds, as stated (the same temperature
        and pressure).
    noted_assumptions : tuple of Assumption
        Assumptions its sources do not state, noted with their status
        (stated by another source, deduced, suspected); see
        :attr:`assumptions`.
    """

    key: str
    label: str
    output: Variable
    inputs: tuple[Variable, ...]
    coefficients: tuple[Coefficient, ...]
    constants: tuple[PhysicalConstant, ...]
    expression: str
    fixed_units: bool
    physical_domains: tuple[ValidityDomain, ...]
    citations: tuple[Citation, ...]
    note: str | None
    matches: tuple[ExternalMatch, ...]
    derivation: Derivation | None = None
    family: str | None = None
    keywords: tuple[str, ...] = ()
    parts: tuple[Part, ...] = ()
    branches: tuple[Branch, ...] = ()
    calls: tuple[Call, ...] = ()
    written: str | None = None
    nature: FormulationNature | None = None
    conditions: str | None = None
    noted_assumptions: tuple[Assumption, ...] = ()

    @property
    def references(self) -> tuple[str, ...]:
        """Keys of the cited sources, in order, without repetition."""
        return tuple(dict.fromkeys(c.reference for c in self.citations))

    @property
    def assumptions(self) -> tuple[Assumption, ...]:
        """Its assumptions: those its sources state, those noted, then those of its parts.

        A composition, a formulation by branches or one calling others
        holds under the assumptions of what it is built from, at any depth;
        each assumption is given once.
        """
        found = [
            Assumption(text, AssumptionStatus.STATED, c.reference)
            for c in self.citations
            for text in c.assumptions
        ]
        found += self.noted_assumptions
        for part in self.parts:
            found += part.formulation.assumptions
        for branch in self.branches:
            found += branch.formulation.assumptions
        return tuple(dict.fromkeys(found))

    @property
    def derived(self) -> bool:
        """Whether nomogram derived it from others, no source printing it.

        A composition, a formulation by branches or one calling others,
        without a citation of its own, or an inversion: its provenance is
        its :attr:`derivation`, never a citation.
        """
        return self.derivation is not None and not self.citations

    @property
    def domains(self) -> tuple[ValidityDomain, ...]:
        """All validity domains: physical ones, then those of each citation."""
        return self.physical_domains + tuple(
            d for c in self.citations for d in c.domains
        )

    @property
    def names(self) -> tuple[str, ...]:
        """Identifiers of the numeric function's arguments, in order."""
        return (
            tuple(v.identifier for v in self.inputs)
            + tuple(c.identifier for c in self.coefficients)
            + tuple(k.identifier for k in self.constants)
        )

    @property
    def _source_limit(self) -> int | None:
        """Bound on the length of the expression, for every parse of it.

        The length of a written expression is bounded; that of one derived
        by nomogram (a composition, branches, calls) is bounded by its parts.
        """
        return MAX_SOURCE_LENGTH if self.derivation is None else None

    @cached_property
    def implicit(self) -> bool:
        """Whether the expression is an implicit equation, ``left == right``.

        The output is then the unknown the source solves for, which may
        appear in both members or not be isolable (VIM 2.48, note 1: the
        measurement model h(Y, X1, ..., Xn) = 0); :meth:`evaluate` finds
        its root. See :attr:`equation_members`.
        """
        try:
            return _split_equation(self.expression, self._source_limit) is not None
        except ExpressionError:
            return True  # an equation written wrong: equation_members says why

    @cached_property
    def equation_members(self) -> tuple[Any, Any]:
        """The two members of an implicit equation, as SymPy expressions.

        The output's identifier is among their symbols.

        Raises
        ------
        ExpressionError
            If the formulation is explicit, or a member is not valid.
        """
        found = _split_equation(self.expression, self._source_limit)
        if found is None:
            msg = f"{self.key}: an explicit formulation has no equation members"
            raise ExpressionError(msg)
        names = (*self.names, self.output.identifier)
        left, right = (
            parse_expression(member, names, limit=self._source_limit)
            for member in found
        )
        return left, right

    @cached_property
    def sympy_expression(self) -> Any:
        """The expression as a SymPy expression.

        Raises
        ------
        ExpressionError
            For an implicit equation, which has no explicit expression of
            its output (see :attr:`equation_members`).
        """
        if self.implicit:
            msg = (
                f"{self.key}: an implicit equation has no explicit expression "
                "of its output; see equation_members"
            )
            raise ExpressionError(msg)
        return parse_expression(self.expression, self.names, limit=self._source_limit)

    @cached_property
    def _members_functions(self) -> tuple[Callable[..., Any], Callable[..., Any]]:
        """The two members as numeric functions of the output, then of :attr:`names`."""
        names = (self.output.identifier, *self.names)
        left, right = self.equation_members
        return compile_numeric(left, names), compile_numeric(right, names)

    @cached_property
    def _member_factor(self) -> float:
        """Factor bringing the right member into the unit of the left one.

        1 for a fixed-units formulation, and where a member is 0 (h == 0),
        which has every dimension. For a quantity equation, each member is
        evaluated with pint quantities, once per branch of its piecewise
        definitions (see :attr:`output_factor`): the branches of a member
        give one unit, both members have the same dimension, and no sum
        adds terms in two units.

        Raises
        ------
        pint.errors.DimensionalityError
            If the two members do not have the same dimension.
        DimensionError
            If the branches of a member give values in different units, or
            a sum adds terms in two units of one dimension.
        """
        if self.fixed_units:
            return 1.0
        from nomogram.dimensions import DimensionError

        unit_of = self._unit_of()
        units = []
        for member in self.equation_members:
            if member == 0:
                continue
            variants = _variants(member)
            found = [unit_of(variant) for variant in variants]
            if any(not _same_unit(unit, found[0]) for unit in found[1:]):
                msg = (
                    f"{self.key}: the branches of a piecewise definition in a "
                    "member give values in different units"
                )
                raise DimensionError(msg)
            if self._mixed_units:
                for variant in variants:
                    _check_sums(self.key, variant, unit_of)
            units.append(found[0])
        if len(units) < 2:
            return 1.0
        return float(Q_(1.0, units[1]).to(units[0]).magnitude)

    def _unit_of(self) -> Callable[[Any], Any]:
        """The unit of an expression of :attr:`names`, from probe values.

        An implicit equation takes a probe of its output too. A probe may
        leave the real domain of the expression (the square root of
        1 - 16 zeta): the value is NaN, the unit holds.
        """
        names, values = self._probe_values

        def unit_of(expr: Any) -> Any:
            with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
                return Q_(compile_numeric(expr, names)(*values)).units

        return unit_of

    @cached_property
    def _probe_values(self) -> tuple[tuple[str, ...], list[Any]]:
        """The names a unit is computed from, and their probe values."""
        values = self._probes()
        names: tuple[str, ...] = self.names
        if self.implicit:
            names = (*names, self.output.identifier)
            unit = semantic_catalog().units[self.output.unit].pint
            values.append(Q_(1.05 ** (len(values) + 1), unit))
        return names, values

    @cached_property
    def _mixed_units(self) -> bool:
        """Whether a sum could add terms in two units of one dimension.

        Not where every unit of its names is coherent, of factor 1 and
        without offset: every product of them is then coherent too, and
        the terms of a sum share their unit.
        """
        _, values = self._probe_values
        return not all(_coherent(q.units) for q in values)

    def _probes(self) -> list[Any]:
        """Distinct values of the inputs, coefficients and constants, with units.

        Only the unit of a result computed from them matters. They grow
        slowly: a composition has dozens of names, and powers of them
        overflow.
        """
        units = semantic_catalog().units
        probe = iter(1.05 ** (i + 1) for i in range(len(self.names)))
        values: list[Any] = [Q_(next(probe), units[v.unit].pint) for v in self.inputs]
        # A coefficient is a pure number unless declared otherwise.
        values += [
            Q_(next(probe), units[c.unit].pint if c.unit else "dimensionless")
            for c in self.coefficients
        ]
        values += [Q_(next(probe), units[k.unit].pint) for k in self.constants]
        return values

    def _search_interval(
        self, search: tuple[float, float] | None
    ) -> tuple[float, float]:
        """Where the root of an implicit equation is sought, in the output's unit.

        Its physical domains on the output and the bounds of its kind,
        narrowed by ``search``; domains stated by sources apply to the
        root found, as to any result.
        """
        low, high = -math.inf, math.inf
        output = self.output.identifier
        for domain in self.physical_domains:
            if output in domain.bounds:
                low = max(low, domain.bounds[output][0])
                high = min(high, domain.bounds[output][1])
        bounds = _kind_bounds_on_scale(self.output)
        if bounds is not None:
            low, high = max(low, bounds[0]), min(high, bounds[1])
        if search is not None:
            low, high = max(low, float(search[0])), min(high, float(search[1]))
        return low, high

    def _solve(
        self,
        values: Mapping[str, Any],
        search: tuple[float, float] | None,
        skip: Any = None,
    ) -> Any:
        """The root of an implicit equation for each set of inputs, NaN without one.

        Neither sought nor reported where an input is NaN, or where
        ``skip`` holds (inputs outside a domain, their result NaN anyway).
        """
        from nomogram._roots import NONE, SEVERAL, UNDETERMINED, solve

        low, high = self._search_interval(search)
        left, right = self._members_functions
        fixed = [c.value for c in self.coefficients]
        fixed += [k.value for k in self.constants]
        factor = self._member_factor

        def members(y: Any, *inputs: Any) -> tuple[Any, Any]:
            return left(y, *inputs, *fixed), factor * right(y, *inputs, *fixed)

        arrays = [np.asarray(values[v.identifier], dtype=float) for v in self.inputs]
        shape = np.broadcast_shapes(*(a.shape for a in arrays)) if arrays else ()
        flat = [np.broadcast_to(a, shape).reshape(-1) for a in arrays]
        sought = np.ones(math.prod(shape), dtype=bool)
        for array in flat:
            sought &= ~np.isnan(array)
        if skip is not None:
            sought &= ~np.broadcast_to(np.asarray(skip, dtype=bool), shape).reshape(-1)
        flat_roots = np.full(sought.shape, np.nan)
        flat_status = np.full(sought.shape, -1)  # not sought
        if sought.any() and low <= high:
            got, codes = solve(members, [a[sought] for a in flat], low, high)
            flat_roots[sought], flat_status[sought] = got, codes
        elif sought.any():
            flat_status[sought] = NONE
        roots, status = flat_roots.reshape(shape), flat_status.reshape(shape)
        reasons = (
            (NONE, "no root in the interval searched"),
            (SEVERAL, "several roots: narrow the interval (a domain, or search=)"),
            (UNDETERMINED, "a residual undefined inside the bracket of a root"),
        )
        found = [
            f"{int(np.sum(status == code))} with {text}"
            for code, text in reasons
            if np.any(status == code)
        ]
        if found:
            message = f"{self.key}: NaN for " + "; ".join(found)
            warnings.warn(message, RootWarning, stacklevel=4)
        return roots

    @cached_property
    def written_expression(self) -> Any:
        """The expression as written, each call of a formulation kept opaque.

        The same as :attr:`sympy_expression` for a formulation without
        calls; with calls, an opaque function per call (``e_w(p, t_d)``),
        its arguments in the order of the called formulation's inputs.
        """
        if not self.calls or self.written is None:
            return self.sympy_expression
        return _opaque_calls(
            self.written,
            self.names,
            [
                (c.alias, [c.arguments[v.identifier] for v in c.formulation.inputs])
                for c in self.calls
            ],
        )

    @cached_property
    def _function(self) -> Callable[..., Any]:
        return compile_numeric(self.sympy_expression, self.names)

    @cached_property
    def output_factor(self) -> float:
        """Factor bringing the raw result into the output unit.

        1 for a fixed-units formulation. For a quantity equation, the
        expression is evaluated once with pint quantities, which checks
        its dimensional homogeneity; a piecewise definition is evaluated
        once per branch (pint quantities do not go through numpy's choice
        of branch), and both sides of each comparison of its conditions
        must be in the same unit, since the comparison is made on the
        numbers.

        Raises
        ------
        pint.errors.DimensionalityError
            If the expression does not have the dimension of the output, or
            a comparison joins two dimensions.
        DimensionError
            If the branches of a piecewise definition give values in
            different units, a comparison joins two units of one dimension
            (a bound in Pa for an input in hPa), or a sum adds terms in two
            units of one dimension: the numeric function adds the numbers,
            and 1500 Pa + 15 hPa would give 1515 Pa.
        """
        if self.fixed_units:
            return 1.0
        from nomogram.dimensions import DimensionError

        units = semantic_catalog().units
        # Distinct probe values, so that no difference such as p - e
        # vanishes; only the unit of the result matters (see _probes).
        unit_of = self._unit_of()
        if self.implicit:
            # Both members of one dimension, each comparison of a condition
            # in one unit; the unknown is in the output's unit.
            left, right = self.equation_members
            for relation in [*_relations(left), *_relations(right)]:
                lhs, rhs = unit_of(relation.lhs), unit_of(relation.rhs)
                if Q_(1.0, lhs).to(rhs).magnitude != 1.0:
                    msg = (
                        f"{self.key}: {relation} compares {lhs:~P} with {rhs:~P}: "
                        "write a bound in the unit of its input"
                    )
                    raise DimensionError(msg)
            _ = self._member_factor
            return 1.0
        for relation in _relations(self.sympy_expression):
            left, right = unit_of(relation.lhs), unit_of(relation.rhs)
            if Q_(1.0, left).to(right).magnitude != 1.0:
                msg = (
                    f"{self.key}: {relation} compares {left:~P} with {right:~P}: "
                    "write a bound in the unit of its input"
                )
                raise DimensionError(msg)
        target = units[self.output.unit].pint
        variants = _variants(self.sympy_expression)
        factors = {
            float(Q_(1.0, unit_of(variant)).to(target).magnitude)
            for variant in variants
        }
        if len(factors) > 1:
            msg = (
                f"{self.key}: the branches of its piecewise definition give "
                "values in different units"
            )
            raise DimensionError(msg)
        if self._mixed_units:
            for variant in variants:
                _check_sums(self.key, variant, unit_of)
        return factors.pop()

    def latex(self, notation: Notation | None = None, **options: Any) -> str:
        """The formulation as a LaTeX equation, in a given notation.

        The typography follows the display options in force
        (:mod:`nomogram.display`), which ``options`` may override, for
        example ``mul_symbol="dot"``.
        """
        return self.render(notation, **options).latex

    def render(self, notation: Notation | None = None, **options: Any) -> Rendering:
        """The formulation displayed: see :func:`nomogram.display.render`."""
        from nomogram.display import render

        return render(self, notation, **options)

    def _repr_latex_(self) -> str:
        """The equation, for notebooks."""
        return f"$${self.latex()}$$"

    @cached_property
    def coefficient_units(self) -> Mapping[str, CoefficientUnit]:
        """The unit of each coefficient, declared or inferred.

        See :func:`nomogram.dimensions.infer_units`.
        """
        from nomogram.dimensions import infer_units

        return infer_units(self)

    def outside_mask(self, values: Mapping[str, Any], basis: Basis = "stated") -> Any:
        """Where values fall outside the selected validity domains.

        Parameters
        ----------
        values : mapping of str to array_like
            Input values, by identifier, in the inputs' units; and the
            output's, by its identifier and in its unit, for the domains that
            bound it (left aside when it is not given).
        basis : {"stated", "physical", "all"}
            Which domains apply.

        Returns
        -------
        numpy.ndarray of bool
            ``True`` where a value lies outside a selected domain.

        Raises
        ------
        ValueError
            If ``basis`` is not one of its values.

        Notes
        -----
        Physical domains all apply. Domains stated by sources combine by
        union between citations (inside if one source says so), and apply
        together within a citation. Bounds on the output are taken apart
        from those on the inputs: the union runs on the inputs over the
        citations that bound them, and on the output over the citations
        that bound it, and a value is outside if either is. A citation that
        only bounds the output thus never widens the inputs another states.

        The bounds the kind of each variable admits by definition
        (:attr:`Variable.kind_bounds`: no negative vapour pressure, no
        temperature below 0 K) apply whatever ``basis``.

        Bounds are closed and tolerate a relative rounding of
        :data:`BOUND_TOLERANCE` of their finite ends, so that a value
        converted between units (0.01 degC is 273.15999999... K) is not
        rejected at a bound; an infinite end bounds nothing.

        A composed formulation is never more permissive than the chain of
        its parts: the domains of each part apply to the values it
        receives and to the value it gives, intermediate values included,
        unless a source of the composed formulation states its own domain
        on its inputs, which then replaces the domains the sources of the
        parts state. Physical domains of the parts always apply. In a
        formulation defined by branches, the domains of each branch apply
        where its condition holds, under the same rule.
        """
        _check_options("nan", basis, "convert")
        return self._outside(values, basis)

    def _outside(self, values: Mapping[str, Any], basis: Basis | None) -> Any:
        """:meth:`outside_mask`; with ``basis=None``, the bounds of kinds only.

        The bounds of the kinds of the parts and branches always apply,
        even where a domain stated for the composition replaces their
        domains.
        """
        arrays = {k: np.asarray(v, dtype=float) for k, v in values.items()}
        shape = np.broadcast_shapes(*(a.shape for a in arrays.values()))
        output = self.output.identifier

        def bounds_of(domain: ValidityDomain, of_output: bool) -> Any:
            return [
                (identifier, low, high)
                for identifier, (low, high) in domain.bounds.items()
                if (identifier == output) == of_output
            ]

        def outside_all(domains: tuple[ValidityDomain, ...], of_output: bool) -> Any:
            result = np.zeros(shape, dtype=bool)
            for domain in domains:
                for identifier, low, high in bounds_of(domain, of_output):
                    if identifier not in arrays:
                        continue  # the output, not given
                    result = result | _beyond(arrays[identifier], low, high)
            return result

        def outside_union(of_output: bool) -> Any:
            # Union between citations: inside if one source says so.
            stating = [
                c.domains
                for c in self.citations
                if any(bounds_of(d, of_output) for d in c.domains)
            ]
            if not stating:
                return np.zeros(shape, dtype=bool)
            inside = np.zeros(shape, dtype=bool)
            for domains in stating:
                inside |= ~outside_all(domains, of_output)
            return ~inside

        outside = self._beyond_kinds(arrays, shape)
        if basis in ("physical", "all"):
            outside |= outside_all(self.physical_domains, of_output=False)
            outside |= outside_all(self.physical_domains, of_output=True)
        if basis in ("stated", "all"):
            outside |= outside_union(of_output=False)
            outside |= outside_union(of_output=True)
        if self.parts or self.branches:
            part_basis: Basis | None = basis
            # A domain stated for a composition on its inputs replaces those
            # of its parts; the domains of called formulations always apply
            # to each call. The bounds of the kinds of the parts always do.
            stated = any(
                bounds_of(d, of_output=False) for c in self.citations for d in c.domains
            )
            if basis not in (None, "physical") and stated and not self.calls:
                part_basis = "physical" if basis == "all" else None
            if self.parts:
                outside = outside | self._parts_outside(arrays, part_basis)
            if self.branches:
                outside = outside | self._branches_outside(arrays, part_basis, shape)
        return outside

    def _beyond_kinds(self, values: Mapping[str, Any], shape: tuple[int, ...]) -> Any:
        """Where a value of a variable lies beyond the bounds of its kind.

        A value on a conventional scale other than the reference one is
        carried to the reference scale first (a Knudsen salinity in per
        mille, a temperature on IPTS-68, a Practical Salinity, which is a
        number); where it cannot be, beyond the conversion, it is compared
        as it is, which bounds that hold on every scale (0 K) do rightly.
        """
        units = semantic_catalog().units
        result = np.zeros(shape, dtype=bool)
        for variable in (*self.inputs, self.output):
            bounds = variable.kind_bounds
            if bounds is None or variable.identifier not in values:
                continue
            value = np.asarray(values[variable.identifier], dtype=float)
            raw = _converted_bounds(bounds.low, bounds.high, bounds.unit, variable.unit)
            scale = variable.scale
            if scale is None or scale.is_reference or not scale.convertible:
                result = result | _beyond(value, *raw)
                continue
            table = variable.unit if scale.unit is None else str(scale.unit)
            on_scale = convert(Q_(value, units[variable.unit].pint), units[table].pint)
            with np.errstate(invalid="ignore"):
                carried = np.asarray(
                    scale.to_reference(np.asarray(on_scale.magnitude, dtype=float)),
                    dtype=float,
                )
            reference = _converted_bounds(bounds.low, bounds.high, bounds.unit, table)
            unconverted = np.isnan(carried) & ~np.isnan(value)
            result = (
                result
                | _beyond(carried, *reference)
                | (unconverted & _beyond(value, *raw))
            )
        return result

    def _branches_outside(
        self, values: Mapping[str, Any], basis: Basis | None, shape: tuple[int, ...]
    ) -> Any:
        """Where the branch whose condition holds is outside its domains."""
        arguments: list[Any] = [values[v.identifier] for v in self.inputs]
        arguments += [c.value for c in self.coefficients]
        arguments += [k.value for k in self.constants]
        outside = np.zeros(shape, dtype=bool)
        for branch, (_, condition) in zip(
            self.branches, self.sympy_expression.args, strict=True
        ):
            with np.errstate(invalid="ignore"):
                active = compile_numeric(condition, self.names)(*arguments)
            own = {
                v.identifier: values[v.identifier] for v in branch.formulation.inputs
            }
            own[branch.formulation.output.identifier] = branch.formulation._raw(own)
            mask = branch.formulation._outside(own, basis)
            outside |= np.broadcast_to(np.asarray(active, dtype=bool), shape) & mask
        return outside

    def _parts_outside(self, values: Mapping[str, Any], basis: Basis | None) -> Any:
        """Where a part receives, or gives, a value outside its domains."""
        computed: dict[str, Any] = {}
        outside: Any = False
        for part in self.parts:
            formulation = part.formulation
            if part.computes is None:
                arguments = {
                    v.identifier: computed.get(v.identifier, values.get(v.identifier))
                    for v in formulation.inputs
                }
                result = formulation._raw(arguments)
            else:
                arguments = {
                    v.identifier: (
                        self._argument(part.arguments[v.identifier], values)
                        if v.identifier in part.arguments
                        else values[part.rename.get(v.identifier, v.identifier)]
                    )
                    for v in formulation.inputs
                }
                result = computed[part.computes] = formulation._raw(arguments)
            given = {**arguments, formulation.output.identifier: result}
            outside = outside | formulation._outside(given, basis)
        return outside

    @cached_property
    def _argument_functions(self) -> Mapping[str, Callable[..., Any]]:
        """The numeric function of each expression passed to a call."""
        texts = {text for part in self.parts for text in part.arguments.values()}
        return MappingProxyType(
            {
                text: compile_numeric(parse_expression(text, self.names), self.names)
                for text in texts
            }
        )

    def _argument(self, text: str, values: Mapping[str, Any]) -> Any:
        """The value of an expression passed to a call, from the inputs."""
        arguments: list[Any] = [values[v.identifier] for v in self.inputs]
        arguments += [c.value for c in self.coefficients]
        arguments += [k.value for k in self.constants]
        return np.asarray(self._argument_functions[text](*arguments), dtype=float)

    def _outside_message(
        self, mask: Any, given: Mapping[str, Any], basis: Basis
    ) -> str:
        """How many values lie outside the domains, and beyond the kinds' bounds."""
        message = f"{self.key}: {int(mask.sum())} value(s) outside its {basis} domain"
        of_kinds = np.broadcast_to(self._outside(given, None), mask.shape)
        if of_kinds.any():
            message += (
                f", {int(of_kinds.sum())} beyond the bounds of the kinds of "
                "its variables or of its parts"
            )
        return message

    def _raw(
        self,
        values: Mapping[str, Any],
        search: tuple[float, float] | None = None,
        skip: Any = None,
    ) -> Any:
        """The result in the output unit, inputs in their units and scales.

        For an implicit equation, its root, not sought where ``skip`` holds
        (see :meth:`_solve` and :meth:`evaluate`).
        """
        if self.implicit:
            return self._solve(values, search, skip)
        arguments: list[Any] = [values[v.identifier] for v in self.inputs]
        arguments += [c.value for c in self.coefficients]
        arguments += [k.value for k in self.constants]
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            result = np.asarray(self._function(*arguments), dtype=float)
        return result * self.output_factor

    def evaluate(
        self,
        *,
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        search: tuple[float, float] | None = None,
        **inputs: Any,
    ) -> Any:
        """Evaluate the formulation on pint quantities.

        Inputs are converted to the unit and scale of each input variable,
        then the numeric function runs, vectorised with numpy. An implicit
        equation is solved for its output: the root is sought where its
        physical domains on the output and the bounds of the output's kind
        allow, narrowed by ``search``; its stated domains then apply to
        the root as to any result. Without exactly one root, the value is
        NaN and a :class:`RootWarning` says why.

        Parameters
        ----------
        outside : {"nan", "warn", "raise", "ignore"}
            Behaviour outside the validity domains: NaN there (default),
            compute and warn, raise, or compute silently (comparisons).
            A value beyond the conversion table or the bounds of a scale
            conversion has no value on the other scale: it is NaN whatever
            the option, and ``"warn"`` and ``"raise"`` report it too.
        basis : {"stated", "physical", "all"}
            Which domains apply (default: those stated by the sources).
        scale : {"convert", "ignore"}
            Inputs are taken on the reference scale of their kind (ITS-90
            for temperatures, Reference Salinity for salinities). With
            ``"convert"`` (default) they are converted to the conventional
            scale the formulation was fitted on, when it is known (NaN
            beyond the conversion table or the bounds of the conversion),
            and the result converted to the reference scale of its kind;
            ``"ignore"`` uses them as they are.
        search : (float, float), optional
            For an implicit equation, the interval of the output searched,
            ``low < high``, in its unit and on its scale: it narrows the
            interval its physical domains and the bounds of its kind allow,
            or widens the sweep of an open end (beyond 10^12 times its
            scale). Not a validity domain; refused for an explicit
            formulation. Where its inputs lie outside the domains selected,
            the root is not sought with ``outside="nan"`` (the value is NaN
            anyway), and ``outside="raise"`` raises before any search.
        **inputs : pint.Quantity
            One quantity per input variable, by identifier.

        Returns
        -------
        pint.Quantity
            The result, in the output unit.

        Raises
        ------
        TypeError
            If an input is missing or unexpected, or ``search`` is given
            for an explicit formulation.
        ValueError
            If ``outside``, ``basis`` or ``scale`` is not one of its values,
            or ``search`` is not two numbers, ``low < high``.
        OutOfDomainError
            With ``outside="raise"``, if a value is outside a domain, or
            beyond a scale conversion.
        ScaleConversionError
            With ``scale="convert"``, if an input or the output is on a
            scale nomogram cannot convert (Absolute Salinity); with
            ``scale="ignore"``, if an input is not written as its scale
            writes it: with a unit on a scale of numbers (Practical
            Salinity), bare on a scale in per mille (Knudsen salinity).
        """
        _check_options(outside, basis, scale)
        if search is not None:
            if not self.implicit:
                msg = f"{self.key}: search= applies to an implicit equation only"
                raise TypeError(msg)
            search = _check_search(self.key, search)
        expected = {v.identifier for v in self.inputs}
        if set(inputs) != expected:
            missing = ", ".join(sorted(expected - set(inputs))) or "none"
            extra = ", ".join(sorted(set(inputs) - expected)) or "none"
            msg = f"{self.key}: missing inputs: {missing}; unexpected: {extra}"
            raise TypeError(msg)
        if scale == "ignore":
            for v in self.inputs:
                _check_given(self.key, v, inputs[v.identifier])
        units = semantic_catalog().units
        values = {
            v.identifier: np.asarray(
                convert(inputs[v.identifier], units[v.unit].pint).magnitude,
                dtype=float,
            )
            for v in self.inputs
        }
        if scale == "convert":
            beyond = []
            for v in self.inputs:
                if v.scale is None or v.scale.is_reference:
                    continue
                v.scale.check_convertible()
                table = units[str(v.scale.unit)].pint
                on_reference = convert(inputs[v.identifier], table).magnitude
                on_scale, failed = v.scale.from_reference(on_reference)
                beyond.append((v.identifier, v.scale, failed))
                values[v.identifier] = np.asarray(
                    convert(Q_(on_scale, table), units[v.unit].pint).magnitude,
                    dtype=float,
                )
            _flag_beyond(self.key, beyond, outside)
        skip = None
        if self.implicit and outside in ("nan", "raise"):
            # The inputs first: no root sought where the value is NaN anyway,
            # nor before an error.
            skip = self.outside_mask(values, basis)
            if outside == "raise" and skip.any():
                raise OutOfDomainError(self._outside_message(skip, values, basis))
        result = self._raw(values, search, skip)
        # The output's domains apply on the formulation's scale, before the
        # result goes back to the reference scale.
        given = {**values, self.output.identifier: result}
        mask = self.outside_mask(given, basis)
        if mask.any() and outside != "ignore":
            message = self._outside_message(mask, given, basis)
            if outside == "raise":
                raise OutOfDomainError(message)
            if outside == "warn":
                warnings.warn(message, ValidityWarning, stacklevel=2)
            else:
                result = np.where(mask, np.nan, result)
        output_unit = units[self.output.unit].pint
        output_scale = self.output.scale
        if (
            scale == "convert"
            and output_scale is not None
            and not output_scale.is_reference
        ):
            # A value computed on the formulation's scale goes back to the
            # reference scale, that of inputs and results.
            output_scale.check_convertible()
            table = units[str(output_scale.unit)].pint
            on_scale = convert(Q_(result, output_unit), table).magnitude
            converted = output_scale.to_reference(on_scale)
            failed = np.isnan(converted) & ~np.isnan(on_scale)
            _flag_beyond(
                self.key, [(self.output.identifier, output_scale, failed)], outside
            )
            result = np.asarray(
                convert(Q_(converted, table), output_unit).magnitude, dtype=float
            )
        magnitude = result.item() if result.ndim == 0 else result
        return Q_(magnitude, output_unit)


def _origin(formulation: Formulation, identifier: str) -> tuple[str, str]:
    """Where a coefficient or a constant of a formulation comes from.

    The key of the formulation that defines a coefficient, through
    compositions and branches, which keep its identifier, and through
    calls, which rename it; or the key of a constant. Then the identifier
    it is written with there.
    """
    if formulation.calls:
        for part in formulation.parts:
            inner = part.formulation
            held = {c.identifier for c in inner.coefficients}
            held |= {c.identifier for c in inner.constants}
            for name, renamed in part.rename.items():
                if renamed == identifier and name in held:
                    return _origin(inner, name)
    else:
        used = [p.formulation for p in formulation.parts]
        used += [b.formulation for b in formulation.branches]
        for inner in used:
            if any(c.identifier == identifier for c in inner.coefficients):
                return _origin(inner, identifier)
    constant = next(
        (c for c in formulation.constants if c.identifier == identifier), None
    )
    return (formulation.key if constant is None else constant.key), identifier
