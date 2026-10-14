# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Quantity kinds, units and CF standard names, from bundled QUDT and CF subsets.

nomogram does not build its own ontology. It bundles a frozen subset of
`QUDT <https://qudt.org/>`_ (quantity kinds and unit definitions, CC BY
4.0) and of the `CF standard name table <https://cfconventions.org/>`_
(CC0 1.0), extracted at development time by
``scripts/extract_semantics.py``. Nothing is fetched at run time.

On top of QUDT, nomogram states the scale type of each kind and whether
it is a difference (QUDT's *delta quantity*, OM's ``Measure``) or a point;
the scale type decides which units apply (offset units only for
interval-scale kinds). Links to external vocabularies (Wikidata...) are
:class:`ExternalMatch` objects carrying a SKOS relation and the date they
were last verified. ``docs/rosetta.md`` maps this vocabulary.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from importlib.resources import files
from types import MappingProxyType
from typing import Any

from nomogram.units import ScaleType

__all__ = [
    "CFStandardName",
    "ExternalMatch",
    "MatchRelation",
    "QuantityKind",
    "SemanticCatalog",
    "UnitDefinition",
    "semantic_catalog",
]

_DIMENSION_VECTOR = re.compile(
    r"^A(-?\d+)E(-?\d+)L(-?\d+)I(-?\d+)M(-?\d+)H(-?\d+)T(-?\d+)D([01])$"
)

#: Base dimensions of a QUDT dimension vector, in order.
_BASE_DIMENSIONS = (
    "amount_of_substance",
    "electric_current",
    "length",
    "luminous_intensity",
    "mass",
    "temperature",
    "time",
)


class MatchRelation(Enum):
    """SKOS mapping relation between a nomogram object and an external one."""

    EXACT = "exact"
    CLOSE = "close"
    BROAD = "broad"
    NARROW = "narrow"

    @property
    def skos(self) -> str:
        """IRI of the corresponding SKOS property."""
        return f"http://www.w3.org/2004/02/skos/core#{self.value}Match"


@dataclass(frozen=True)
class ExternalMatch:
    """Link from a nomogram object to an object of an external vocabulary.

    Attributes
    ----------
    target : str
        IRI of the external object, for example a Wikidata entity.
    relation : MatchRelation
        How close the two objects are. Links imported from QUDT's
        ``wikidataMatch``, a plain annotation, are close matches.
    verified : datetime.date
        Date the link was last verified against its source.
    """

    target: str
    relation: MatchRelation
    verified: datetime.date


def _dimensions(vector: str) -> Mapping[str, int]:
    match = _DIMENSION_VECTOR.match(vector)
    if match is None:
        msg = f"invalid QUDT dimension vector: {vector!r}"
        raise ValueError(msg)
    exponents = (int(e) for e in match.groups()[:7])
    return MappingProxyType(
        {d: e for d, e in zip(_BASE_DIMENSIONS, exponents, strict=True) if e}
    )


@dataclass(frozen=True)
class QuantityKind:
    """A quantity kind, from QUDT or defined by nomogram, with its scale typing.

    Kinds defined by nomogram (absent from QUDT) specialize a QUDT kind
    and have no IRI yet: their local name is stable and will become the
    end of a persistent IRI once nomogram has one.

    Attributes
    ----------
    name : str
        Local name, for example ``"CelsiusTemperature"``.
    origin : str
        ``"qudt"`` or ``"nomogram"``.
    iri : str or None
        QUDT IRI; ``None`` for a kind defined by nomogram.
    label : str
        English label.
    dimension_vector : str
        QUDT dimension vector, for example ``"A0E0L0I0M0H1T0D0"``.
    specialization_of : str or None
        QUDT local name of the kind this one specializes.
    scale_type : ScaleType
        Scale of the kind's values (nomogram's addition).
    delta : bool
        Whether values are differences rather than points (nomogram's
        addition; QUDT's ``isDeltaQuantity`` is set on no kind).
    cf_standard_names : tuple of str
        CF standard names for this kind.
    applicable_units : tuple of str
        QUDT local names of the units that apply.
    added_units : tuple of str
        The applicable units QUDT does not declare, added by nomogram.
    matches : tuple of ExternalMatch
        Links to external vocabularies.
    """

    name: str
    origin: str
    iri: str | None
    label: str
    dimension_vector: str
    specialization_of: str | None
    scale_type: ScaleType
    delta: bool
    cf_standard_names: tuple[str, ...]
    applicable_units: tuple[str, ...]
    added_units: tuple[str, ...]
    matches: tuple[ExternalMatch, ...]

    @property
    def dimensions(self) -> Mapping[str, int]:
        """Non-zero exponents of the base dimensions, by dimension name."""
        return _dimensions(self.dimension_vector)


@dataclass(frozen=True)
class UnitDefinition:
    """A QUDT unit definition, with its pint expression.

    A value v in this unit is ``(v + offset) * multiplier`` in the coherent
    SI unit of the same dimension (QUDT's conversion rule).

    Attributes
    ----------
    name : str
        QUDT local name, for example ``"DEG_C"``.
    iri : str
        QUDT IRI.
    label : str
        QUDT English label.
    symbol : str or None
        QUDT symbol (the glyph).
    dimension_vector : str
        QUDT dimension vector.
    multiplier : float
        QUDT ``conversionMultiplier``.
    offset : float
        QUDT ``conversionOffset``; non-zero for offset units such as
        ``DEG_C``.
    ucum : str or None
        UCUM code.
    udunits : str or None
        UDUNITS code.
    pint : str
        Expression of the unit in pint, for example ``"degC"``.
    matches : tuple of ExternalMatch
        Links to external vocabularies.
    """

    name: str
    iri: str
    label: str
    symbol: str | None
    dimension_vector: str
    multiplier: float
    offset: float
    ucum: str | None
    udunits: str | None
    pint: str
    matches: tuple[ExternalMatch, ...]

    @property
    def dimensions(self) -> Mapping[str, int]:
        """Non-zero exponents of the base dimensions, by dimension name."""
        return _dimensions(self.dimension_vector)


@dataclass(frozen=True)
class CFStandardName:
    """A CF standard name and its canonical unit.

    Attributes
    ----------
    name : str
        The standard name, for example ``"relative_humidity"``.
    canonical_units : str
        CF canonical unit, in UDUNITS syntax (``"kg m-3"``).
    pint : str
        The same unit as a pint expression (``"kg * m ** -3"``).
    """

    name: str
    canonical_units: str
    pint: str


@dataclass(frozen=True)
class SemanticCatalog:
    """The bundled subsets, read-only.

    Attributes
    ----------
    quantity_kinds : mapping of str to QuantityKind
        By QUDT local name.
    units : mapping of str to UnitDefinition
        By QUDT local name.
    cf_standard_names : mapping of str to CFStandardName
        By standard name.
    qudt_version : str
        QUDT release the subset was extracted from.
    cf_version : str
        CF standard name table version.
    extracted : datetime.date
        Extraction date.
    """

    quantity_kinds: Mapping[str, QuantityKind]
    units: Mapping[str, UnitDefinition]
    cf_standard_names: Mapping[str, CFStandardName]
    qudt_version: str
    cf_version: str
    extracted: datetime.date


def _matches(items: list[dict[str, str]]) -> tuple[ExternalMatch, ...]:
    return tuple(
        ExternalMatch(
            target=item["target"],
            relation=MatchRelation(item["relation"]),
            verified=datetime.date.fromisoformat(item["verified"]),
        )
        for item in items
    )


def _kind(name: str, data: dict[str, Any]) -> QuantityKind:
    return QuantityKind(
        name=name,
        origin="qudt",
        iri=data["iri"],
        label=data["label"],
        dimension_vector=data["dimension_vector"],
        specialization_of=data["specialization_of"],
        scale_type=ScaleType(data["scale_type"]),
        delta=data["delta"],
        cf_standard_names=tuple(data["cf_standard_names"]),
        applicable_units=tuple(data["applicable_units"]),
        added_units=tuple(data["added_units"]),
        matches=_matches(data["matches"]),
    )


def _unit(name: str, data: dict[str, Any]) -> UnitDefinition:
    return UnitDefinition(
        name=name,
        iri=data["iri"],
        label=data["label"],
        symbol=data["symbol"],
        dimension_vector=data["dimension_vector"],
        multiplier=data["multiplier"],
        offset=data["offset"],
        ucum=data["ucum"],
        udunits=data["udunits"],
        pint=data["pint"],
        matches=_matches(data["matches"]),
    )


@lru_cache(maxsize=1)
def semantic_catalog() -> SemanticCatalog:
    """Return the bundled QUDT and CF subsets.

    The file is read once; the catalog is immutable and shared.

    Returns
    -------
    SemanticCatalog
        Quantity kinds, unit definitions and CF standard names.
    """
    resource = files("nomogram") / "data" / "semantics.json"
    data = json.loads(resource.read_text(encoding="utf-8"))
    sources = data["sources"]
    return SemanticCatalog(
        quantity_kinds=MappingProxyType(
            {n: _kind(n, d) for n, d in data["quantity_kinds"].items()}
        ),
        units=MappingProxyType({n: _unit(n, d) for n, d in data["units"].items()}),
        cf_standard_names=MappingProxyType(
            {
                n: CFStandardName(n, d["canonical_units"], d["pint"])
                for n, d in data["cf_standard_names"].items()
            }
        ),
        qudt_version=sources["qudt"]["version"],
        cf_version=sources["cf_standard_names"]["version"],
        extracted=datetime.date.fromisoformat(sources["extracted"]),
    )
