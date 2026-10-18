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

import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from functools import cached_property
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from nomogram.expression import compile_numeric, parse_expression
from nomogram.semantics import ExternalMatch, semantic_catalog
from nomogram.units import Q_, convert

if TYPE_CHECKING:
    from nomogram.dimensions import CoefficientUnit
    from nomogram.display import Rendering

__all__ = [
    "Citation",
    "Coefficient",
    "ConventionalScale",
    "Derivation",
    "DomainBasis",
    "Formulation",
    "Notation",
    "OutOfDomainError",
    "PhysicalConstant",
    "Reference",
    "ReferenceStatus",
    "Relation",
    "RelationKind",
    "ScaleBasis",
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
        Address, when there is no DOI.
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
    temperatures on the scale in force at the time (IPTS-68, ITS-48...).
    Each quantity kind has one reference scale (ITS-90 for temperatures);
    inputs are taken on it and converted to the scale of the formulation
    before evaluation, and results converted back.

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
        QUDT name of the unit of the conversion table.
    points : tuple of float
        Values on the reference scale where the difference is tabulated;
        empty for a reference scale.
    difference : tuple of float
        Value on the reference scale minus value on this scale, at those
        points.
    reference : str or None
        Key of the source of the scale or of its table.
    """

    key: str
    label: str
    kinds: tuple[str, ...]
    reference_scale: str | None
    unit: str | None
    points: tuple[float, ...]
    difference: tuple[float, ...]
    reference: str | None

    @property
    def is_reference(self) -> bool:
        """Whether this is the reference scale of its kinds."""
        return self.reference_scale is None

    def from_reference(self, values: Any) -> tuple[Any, Any]:
        """Values on this scale, from values on the reference scale.

        Parameters
        ----------
        values : array_like
            Values on the reference scale, in the unit of the table.

        Returns
        -------
        (numpy.ndarray, numpy.ndarray of bool)
            The values on this scale (linear interpolation of the table),
            and where they fall outside the table (NaN there).
        """
        values = np.asarray(values, dtype=float)
        if not self.points:
            return values, np.zeros(values.shape, dtype=bool)
        outside = (values < self.points[0]) | (values > self.points[-1])
        shift = np.interp(values, self.points, self.difference)
        return np.where(outside, np.nan, values - shift), outside

    def to_reference(self, values: Any) -> Any:
        """Values on the reference scale, from values on this scale.

        Inverts :meth:`from_reference` by fixed-point iteration (the
        differences are small and vary slowly); NaN beyond the table.
        """
        values = np.asarray(values, dtype=float)
        if not self.points:
            return values
        on_reference = values
        for _ in range(4):
            on_reference = values + np.interp(
                on_reference, self.points, self.difference
            )
        outside = (on_reference < self.points[0]) | (on_reference > self.points[-1])
        return np.where(outside, np.nan, on_reference)


class RelationKind(Enum):
    """What a relation between two formulations states."""

    #: The subject equals the object, possibly given substitutions.
    EQUIVALENT = "equivalent"
    #: The subject approximates the object within a stated deviation.
    APPROXIMATES = "approximates"


@dataclass(frozen=True)
class Relation:
    """A relation between two formulations, as a source states it.

    A relation is a claim, cited: nomogram verifies it
    (:func:`nomogram.relations.verify`) but never invents one. Deviations
    nomogram computes are observations (:func:`nomogram.comparison.compare`).

    Attributes
    ----------
    key : str
        Catalog key.
    kind : RelationKind
        Equivalence or approximation.
    subject, object : str
        Keys of the two formulations.
    citation : str
        Key of the source that states the relation.
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
        For an equivalence, inputs of the object expressed with those of
        the subject (``{"P_d": "P - e"}``).
    scale : {"convert", "ignore"}
        How the formulations are evaluated for the claim: with conversion
        of temperature scales, or as given, each on its own scale.
    note : str or None
        Remark.
    """

    key: str
    kind: RelationKind
    subject: str
    object: str
    citation: str
    accuracy: float | None = None
    at: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    bounds: Mapping[str, tuple[float, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    given: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    scale: ScaleConversion = "convert"
    note: str | None = None


@dataclass(frozen=True)
class Derivation:
    """How a formulation was derived from others.

    Attributes
    ----------
    source : str
        Key of the formulation it derives from; for a composition, the
        formulation evaluated last.
    method : str
        ``"symbolic inversion"`` (closed form found by SymPy),
        ``"numerical inversion"`` or ``"composition"``.
    solved_for : str or None
        For an inversion, identifier of the source's input that became the
        output.
    parts : mapping of str to str
        For a composition, the formulation computing each input of the
        source it replaces: input identifier to formulation key.
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
        For a temperature, the scale the formulation was fitted on;
        ``None`` when unknown or not applicable.
    scale_basis : ScaleBasis or None
        How that scale is known.
    """

    identifier: str
    kind: str
    unit: str
    description: str
    scale: ConventionalScale | None = None
    scale_basis: ScaleBasis | None = None


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
    """

    key: str
    identifier: str
    value: float
    unit: str
    description: str
    reference: str
    matches: tuple[ExternalMatch, ...]


@dataclass(frozen=True)
class ValidityDomain:
    """An objective validity domain of a formulation.

    Attributes
    ----------
    basis : DomainBasis
        Physical, or stated by the author or the cited publication.
    bounds : mapping of str to (float, float)
        Closed interval per input identifier, in the input's unit.
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
        Conventional reference scales the source states for inputs, by
        identifier.
    accuracy : str or None
        Accuracy the source claims, as stated.
    note : str or None
        Remark on this citation.
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

    @property
    def references(self) -> tuple[str, ...]:
        """Keys of the cited sources, in order, without repetition."""
        return tuple(dict.fromkeys(c.reference for c in self.citations))

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

    @cached_property
    def sympy_expression(self) -> Any:
        """The expression as a SymPy expression."""
        return parse_expression(self.expression, self.names)

    @cached_property
    def _function(self) -> Callable[..., Any]:
        return compile_numeric(self.sympy_expression, self.names)

    @cached_property
    def output_factor(self) -> float:
        """Factor bringing the raw result into the output unit.

        1 for a fixed-units formulation. For a quantity equation, the
        expression is evaluated once with pint quantities, which checks
        its dimensional homogeneity.

        Raises
        ------
        pint.errors.DimensionalityError
            If the expression does not have the dimension of the output.
        """
        if self.fixed_units:
            return 1.0
        units = semantic_catalog().units
        # Distinct probe values, so that no difference such as p - e
        # vanishes; only the unit of the result matters.
        probe = iter(1.5 ** (i + 1) for i in range(len(self.names)))
        values: list[Any] = [Q_(next(probe), units[v.unit].pint) for v in self.inputs]
        values += [next(probe) for _ in self.coefficients]
        values += [Q_(next(probe), units[k.unit].pint) for k in self.constants]
        result = Q_(self._function(*values))
        return float(Q_(1.0, result.units).to(units[self.output.unit].pint).magnitude)

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
        """Where input values fall outside the selected validity domains.

        Parameters
        ----------
        values : mapping of str to array_like
            Input values, by identifier, in the inputs' units.
        basis : {"stated", "physical", "all"}
            Which domains apply.

        Returns
        -------
        numpy.ndarray of bool
            ``True`` where a value lies outside a selected domain.

        Notes
        -----
        Physical domains all apply. Domains stated by sources combine by
        union between citations (inside if one source says so), and apply
        together within a citation.

        Bounds are closed and tolerate a relative rounding of
        :data:`BOUND_TOLERANCE`, so that a value converted between units
        (0.01 degC is 273.15999999... K) is not rejected at a bound.
        """
        arrays = {k: np.asarray(v, dtype=float) for k, v in values.items()}
        shape = np.broadcast_shapes(*(a.shape for a in arrays.values()))

        def outside_all(domains: tuple[ValidityDomain, ...]) -> Any:
            result = np.zeros(shape, dtype=bool)
            for domain in domains:
                for identifier, (low, high) in domain.bounds.items():
                    value = arrays[identifier]
                    margin = BOUND_TOLERANCE * max(abs(low), abs(high), 1.0)
                    result = result | (value < low - margin) | (value > high + margin)
            return result

        outside = np.zeros(shape, dtype=bool)
        if basis in ("physical", "all"):
            outside |= outside_all(self.physical_domains)
        if basis in ("stated", "all"):
            # Union between citations: inside if one source says so.
            stating = [c.domains for c in self.citations if c.domains]
            if stating:
                inside = np.zeros(shape, dtype=bool)
                for domains in stating:
                    inside |= ~outside_all(domains)
                outside |= ~inside
        return outside

    def evaluate(
        self,
        *,
        outside: Outside = "nan",
        basis: Basis = "stated",
        scale: ScaleConversion = "convert",
        **inputs: Any,
    ) -> Any:
        """Evaluate the formulation on pint quantities.

        Inputs are converted to the unit and scale of each input variable,
        then the numeric function runs, vectorised with numpy.

        Parameters
        ----------
        outside : {"nan", "warn", "raise", "ignore"}
            Behaviour outside the validity domains: NaN there (default),
            compute and warn, raise, or compute silently (comparisons).
        basis : {"stated", "physical", "all"}
            Which domains apply (default: those stated by the sources).
        scale : {"convert", "ignore"}
            Inputs are taken on the reference scale of their kind (ITS-90
            for temperatures). With ``"convert"`` (default) they are
            converted to the conventional scale the formulation was fitted
            on, when it is known (NaN beyond the conversion table), and
            the result converted back; ``"ignore"`` uses them as they are.
        **inputs : pint.Quantity
            One quantity per input variable, by identifier.

        Returns
        -------
        pint.Quantity
            The result, in the output unit.

        Raises
        ------
        TypeError
            If an input is missing or unexpected.
        OutOfDomainError
            With ``outside="raise"``, if a value is outside a domain.
        """
        expected = {v.identifier for v in self.inputs}
        if set(inputs) != expected:
            missing = ", ".join(sorted(expected - set(inputs))) or "none"
            extra = ", ".join(sorted(set(inputs) - expected)) or "none"
            msg = f"{self.key}: missing inputs: {missing}; unexpected: {extra}"
            raise TypeError(msg)
        units = semantic_catalog().units
        values = {
            v.identifier: np.asarray(
                convert(inputs[v.identifier], units[v.unit].pint).magnitude,
                dtype=float,
            )
            for v in self.inputs
        }
        if scale == "convert":
            for v in self.inputs:
                if v.scale is None or v.scale.is_reference or v.scale.unit is None:
                    continue
                table = units[v.scale.unit].pint
                on_reference = convert(inputs[v.identifier], table).magnitude
                on_scale, _ = v.scale.from_reference(on_reference)
                values[v.identifier] = np.asarray(
                    convert(Q_(on_scale, table), units[v.unit].pint).magnitude,
                    dtype=float,
                )
        arguments: list[Any] = [values[v.identifier] for v in self.inputs]
        arguments += [c.value for c in self.coefficients]
        arguments += [k.value for k in self.constants]
        with np.errstate(invalid="ignore", divide="ignore"):
            result = np.asarray(self._function(*arguments), dtype=float)
        result = result * self.output_factor
        mask = self.outside_mask(values, basis)
        if mask.any() and outside != "ignore":
            message = (
                f"{self.key}: {int(mask.sum())} value(s) outside its {basis} domain"
            )
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
            and output_scale.unit is not None
        ):
            # A value computed on the formulation's scale goes back to the
            # reference scale, that of inputs and results.
            table = units[output_scale.unit].pint
            on_scale = convert(Q_(result, output_unit), table).magnitude
            on_reference = Q_(output_scale.to_reference(on_scale), table)
            result = np.asarray(
                convert(on_reference, output_unit).magnitude, dtype=float
            )
        magnitude = result.item() if result.ndim == 0 else result
        return Q_(magnitude, output_unit)
