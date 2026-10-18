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
import dataclasses
import datetime
import os
import sys
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pint

from nomogram.dimensions import DimensionError
from nomogram.expression import (
    LATEX_COMMANDS,
    ExpressionError,
    latex_commands,
    parse_expression,
)
from nomogram.model import (
    Citation,
    Coefficient,
    ConventionalScale,
    DomainBasis,
    Formulation,
    Notation,
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
from nomogram.relations import match_inputs
from nomogram.semantics import (
    ExternalMatch,
    MatchRelation,
    QuantityKind,
    semantic_catalog,
)

__all__ = [
    "FORMAT",
    "Catalog",
    "CatalogError",
    "Family",
    "catalog",
    "describe",
    "load_catalog",
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

    def formulations_of(self, kind: str) -> tuple[Formulation, ...]:
        """The alternative formulations computing a quantity kind."""
        return tuple(f for f in self.formulations.values() if f.output.kind == kind)


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
    where: str, coefficients: tuple[Coefficient, ...], citations: tuple[Citation, ...]
) -> tuple[Coefficient, ...]:
    """Coefficients with the units their citations state."""
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
        if stated and coefficient.unit is not None:
            msg = f"{where}: the unit of {coefficient.identifier} is both added and stated"
            raise CatalogError(msg)
        if stated:
            coefficient = dataclasses.replace(
                coefficient, unit=stated.pop(), unit_basis=UnitBasis.STATED
            )
        result.append(coefficient)
    return tuple(result)


def _stated_scales(
    where: str, inputs: tuple[Variable, ...], citations: tuple[Citation, ...]
) -> tuple[Variable, ...]:
    """Inputs with the temperature scales their citations state."""
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
        if stated and variable.scale is not None:
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
                where, table, ("label", "specialization_of"), ("description", "matches")
            )
            if name in self.kinds:
                msg = f"{where}: already a QUDT kind"
                raise CatalogError(msg)
            parent = self.kinds.get(f["specialization_of"])
            if parent is None:
                msg = f"{where}.specialization_of: unknown kind {f['specialization_of']!r}"
                raise CatalogError(msg)
            self.kinds[name] = QuantityKind(
                name=name,
                origin="nomogram",
                iri=None,
                label=f["label"],
                dimension_vector=parent.dimension_vector,
                specialization_of=parent.name,
                scale_type=parent.scale_type,
                delta=parent.delta,
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
                ("matches",),
            )
            self.constants[key] = PhysicalConstant(
                key=key,
                identifier=f["identifier"],
                value=float(f["value"]),
                unit=self.unit(f"{where}.unit", f["unit"]),
                description=f["description"],
                reference=self.reference(f"{where}.reference", f["reference"]),
                matches=_matches(where, f["matches"]),
            )

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
        # Reference scales first: derived scales refer to them.
        order = sorted(tables, key=lambda k: "reference_scale" in tables[k])
        reference_of: dict[str, str] = {}
        for key in order:
            where = f"scales.{key}"
            f = _fields(
                where,
                tables[key],
                ("label", "kinds"),
                ("reference_scale", "unit", "differences", "reference"),
            )
            kinds = tuple(self.kind(f"{where}.kinds", k).name for k in f["kinds"])
            if not kinds:
                msg = f"{where}.kinds: at least one quantity kind"
                raise CatalogError(msg)
            parent = f["reference_scale"]
            points: tuple[float, ...] = ()
            difference: tuple[float, ...] = ()
            unit = None
            if parent is None:
                if f["differences"] is not None or f["unit"] is not None:
                    msg = f"{where}: a reference scale has no conversion table"
                    raise CatalogError(msg)
                for kind in kinds:
                    if kind in reference_of:
                        msg = (
                            f"{where}: {kind} already has a reference scale, "
                            f"{reference_of[kind]}"
                        )
                        raise CatalogError(msg)
                    reference_of[kind] = key
            else:
                base = self.scales.get(parent)
                if base is None or not base.is_reference:
                    msg = (
                        f"{where}.reference_scale: {parent!r} is not a reference scale"
                    )
                    raise CatalogError(msg)
                outside = sorted(set(kinds) - set(base.kinds))
                if outside:
                    msg = f"{where}.kinds: {', '.join(outside)} not covered by {parent}"
                    raise CatalogError(msg)
                if f["unit"] is None or not f["differences"]:
                    msg = f"{where}: a derived scale needs a unit and differences"
                    raise CatalogError(msg)
                unit = self.unit(f"{where}.unit", f["unit"])
                pairs = [tuple(float(x) for x in row) for row in f["differences"]]
                if any(len(row) != 2 for row in pairs):
                    msg = (
                        f"{where}.differences: expected [reference value, "
                        "reference value - value] pairs"
                    )
                    raise CatalogError(msg)
                points = tuple(row[0] for row in pairs)
                if any(b <= a for a, b in pairwise(points)):
                    msg = f"{where}.differences: reference values must increase"
                    raise CatalogError(msg)
                difference = tuple(row[1] for row in pairs)
            self.scales[key] = ConventionalScale(
                key=key,
                label=f["label"],
                kinds=kinds,
                reference_scale=parent,
                unit=unit,
                points=points,
                difference=difference,
                reference=self.optional_reference(f"{where}.reference", f["reference"]),
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
                    Coefficient(identifier, float(f["value"]), unit, f["note"], basis)
                )
            else:
                result.append(Coefficient(identifier, float(value), None, None))
        return tuple(result)

    @staticmethod
    def bounds(
        where: str, table: Any, inputs: tuple[Variable, ...]
    ) -> Mapping[str, tuple[float, float]]:
        names = {v.identifier for v in inputs}
        bounds = {}
        for identifier, interval in table.items():
            if identifier not in names:
                msg = f"{where}: {identifier!r} is not an input"
                raise CatalogError(msg)
            low, high = (float(x) for x in interval)
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
    ) -> tuple[Citation, ...]:
        result = []
        seen = set()
        by_identifier = {v.identifier: v for v in inputs}
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
                    msg = f"{w}.scales: {identifier!r} is not an input"
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
        )
        formulation = Formulation(
            key=key,
            label=f["label"],
            output=output,
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
        for identifier, value in (f["at"] or {}).items():
            if identifier not in names:
                msg = f"{where}.at: {identifier!r} is not an input of {subject.key}"
                raise CatalogError(msg)
            at[identifier] = float(value)
        given = dict(f["given"] or {})
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
        return Relation(
            key=key,
            kind=kind,
            subject=subject.key,
            object=other.key,
            citation=self.reference(f"{where}.citation", f["citation"]),
            accuracy=None if f["accuracy"] is None else float(f["accuracy"]),
            at=MappingProxyType(at),
            bounds=bounds,
            given=MappingProxyType({k: str(v) for k, v in given.items()}),
            scale=scale,
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
        try:
            _ = formulation.output_factor
        except pint.errors.DimensionalityError as exc:
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
        formulations = {
            key: self.formulation(key, table)
            for key, table in self.data["formulations"].items()
        }
        relations = {
            key: self.relation(key, table, formulations)
            for key, table in self.data["relations"].items()
        }
        return Catalog(
            kinds=MappingProxyType(self.kinds),
            formulations=MappingProxyType(formulations),
            relations=MappingProxyType(relations),
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


def _references(section: str, table: Any) -> set[tuple[str, str]]:
    """The entries of other sections an entry refers to, by key.

    Called on validated data only: the builder has checked every field.
    """
    found: set[tuple[str, str]] = set()

    def add(target: str, value: Any) -> None:
        if isinstance(value, str):  # None when absent, a table for an inline notation
            found.add((target, value))

    if section == "formulations":
        for variable in (table["output"], *table["inputs"]):
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
    elif section == "trade_terms":
        for meaning in table["meanings"]:
            add("kinds", meaning["kind"])
            for source in meaning.get("sources", ()):
                add("references", source)
    elif section == "kinds":
        add("kinds", table["specialization_of"])
    elif section == "relations":
        add("formulations", table["subject"])
        add("formulations", table["object"])
        add("references", table["citation"])
    elif section == "scales":
        for kind in table["kinds"]:
            add("kinds", kind)
        add("scales", table.get("reference_scale"))
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
        ``scales`` and ``formulations`` (all optional). A document with a
        header is a family: its entries may refer only to its own entries
        and to those of the families it requires, and every family it
        requires must be used.

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
    return dataclasses.replace(built, families=MappingProxyType(families))


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
        scales and families.
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


def main(argv: list[str] | None = None) -> int:
    """Command line: ``python -m nomogram.catalog describe FILE``."""
    parser = argparse.ArgumentParser(prog="python -m nomogram.catalog")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "describe", help="print the header a catalog file needs"
    )
    command.add_argument("file", type=Path)
    arguments = parser.parse_args(argv)
    sys.stdout.write(describe(arguments.file))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
