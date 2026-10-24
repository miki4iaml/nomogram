# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The formula catalog: hand-written TOML, validated when loaded.

The bundled catalog lives in ``src/nomogram/data/catalog/*.toml`` and is
read with :mod:`tomllib`. Loading checks everything a reader could get
wrong: every identifier of an expression is declared and used, units and
quantity kinds exist, each unit applies to its kind, cited references and
constants exist, domains name real inputs, and quantity equations are
dimensionally homogeneous. Unknown keys are refused, so that a typo never
goes unnoticed.

Quantity kinds come from the bundled QUDT subset
(:func:`nomogram.semantics.semantic_catalog`); the catalog may define
further kinds, each specializing a QUDT kind (see
:class:`nomogram.semantics.QuantityKind`).
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import datetime
import math
import os
import sys
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from functools import cached_property, lru_cache
from importlib.resources import files
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import pint
import sympy

from nomogram.dimensions import DimensionError
from nomogram.expression import (
    LATEX_COMMANDS,
    PIECEWISE,
    ExpressionError,
    _pieces,
    compile_numeric,
    latex_commands,
    parse_expression,
)
from nomogram.model import (
    Branch,
    CheckCase,
    Citation,
    Coefficient,
    ConstantNature,
    ConventionalScale,
    CrossCheck,
    Derivation,
    DomainBasis,
    Formulation,
    Notation,
    Part,
    PhysicalConstant,
    Reference,
    ReferenceStatus,
    Relation,
    RelationKind,
    ScaleBasis,
    ScaleConversion,
    TradeMeaning,
    TradeTerm,
    UnitBasis,
    ValidityDomain,
    Variable,
)
from nomogram.relations import (
    match_inputs,
    record,
    replay,
    report,
    signature,
    verdict,
)
from nomogram.semantics import (
    ExternalMatch,
    MatchRelation,
    QuantityKind,
    semantic_catalog,
)
from nomogram.units import Q_, ScaleType

if TYPE_CHECKING:
    from collections.abc import Callable

    from nomogram.search import Entry, Selection

__all__ = [
    "FORMAT",
    "Catalog",
    "CatalogError",
    "Family",
    "catalog",
    "check",
    "describe",
    "load_catalog",
    "stats",
]

_SECTIONS = (
    "kinds",
    "references",
    "constants",
    "notations",
    "trade_terms",
    "scales",
    "formulations",
    "relations",
    "cross_checks",
)


#: Version of the catalog format, declared by every named family.
FORMAT = 2


class CatalogError(ValueError):
    """The catalog is invalid; the message names the faulty entry."""


@dataclass(frozen=True)
class Family:
    """A family of the catalog: one TOML file, and what it requires.

    A family is pure when it holds entries, and an aggregate when it only
    requires other families. Entries belong to the family of their file;
    nothing is written in the entries themselves.

    Attributes
    ----------
    name : str
        Name of the family, for example ``"water-vapour"``.
    label : str
        Its title.
    requires : tuple of str
        Families it depends on.
    matches : tuple of ExternalMatch
        Links to external vocabularies (GCMD, PhySH, IEV, Wikidata...).
    keywords : tuple of str
        Keywords for discovery.
    contents : mapping of str to tuple of str
        Keys of the entries it defines, by section.
    """

    name: str
    label: str
    requires: tuple[str, ...]
    matches: tuple[ExternalMatch, ...]
    keywords: tuple[str, ...]
    contents: Mapping[str, tuple[str, ...]]

    @property
    def formulations(self) -> tuple[str, ...]:
        """Keys of the formulations of the family."""
        return self.contents.get("formulations", ())

    @property
    def is_aggregate(self) -> bool:
        """Whether the family holds no entry and only requires others."""
        return not any(self.contents.values())


@dataclass(frozen=True)
class Catalog:
    """Formulations and everything they refer to, read-only.

    Attributes
    ----------
    kinds : mapping of str to QuantityKind
        QUDT kinds and the kinds defined by the catalog, by name.
    formulations : mapping of str to Formulation
        By key.
    references : mapping of str to Reference
        By key.
    constants : mapping of str to PhysicalConstant
        By key.
    notations : mapping of str to Notation
        By key.
    trade_terms : mapping of str to TradeTerm
        By key.
    scales : mapping of str to ConventionalScale
        By key.
    relations : mapping of str to Relation
        Relations between formulations stated by sources, by key.
    families : mapping of str to Family
        By key.
    cross_checks : mapping of str to CrossCheck
        Values of formulations computed by other implementations, by key.
    links : mapping of str to tuple of str
        For each entry (``section.key``), the entries it refers to: kinds
        of its variables (those a composition takes from its parts
        included), cited references, notations, constants, scales,
        units (of its variables, constants and declared coefficients; of
        a constant, of a scale), the formulations a composition, a
        relation or a cross-check uses, the families a family requires.
    """

    kinds: Mapping[str, QuantityKind]
    formulations: Mapping[str, Formulation]
    references: Mapping[str, Reference]
    constants: Mapping[str, PhysicalConstant]
    notations: Mapping[str, Notation]
    trade_terms: Mapping[str, TradeTerm]
    scales: Mapping[str, ConventionalScale]
    relations: Mapping[str, Relation] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )
    families: Mapping[str, Family] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )
    cross_checks: Mapping[str, CrossCheck] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )
    links: Mapping[str, tuple[str, ...]] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )

    def formulations_of(self, kind: str) -> tuple[Formulation, ...]:
        """The alternative formulations computing a quantity kind."""
        return tuple(f for f in self.formulations.values() if f.output.kind == kind)

    @cached_property
    def _search_index(self) -> Any:
        from nomogram.search import index

        return index(self)

    def search(
        self,
        *terms: str,
        section: str | None = None,
        specializations: bool = True,
        **fields: str,
    ) -> Selection:
        """Find entries of the catalog by words, wildcards and fields.

        Parameters
        ----------
        *terms : str
            Shell-style patterns (``*``, ``?``, ``[...]``), each matched
            against the words of an entry, without case or accents; all
            must match. ``"buck*"``, ``"absolute humidity"``.
        section : str, optional
            Only entries of this section (a pattern too):
            ``"formulations"``, ``"kinds"``, ``"references"``...
        specializations : bool
            With ``kind=``, also the kinds that specialize the matched ones
            (default).
        **fields : str
            Field filters, patterns as well (:data:`nomogram.search.FIELDS`):
            ``kind``, ``unit``, ``output``, ``input``, ``variable``,
            ``symbol`` with ``notation``, ``source`` with ``equation``,
            ``family``, ``keyword``, ``key``.

        Returns
        -------
        Selection
            The entries found, in catalog order; search it again, or
            combine it with ``&``, ``|`` and ``-``.

        Raises
        ------
        TypeError
            For an unknown field.

        Examples
        --------
        >>> c = catalog()
        >>> c.search("buck*", section="formulations").refs[:2]
        ('formulations.buck1981_magnus', 'formulations.buck1981')
        >>> c.search(variable="rho*").refs
        ('formulations.mass_concentration_ideal_gas', 'formulations.itu_r_p453_vapour_pressure_from_density')
        """
        from nomogram.search import search

        return search(
            self,
            terms,
            section=section,
            specializations=specializations,
            filters=fields,
        )

    @cached_property
    def _positions(self) -> Mapping[str, int]:
        """Position of each entry (``section.key``) in catalog order."""
        records = self._search_index.records
        return MappingProxyType({r.entry.ref: i for i, r in enumerate(records)})

    def _in_order(self, selection: Selection) -> Selection:
        """The same entries, in catalog order."""
        from nomogram.search import Selection

        positions = self._positions
        entries = sorted(selection.entries, key=lambda e: positions[e.ref])
        return Selection(tuple(entries), self)

    def uses(self, entry: str | Entry) -> Selection:
        """The entries an entry refers to (see :attr:`links`), in catalog order.

        ``catalog().uses("formulations.itu_r_p453_es_water")`` gives its
        parts, its kinds and its reference.
        """
        from nomogram.search import uses

        return self._in_order(uses(self, entry))

    def used_by(self, entry: str | Entry) -> Selection:
        """The entries that refer to an entry, in catalog order.

        ``catalog().used_by("references.itu_r_p453_14")`` gives everything
        citing ITU-R P.453.
        """
        from nomogram.search import used_by

        return self._in_order(used_by(self, entry))


def _fields(
    where: str, table: Any, required: Iterable[str], optional: Iterable[str] = ()
) -> dict[str, Any]:
    if not isinstance(table, dict):
        msg = f"{where}: expected a table"
        raise CatalogError(msg)
    required, optional = tuple(required), tuple(optional)
    unknown = sorted(set(table) - set(required) - set(optional))
    if unknown:
        msg = f"{where}: unknown keys: {', '.join(unknown)}"
        raise CatalogError(msg)
    missing = sorted(set(required) - set(table))
    if missing:
        msg = f"{where}: missing keys: {', '.join(missing)}"
        raise CatalogError(msg)
    return {k: table.get(k) for k in required + optional}


def _enum(where: str, enum: Any, value: Any) -> Any:
    try:
        return enum(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum)
        msg = f"{where}: {value!r} is not one of {allowed}"
        raise CatalogError(msg) from None


def _number(where: str, value: Any) -> float:
    """A finite number of the catalog (TOML allows nan and inf)."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
    ):
        msg = f"{where}: expected a finite number, not {value!r}"
        raise CatalogError(msg)
    return float(value)


def _printed_number(where: str, value: Any) -> tuple[float, str | None]:
    """A finite number, written as a number or as decimal text.

    Text keeps the digits as printed, significant trailing zeros included
    (``"287.0500"``), which a TOML float loses whatever its notation; the
    text is returned with the number, ``None`` for a plain number.
    """
    if not isinstance(value, str):
        return _number(where, value), None
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        number = None
    if number is None or not number.is_finite() or value != value.strip():
        msg = f"{where}: expected a finite decimal number, not {value!r}"
        raise CatalogError(msg)
    return float(number), value


def _check_pieces(where: str, formulation: Formulation) -> None:
    """A piecewise definition cuts the range of one input into intervals.

    Every condition is an interval of the same input, bounded by numbers,
    coefficients or constants, and the intervals do not overlap; where none
    holds, the formulation gives NaN.
    """
    pairs = [(c.identifier, c.value) for c in formulation.coefficients]
    pairs += [(k.identifier, k.value) for k in formulation.constants]
    values = {sympy.Symbol(name, real=True): value for name, value in pairs}
    inputs = [v.identifier for v in formulation.inputs]
    for node in sympy.preorder_traversal(formulation.sympy_expression):
        if not isinstance(node, sympy.Piecewise):
            continue
        try:
            pieces = _pieces(node, inputs)
        except ExpressionError as exc:
            msg = f"{where}.expression: {exc}"
            raise CatalogError(msg) from None
        variable = pieces[0].variable
        spans = sorted(
            (
                float(p.low.xreplace(values)),
                not p.low_closed,
                float(p.high.xreplace(values)),
                p.high_closed,
            )
            for p in pieces
        )
        for low, low_open, high, high_closed in spans:
            if low > high or (low == high and (low_open or not high_closed)):
                msg = f"{where}.expression: an empty interval of {variable}"
                raise CatalogError(msg)
        for (_, _, high, high_closed), (low, low_open, _, _) in pairwise(spans):
            if high > low or (high == low and high_closed and not low_open):
                msg = f"{where}.expression: the intervals of {variable} overlap"
                raise CatalogError(msg)


def _exact(constant: PhysicalConstant) -> Any:
    """The value of a constant as an exact rational, as it is printed."""
    text = constant.printed or repr(constant.value)
    return _rational(text)


def _rational(text: str) -> Any:
    """A decimal text as an exact SymPy rational (``6.02214076e+23`` too)."""
    fraction = Fraction(Decimal(text))
    return sympy.Rational(fraction.numerator, fraction.denominator)


def _pair(where: str, value: Any, expected: str) -> tuple[float, float]:
    """Two finite numbers, as a TOML array of two."""
    if not isinstance(value, list) or len(value) != 2:
        msg = f"{where}: expected {expected}, not {value!r}"
        raise CatalogError(msg)
    first, second = (_number(f"{where}[{i}]", v) for i, v in enumerate(value))
    return first, second


def _matches(where: str, items: Any) -> tuple[ExternalMatch, ...]:
    result = []
    for i, item in enumerate(items or ()):
        f = _fields(f"{where}.matches[{i}]", item, ("target", "relation", "verified"))
        if not isinstance(f["verified"], datetime.date):
            msg = f"{where}.matches[{i}].verified: expected a date (YYYY-MM-DD)"
            raise CatalogError(msg)
        relation = _enum(f"{where}.matches[{i}].relation", MatchRelation, f["relation"])
        result.append(ExternalMatch(f["target"], relation, f["verified"]))
    return tuple(result)


def _stated_units(
    where: str,
    coefficients: tuple[Coefficient, ...],
    citations: tuple[Citation, ...],
    inherited: Mapping[str, str] | None = None,
) -> tuple[Coefficient, ...]:
    """Coefficients with the units their citations state.

    ``inherited`` gives, for a composed formulation, the part each
    coefficient comes from: a citation may restate the unit it has there,
    not contradict it.
    """
    result = []
    for coefficient in coefficients:
        stated = {
            c.units[coefficient.identifier]
            for c in citations
            if coefficient.identifier in c.units
        }
        if len(stated) > 1:
            msg = (
                f"{where}: citations state different units for {coefficient.identifier}"
            )
            raise CatalogError(msg)
        part = (inherited or {}).get(coefficient.identifier)
        if stated and coefficient.unit is not None and part is not None:
            if stated != {coefficient.unit}:
                basis = getattr(coefficient.unit_basis, "value", None)
                msg = (
                    f"{where}: states the unit {next(iter(stated))} for "
                    f"{coefficient.identifier}, but {part} gives "
                    f"{coefficient.unit} ({basis})"
                )
                raise CatalogError(msg)
        elif stated and coefficient.unit is not None:
            msg = f"{where}: the unit of {coefficient.identifier} is both added and stated"
            raise CatalogError(msg)
        if stated:
            coefficient = dataclasses.replace(
                coefficient, unit=stated.pop(), unit_basis=UnitBasis.STATED
            )
        result.append(coefficient)
    return tuple(result)


def _stated_scales(
    where: str,
    inputs: tuple[Variable, ...],
    citations: tuple[Citation, ...],
    inherited: Mapping[str, str] | None = None,
) -> tuple[Variable, ...]:
    """Variables with the conventional scales their citations state.

    ``inherited`` gives, for a composed formulation, the part each
    variable comes from: a citation may restate the scale it has there,
    not contradict it.
    """
    result = []
    for variable in inputs:
        stated = {
            c.scales[variable.identifier].key: c.scales[variable.identifier]
            for c in citations
            if variable.identifier in c.scales
        }
        if len(stated) > 1:
            msg = f"{where}: citations state different scales for {variable.identifier}"
            raise CatalogError(msg)
        part = (inherited or {}).get(variable.identifier)
        if stated and variable.scale is not None and part is not None:
            if set(stated) != {variable.scale.key}:
                basis = getattr(variable.scale_basis, "value", None)
                msg = (
                    f"{where}: states the scale {next(iter(stated))} for "
                    f"{variable.identifier}, but {part} gives "
                    f"{variable.scale.key} ({basis})"
                )
                raise CatalogError(msg)
        elif stated and variable.scale is not None:
            msg = f"{where}: the scale of {variable.identifier} is both inferred and stated"
            raise CatalogError(msg)
        if stated:
            (scale,) = stated.values()
            variable = dataclasses.replace(
                variable, scale=scale, scale_basis=ScaleBasis.STATED
            )
        result.append(variable)
    return tuple(result)


def _keywords(where: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(k, str) and k for k in value):
        msg = f"{where}: expected a list of non-empty strings"
        raise CatalogError(msg)
    return tuple(value)


def _check_symbols(where: str, symbols: Any) -> None:
    for identifier, tex in symbols.items():
        unknown = latex_commands(tex) - LATEX_COMMANDS
        if unknown:
            msg = (
                f"{where}.{identifier}: LaTeX commands outside the "
                f"subset common to MathJax, KaTeX and mathtext: "
                f"{', '.join(sorted(unknown))}"
            )
            raise CatalogError(msg)


#: What a composed formulation takes from its parts, never written.
_DERIVED = (
    "expression",
    "fixed_units",
    "inputs",
    "coefficients",
    "constants",
    "domains",
)


def _defined_in(formulation: Formulation, identifier: str) -> str:
    """Key of the formulation that defines a coefficient, through compositions."""
    used = [p.formulation for p in formulation.parts]
    used += [b.formulation for b in formulation.branches]
    for inner in used:
        if any(c.identifier == identifier for c in inner.coefficients):
            return _defined_in(inner, identifier)
    return formulation.key


def _substitute(
    outer: Formulation,
    inner: Mapping[str, Formulation],
    renames: Mapping[str, Mapping[str, str]],
    fixed: bool,
) -> str:
    """The expression of a composition: inner expressions put in the outer one.

    The substitution works on the source text (its syntax tree), so that
    the composed expression reads like the parts. In a fixed-units
    composition, a quantity equation keeps its value in its output unit
    through its factor (:attr:`~nomogram.model.Formulation.output_factor`).
    """

    def body(formulation: Formulation, rename: Mapping[str, str]) -> ast.expr:
        tree = ast.parse(formulation.expression, mode="eval").body
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                node.id = rename.get(node.id, node.id)
        if fixed and not formulation.fixed_units and formulation.output_factor != 1.0:
            tree = ast.BinOp(ast.Constant(formulation.output_factor), ast.Mult(), tree)
        return tree

    parts = {i: body(p, renames[i]) for i, p in inner.items()}

    class Substitute(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.expr:
            return parts.get(node.id, node)

    return ast.unparse(Substitute().visit(body(outer, {})))


class _Builder:
    def __init__(
        self,
        data: dict[str, dict[str, Any]],
        owners: Mapping[tuple[str, str], str | None] | None = None,
    ) -> None:
        self.data = data
        self.owners = owners or {}
        self.semantics = semantic_catalog()
        self.kinds: dict[str, QuantityKind] = dict(self.semantics.quantity_kinds)
        self.references: dict[str, Reference] = {}
        self.constants: dict[str, PhysicalConstant] = {}
        #: The definition of a constant, scaled to its unit.
        self.definitions: dict[str, Any] = {}
        self.scales: dict[str, ConventionalScale] = {}
        self.notations: dict[str, Notation] = {}

    def reference(self, where: str, key: Any) -> str:
        if key not in self.references:
            msg = f"{where}: unknown reference {key!r}"
            raise CatalogError(msg)
        return str(key)

    def optional_reference(self, where: str, key: Any) -> str | None:
        return None if key is None else self.reference(where, key)

    def unit(self, where: str, name: Any) -> str:
        if name not in self.semantics.units:
            msg = f"{where}: unknown unit {name!r}"
            raise CatalogError(msg)
        return str(name)

    def build_kinds(self) -> None:
        for name, table in self.data["kinds"].items():
            where = f"kinds.{name}"
            f = _fields(
                where,
                table,
                ("label", "specialization_of"),
                ("description", "matches", "scale_type"),
            )
            if name in self.kinds:
                msg = f"{where}: already a QUDT kind"
                raise CatalogError(msg)
            parent = self.kinds.get(f["specialization_of"])
            if parent is None:
                msg = f"{where}.specialization_of: unknown kind {f['specialization_of']!r}"
                raise CatalogError(msg)
            # A kind may be on an interval scale under a ratio-scale parent:
            # the modified refractivity M has a conventional origin.
            scale_type = parent.scale_type
            if f["scale_type"] is not None:
                scale_type = _enum(f"{where}.scale_type", ScaleType, f["scale_type"])
            self.kinds[name] = QuantityKind(
                name=name,
                origin="nomogram",
                iri=None,
                label=f["label"],
                dimension_vector=parent.dimension_vector,
                specialization_of=parent.name,
                scale_type=scale_type,
                delta=parent.delta and scale_type is ScaleType.RATIO,
                cf_standard_names=(),
                applicable_units=parent.applicable_units,
                added_units=(),
                matches=_matches(where, f["matches"]),
            )

    def build_references(self) -> None:
        for key, table in self.data["references"].items():
            where = f"references.{key}"
            f = _fields(
                where,
                table,
                ("authors", "title", "status"),
                ("year", "container", "doi", "url", "note", "matches"),
            )
            self.references[key] = Reference(
                key=key,
                authors=f["authors"],
                year=f["year"],
                title=f["title"],
                container=f["container"],
                doi=f["doi"],
                url=f["url"],
                status=_enum(f"{where}.status", ReferenceStatus, f["status"]),
                note=f["note"],
                matches=_matches(where, f["matches"]),
            )

    def build_constants(self) -> None:
        for key, table in self.data["constants"].items():
            where = f"constants.{key}"
            f = _fields(
                where,
                table,
                ("identifier", "value", "unit", "description", "reference"),
                (
                    "nature",
                    "uncertainty",
                    "conditions",
                    "definition",
                    "constants",
                    "tolerance",
                    "note",
                    "matches",
                ),
            )
            nature = None
            if f["nature"] is not None:
                nature = _enum(f"{where}.nature", ConstantNature, f["nature"])
            value, printed = _printed_number(f"{where}.value", f["value"])
            uncertainty = None
            if f["uncertainty"] is not None:
                uncertainty = _number(f"{where}.uncertainty", f["uncertainty"])
                if nature is ConstantNature.EXACT:
                    msg = f"{where}.uncertainty: an exact constant has none"
                    raise CatalogError(msg)
                if uncertainty <= 0:
                    msg = f"{where}.uncertainty: expected a positive number"
                    raise CatalogError(msg)
            for name in ("conditions", "definition", "note"):
                text = f[name]
                if text is not None and (not isinstance(text, str) or not text.strip()):
                    msg = f"{where}.{name}: expected a non-empty string"
                    raise CatalogError(msg)
            conditions = f["conditions"]
            components = f["constants"] or []
            if not isinstance(components, list) or not all(
                isinstance(c, str) for c in components
            ):
                msg = f"{where}.constants: expected a list of constant keys"
                raise CatalogError(msg)
            tolerance = None
            if f["tolerance"] is not None:
                tolerance = _number(f"{where}.tolerance", f["tolerance"])
                if tolerance <= 0:
                    msg = f"{where}.tolerance: expected a positive number"
                    raise CatalogError(msg)
                if not f["note"]:
                    msg = (
                        f"{where}.tolerance: a note must say by how much and why "
                        "the source departs from its definition"
                    )
                    raise CatalogError(msg)
            if f["definition"] is None and (components or tolerance is not None):
                name = "constants" if components else "tolerance"
                msg = f"{where}.{name}: only with a definition"
                raise CatalogError(msg)
            self.constants[key] = PhysicalConstant(
                key=key,
                identifier=f["identifier"],
                value=value,
                unit=self.unit(f"{where}.unit", f["unit"]),
                description=f["description"],
                reference=self.reference(f"{where}.reference", f["reference"]),
                matches=_matches(where, f["matches"]),
                nature=nature,
                uncertainty=uncertainty,
                conditions=conditions,
                printed=printed,
                definition=f["definition"],
                components=tuple(components),
                tolerance=tolerance,
                note=f["note"],
            )
        for key in self.constants:
            self.check_definition(key)
        self.check_definition_cycles()
        for key in self.definitions:
            self.check_value(key)

    def check_definition(self, key: str) -> None:
        """The definition of a constant, if any, uses its components and gives its unit."""
        constant = self.constants[key]
        if constant.definition is None:
            return
        where = f"constants.{key}"
        parts = []
        for name in constant.components:
            if name not in self.constants:
                msg = f"{where}.constants: unknown constant {name!r}"
                raise CatalogError(msg)
            parts.append(self.constants[name])
        identifiers = [p.identifier for p in parts]
        for identifier in identifiers:
            if identifiers.count(identifier) > 1:
                msg = f"{where}.constants: {identifier!r} names two constants"
                raise CatalogError(msg)
        try:
            expr = parse_expression(constant.definition, identifiers)
        except ExpressionError as exc:
            msg = f"{where}.definition: {exc}"
            raise CatalogError(msg) from None
        unused = sorted(set(identifiers) - {s.name for s in expr.free_symbols})
        if unused:
            msg = f"{where}.constants: not used by the definition: {', '.join(unused)}"
            raise CatalogError(msg)
        units = self.semantics.units
        target = units[constant.unit].pint
        function = compile_numeric(expr, tuple(identifiers))
        result = Q_(function(*(Q_(p.value, units[p.unit].pint) for p in parts)))
        try:
            factor = Q_(1.0, result.units).to(target).magnitude
        except pint.errors.DimensionalityError:
            unit = format(result.units, "~P") or "1"
            msg = f"{where}.definition: gives {unit}, not {target}"
            raise CatalogError(msg) from None
        self.definitions[key] = expr * _rational(repr(factor))

    def evaluate(self, key: str, value: Callable[[str], Any]) -> Any:
        """The definition of a constant, on the values ``value`` gives its components."""
        expr = self.definitions[key]
        names = {
            self.constants[n].identifier: n for n in self.constants[key].components
        }
        return expr.subs({s: value(names[s.name]) for s in expr.free_symbols})

    def unrounded(self, key: str) -> Any:
        """The exact value of a constant: its definition, recursively, else as printed."""
        if key not in self.definitions:
            return _exact(self.constants[key])
        return self.evaluate(key, self.unrounded)

    def check_value(self, key: str) -> None:
        """The value of a constant agrees with its definition.

        The formula is evaluated in exact arithmetic (π exact), so that an
        exact product is not taken for a rounding, on the values the
        components print and on their unrounded values (the definition of a
        component, recursively): a source may derive a constant from either.
        The value agrees with one of the two results within the tolerance
        the catalog states, else the uncertainty the source gives; an exact
        constant prints a truncation of it (less than one unit of its last
        digit below); any other value is rounded to half a unit of its last
        digit.
        """
        constant = self.constants[key]
        results = [
            self.evaluate(key, lambda name: _exact(self.constants[name])),
            self.evaluate(key, self.unrounded),
        ]
        printed = Decimal(constant.printed or repr(constant.value))
        digit = sympy.Rational(10) ** printed.as_tuple().exponent
        differences = [sympy.N(r - _rational(str(printed)), 30) for r in results]
        if constant.tolerance is not None or constant.uncertainty is not None:
            allowed = _rational(repr(constant.tolerance or constant.uncertainty))
            agrees = any(abs(d) <= allowed for d in differences)
            rule = f"beyond {float(allowed):g}"
        elif constant.nature is ConstantNature.EXACT:
            agrees = any(0 <= d < digit for d in differences)
            rule = "an exact constant prints a truncation of its definition"
        else:
            agrees = any(abs(d) <= digit / 2 for d in differences)
            rule = "beyond half a unit of its last digit"
        if not agrees:
            found = f"{sympy.N(results[0], 20)}"
            if results[1] != results[0]:
                found += f" (unrounded components: {sympy.N(results[1], 20)})"
            msg = (
                f"constants.{key}.value: {printed} departs from its definition "
                f"{constant.definition} = {found} ({rule})"
            )
            raise CatalogError(msg)

    def check_definition_cycles(self) -> None:
        """No constant is defined, through others, by itself."""
        done: set[str] = set()

        def visit(key: str, path: tuple[str, ...]) -> None:
            if key in path:
                cycle = " -> ".join((*path[path.index(key) :], key))
                msg = f"constants.{key}: definitions form a cycle ({cycle})"
                raise CatalogError(msg)
            if key in done:
                return
            for name in self.constants[key].components:
                visit(name, (*path, key))
            done.add(key)

        for key in sorted(self.constants):
            visit(key, ())

    def build_notations(self) -> dict[str, Notation]:
        notations = {}
        for key, table in self.data["notations"].items():
            where = f"notations.{key}"
            f = _fields(where, table, ("label", "symbols"), ("reference",))
            _check_symbols(f"{where}.symbols", f["symbols"])
            notations[key] = Notation(
                key=key,
                label=f["label"],
                symbols=MappingProxyType(dict(f["symbols"])),
                reference=self.optional_reference(f"{where}.reference", f["reference"]),
            )
        return notations

    def build_trade_terms(self) -> dict[str, TradeTerm]:
        terms = {}
        for key, table in self.data["trade_terms"].items():
            where = f"trade_terms.{key}"
            f = _fields(where, table, ("term", "language", "meanings"), ("matches",))
            meanings = []
            for i, item in enumerate(f["meanings"]):
                w = f"{where}.meanings[{i}]"
                m = _fields(w, item, ("community", "kind", "definition", "sources"))
                self.kind(f"{w}.kind", m["kind"])
                sources = tuple(self.reference(f"{w}.sources", s) for s in m["sources"])
                meanings.append(
                    TradeMeaning(m["community"], m["kind"], m["definition"], sources)
                )
            terms[key] = TradeTerm(
                key=key,
                term=f["term"],
                language=f["language"],
                meanings=tuple(meanings),
                matches=_matches(where, f["matches"]),
            )
        return terms

    def kind(self, where: str, name: Any) -> QuantityKind:
        if name not in self.kinds:
            msg = f"{where}: unknown kind {name!r}"
            raise CatalogError(msg)
        return self.kinds[name]

    def build_scales(self) -> None:
        tables = self.data["scales"]
        reference_of: dict[str, str] = {}
        pending = dict(tables)
        # Reference scales first, then each scale after the one it converts to.
        for key, table in pending.items():
            if not isinstance(table, dict):
                msg = f"scales.{key}: expected a table"
                raise CatalogError(msg)
            for name in ("reference_scale", "base"):
                if name in table and not isinstance(table[name], str):
                    msg = f"scales.{key}.{name}: expected a scale key"
                    raise CatalogError(msg)
        while pending:
            ready = [
                key
                for key, table in pending.items()
                if "reference_scale" not in table
                or table.get("base") in self.scales
                or table.get("base") not in tables
            ]
            if not ready:
                msg = f"scales: conversions form a cycle: {', '.join(sorted(pending))}"
                raise CatalogError(msg)
            ready.sort(key=lambda k: "reference_scale" in pending[k])
            for key in ready:
                self.scales[key] = self.scale(key, pending.pop(key), reference_of)

    def scale(
        self, key: str, table: Any, reference_of: dict[str, str]
    ) -> ConventionalScale:
        where = f"scales.{key}"
        f = _fields(
            where,
            table,
            ("label", "kinds"),
            (
                "reference_scale",
                "unit",
                "differences",
                "reference",
                "symbol",
                "subscript",
                "conversion",
                "base",
                "bounds",
                "convertible",
                "cf_standard_names",
                "note",
            ),
        )
        for name in ("symbol", "subscript", "conversion"):
            if f[name] is not None and (not isinstance(f[name], str) or not f[name]):
                msg = f"{where}.{name}: expected a non-empty string"
                raise CatalogError(msg)
        kinds = tuple(self.kind(f"{where}.kinds", k).name for k in f["kinds"])
        if not kinds:
            msg = f"{where}.kinds: at least one quantity kind"
            raise CatalogError(msg)
        parent = f["reference_scale"]
        if f["convertible"] is not None and not isinstance(f["convertible"], bool):
            msg = f"{where}.convertible: expected true or false"
            raise CatalogError(msg)
        convertible = f["convertible"] is None or f["convertible"]
        cf_names = _keywords(f"{where}.cf_standard_names", f["cf_standard_names"])
        unknown = sorted(set(cf_names) - set(self.semantics.cf_standard_names))
        if unknown:
            msg = (
                f"{where}.cf_standard_names: not in the frozen CF subset: "
                f"{', '.join(unknown)} (scripts/extract_semantics.py, SCALE_CF_NAMES)"
            )
            raise CatalogError(msg)
        conversion_fields = ("unit", "differences", "conversion", "base", "bounds")
        common = {
            "key": key,
            "label": f["label"],
            "kinds": kinds,
            "reference_scale": parent,
            "reference": self.optional_reference(f"{where}.reference", f["reference"]),
            "symbol": f["symbol"],
            "subscript": f["subscript"],
            "cf_standard_names": cf_names,
            "note": f["note"],
        }
        if parent is None:
            given = [n for n in (*conversion_fields, "convertible") if f[n] is not None]
            if given:
                msg = f"{where}: a reference scale has no conversion table ({', '.join(given)})"
                raise CatalogError(msg)
            for kind in kinds:
                if kind in reference_of:
                    msg = (
                        f"{where}: {kind} already has a reference scale, "
                        f"{reference_of[kind]}"
                    )
                    raise CatalogError(msg)
                reference_of[kind] = key
            return ConventionalScale(unit=None, points=(), difference=(), **common)
        top = self.scales.get(parent)
        if top is None or not top.is_reference:
            msg = f"{where}.reference_scale: {parent!r} is not a reference scale"
            raise CatalogError(msg)
        outside = sorted(set(kinds) - set(top.kinds))
        if outside:
            msg = f"{where}.kinds: {', '.join(outside)} not covered by {parent}"
            raise CatalogError(msg)
        if not convertible:
            given = [n for n in conversion_fields if f[n] is not None and n != "unit"]
            if given:
                msg = f"{where}: a scale without conversion has no {', '.join(given)}"
                raise CatalogError(msg)
            unit = None if f["unit"] is None else self.unit(f"{where}.unit", f["unit"])
            return ConventionalScale(
                unit=unit, points=(), difference=(), convertible=False, **common
            )
        if f["unit"] is None or (f["differences"] is None) == (f["conversion"] is None):
            msg = (
                f"{where}: a derived scale needs a unit and differences, or a unit "
                "and a conversion"
            )
            raise CatalogError(msg)
        unit = self.unit(f"{where}.unit", f["unit"])
        if f["differences"] is not None:
            if f["base"] is not None or f["bounds"] is not None:
                msg = f"{where}: a table converts to the reference scale, without base or bounds"
                raise CatalogError(msg)
            expected = "[reference value, reference value - value] pairs"
            rows = f["differences"]
            if not isinstance(rows, list) or not rows:
                msg = f"{where}.differences: expected {expected}"
                raise CatalogError(msg)
            pairs = [
                _pair(f"{where}.differences[{i}]", row, expected)
                for i, row in enumerate(rows)
            ]
            points = tuple(row[0] for row in pairs)
            if any(b <= a for a, b in pairwise(points)):
                msg = f"{where}.differences: reference values must increase"
                raise CatalogError(msg)
            return ConventionalScale(
                unit=unit,
                points=points,
                difference=tuple(row[1] for row in pairs),
                **common,
            )
        try:
            parse_expression(f["conversion"], ["x"])
        except ExpressionError as exc:
            msg = f"{where}.conversion: {exc}"
            raise CatalogError(msg) from None
        base = None
        if f["base"] is not None and f["base"] != parent:
            base = self.scales.get(f["base"])
            if (
                base is None
                or base.is_reference
                or not base.convertible
                or not set(kinds) <= set(base.kinds)
            ):
                msg = (
                    f"{where}.base: {f['base']!r} is not a convertible scale of "
                    "the same kinds"
                )
                raise CatalogError(msg)
            if base.reference_scale != parent or base.unit != unit:
                msg = (
                    f"{where}.base: {f['base']} must lead to {parent} in the same "
                    f"unit, {unit}"
                )
                raise CatalogError(msg)
        bounds = None
        if f["bounds"] is not None:
            values = f["bounds"]
            if (
                not isinstance(values, list)
                or len(values) != 2
                or not all(isinstance(v, int | float) for v in values)
                or not all(math.isfinite(v) for v in values)
            ):
                msg = f"{where}.bounds: expected [low, high], two finite numbers"
                raise CatalogError(msg)
            low, high = (float(v) for v in values)
            if not low < high:
                msg = f"{where}.bounds: empty interval"
                raise CatalogError(msg)
            bounds = (low, high)
        return ConventionalScale(
            unit=unit,
            points=(),
            difference=(),
            base=base,
            conversion=f["conversion"],
            bounds=bounds,
            **common,
        )

    def check_scale(
        self, where: str, variable: Variable, key: Any
    ) -> ConventionalScale:
        """The scale ``key`` for a variable, if it applies to its kind and unit."""
        scale = self.scales.get(key)
        if scale is None:
            msg = f"{where}: unknown scale {key!r}"
            raise CatalogError(msg)
        if variable.kind not in scale.kinds:
            msg = f"{where}: scale {key} does not apply to {variable.kind}"
            raise CatalogError(msg)
        if scale.unit is not None:
            units = self.semantics.units
            ours = units[variable.unit].dimension_vector
            if ours != units[scale.unit].dimension_vector:
                msg = f"{where}: {variable.unit} cannot be converted to {scale.unit}"
                raise CatalogError(msg)
        return scale

    def variable(self, where: str, table: Any) -> Variable:
        f = _fields(
            where,
            table,
            ("identifier", "kind", "unit", "description"),
            ("scale", "scale_basis"),
        )
        kind = self.kind(f"{where}.kind", f["kind"])
        unit = self.unit(f"{where}.unit", f["unit"])
        if unit not in kind.applicable_units:
            msg = f"{where}.unit: {unit} does not apply to {kind.name}"
            raise CatalogError(msg)
        scale, basis = f["scale"], f["scale_basis"]
        if (scale is None) != (basis is None):
            msg = f"{where}: scale and scale_basis go together"
            raise CatalogError(msg)
        if scale is not None:
            plain = Variable(f["identifier"], kind.name, unit, f["description"])
            found = self.check_scale(f"{where}.scale", plain, scale)
            basis = _enum(f"{where}.scale_basis", ScaleBasis, basis)
            if basis is ScaleBasis.STATED:
                msg = (
                    f"{where}: a scale stated by a source goes in its citation "
                    f'(scales = {{ {f["identifier"]} = "{scale}" }})'
                )
                raise CatalogError(msg)
            return Variable(
                f["identifier"],
                kind.name,
                unit,
                f["description"],
                found,
                basis,
            )
        return Variable(f["identifier"], kind.name, unit, f["description"])

    def coefficients(self, where: str, table: Any) -> tuple[Coefficient, ...]:
        result = []
        for identifier, value in (table or {}).items():
            if isinstance(value, dict):
                place = f"{where}.{identifier}"
                f = _fields(place, value, ("value",), ("unit", "unit_basis", "note"))
                unit, basis = f["unit"], f["unit_basis"]
                if unit is not None:
                    unit = self.unit(f"{place}.unit", unit)
                    if basis is None:
                        msg = (
                            f"{place}: a declared unit needs unit_basis: "
                            '"added" (with a note) here; a unit stated by the '
                            "source goes in its citation (units = { ... })"
                        )
                        raise CatalogError(msg)
                    basis = _enum(f"{place}.unit_basis", UnitBasis, basis)
                    if basis is UnitBasis.STATED:
                        msg = (
                            f"{place}: a unit stated by the source goes in its "
                            f'citation (units = {{ {identifier} = "{unit}" }})'
                        )
                        raise CatalogError(msg)
                    if not f["note"]:
                        msg = f"{place}: an added unit needs a note saying why"
                        raise CatalogError(msg)
                elif basis is not None:
                    msg = f"{place}: unit_basis without a unit"
                    raise CatalogError(msg)
                result.append(
                    Coefficient(
                        identifier,
                        _number(f"{place}.value", f["value"]),
                        unit,
                        f["note"],
                        basis,
                    )
                )
            else:
                number = _number(f"{where}.{identifier}", value)
                result.append(Coefficient(identifier, number, None, None))
        return tuple(result)

    @staticmethod
    def bounds(
        where: str, table: Any, inputs: tuple[Variable, ...]
    ) -> Mapping[str, tuple[float, float]]:
        names = {v.identifier for v in inputs}
        bounds = {}
        if not isinstance(table, dict):
            msg = f"{where}: expected a table of input identifier to [low, high]"
            raise CatalogError(msg)
        for identifier, interval in table.items():
            if identifier not in names:
                msg = f"{where}: {identifier!r} is not an input"
                raise CatalogError(msg)
            low, high = _pair(
                f"{where}.{identifier}", interval, "[low, high], two finite numbers"
            )
            if not low < high:
                msg = f"{where}.{identifier}: empty interval"
                raise CatalogError(msg)
            bounds[identifier] = (low, high)
        return MappingProxyType(bounds)

    def domains(
        self,
        where: str,
        items: Any,
        inputs: tuple[Variable, ...],
        reference: str | None,
    ) -> tuple[ValidityDomain, ...]:
        """Physical domains (``reference`` None), or those a citation states."""
        result = []
        for i, item in enumerate(items or ()):
            w = f"{where}[{i}]"
            optional = (
                ("criterion", "reference") if reference is None else ("criterion",)
            )
            f = _fields(w, item, ("bounds",), optional)
            result.append(
                ValidityDomain(
                    basis=DomainBasis.PHYSICAL
                    if reference is None
                    else DomainBasis.STATED,
                    bounds=self.bounds(f"{w}.bounds", f["bounds"], inputs),
                    criterion=f["criterion"],
                    reference=(
                        reference
                        if reference is not None
                        else self.optional_reference(f"{w}.reference", f["reference"])
                    ),
                )
            )
        return tuple(result)

    def citations(
        self,
        where: str,
        items: Any,
        formulation: str,
        inputs: tuple[Variable, ...],
        names: set[str],
        coefficients: set[str],
        outputs: tuple[Variable, ...] = (),
    ) -> tuple[Citation, ...]:
        result = []
        seen = set()
        by_identifier = {v.identifier: v for v in (*inputs, *outputs)}
        for i, item in enumerate(items or ()):
            w = f"{where}[{i}]"
            f = _fields(
                w,
                item,
                ("reference",),
                (
                    "equation",
                    "notation",
                    "domains",
                    "units",
                    "scales",
                    "accuracy",
                    "note",
                ),
            )
            reference = self.reference(f"{w}.reference", f["reference"])
            equation = None if f["equation"] is None else str(f["equation"])
            if (reference, equation) in seen:
                msg = f"{w}: {reference} cited twice for the same equation"
                raise CatalogError(msg)
            seen.add((reference, equation))
            units = {}
            for identifier, unit in (f["units"] or {}).items():
                if identifier not in coefficients:
                    msg = f"{w}.units: {identifier!r} is not a coefficient"
                    raise CatalogError(msg)
                units[identifier] = self.unit(f"{w}.units.{identifier}", unit)
            scales = {}
            for identifier, scale in (f["scales"] or {}).items():
                variable = by_identifier.get(identifier)
                if variable is None:
                    msg = f"{w}.scales: {identifier!r} is not a variable"
                    raise CatalogError(msg)
                scales[identifier] = self.check_scale(
                    f"{w}.scales.{identifier}", variable, scale
                )
            result.append(
                Citation(
                    reference=reference,
                    equation=equation,
                    notation=self.citation_notation(
                        f"{w}.notation", f["notation"], formulation, reference, names
                    ),
                    domains=self.domains(
                        f"{w}.domains", f["domains"], inputs, reference
                    ),
                    units=MappingProxyType(units),
                    scales=MappingProxyType(scales),
                    accuracy=f["accuracy"],
                    note=f["note"],
                )
            )
        return tuple(result)

    def citation_notation(
        self, where: str, value: Any, formulation: str, reference: str, names: set[str]
    ) -> Notation | None:
        """A convention of the catalog by key, or the source's own symbols."""
        if value is None:
            return None
        if isinstance(value, str):
            if value not in self.notations:
                msg = f"{where}: unknown notation {value!r}"
                raise CatalogError(msg)
            return self.notations[value]
        unknown = sorted(set(value) - names)
        if unknown:
            msg = f"{where}: not identifiers of the formulation: {', '.join(unknown)}"
            raise CatalogError(msg)
        _check_symbols(where, value)
        return Notation(
            key=f"{formulation}:{reference}",
            label=f"Notation of {reference}",
            symbols=MappingProxyType(dict(value)),
            reference=reference,
        )

    def formulation(self, key: str, table: Any) -> Formulation:
        where = f"formulations.{key}"
        f = _fields(
            where,
            table,
            ("label", "expression", "fixed_units", "output", "inputs"),
            (
                "coefficients",
                "constants",
                "domains",
                "citations",
                "note",
                "matches",
                "keywords",
            ),
        )
        output = self.variable(f"{where}.output", f["output"])
        inputs = tuple(
            self.variable(f"{where}.inputs[{i}]", v) for i, v in enumerate(f["inputs"])
        )
        constants = []
        for name in f["constants"] or ():
            if name not in self.constants:
                msg = f"{where}.constants: unknown constant {name!r}"
                raise CatalogError(msg)
            constants.append(self.constants[name])
        coefficients = self.coefficients(f"{where}.coefficients", f["coefficients"])
        names = (
            {output.identifier}
            | {v.identifier for v in inputs}
            | {c.identifier for c in coefficients}
            | {k.identifier for k in constants}
        )
        citations = self.citations(
            f"{where}.citations",
            f["citations"],
            key,
            inputs,
            names,
            {c.identifier for c in coefficients},
            (output,),
        )
        formulation = Formulation(
            key=key,
            label=f["label"],
            output=_stated_scales(f"{where}.citations", (output,), citations)[0],
            inputs=_stated_scales(f"{where}.citations", inputs, citations),
            coefficients=_stated_units(f"{where}.citations", coefficients, citations),
            constants=tuple(constants),
            expression=f["expression"],
            fixed_units=bool(f["fixed_units"]),
            physical_domains=self.domains(
                f"{where}.domains", f["domains"], inputs, None
            ),
            citations=citations,
            note=f["note"],
            matches=_matches(where, f["matches"]),
            family=self.owners.get(("formulations", key)),
            keywords=_keywords(f"{where}.keywords", f["keywords"]),
        )
        self.check(where, formulation)
        return formulation

    def feeds(self, output_kind: str, input_kind: str) -> bool:
        """Whether a result of one kind may feed an input of another.

        The kinds of this catalog, not those of the bundled one (see
        :func:`nomogram.comparison.feeds`).
        """
        kind = self.kinds.get(output_kind)
        while kind is not None:
            if kind.name == input_kind:
                return True
            kind = self.kinds.get(kind.specialization_of or "")
        return False

    @staticmethod
    def part(
        where: str, name: Any, formulations: Mapping[str, Formulation]
    ) -> Formulation:
        if not isinstance(name, str) or name not in formulations:
            msg = f"{where}: unknown formulation {name!r}"
            raise CatalogError(msg)
        return formulations[name]

    def composed(
        self, key: str, table: Any, formulations: Mapping[str, Formulation]
    ) -> Formulation:
        """A formulation written as a composition of others."""
        where = f"formulations.{key}"
        derived = sorted(set(table) & set(_DERIVED))
        if derived:
            msg = f"{where}: a composed formulation takes {', '.join(derived)} from its parts"
            raise CatalogError(msg)
        f = _fields(
            where,
            table,
            ("label", "composition"),
            ("output", "citations", "note", "matches", "keywords"),
        )
        place = f"{where}.composition"
        c = _fields(place, f["composition"], ("outer", "inner"), ("bind",))
        outer = self.part(f"{place}.outer", c["outer"], formulations)
        if not isinstance(c["inner"], dict) or not c["inner"]:
            msg = f"{place}.inner: expected a table of input identifier to formulation"
            raise CatalogError(msg)
        outer_inputs = {v.identifier: v for v in outer.inputs}
        bounded = {
            _pieces(node, outer_inputs)[0].variable.name
            for node in sympy.preorder_traversal(outer.sympy_expression)
            if isinstance(node, sympy.Piecewise)
        }
        inner: dict[str, Formulation] = {}
        for identifier, name in c["inner"].items():
            w = f"{place}.inner.{identifier}"
            part = self.part(w, name, formulations)
            target = outer_inputs.get(identifier)
            if target is None:
                msg = f"{w}: {outer.key} has no input {identifier!r}"
                raise CatalogError(msg)
            if identifier in bounded:
                # A condition on a computed value is no interval of an input.
                msg = (
                    f"{w}: a condition of {outer.key}'s piecewise definition "
                    f"bounds {identifier}, which {part.key} computes; the "
                    "conditions bound inputs of the composed formulation"
                )
                raise CatalogError(msg)
            if not self.feeds(part.output.kind, target.kind):
                msg = (
                    f"{w}: {part.key} computes {part.output.kind}, "
                    f"but {identifier} is {target.kind}"
                )
                raise CatalogError(msg)
            if part.output.unit != target.unit:
                msg = (
                    f"{w}: {part.key} gives {part.output.unit}, "
                    f"but {identifier} is in {target.unit}"
                )
                raise CatalogError(msg)
            if part.output.scale != target.scale:
                msg = (
                    f"{w}: {part.key} gives a value on scale "
                    f"{getattr(part.output.scale, 'key', None)}, but {identifier} "
                    f"is on {getattr(target.scale, 'key', None)}"
                )
                raise CatalogError(msg)
            inner[identifier] = part
        bind = dict(c["bind"] or {})
        for source, name in bind.items():
            if not any(
                source in {v.identifier for v in p.inputs} for p in inner.values()
            ):
                msg = (
                    f"{place}.bind: {source!r} is not an input of an inner formulation"
                )
                raise CatalogError(msg)
            if name in inner:
                msg = f"{place}.bind: {name!r} is computed by {inner[name].key}"
                raise CatalogError(msg)
        renames = {
            identifier: {
                v.identifier: bind[v.identifier]
                for v in part.inputs
                if v.identifier in bind
            }
            for identifier, part in inner.items()
        }

        # Inputs: those of the outer formulation it still needs, then those of
        # the inner ones; one identifier is one input, alike in every part.
        inputs: dict[str, Variable] = {}
        came_from: dict[str, str] = {}
        pieces = [(outer, v) for v in outer.inputs if v.identifier not in inner]
        for identifier, part in inner.items():
            rename = renames[identifier]
            pieces += [
                (
                    part,
                    dataclasses.replace(
                        v, identifier=rename.get(v.identifier, v.identifier)
                    ),
                )
                for v in part.inputs
            ]
        for piece, variable in pieces:
            came_from.setdefault(variable.identifier, piece.key)
            known = inputs.setdefault(variable.identifier, variable)
            if (known.kind, known.unit, known.scale) != (
                variable.kind,
                variable.unit,
                variable.scale,
            ):
                msg = (
                    f"{where}: input {variable.identifier} of {piece.key} differs "
                    "in kind, unit or scale from the input of the same name in "
                    "another part; rename it with bind"
                )
                raise CatalogError(msg)

        # Part, and formulation that defines it, of each coefficient.
        owner: dict[str, tuple[str, str]] = {}
        coefficients: list[Coefficient] = []
        constants: dict[str, PhysicalConstant] = {}
        for piece in (outer, *inner.values()):
            for coefficient in piece.coefficients:
                origin = _defined_in(piece, coefficient.identifier)
                if coefficient.identifier in owner:
                    first, defined = owner[coefficient.identifier]
                    if defined == origin:
                        # One part reached twice (directly and inside another):
                        # one coefficient, with the unit a citation states.
                        index = next(
                            i
                            for i, c in enumerate(coefficients)
                            if c.identifier == coefficient.identifier
                        )
                        kept = coefficients[index]
                        if kept.unit is None:
                            coefficients[index] = coefficient
                        elif coefficient.unit not in (None, kept.unit):
                            msg = (
                                f"{where}: coefficient {coefficient.identifier} of "
                                f"{origin} is in {kept.unit} in {first} and in "
                                f"{coefficient.unit} in {piece.key}"
                            )
                            raise CatalogError(msg)
                        continue
                    msg = (
                        f"{where}: coefficient {coefficient.identifier} in both "
                        f"{first} and {piece.key}"
                    )
                    raise CatalogError(msg)
                owner[coefficient.identifier] = (piece.key, origin)
                coefficients.append(coefficient)
            for constant in piece.constants:
                found = constants.setdefault(constant.identifier, constant)
                if found.key != constant.key:
                    msg = (
                        f"{where}: constant {constant.identifier} is {found.key} "
                        f"in one part and {constant.key} in {piece.key}"
                    )
                    raise CatalogError(msg)

        output = outer.output
        if f["output"] is not None:
            output = self.variable(f"{where}.output", f["output"])
            if not self.feeds(output.kind, outer.output.kind):
                msg = (
                    f"{where}.output: {output.kind} is not a specialization of "
                    f"{outer.output.kind}, the output of {outer.key}"
                )
                raise CatalogError(msg)
            if output.unit != outer.output.unit:
                msg = (
                    f"{where}.output: the unit is that of {outer.key}'s output, "
                    f"{outer.output.unit}"
                )
                raise CatalogError(msg)
            if output.scale is not None and output.scale != outer.output.scale:
                msg = (
                    f"{where}.output: the scale is that of {outer.key}'s output, "
                    f"{getattr(outer.output.scale, 'key', None)}"
                )
                raise CatalogError(msg)
            output = dataclasses.replace(
                output,
                scale=outer.output.scale,
                scale_basis=outer.output.scale_basis,
            )

        # Physical domains travel with the inputs they bound.
        domains = [d for d in outer.physical_domains if not set(d.bounds) & set(inner)]
        for identifier, part in inner.items():
            rename = renames[identifier]
            domains += [
                dataclasses.replace(
                    d,
                    bounds=MappingProxyType(
                        {rename.get(k, k): b for k, b in d.bounds.items()}
                    ),
                )
                for d in part.physical_domains
            ]

        fixed = any(p.fixed_units for p in (outer, *inner.values()))
        names = {output.identifier} | set(inputs) | set(owner) | set(constants)
        variables = tuple(inputs.values())
        citations = self.citations(
            f"{where}.citations",
            f["citations"],
            key,
            variables,
            names,
            set(owner),
            (output,),
        )
        stated = f"{where}.citations"
        formulation = Formulation(
            key=key,
            label=f["label"],
            output=_stated_scales(
                stated, (output,), citations, {output.identifier: outer.key}
            )[0],
            inputs=_stated_scales(stated, variables, citations, came_from),
            coefficients=_stated_units(
                stated,
                tuple(coefficients),
                citations,
                {identifier: part for identifier, (part, _) in owner.items()},
            ),
            constants=tuple(constants.values()),
            expression=_substitute(outer, inner, renames, fixed),
            fixed_units=fixed,
            physical_domains=tuple(domains),
            citations=citations,
            note=f["note"],
            matches=_matches(where, f["matches"]),
            derivation=Derivation(
                outer.key,
                "composition",
                parts=MappingProxyType({i: p.key for i, p in inner.items()}),
            ),
            family=self.owners.get(("formulations", key)),
            keywords=_keywords(f"{where}.keywords", f["keywords"]),
            parts=(
                *(Part(p, i, MappingProxyType(renames[i])) for i, p in inner.items()),
                Part(outer, None),
            ),
        )
        self.check(where, formulation)
        return formulation

    def branched(
        self, key: str, table: Any, formulations: Mapping[str, Formulation]
    ) -> Formulation:
        """A formulation defined by pieces, each a formulation of the catalog."""
        where = f"formulations.{key}"
        derived = sorted(set(table) & set(_DERIVED))
        if derived:
            msg = (
                f"{where}: a formulation by branches takes {', '.join(derived)} "
                "from its branches"
            )
            raise CatalogError(msg)
        f = _fields(
            where,
            table,
            ("label", "branches", "output"),
            ("citations", "note", "matches", "keywords"),
        )
        if not isinstance(f["branches"], list) or len(f["branches"]) < 2:
            msg = (
                f"{where}.branches: expected a list of at least two "
                "{ formulation, where } tables"
            )
            raise CatalogError(msg)
        output = self.variable(f"{where}.output", f["output"])
        branches: list[tuple[Formulation, str]] = []
        for index, item in enumerate(f["branches"]):
            w = f"{where}.branches[{index}]"
            b = _fields(w, item, ("formulation", "where"), ())
            part = self.part(f"{w}.formulation", b["formulation"], formulations)
            if not self.feeds(part.output.kind, output.kind):
                msg = (
                    f"{w}: {part.key} computes {part.output.kind}, which is not "
                    f"{output.kind} or a specialization of it"
                )
                raise CatalogError(msg)
            if part.output.unit != output.unit:
                msg = f"{w}: {part.key} gives {part.output.unit}, not {output.unit}"
                raise CatalogError(msg)
            branches.append((part, b["where"]))
        first = branches[0][0]
        for part, _ in branches[1:]:
            if part.output.scale != first.output.scale:
                msg = f"{where}.branches: the branches give values on different scales"
                raise CatalogError(msg)
            if part.fixed_units != first.fixed_units:
                msg = (
                    f"{where}.branches: the branches mix numerical value and "
                    "quantity equations"
                )
                raise CatalogError(msg)
        output = dataclasses.replace(
            output, scale=first.output.scale, scale_basis=first.output.scale_basis
        )

        # Inputs: one identifier is one input, alike in every branch.
        inputs: dict[str, Variable] = {}
        came_from: dict[str, str] = {}
        for part, _ in branches:
            for variable in part.inputs:
                came_from.setdefault(variable.identifier, part.key)
                known = inputs.setdefault(variable.identifier, variable)
                if (known.kind, known.unit, known.scale) != (
                    variable.kind,
                    variable.unit,
                    variable.scale,
                ):
                    msg = (
                        f"{where}: input {variable.identifier} of {part.key} "
                        "differs in kind, unit or scale from the input of the "
                        "same name in another branch"
                    )
                    raise CatalogError(msg)

        # Formulation that defines each coefficient: one formulation may serve
        # two branches, two formulations may not share a name.
        owner: dict[str, str] = {}
        coefficients: list[Coefficient] = []
        constants: dict[str, PhysicalConstant] = {}
        for part, _ in branches:
            for coefficient in part.coefficients:
                origin = _defined_in(part, coefficient.identifier)
                if owner.get(coefficient.identifier, origin) != origin:
                    msg = (
                        f"{where}: coefficient {coefficient.identifier} in both "
                        f"{owner[coefficient.identifier]} and {origin}"
                    )
                    raise CatalogError(msg)
                if coefficient.identifier not in owner:
                    owner[coefficient.identifier] = origin
                    coefficients.append(coefficient)
            for constant in part.constants:
                found = constants.setdefault(constant.identifier, constant)
                if found.key != constant.key:
                    msg = (
                        f"{where}: constant {constant.identifier} is {found.key} "
                        f"in one branch and {constant.key} in {part.key}"
                    )
                    raise CatalogError(msg)

        known_names = [*inputs, *owner, *constants]
        for index, (_, condition) in enumerate(branches):
            try:
                parse_expression(f"{PIECEWISE}((0, {condition}))", known_names)
            except (ExpressionError, TypeError) as exc:
                msg = f"{where}.branches[{index}].where: {exc}"
                raise CatalogError(msg) from None
        pieces = ", ".join(f"({p.expression}, {c})" for p, c in branches)
        names = {output.identifier} | set(known_names)
        variables = tuple(inputs.values())
        citations = self.citations(
            f"{where}.citations",
            f["citations"],
            key,
            variables,
            names,
            set(owner),
            (output,),
        )
        stated = f"{where}.citations"
        formulation = Formulation(
            key=key,
            label=f["label"],
            output=_stated_scales(
                stated, (output,), citations, {output.identifier: first.key}
            )[0],
            inputs=_stated_scales(stated, variables, citations, came_from),
            coefficients=_stated_units(stated, tuple(coefficients), citations, owner),
            constants=tuple(constants.values()),
            expression=f"{PIECEWISE}({pieces})",
            fixed_units=first.fixed_units,
            physical_domains=(),
            citations=citations,
            note=f["note"],
            matches=_matches(where, f["matches"]),
            derivation=Derivation(
                first.key,
                "branches",
                parts=MappingProxyType({c: p.key for p, c in branches}),
            ),
            family=self.owners.get(("formulations", key)),
            keywords=_keywords(f"{where}.keywords", f["keywords"]),
            branches=tuple(Branch(p, c) for p, c in branches),
        )
        self.check(where, formulation)
        return formulation

    @staticmethod
    def composition_order(tables: Mapping[str, Any]) -> list[str]:
        """Composed formulations and branches, each after those it uses."""
        composed = {
            key: table
            for key, table in tables.items()
            if isinstance(table, dict)
            and ("composition" in table or "branches" in table)
        }
        order: list[str] = []

        def visit(key: str, path: list[str]) -> None:
            if key in order:
                return
            if key in path:
                cycle = " -> ".join([*path[path.index(key) :], key])
                msg = f"formulations.{key}: compositions form a cycle: {cycle}"
                raise CatalogError(msg)
            names = _used_formulations(composed[key])
            for name in names:
                if isinstance(name, str) and name in composed:
                    visit(name, [*path, key])
            order.append(key)

        for key in composed:
            visit(key, [])
        return order

    def relation(
        self, key: str, table: Any, formulations: Mapping[str, Formulation]
    ) -> Relation:
        where = f"relations.{key}"
        f = _fields(
            where,
            table,
            ("kind", "subject", "object", "citation"),
            ("accuracy", "at", "bounds", "given", "scale", "note"),
        )
        kind = _enum(f"{where}.kind", RelationKind, f["kind"])
        ends = []
        for role in ("subject", "object"):
            if f[role] not in formulations:
                msg = f"{where}.{role}: unknown formulation {f[role]!r}"
                raise CatalogError(msg)
            ends.append(formulations[f[role]])
        subject, other = ends
        if subject.output.kind != other.output.kind:
            msg = (
                f"{where}: {subject.key} computes {subject.output.kind}, "
                f"{other.key} computes {other.output.kind}"
            )
            raise CatalogError(msg)
        scale: ScaleConversion = f["scale"] or "convert"
        if scale not in ("convert", "ignore"):
            msg = f"{where}.scale: expected convert or ignore, not {scale!r}"
            raise CatalogError(msg)
        bounds = self.bounds(f"{where}.bounds", f["bounds"] or {}, subject.inputs)
        names = {v.identifier for v in subject.inputs}
        at = {}
        if not isinstance(f["at"] or {}, dict):
            msg = f"{where}.at: expected a table of input identifier to value"
            raise CatalogError(msg)
        for identifier, value in (f["at"] or {}).items():
            if identifier not in names:
                msg = f"{where}.at: {identifier!r} is not an input of {subject.key}"
                raise CatalogError(msg)
            at[identifier] = _number(f"{where}.at.{identifier}", value)
            low, high = bounds.get(identifier, (-math.inf, math.inf))
            if not low <= at[identifier] <= high:
                msg = (
                    f"{where}.at.{identifier}: {value!r} is outside the bounds "
                    f"[{low}, {high}]"
                )
                raise CatalogError(msg)
        accuracy = None
        if f["accuracy"] is not None:
            accuracy = _number(f"{where}.accuracy", f["accuracy"])
            if not accuracy > 0:
                msg = f"{where}.accuracy: expected a positive percentage, not {accuracy!r}"
                raise CatalogError(msg)
        raw_given = f["given"] or {}
        if not isinstance(raw_given, dict) or not all(
            isinstance(v, str) for v in raw_given.values()
        ):
            msg = f"{where}.given: expected a table of expressions, by input identifier"
            raise CatalogError(msg)
        given = dict(raw_given)
        unfed = sorted(
            v.identifier
            for v in other.inputs
            if v.identifier not in match_inputs(subject, other)
            and v.identifier not in given
        )
        if unfed:
            msg = (
                f"{where}: inputs of {other.key} matching no input of "
                f"{subject.key}: {', '.join(unfed)}"
            )
            raise CatalogError(msg)
        if kind is RelationKind.APPROXIMATES:
            if f["accuracy"] is None or set(bounds) != names:
                msg = (
                    f"{where}: an approximation states its accuracy and bounds "
                    f"every input of {subject.key}"
                )
                raise CatalogError(msg)
            if given:
                msg = f"{where}.given: only for an equivalence"
                raise CatalogError(msg)
        else:
            if f["accuracy"] is not None:
                msg = f"{where}.accuracy: only for an approximation"
                raise CatalogError(msg)
            others = {v.identifier for v in other.inputs}
            for identifier, source in given.items():
                if identifier not in others:
                    msg = (
                        f"{where}.given: {identifier!r} is not an input of {other.key}"
                    )
                    raise CatalogError(msg)
                try:
                    parse_expression(str(source), sorted(names))
                except ExpressionError as exc:
                    msg = f"{where}.given.{identifier}: {exc}"
                    raise CatalogError(msg) from None
            self.check_units(where, subject, other, given)
        return Relation(
            key=key,
            kind=kind,
            subject=subject.key,
            object=other.key,
            citation=self.reference(f"{where}.citation", f["citation"]),
            accuracy=accuracy,
            at=MappingProxyType(at),
            bounds=bounds,
            given=MappingProxyType({k: str(v) for k, v in given.items()}),
            scale=scale,
            note=f["note"],
        )

    @staticmethod
    def check_units(
        where: str, subject: Formulation, other: Formulation, given: Mapping[str, Any]
    ) -> None:
        """An equivalence is proved on the expressions as written: same units.

        The output, and every input of the object with the subject inputs
        feeding it (matched, or used by its ``given`` expression), must be
        in the same unit; conversions in ``given`` are not supported.
        """
        units = {v.identifier: v.unit for v in subject.inputs}
        matched = match_inputs(subject, other)
        found = []
        if subject.output.unit != other.output.unit:
            found.append(f"output in {subject.output.unit} and {other.output.unit}")
        for variable in other.inputs:
            if variable.identifier in given:
                expr = parse_expression(str(given[variable.identifier]), sorted(units))
                sources = sorted(s.name for s in expr.free_symbols)
            else:
                sources = [matched[variable.identifier]]
            found += [
                f"{variable.identifier} in {variable.unit} fed by {s} in {units[s]}"
                for s in sources
                if units[s] != variable.unit
            ]
        if found:
            msg = (
                f"{where}: an equivalence is proved on the expressions as "
                f"written, which needs the same units: {'; '.join(found)}"
            )
            raise CatalogError(msg)

    def cross_check(
        self, key: str, table: Any, formulations: Mapping[str, Formulation]
    ) -> CrossCheck:
        where = f"cross_checks.{key}"
        f = _fields(
            where,
            table,
            ("implementation", "version", "checked", "cases"),
            ("url", "note"),
        )
        if not isinstance(f["checked"], datetime.date):
            msg = f"{where}.checked: expected a date (YYYY-MM-DD)"
            raise CatalogError(msg)
        if not isinstance(f["cases"], list) or not f["cases"]:
            msg = f"{where}.cases: expected a non-empty list of cases"
            raise CatalogError(msg)
        cases = []
        for i, item in enumerate(f["cases"]):
            w = f"{where}.cases[{i}]"
            c = _fields(w, item, ("formulation", "inputs", "value"), ("call", "rtol"))
            formulation = self.part(f"{w}.formulation", c["formulation"], formulations)
            names = {v.identifier for v in formulation.inputs}
            if not isinstance(c["inputs"], dict) or set(c["inputs"]) != names:
                msg = (
                    f"{w}.inputs: expected a value for each input of "
                    f"{formulation.key}: {', '.join(sorted(names))}"
                )
                raise CatalogError(msg)
            rtol = 1e-12 if c["rtol"] is None else _number(f"{w}.rtol", c["rtol"])
            if not rtol > 0:
                msg = f"{w}.rtol: expected a positive tolerance"
                raise CatalogError(msg)
            cases.append(
                CheckCase(
                    formulation=formulation.key,
                    inputs=MappingProxyType(
                        {
                            k: _number(f"{w}.inputs.{k}", v)
                            for k, v in c["inputs"].items()
                        }
                    ),
                    value=_number(f"{w}.value", c["value"]),
                    call=c["call"],
                    rtol=rtol,
                )
            )
        return CrossCheck(
            key=key,
            implementation=str(f["implementation"]),
            version=str(f["version"]),
            checked=f["checked"],
            cases=tuple(cases),
            url=f["url"],
            note=f["note"],
        )

    @staticmethod
    def check(where: str, formulation: Formulation) -> None:
        names = formulation.names
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if formulation.output.identifier in names:
            duplicates.append(formulation.output.identifier)
        if duplicates:
            msg = f"{where}: identifiers declared twice: {', '.join(duplicates)}"
            raise CatalogError(msg)
        try:
            expr = formulation.sympy_expression
        except ExpressionError as exc:
            msg = f"{where}.expression: {exc}"
            raise CatalogError(msg) from None
        unused = sorted(set(names) - {s.name for s in expr.free_symbols})
        if unused:
            msg = f"{where}: declared but not used: {', '.join(unused)}"
            raise CatalogError(msg)
        if not formulation.parts:
            _check_pieces(where, formulation)
        try:
            _ = formulation.output_factor
        except (pint.errors.DimensionalityError, DimensionError) as exc:
            msg = f"{where}: not dimensionally homogeneous: {exc}"
            raise CatalogError(msg) from None
        # Every coefficient needs a unit, declared or inferred.
        try:
            units = formulation.coefficient_units
        except DimensionError as exc:
            msg = f"{where}: units contradict the expression, {exc}"
            raise CatalogError(msg) from None
        undetermined = sorted(k for k, u in units.items() if u.unit is None)
        if undetermined:
            msg = (
                f"{where}: the expression does not determine the unit of "
                f"{', '.join(undetermined)}; declare it: in the citation of "
                "the source that gives it (units = { ... }), or on the "
                'coefficient with unit_basis = "added" and a note'
            )
            raise CatalogError(msg)

    def build(self) -> Catalog:
        self.build_kinds()
        self.build_references()
        self.build_constants()
        self.build_scales()
        self.notations = self.build_notations()
        trade_terms = self.build_trade_terms()
        tables = self.data["formulations"]
        built = {
            key: self.formulation(key, table)
            for key, table in tables.items()
            if not (
                isinstance(table, dict)
                and ("composition" in table or "branches" in table)
            )
        }
        for key in self.composition_order(tables):
            if "branches" in tables[key]:
                built[key] = self.branched(key, tables[key], built)
            else:
                built[key] = self.composed(key, tables[key], built)
        formulations = {key: built[key] for key in tables}
        # Two sources of one formulation make one entry with two citations.
        seen: dict[str, str] = {}
        for key, formulation in formulations.items():
            fingerprint = signature(formulation)
            if fingerprint in seen:
                first = seen[fingerprint]
                msg = (
                    f"formulations.{key}: identical to formulations.{first} (same "
                    "expression, coefficients, quantity kinds and units); add a "
                    f"citation to {first} instead"
                )
                raise CatalogError(msg)
            seen[fingerprint] = key
        relations = {
            key: self.relation(key, table, formulations)
            for key, table in self.data["relations"].items()
        }
        return Catalog(
            kinds=MappingProxyType(self.kinds),
            formulations=MappingProxyType(formulations),
            relations=MappingProxyType(relations),
            cross_checks=MappingProxyType(
                {
                    key: self.cross_check(key, table, formulations)
                    for key, table in self.data["cross_checks"].items()
                }
            ),
            references=MappingProxyType(self.references),
            constants=MappingProxyType(self.constants),
            notations=MappingProxyType(self.notations),
            trade_terms=MappingProxyType(trade_terms),
            scales=MappingProxyType(self.scales),
        )


Source = str | os.PathLike[str]

_HEADER = "catalog"


def _read(number: int, source: Source) -> tuple[str, dict[str, Any]]:
    """The name of a document and its content, header removed."""
    if isinstance(source, os.PathLike):
        label = Path(source).name
        text = Path(source).read_text(encoding="utf-8")
    else:
        label, text = f"document {number}", source
    try:
        return label, tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"{label}: invalid TOML: {exc}"
        raise CatalogError(msg) from None


def _header(label: str, table: Any) -> dict[str, Any]:
    where = f"{label}: [{_HEADER}]"
    f = _fields(
        where, table, ("name", "format"), ("label", "requires", "matches", "keywords")
    )
    if f["format"] != FORMAT:
        msg = f"{where}: format {f['format']!r} is not supported (expected {FORMAT})"
        raise CatalogError(msg)
    requires = f["requires"] or []
    if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
        msg = f"{where}.requires: expected a list of family names"
        raise CatalogError(msg)
    f["requires"] = tuple(requires)
    return f


def _used_formulations(table: Any) -> list[Any]:
    """The formulations a composition or a formulation by branches uses, by key.

    Called on unvalidated tables too (to order the entries before building
    them): anything malformed is left to the builder.
    """
    composition = table.get("composition")
    if isinstance(composition, dict):
        inner = composition.get("inner")
        return [
            composition.get("outer"),
            *(inner.values() if isinstance(inner, dict) else ()),
        ]
    branches = table.get("branches")
    if isinstance(branches, list):
        return [b.get("formulation") for b in branches if isinstance(b, dict)]
    return []


def _references(section: str, table: Any) -> set[tuple[str, str]]:
    """The entries of other sections an entry refers to, by key.

    Called on validated data only: the builder has checked every field.
    """
    found: set[tuple[str, str]] = set()

    def add(target: str, value: Any) -> None:
        if isinstance(value, str):  # None when absent, a table for an inline notation
            found.add((target, value))

    if section == "formulations":
        for name in _used_formulations(table):
            add("formulations", name)
        variables = [table["output"]] if "output" in table else []
        for variable in (*variables, *table.get("inputs", ())):
            add("kinds", variable["kind"])
            add("scales", variable.get("scale"))
        for constant in table.get("constants", ()):
            add("constants", constant)
        for domain in table.get("domains", ()):
            add("references", domain.get("reference"))
        for citation in table.get("citations", ()):
            add("references", citation["reference"])
            add("notations", citation.get("notation"))
            for scale in citation.get("scales", {}).values():
                add("scales", scale)
    elif section in ("constants", "notations"):
        add("references", table.get("reference"))
        for constant in table.get("constants", ()):
            add("constants", constant)
    elif section == "trade_terms":
        for meaning in table["meanings"]:
            add("kinds", meaning["kind"])
            for source in meaning.get("sources", ()):
                add("references", source)
    elif section == "kinds":
        add("kinds", table["specialization_of"])
    elif section == "cross_checks":
        for case in table["cases"]:
            add("formulations", case["formulation"])
    elif section == "relations":
        add("formulations", table["subject"])
        add("formulations", table["object"])
        add("references", table["citation"])
    elif section == "scales":
        for kind in table["kinds"]:
            add("kinds", kind)
        add("scales", table.get("reference_scale"))
        add("scales", table.get("base"))
        add("references", table.get("reference"))
    return found


def _closure(name: str, requires: Mapping[str, tuple[str, ...]]) -> set[str]:
    seen: set[str] = set()
    pending = list(requires.get(name, ()))
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(requires.get(current, ()))
    return seen


def _used_families(
    name: str,
    data: Mapping[str, Mapping[str, Any]],
    owners: Mapping[tuple[str, str], str | None],
) -> dict[str, tuple[str, str, str, str]]:
    """Families an entry of ``name`` refers to, with one example of use."""
    used: dict[str, tuple[str, str, str, str]] = {}
    for (section, key), owner in owners.items():
        if owner != name:
            continue
        for target in sorted(_references(section, data[section][key])):
            if target not in owners:
                continue  # a QUDT kind, or unknown: the builder says so
            other = owners[target]
            if other == name:
                continue
            if other is None:
                msg = (
                    f"catalog {name}: {section}.{key} uses {target[0]}.{target[1]} "
                    "from a document without [catalog] header"
                )
                raise CatalogError(msg)
            used.setdefault(other, (section, key, *target))
    return used


def _minimal(used: set[str], requires: Mapping[str, tuple[str, ...]]) -> list[str]:
    """The used families not already brought by another used family."""
    return sorted(
        u for u in used if not any(u in _closure(v, requires) for v in used if v != u)
    )


def _check_requires(headers: Mapping[str, dict[str, Any]]) -> None:
    """Required families are loaded, and requires form no cycle."""
    requires = {name: h["requires"] for name, h in headers.items()}
    for name, needed in requires.items():
        for other in needed:
            if other not in requires:
                msg = f"catalog {name}: requires unknown family {other!r}"
                raise CatalogError(msg)
        if name in _closure(name, requires):
            msg = f"catalog {name}: requires form a cycle"
            raise CatalogError(msg)


def _check_families(
    headers: Mapping[str, dict[str, Any]],
    data: Mapping[str, Mapping[str, Any]],
    owners: Mapping[tuple[str, str], str | None],
) -> None:
    """Each family uses only what it requires, and all that it requires."""
    requires = {name: h["requires"] for name, h in headers.items()}
    for name in headers:
        if not any(owner == name for owner in owners.values()):
            continue  # an aggregate: requires only
        used = _used_families(name, data, owners)
        brought = _closure(name, requires)
        for other, (section, key, s2, k2) in sorted(used.items()):
            if other not in brought:
                msg = (
                    f"catalog {name}: {section}.{key} uses {s2}.{k2} from family "
                    f"{other}; add it to requires"
                )
                raise CatalogError(msg)
        for other in requires[name]:
            if not ({other} | _closure(other, requires)) & set(used):
                msg = (
                    f"catalog {name}: requires {other} but uses nothing from it; "
                    f"requires = {_minimal(set(used), requires)}"
                )
                raise CatalogError(msg)


def load_catalog(sources: Iterable[Source]) -> Catalog:
    """Build a catalog from TOML documents, merged section by section.

    Parameters
    ----------
    sources : iterable of str or path-like
        TOML texts, or paths to TOML files, with an optional ``[catalog]``
        header (name, format, requires...) and the sections ``kinds``,
        ``references``, ``constants``, ``notations``, ``trade_terms``,
        ``scales``, ``formulations``, ``relations`` and ``cross_checks``
        (all optional). A document with a header is a family: its entries
        may refer only to its own entries and to those of the families it
        requires, and every family it requires must be used.

    Returns
    -------
    Catalog
        The validated catalog.

    Raises
    ------
    CatalogError
        If a document is not valid TOML, an entry or family is defined
        twice, or any check fails; the message names the faulty entry.
    """
    data: dict[str, dict[str, Any]] = {section: {} for section in _SECTIONS}
    owners: dict[tuple[str, str], str | None] = {}
    headers: dict[str, dict[str, Any]] = {}
    for number, source in enumerate(sources, start=1):
        label, document = _read(number, source)
        name = None
        if _HEADER in document:
            header = _header(label, document.pop(_HEADER))
            name = header["name"]
            if name in headers:
                msg = f"{label}: family {name} defined twice"
                raise CatalogError(msg)
            headers[name] = header
        unknown = sorted(set(document) - set(_SECTIONS))
        if unknown:
            msg = f"{label}: unknown sections: {', '.join(unknown)}"
            raise CatalogError(msg)
        for section, entries in document.items():
            twice = sorted(set(entries) & set(data[section]))
            if twice:
                msg = f"{section}: defined twice: {', '.join(twice)}"
                raise CatalogError(msg)
            data[section].update(entries)
            owners.update(((section, key), name) for key in entries)
    _check_requires(headers)
    built = _Builder(data, owners).build()
    _check_families(headers, data, owners)
    families = {
        name: Family(
            name=name,
            label=h["label"] or name,
            requires=h["requires"],
            matches=_matches(f"[{_HEADER}] {name}", h["matches"]),
            keywords=_keywords(f"[{_HEADER}] {name}.keywords", h["keywords"]),
            contents=MappingProxyType(
                {
                    section: tuple(
                        k for (s, k), o in owners.items() if s == section and o == name
                    )
                    for section in _SECTIONS
                }
            ),
        )
        for name, h in headers.items()
    }
    return dataclasses.replace(
        built,
        families=MappingProxyType(families),
        links=_links(data, owners, headers, built),
    )


def _links(
    data: Mapping[str, Mapping[str, Any]],
    owners: Mapping[tuple[str, str], str | None],
    headers: Mapping[str, dict[str, Any]],
    built: Catalog,
) -> Mapping[str, tuple[str, ...]]:
    """For each entry, the existing entries it refers to (``section.key``).

    A formulation also refers to the kinds, scales and units of its
    variables and to its constants as built: a composition writes none, it
    takes them from its parts. It refers to the units of its constants and
    to the declared units of its coefficients (added or stated, never
    inferred); a constant or a scale to its unit. Units were checked
    against the semantic catalog when built. The family check reads the
    written tables only (:func:`_references`): units belong to no family.
    """
    links: dict[str, tuple[str, ...]] = {}
    for section, key in owners:
        references = _references(section, data[section][key])
        if section == "formulations":
            formulation = built.formulations[key]
            for variable in (formulation.output, *formulation.inputs):
                references.add(("kinds", variable.kind))
                references.add(("units", variable.unit))
                if variable.scale is not None:
                    references.add(("scales", variable.scale.key))
            for coefficient in formulation.coefficients:
                if coefficient.unit is not None:
                    references.add(("units", coefficient.unit))
            for constant in formulation.constants:
                references.add(("constants", constant.key))
                references.add(("units", constant.unit))
        elif section == "constants":
            references.add(("units", built.constants[key].unit))
        elif section == "scales":
            scale_unit = built.scales[key].unit
            if scale_unit is not None:
                references.add(("units", scale_unit))
        targets = sorted(references)
        found = tuple(
            f"{s}.{k}"
            for s, k in targets
            if (s, k) in owners or (s == "kinds" and k in built.kinds) or s == "units"
        )
        if found:
            links[f"{section}.{key}"] = found
    for name, header in headers.items():
        if header["requires"]:
            links[f"families.{name}"] = tuple(
                f"families.{r}" for r in header["requires"]
            )
    return MappingProxyType(links)


def _bundled() -> dict[str, tuple[str, tuple[str, ...]]]:
    """The bundled families: name to (text, requires)."""
    folder = files("nomogram") / "data" / "catalog"
    found = {}
    entries = sorted(
        (e for e in folder.iterdir() if e.name.endswith(".toml")), key=lambda e: e.name
    )
    for entry in entries:
        text = entry.read_text(encoding="utf-8")
        header = _header(entry.name, tomllib.loads(text).get(_HEADER))
        found[header["name"]] = (text, header["requires"])
    return found


def catalog(*families: str, extra: Iterable[Source] = ()) -> Catalog:
    """Return a catalog of bundled families, read and validated once.

    Parameters
    ----------
    *families : str
        Names of the bundled families to load, with the families they
        require; all of them by default.
    extra : iterable of path-like
        Personal catalogs, loaded in addition: TOML files with a
        ``[catalog]`` header; their keys must start with their family
        name and a colon (``"mylab:buck1996_corrected"``), and the bundled
        families they require are loaded too.

    Returns
    -------
    Catalog
        Formulations, references, constants, notations, trade terms,
        scales, relations, cross-checks and families.
    """
    return _catalog(tuple(sorted(set(families))), tuple(os.fspath(p) for p in extra))


@lru_cache(maxsize=16)
def _catalog(families: tuple[str, ...], extra: tuple[str, ...]) -> Catalog:
    bundled = _bundled()
    personal = [_read(0, Path(path)) for path in extra]
    wanted = set(families) or set(bundled)
    for label, document in personal:
        header = _header(label, document.get(_HEADER))
        if header["name"] in bundled:
            msg = f"{label}: {header['name']} is the name of a bundled family"
            raise CatalogError(msg)
        prefix = f"{header['name']}:"
        for section in _SECTIONS:
            for key in document.get(section, {}):
                if not key.startswith(prefix):
                    msg = f"{label}: {section}.{key} must start with {prefix!r}"
                    raise CatalogError(msg)
        wanted |= {r for r in header["requires"] if r in bundled}
    unknown = sorted(wanted - set(bundled))
    if unknown:
        msg = f"unknown families: {', '.join(unknown)}"
        raise CatalogError(msg)
    requires = {name: required for name, (_, required) in bundled.items()}
    for name in list(wanted):
        wanted |= _closure(name, requires) & set(bundled)
    texts: list[Source] = [bundled[name][0] for name in sorted(wanted)]
    return load_catalog([*texts, *(Path(path) for path in extra)])


def describe(source: Source) -> str:
    """The ``[catalog]`` header a TOML file needs, its requires computed.

    The file is read with all the bundled families, and its requires are
    the families its entries use (those already brought by another one
    left out).

    Parameters
    ----------
    source : path-like
        The TOML file.

    Returns
    -------
    str
        The header, to copy into the file.
    """
    path = Path(source)
    _, document = _read(0, path)
    current = document.pop(_HEADER, None) or {}
    name = current.get("name") or path.stem
    data: dict[str, dict[str, Any]] = {section: {} for section in _SECTIONS}
    owners: dict[tuple[str, str], str | None] = {}
    requires: dict[str, tuple[str, ...]] = {}
    documents = [
        (n, tomllib.loads(text)) for n, (text, _) in _bundled().items() if n != name
    ]
    for family, content in [*documents, (name, document)]:
        header = content.pop(_HEADER, None) or {}
        requires[family] = tuple(header.get("requires", ()))
        for section in _SECTIONS:
            entries = content.get(section, {})
            data[section].update(entries)
            owners.update(((section, key), family) for key in entries)
    used = set(_used_families(name, data, owners))
    has_entries = any(document.get(section) for section in _SECTIONS)
    # An aggregate holds no entry: its requires are its own choice.
    needed = (
        _minimal(used, requires) if has_entries else list(current.get("requires", ()))
    )
    lines = [
        f"[{_HEADER}]",
        f'name = "{name}"',
        f'label = "{current.get("label") or name}"',
        f"format = {FORMAT}",
        "requires = [" + ", ".join(f'"{r}"' for r in needed) + "]",
    ]
    return "\n".join(lines) + "\n"


def check(source: Source) -> str:
    """Observations on the formulations of a catalog file, before a review.

    The file is loaded with the bundled families (as a personal catalog
    when it is not one of them): identical formulations are refused at
    that point. For each of its formulations, the report lists those of
    the same form and the deviations observed against every formulation
    of the same kind (:func:`nomogram.relations.report`).

    Parameters
    ----------
    source : path-like
        The TOML file.

    Returns
    -------
    str
        The report, as plain text.

    Raises
    ------
    CatalogError
        If the file, loaded with the bundled families, is not valid.
    """
    path = Path(source).resolve()
    folder = files("nomogram") / "data" / "catalog"
    bundled = {Path(str(e)).resolve() for e in folder.iterdir()}
    loaded = catalog() if path in bundled else catalog(extra=[path])
    _, document = _read(0, path)
    return report(loaded, list(document.get("formulations", {})))


_WIKIDATA = "http://www.wikidata.org/entity/"


def _indicators(loaded: Catalog) -> list[tuple[str, str, int, int]]:
    """(goal, indicator, count, total) for each indicator of the design goals.

    Kinds "used" are those of the formulations' outputs and inputs; an
    input is "on a conventional scale" when its kind, or a kind it
    specializes, is one a scale of the catalog applies to.
    """
    formulations = list(loaded.formulations.values())
    computed = Counter(f.output.kind for f in formulations)
    used = {f.output.kind for f in formulations}
    used |= {v.kind for f in formulations for v in f.inputs}

    def lineage(name: str) -> list[QuantityKind]:
        # A QUDT kind may specialize one outside the bundled subset.
        found = [loaded.kinds[name]]
        while found[-1].specialization_of in loaded.kinds:
            found.append(loaded.kinds[str(found[-1].specialization_of)])
        return found

    scaled = {k for s in loaded.scales.values() for k in s.kinds}
    on_scale = [
        v
        for f in formulations
        for v in f.inputs
        if any(k.name in scaled for k in lineage(v.kind))
    ]
    references = list(loaded.references.values())

    def linked(matches: Iterable[ExternalMatch]) -> bool:
        return any(m.target.startswith(_WIKIDATA) for m in matches)

    alternatives = "1. Alternatives side by side"
    stated = "2. Validity, scale and sources stated, never invented"
    shared = "5. Linked to shared vocabularies"
    return [
        (
            alternatives,
            "quantity kinds computed by several formulations",
            sum(n > 1 for n in computed.values()),
            len(computed),
        ),
        (
            stated,
            "formulations with a validity domain",
            sum(
                bool(f.domains) or any(p.formulation.domains for p in f.parts)
                for f in formulations
            ),
            len(formulations),
        ),
        (
            stated,
            "inputs on a conventional scale with their scale recorded",
            sum(v.scale is not None for v in on_scale),
            len(on_scale),
        ),
        (
            stated,
            "references checked against the source",
            sum(r.status is ReferenceStatus.VERIFIED for r in references),
            len(references),
        ),
        (
            shared,
            "quantity kinds used that are QUDT kinds or specialize one",
            sum(any(q.origin == "qudt" for q in lineage(k)) for k in used),
            len(used),
        ),
        (
            shared,
            "quantity kinds used with a CF standard name",
            sum(bool(loaded.kinds[k].cf_standard_names) for k in used),
            len(used),
        ),
        (
            shared,
            "quantity kinds used with a Wikidata link",
            sum(linked(loaded.kinds[k].matches) for k in used),
            len(used),
        ),
        (
            shared,
            "formulations with a Wikidata link",
            sum(linked(f.matches) for f in formulations),
            len(formulations),
        ),
        (
            shared,
            "references with a Wikidata link",
            sum(linked(r.matches) for r in references),
            len(references),
        ),
    ]


def stats(loaded: Catalog | None = None) -> str:
    """The indicators of the design goals, as plain text.

    The design goals (AGENTS.md) are rules, enforced by the loader and
    the tests, and indicators of how far the catalog covers them: each
    indicator counts what the catalog covers out of what it could cover.

    Parameters
    ----------
    loaded : Catalog, optional
        The catalog to measure; the bundled one by default.

    Returns
    -------
    str
        One line per indicator, under the goal it measures.
    """
    lines = ["Indicators of the design goals (AGENTS.md)"]
    goal = None
    for name, indicator, count, total in _indicators(loaded or catalog()):
        if name != goal:
            lines.append(name)
            goal = name
        lines.append(f"  {indicator}: {count} of {total}")
    return "\n".join(lines) + "\n"


def _verdicts(write: bool) -> str:
    """The verdicts on the relations of the bundled catalog, one per line."""
    loaded = catalog()
    lines = []
    if write:
        computed, reused = record(loaded)
        lines.append(f"registry written: {computed} computed, {reused} reused")
    for key in sorted(loaded.relations):
        found = verdict(loaded.relations[key], loaded)
        value = "" if found.value is None else f" {found.value:.4g} %"
        lines.append(f"{key}: {found.status}{value}")
    for key in sorted(loaded.cross_checks):
        check = loaded.cross_checks[key]
        agreeing = sum(r.agrees for r in replay(check, loaded))
        lines.append(
            f"{key}: {agreeing} of {len(check.cases)} cases agree with "
            f"{check.implementation} {check.version} (checked {check.checked})"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Command line: ``python -m nomogram.catalog describe|check FILE``, ``verify``, ``stats``."""
    parser = argparse.ArgumentParser(prog="python -m nomogram.catalog")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("describe", "print the header a catalog file needs"),
        ("check", "report on the formulations of a catalog file"),
    ):
        commands.add_parser(name, help=text).add_argument("file", type=Path)
    verify_command = commands.add_parser(
        "verify", help="verdicts on the relations of the bundled catalog"
    )
    verify_command.add_argument(
        "--record",
        action="store_true",
        help="compute what is missing and write the registry",
    )
    commands.add_parser(
        "stats", help="indicators of the design goals for the bundled catalog"
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "verify":
            sys.stdout.write(_verdicts(arguments.record))
            return 0
        if arguments.command == "stats":
            sys.stdout.write(stats())
            return 0
        action = describe if arguments.command == "describe" else check
        sys.stdout.write(action(arguments.file))
    except CatalogError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
