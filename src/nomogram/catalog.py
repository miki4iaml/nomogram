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

import datetime
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Any

import pint

from nomogram.expression import ExpressionError
from nomogram.model import (
    Coefficient,
    DomainBasis,
    Formulation,
    Notation,
    PhysicalConstant,
    Reference,
    ReferenceStatus,
    TradeMeaning,
    TradeTerm,
    ValidityDomain,
    Variable,
)
from nomogram.semantics import (
    ExternalMatch,
    MatchRelation,
    QuantityKind,
    semantic_catalog,
)

__all__ = ["Catalog", "CatalogError", "catalog", "load_catalog"]

_SECTIONS = (
    "kinds",
    "references",
    "constants",
    "notations",
    "trade_terms",
    "formulations",
)


class CatalogError(ValueError):
    """The catalog is invalid; the message names the faulty entry."""


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
    """

    kinds: Mapping[str, QuantityKind]
    formulations: Mapping[str, Formulation]
    references: Mapping[str, Reference]
    constants: Mapping[str, PhysicalConstant]
    notations: Mapping[str, Notation]
    trade_terms: Mapping[str, TradeTerm]

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


class _Builder:
    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data
        self.semantics = semantic_catalog()
        self.kinds: dict[str, QuantityKind] = dict(self.semantics.quantity_kinds)
        self.references: dict[str, Reference] = {}
        self.constants: dict[str, PhysicalConstant] = {}

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

    def variable(self, where: str, table: Any) -> Variable:
        f = _fields(where, table, ("identifier", "kind", "unit", "description"))
        kind = self.kind(f"{where}.kind", f["kind"])
        unit = self.unit(f"{where}.unit", f["unit"])
        if unit not in kind.applicable_units:
            msg = f"{where}.unit: {unit} does not apply to {kind.name}"
            raise CatalogError(msg)
        return Variable(f["identifier"], kind.name, unit, f["description"])

    def coefficients(self, where: str, table: Any) -> tuple[Coefficient, ...]:
        result = []
        for identifier, value in (table or {}).items():
            if isinstance(value, dict):
                f = _fields(
                    f"{where}.{identifier}", value, ("value",), ("unit", "note")
                )
                unit = f["unit"]
                if unit is not None:
                    unit = self.unit(f"{where}.{identifier}.unit", unit)
                result.append(
                    Coefficient(identifier, float(f["value"]), unit, f["note"])
                )
            else:
                result.append(Coefficient(identifier, float(value), None, None))
        return tuple(result)

    def domains(
        self, where: str, items: Any, inputs: tuple[Variable, ...]
    ) -> tuple[ValidityDomain, ...]:
        names = {v.identifier for v in inputs}
        result = []
        for i, item in enumerate(items or ()):
            w = f"{where}[{i}]"
            f = _fields(w, item, ("basis", "bounds"), ("criterion", "reference"))
            bounds = {}
            for identifier, interval in f["bounds"].items():
                if identifier not in names:
                    msg = f"{w}.bounds: {identifier!r} is not an input"
                    raise CatalogError(msg)
                low, high = (float(x) for x in interval)
                if not low < high:
                    msg = f"{w}.bounds.{identifier}: empty interval"
                    raise CatalogError(msg)
                bounds[identifier] = (low, high)
            result.append(
                ValidityDomain(
                    basis=_enum(f"{w}.basis", DomainBasis, f["basis"]),
                    bounds=MappingProxyType(bounds),
                    criterion=f["criterion"],
                    reference=self.optional_reference(f"{w}.reference", f["reference"]),
                )
            )
        return tuple(result)

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
                "accuracy",
                "references",
                "note",
                "matches",
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
        formulation = Formulation(
            key=key,
            label=f["label"],
            output=output,
            inputs=inputs,
            coefficients=self.coefficients(f"{where}.coefficients", f["coefficients"]),
            constants=tuple(constants),
            expression=f["expression"],
            fixed_units=bool(f["fixed_units"]),
            domains=self.domains(f"{where}.domains", f["domains"], inputs),
            accuracy=f["accuracy"],
            references=tuple(
                self.reference(f"{where}.references", r) for r in f["references"] or ()
            ),
            note=f["note"],
            matches=_matches(where, f["matches"]),
        )
        self.check(where, formulation)
        return formulation

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

    def build(self) -> Catalog:
        self.build_kinds()
        self.build_references()
        self.build_constants()
        notations = self.build_notations()
        trade_terms = self.build_trade_terms()
        formulations = {
            key: self.formulation(key, table)
            for key, table in self.data["formulations"].items()
        }
        return Catalog(
            kinds=MappingProxyType(self.kinds),
            formulations=MappingProxyType(formulations),
            references=MappingProxyType(self.references),
            constants=MappingProxyType(self.constants),
            notations=MappingProxyType(notations),
            trade_terms=MappingProxyType(trade_terms),
        )


def load_catalog(sources: Iterable[str]) -> Catalog:
    """Build a catalog from TOML texts, merged section by section.

    Parameters
    ----------
    sources : iterable of str
        TOML documents with the sections ``kinds``, ``references``,
        ``constants``, ``notations``, ``trade_terms`` and ``formulations``
        (all optional).

    Returns
    -------
    Catalog
        The validated catalog.

    Raises
    ------
    CatalogError
        If a document is not valid TOML, an entry is defined twice, or any
        check fails; the message names the faulty entry.
    """
    data: dict[str, dict[str, Any]] = {section: {} for section in _SECTIONS}
    for number, text in enumerate(sources, start=1):
        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            msg = f"document {number}: invalid TOML: {exc}"
            raise CatalogError(msg) from None
        unknown = sorted(set(document) - set(_SECTIONS))
        if unknown:
            msg = f"document {number}: unknown sections: {', '.join(unknown)}"
            raise CatalogError(msg)
        for section, entries in document.items():
            twice = sorted(set(entries) & set(data[section]))
            if twice:
                msg = f"{section}: defined twice: {', '.join(twice)}"
                raise CatalogError(msg)
            data[section].update(entries)
    return _Builder(data).build()


@lru_cache(maxsize=1)
def catalog() -> Catalog:
    """Return the bundled catalog, read and validated once.

    Returns
    -------
    Catalog
        Formulations, references, constants, notations and trade terms.
    """
    folder = files("nomogram") / "data" / "catalog"
    texts = [
        entry.read_text(encoding="utf-8")
        for entry in sorted(folder.iterdir(), key=lambda e: e.name)
        if entry.name.endswith(".toml")
    ]
    return load_catalog(texts)
