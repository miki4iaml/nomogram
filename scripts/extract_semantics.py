# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Development tool: extract nomogram's subset of QUDT and CF standard names.

Reads a frozen release of QUDT (Turtle files) and of the CF standard name
table (XML), and writes ``src/nomogram/data/semantics.json``: the quantity
kinds, units and CF standard names nomogram uses, nothing more. The
package reads that file at run time with :mod:`importlib.resources`;
neither rdflib nor any network access is needed then.

Never edit ``semantics.json`` by hand: change the selection below and run
the script again. Sources (download them into a local folder first):

- QUDT 3.5.2 (CC BY 4.0),
  ``https://raw.githubusercontent.com/qudt/qudt-public-repo/v3.5.2/src/main/rdf/``
  + ``vocab/quantitykinds/VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl`` and
  ``vocab/unit/VOCAB_QUDT-UNITS-ALL.ttl``;
- CF standard name table 95 (CC0 1.0),
  ``https://cfconventions.org/Data/cf-standard-names/95/src/cf-standard-name-table.xml``.

Usage::

    uv run python scripts/extract_semantics.py --qudt-version 3.5.2 \\
        --kinds VOCAB_QUDT-QUANTITY-KINDS-ALL.ttl \\
        --units VOCAB_QUDT-UNITS-ALL.ttl \\
        --cf cf-standard-name-table.xml \\
        --output src/nomogram/data/semantics.json

What nomogram adds to the sources is stated here, not hidden in the data:
the scale type and the point/difference typing of each kind (QUDT
records it as ``isDeltaQuantity`` on a quantity in its context, not on
kinds), the link from each kind to CF
standard names, and the pint expression of each unit.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import xml.etree.ElementTree as ET  # parses a trusted, pinned CF release
from pathlib import Path
from typing import Any, Literal, NamedTuple

from rdflib import Graph, Namespace, URIRef

QUDT = Namespace("http://qudt.org/schema/qudt/")
QK = Namespace("http://qudt.org/vocab/quantitykind/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
RDFS_LABEL = URIRef("http://www.w3.org/2000/01/rdf-schema#label")

#: Links to CF standard names: the namespace of the NERC Vocabulary
#: Server, as nomogram.semantics.CF_NAMESPACE.
CF_NAMESPACE = "http://vocab.nerc.ac.uk/standard_name/"


class KindSpec(NamedTuple):
    """nomogram's additions to a QUDT quantity kind."""

    scale_type: str
    delta: bool
    #: CF standard names with their SKOS relation: "exact", "close", or
    #: "narrow" when the CF name is narrower (the temperature of air).
    cf_standard_names: tuple[tuple[str, str], ...] = ()
    #: Units QUDT does not declare for the kind, added by nomogram.
    added_units: tuple[str, ...] = ()
    #: Whether its units carry an offset (degC); by default, those of an
    #: interval scale do. An interval scale whose zero is a reference
    #: surface rather than a unit (altitude) takes multiplicative units;
    #: ``"any"`` takes both (a temperature point written in degC or in K).
    offset_units: bool | Literal["any"] | None = None


#: Quantity kinds kept, by QUDT local name.
KINDS: dict[str, KindSpec] = {
    "ThermodynamicTemperature": KindSpec(
        "ratio", delta=False, cf_standard_names=(("air_temperature", "narrow"),)
    ),
    # CF names a temperature by its medium, not by its scale: a variable
    # named air_temperature may be in degC, any unit convertible to the
    # canonical K being allowed (CF conventions, section 3.3). The air's
    # temperature is narrower than the kind; so is the air's pressure.
    "CelsiusTemperature": KindSpec(
        "interval", delta=False, cf_standard_names=(("air_temperature", "narrow"),)
    ),
    # A temperature point, never matched with air temperature. Empirical
    # formulas give it in degC; CF (its canonical unit) and the IFS give it
    # in K. QUDT has one kind for both, where the air temperature has two,
    # so it takes units with and without an offset.
    "DewPointTemperature": KindSpec(
        "interval",
        delta=False,
        cf_standard_names=(("dew_point_temperature", "exact"),),
        offset_units="any",
    ),
    # The parent of the dew point and of the wet-bulb temperature, under
    # which the catalog declares the frost point and the ice-bulb
    # temperature as their siblings: a frost point must not feed a dew
    # point input.
    "Temperature": KindSpec("interval", delta=False, offset_units="any"),
    # The temperature of a wet-bulb thermometer (psychrometer), in degC in
    # the formulas, in K for CF.
    "WetBulbTemperature": KindSpec(
        "interval",
        delta=False,
        cf_standard_names=(("wet_bulb_temperature", "exact"),),
        offset_units="any",
    ),
    "TemperatureDifference": KindSpec("ratio", delta=True),
    # ISO 80000 psi = x / x_sat, the mixing ratio over its saturation value:
    # the "relative humidity" r / r_sat of some textbooks (TEOS-10 3.40.2).
    # QUDT 3.5.2 declares the unit 1; a ratio, it takes % too.
    "RelativeMassRatioOfVapour": KindSpec(
        "ratio",
        delta=False,
        added_units=("PERCENT",),
    ),
    # p / p_sat over either phase, the parent of the relative humidity (with
    # respect to water, as QUDT defines it) under which the catalog declares
    # the relative humidity with respect to ice as its sibling: one must
    # not feed an input of the other. QUDT 3.5.2 gives it no unit; a ratio,
    # it takes 1 and %.
    "RelativePartialPressure": KindSpec(
        "ratio",
        delta=False,
        added_units=("UNITLESS", "PERCENT"),
    ),
    # CF's canonical unit for relative humidity is 1.
    "RelativeHumidity": KindSpec(
        "ratio",
        delta=False,
        cf_standard_names=(("relative_humidity", "exact"),),
        added_units=("UNITLESS",),
    ),
    "Pressure": KindSpec(
        "ratio", delta=False, cf_standard_names=(("air_pressure", "narrow"),)
    ),
    "VapourPressure": KindSpec(
        "ratio",
        delta=False,
        cf_standard_names=(("water_vapor_partial_pressure_in_air", "exact"),),
    ),
    "MassConcentrationOfWaterVapour": KindSpec(
        "ratio",
        delta=False,
        cf_standard_names=(("mass_concentration_of_water_vapor_in_air", "exact"),),
    ),
    # QUDT gives this kind no specializationOf MassRatio, so the mass
    # ratio units do not reach it; g/kg is its usual unit.
    "MassRatioOfWaterVapourToDryGas": KindSpec(
        "ratio",
        delta=False,
        cf_standard_names=(("humidity_mixing_ratio", "exact"),),
        added_units=("GM-PER-KiloGM", "KiloGM-PER-KiloGM"),
    ),
    # CF's canonical unit for specific humidity is 1.
    "SpecificHumidity": KindSpec(
        "ratio",
        delta=False,
        cf_standard_names=(("specific_humidity", "exact"),),
        added_units=("UNITLESS",),
    ),
    # Kept although nomogram does not use it as a kind: the term is
    # ambiguous across trades (see docs/rosetta.md).
    "AbsoluteHumidity": KindSpec("ratio", delta=False),
    # Energy per unit mass, in which latent heats are given; QUDT declares
    # J/kg for it. The parent of the geopotential (catalog), which CF
    # gives in m2 s-2: QUDT declares that unit for SpecificModulus only.
    "SpecificEnergy": KindSpec("ratio", delta=False, added_units=("M2-PER-SEC2",)),
    # Radio refractivity (ITU-R P.453): the refractive index, the parent of
    # the dimensionless kinds nomogram defines, and heights above the
    # surface (CF: "the vertical distance above the surface").
    "RefractiveIndex": KindSpec("ratio", delta=False),
    "DimensionlessRatio": KindSpec("ratio", delta=False),
    "Height": KindSpec("ratio", delta=False, cf_standard_names=(("height", "exact"),)),
    # Altitude: height above the geoid (CF), a reference surface fixed by
    # convention, hence an interval scale; QUDT's description leaves the
    # reference to the context. CF's height above mean sea level is close:
    # the time-mean sea surface, which the geoid approximates; ITU-R writes
    # "above sea level" for the altitude of the surface.
    "Altitude": KindSpec(
        "interval",
        delta=False,
        cf_standard_names=(
            ("altitude", "exact"),
            ("height_above_mean_sea_level", "close"),
        ),
        offset_units=False,
    ),
    # Salinity and chlorinity of sea water are mass fractions; QUDT has no
    # kind for either (nomogram defines them in the sea-water family). QUDT
    # 3.5.2 gives MassFraction FRACTION, PERCENT, UNITLESS and IU-PER-MilliGM;
    # CF writes salinities in 1e-3 (per mille) and g/kg, added here.
    "MassFraction": KindSpec(
        "ratio",
        delta=False,
        added_units=("PERMILLE", "GM-PER-KiloGM", "KiloGM-PER-KiloGM"),
    ),
    # Vapour pressure of sea water from its osmotic coefficient and the total
    # molality of dissolved species (Dickson et al. 2007).
    "OsmoticCoefficient": KindSpec("ratio", delta=False),
    "MolalityOfSolute": KindSpec("ratio", delta=False),
    # The definitions of WMO-No. 8, Annex 4.A: the mixing ratio, specific
    # humidity and vapour concentration from masses and a volume, the mole
    # fraction of water vapour from amounts of substance.
    "Mass": KindSpec("ratio", delta=False),
    "Volume": KindSpec("ratio", delta=False),
    "AmountOfSubstance": KindSpec("ratio", delta=False),
    "MoleFraction": KindSpec("ratio", delta=False),
    # Bechtold (2015): the density of moist air, which defines the virtual
    # temperature, and the total water mixing ratio of the equivalent
    # potential temperature, specialized in the catalog.
    "Density": KindSpec("ratio", delta=False),
    # WMO-No. 8: the psychrometer coefficient A, in K-1 (4.1, 4.2), and the
    # specific heats of dry air and water vapour of the wet-bulb
    # temperature (4.A.19).
    "InverseTemperature": KindSpec("ratio", delta=False),
    "SpecificHeatCapacityAtConstantPressure": KindSpec("ratio", delta=False),
    "MassRatio": KindSpec("ratio", delta=False),
    # Vertical coordinates: the parent of the geopotential height
    # (catalog), which must not feed an altitude input: the two differ by
    # 19 m at 11 km.
    "Length": KindSpec("ratio", delta=False),
    # The acceleration of free fall, local or conventional (g_n).
    "AccelerationOfGravity": KindSpec("ratio", delta=False),
    # A temperature difference per length, without a sign; the catalog
    # specializes it in two siblings, the lapse rate -dT/dz and dT/dz.
    "TemperatureGradient": KindSpec("ratio", delta=False),
    # The wind: the components of the velocity of the air, and its speed.
    # QUDT's Velocity is an exact match of LinearVelocity.
    "Velocity": KindSpec(
        "ratio",
        delta=False,
        cf_standard_names=(("eastward_wind", "narrow"), ("northward_wind", "narrow")),
    ),
    "Speed": KindSpec(
        "ratio", delta=False, cf_standard_names=(("wind_speed", "narrow"),)
    ),
    # The parent of the geodetic latitude (catalog), in normal gravity
    # formulas.
    "PlaneAngle": KindSpec("ratio", delta=False),
    # ISO 2533: the speed of sound (equation 21), the dynamic viscosity of
    # Sutherland (22), the kinematic viscosity (23) and the thermal
    # conductivity (24) of air. CF names the speed of sound by its medium.
    "SpeedOfSound": KindSpec(
        "ratio", delta=False, cf_standard_names=(("speed_of_sound_in_air", "narrow"),)
    ),
    "DynamicViscosity": KindSpec("ratio", delta=False),
    "KinematicViscosity": KindSpec("ratio", delta=False),
    "ThermalConductivity": KindSpec("ratio", delta=False),
    # The IFS: the parent of the square of the Brunt-Vaisala frequency
    # (catalog), in s-2.
    "InverseSquareTime": KindSpec("ratio", delta=False),
}

#: Units kept, by QUDT local name, with their pint expression.
UNITS: dict[str, str] = {
    "K": "K",
    "DEG_C": "degC",
    "DEG_F": "degF",
    "PA": "Pa",
    "HectoPA": "hPa",
    "KiloPA": "kPa",
    "GM-PER-M3": "g/m^3",
    "KiloGM-PER-M3": "kg/m^3",
    "GM-PER-KiloGM": "g/kg",
    "KiloGM-PER-KiloGM": "kg/kg",
    "PERCENT": "percent",
    "UNITLESS": "dimensionless",
    "J-PER-KiloGM-K": "J/(kg*K)",
    "PPM": "ppm",
    "PERMILLE": "permille",
    "MilliM_HG": "mmHg",
    "ATM": "atm",
    "MOL-PER-KiloGM": "mol/kg",
    "M": "m",
    "KiloM": "km",
    "KiloGM": "kg",
    "GM": "g",
    "M3": "m^3",
    "L": "L",
    "MOL": "mol",
    # Units of physical constants.
    "J-PER-K": "J/K",
    "J-SEC": "J*s",
    "M-PER-SEC": "m/s",
    "PER-MOL": "1/mol",
    "PER-K": "1/K",
    "J-PER-MOL-K": "J/(mol*K)",
    "W-PER-M2-K4": "W/(m^2*K^4)",
    "KiloGM-PER-MOL": "kg/mol",
    "J-PER-KiloGM": "J/kg",
    # ASHRAE (via PsychroLib): the coefficients of equations 33 and 35.
    "KiloJ-PER-KiloGM": "kJ/kg",
    "KiloJ-PER-KiloGM-K": "kJ/(kg*K)",
    # Vertical coordinates and the hydrostatic atmosphere: gravity, the
    # geopotential (CF writes m2 s-2), temperature gradients, and the foot
    # of pressure altitudes and flight levels.
    "M-PER-SEC2": "m/s^2",
    "M2-PER-SEC2": "m^2/s^2",
    "K-PER-M": "K/m",
    "FT": "ft",
    # Angles: the latitude, in radians where sin or cos take it.
    "RAD": "radian",
    "DEG": "degree",
    # ISO 2533 and the IFS: the viscosities, the thermal conductivity of
    # air, and the square of a frequency.
    "PA-SEC": "Pa*s",
    "M2-PER-SEC": "m^2/s",
    "W-PER-M-K": "W/(m*K)",
    "PER-SEC2": "1/s^2",
}

#: CF standard names of conventional scales (catalog `[scales]`), kept
#: in the frozen subset so that the catalog can check them.
SCALE_CF_NAMES: tuple[str, ...] = (
    "sea_water_knudsen_salinity",
    "sea_water_cox_salinity",
    "sea_water_practical_salinity",
    "sea_water_reference_salinity",
    "sea_water_absolute_salinity",
)

#: CF standard names of the quantity kinds the catalog declares (catalog
#: `[kinds]`), kept in the frozen subset so that the catalog can check
#: them.
LOCAL_KIND_CF_NAMES: tuple[str, ...] = (
    "virtual_temperature",
    "air_potential_temperature",
    "air_equivalent_potential_temperature",
    "air_density",
    "mole_fraction_of_water_vapor_in_air",
    "sea_water_salinity",
    "surface_altitude",
    # Vertical coordinates (atmosphere family).
    "geopotential",
    "geopotential_height",
    "atmosphere_layer_thickness_expressed_as_geopotential_height_difference",
    "air_temperature_lapse_rate",
    "surface_air_pressure",
    "air_pressure_at_mean_sea_level",
    "height_above_reference_ellipsoid",
    "geoid_height_above_reference_ellipsoid",
    "latitude",
    # Static stability (ECMWF IFS).
    "square_of_brunt_vaisala_frequency_in_air",
)

#: Symbols nomogram displays instead of QUDT's, with the reason.
SYMBOLS: dict[str, str] = {
    # QUDT writes "PPM"; the SI Brochure (9th ed., 5.4.7) and ITU-R P.453
    # (its N_wet in ppm) write "ppm", as does UCUM ("[ppm]").
    "PPM": "ppm",
    # QUDT writes the CJK sign U+4E00, a deliberate choice
    # (qudt/qudt-public-repo#712, where "1" and "-" were proposed); the SI
    # Brochure (9th ed., 2.3.3 and 5.4.7) gives the unit one the symbol 1,
    # rarely written.
    "UNITLESS": "1",
    # QUDT writes "/mol"; the SI Brochure (9th ed., table 1) writes mol⁻¹,
    # as does UCUM ("mol-1").
    "PER-MOL": "mol⁻¹",
    # Likewise "/K" for QUDT, K⁻¹ for the SI Brochure.
    "PER-K": "K⁻¹",
    # And "/s²" for QUDT, s⁻² for the SI Brochure.
    "PER-SEC2": "s⁻²",
}

#: QUDT's ``wikidataMatch`` is a plain annotation, not a SKOS mapping
#: property: its links are imported as close matches.
WIKIDATA_RELATION = "close"

#: UDUNITS names CF gives to angles of a direction: latitudes are in
#: degree_north, longitudes in degree_east (CF conventions, 4.1 and 4.2).
_UDUNITS_ALIASES: dict[str, str] = {"degree_north": "degree", "degree_east": "degree"}

_UDUNITS_FACTOR = re.compile(r"^([A-Za-z]+)(-?\d+)?$")
_UDUNITS_NUMBER = re.compile(r"^\d+(\.\d+)?([eE]-?\d+)?$")


def udunits_to_pint(expression: str) -> str:
    """Translate a CF canonical unit (UDUNITS syntax) into a pint expression.

    Only the syntax of CF canonical units is handled: factors separated by
    spaces, each a unit symbol with an optional integer exponent
    (``kg m-3``) or a number (``1e-3``), or ``1`` for dimensionless.

    Parameters
    ----------
    expression : str
        The canonical unit, for example ``"kg m-3"``.

    Returns
    -------
    str
        The pint expression, for example ``"kg * m ** -3"``.

    Raises
    ------
    ValueError
        If a factor is outside the handled syntax.
    """
    if expression.strip() == "1":
        return "dimensionless"
    factors = []
    for factor in expression.split():
        factor = _UDUNITS_ALIASES.get(factor, factor)
        if _UDUNITS_NUMBER.match(factor):
            factors.append(factor)  # a scale factor, such as 1e-3 (per mille)
            continue
        match = _UDUNITS_FACTOR.match(factor)
        if match is None:
            msg = f"unsupported UDUNITS factor: {factor!r}"
            raise ValueError(msg)
        symbol, exponent = match.groups()
        factors.append(symbol if exponent is None else f"{symbol} ** {exponent}")
    return " * ".join(factors)


def _value(graph: Graph, subject: URIRef, predicate: URIRef) -> str | None:
    values = sorted(str(o) for o in graph.objects(subject, predicate))
    return values[0] if values else None


def _local(iri: str | None) -> str | None:
    return None if iri is None else iri.rstrip("/").rsplit("/", 1)[-1]


def _english_label(graph: Graph, subject: URIRef) -> str:
    labels = list(graph.objects(subject, RDFS_LABEL))
    english = [str(o) for o in labels if getattr(o, "language", None) == "en"]
    plain = [str(o) for o in labels if getattr(o, "language", None) is None]
    candidates = sorted(english) or sorted(plain)
    if not candidates:
        msg = f"no label for {subject}"
        raise ValueError(msg)
    return candidates[0]


def _matches(wikidata: str | None, date: str) -> list[dict[str, str]]:
    if wikidata is None:
        return []
    return [{"target": wikidata, "relation": WIKIDATA_RELATION, "verified": date}]


def _require(graph: Graph, subject: URIRef) -> None:
    if (subject, None, None) not in graph:
        msg = f"not found in the source: {subject}"
        raise ValueError(msg)


def unit_kinds(graph: Graph) -> dict[str, set[str]]:
    """Quantity kinds each selected unit is declared for in QUDT."""
    kinds: dict[str, set[str]] = {}
    for name in UNITS:
        subject = UNIT[name]
        declared = set(graph.objects(subject, QUDT.unitForQuantityKind))
        declared |= set(graph.objects(subject, QUDT.hasQuantityKind))
        kinds[name] = {str(_local(str(k))) for k in declared}
    return kinds


def ancestors(graph: Graph, name: str) -> set[str]:
    """Quantity kinds that ``name`` specializes, directly or not."""
    found: set[str] = set()
    pending = [name]
    while pending:
        parent = _local(_value(graph, QK[pending.pop()], QUDT.specializationOf))
        if parent is not None and parent not in found:
            found.add(parent)
            pending.append(parent)
    return found


def extract_units(graph: Graph, date: str) -> dict[str, dict[str, Any]]:
    """Extract the selected units from the QUDT units graph."""
    units: dict[str, dict[str, Any]] = {}
    for name, pint_expression in UNITS.items():
        subject = UNIT[name]
        _require(graph, subject)
        multiplier = _value(graph, subject, QUDT.conversionMultiplier)
        offset = _value(graph, subject, QUDT.conversionOffset)
        units[name] = {
            "iri": str(subject),
            "label": _english_label(graph, subject),
            "symbol": SYMBOLS.get(name, _value(graph, subject, QUDT.symbol)),
            "dimension_vector": _local(_value(graph, subject, QUDT.hasDimensionVector)),
            "multiplier": float(multiplier) if multiplier is not None else 1.0,
            "offset": float(offset) if offset is not None else 0.0,
            "ucum": _value(graph, subject, QUDT.ucumCode),
            "udunits": _value(graph, subject, QUDT.udunitsCode),
            "pint": pint_expression,
            "matches": _matches(_value(graph, subject, QUDT.wikidataMatch), date),
        }
    return units


def extract_kinds(
    graph: Graph,
    units: dict[str, dict[str, Any]],
    declared: dict[str, set[str]],
    date: str,
) -> dict[str, dict[str, Any]]:
    """Extract the selected quantity kinds from the QUDT quantity kinds graph.

    QUDT declares units for general kinds (``DEG_C`` for ``Temperature``),
    so a unit applies to a kind when it is declared for that kind or for
    one it specializes. nomogram then applies its scale rule: offset units
    only for interval-scale kinds, multiplicative units only for the
    others. Without it, QUDT would make ``DEG_C`` applicable to the
    thermodynamic temperature. A kind may set ``offset_units`` when its
    scale's zero comes from a reference surface rather than from the unit
    (an altitude is on an interval scale, in metres), or to take both
    (the dew point, in degC or in K).
    """
    kinds: dict[str, dict[str, Any]] = {}
    for name, spec in KINDS.items():
        subject = QK[name]
        _require(graph, subject)
        lineage = {name} | ancestors(graph, name)
        offset = spec.offset_units
        if offset is None:
            offset = spec.scale_type == "interval"
        applicable = {
            unit
            for unit, data in units.items()
            if declared[unit] & lineage
            and (offset == "any" or (data["offset"] != 0.0) == offset)
        }
        added = set(spec.added_units) - applicable
        kinds[name] = {
            "iri": str(subject),
            "label": _english_label(graph, subject),
            "dimension_vector": _local(_value(graph, subject, QUDT.hasDimensionVector)),
            "specialization_of": _local(_value(graph, subject, QUDT.specializationOf)),
            "scale_type": spec.scale_type,
            "delta": spec.delta,
            "applicable_units": sorted(applicable | added),
            "added_units": sorted(added),
            "matches": _matches(_value(graph, subject, QUDT.wikidataMatch), date)
            + [
                {
                    "target": f"{CF_NAMESPACE}{cf}/",
                    "relation": relation,
                    "verified": date,
                }
                for cf, relation in spec.cf_standard_names
            ],
        }
    return kinds


def extract_cf(path: Path, names: set[str]) -> tuple[str, dict[str, dict[str, str]]]:
    """Extract the selected standard names and the version of a CF table."""
    root = ET.parse(path).getroot()
    version = root.findtext("version_number")
    if version is None:
        msg = f"no version_number in {path}"
        raise ValueError(msg)
    entries: dict[str, dict[str, str]] = {}
    for entry in root.iter("entry"):
        name = entry.get("id")
        if name in names:
            canonical = entry.findtext("canonical_units") or ""
            entries[name] = {
                "canonical_units": canonical,
                "pint": udunits_to_pint(canonical),
            }
    missing = sorted(names - entries.keys())
    if missing:
        msg = "CF standard names not found: " + ", ".join(missing)
        raise ValueError(msg)
    return version.strip(), dict(sorted(entries.items()))


def extract(
    kinds_path: Path,
    units_path: Path,
    cf_path: Path,
    qudt_version: str,
    date: str,
) -> dict[str, Any]:
    """Build the content of ``semantics.json`` from the source files."""
    units_graph = Graph()
    units_graph.parse(units_path, format="turtle")
    kinds_graph = Graph()
    kinds_graph.parse(kinds_path, format="turtle")
    units = extract_units(units_graph, date)
    kinds = extract_kinds(kinds_graph, units, unit_kinds(units_graph), date)
    cf_names = {n for spec in KINDS.values() for n, _ in spec.cf_standard_names}
    cf_names |= set(SCALE_CF_NAMES) | set(LOCAL_KIND_CF_NAMES)
    cf_version, cf = extract_cf(cf_path, cf_names)
    return {
        "sources": {
            "qudt": {
                "version": qudt_version,
                "license": "CC-BY-4.0",
                "attribution": "QUDT.org, https://qudt.org/",
            },
            "cf_standard_names": {
                "version": cf_version,
                "license": "CC0-1.0",
                "attribution": "CF Conventions, https://cfconventions.org/",
            },
            "extracted": date,
        },
        "quantity_kinds": kinds,
        "units": units,
        "cf_standard_names": cf,
    }


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--kinds", type=Path, required=True)
    parser.add_argument("--units", type=Path, required=True)
    parser.add_argument("--cf", type=Path, required=True)
    parser.add_argument("--qudt-version", required=True)
    parser.add_argument(
        "--date",
        default=datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
        help="extraction date, recorded as the verification date of links",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = extract(args.kinds, args.units, args.cf, args.qudt_version, args.date)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(data, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
