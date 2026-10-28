# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.semantics` and the bundled QUDT and CF subsets."""

import dataclasses
import datetime

import pytest

from nomogram.semantics import (
    CF_NAMESPACE,
    ExternalMatch,
    MatchRelation,
    QuantityKind,
    semantic_catalog,
)
from nomogram.units import Q_, ScaleType, is_offset_unit, ureg

CATALOG = semantic_catalog()

#: QUDT base dimensions, as named by pint.
PINT_DIMENSIONS = {
    "amount_of_substance": "[substance]",
    "electric_current": "[current]",
    "length": "[length]",
    "luminous_intensity": "[luminosity]",
    "mass": "[mass]",
    "temperature": "[temperature]",
    "time": "[time]",
}


def pint_dimensions(expression: str) -> dict[str, object]:
    dimensionality = Q_(1, expression).dimensionality
    return {d: e for d, e in dimensionality.items() if e}


def expected_dimensions(dimensions: dict[str, int]) -> dict[str, int]:
    return {PINT_DIMENSIONS[d]: e for d, e in dimensions.items()}


def test_sources_are_recorded() -> None:
    assert CATALOG.qudt_version == "3.5.2"
    assert CATALOG.cf_version == "95"
    assert CATALOG.extracted == datetime.date(2026, 10, 26)


def test_catalog_is_read_once() -> None:
    assert semantic_catalog() is CATALOG


def test_unit_symbols_follow_the_si_brochure() -> None:
    # SI Brochure, 9th ed., 2.3.3 and 5.4.7; QUDT writes the unit one U+4E00.
    assert CATALOG.units["UNITLESS"].symbol == "1"
    assert CATALOG.units["PPM"].symbol == "ppm"
    assert CATALOG.units["PERCENT"].symbol == "%"
    # Table 1 writes mol⁻¹; QUDT writes /mol.
    assert CATALOG.units["PER-MOL"].symbol == "mol⁻¹"


def test_reference_case_kinds_are_present() -> None:
    for name in (
        "ThermodynamicTemperature",
        "CelsiusTemperature",
        "TemperatureDifference",
        "RelativeHumidity",
        "VapourPressure",
        "MassConcentrationOfWaterVapour",
        "MassRatioOfWaterVapourToDryGas",
        "SpecificHumidity",
        "DewPointTemperature",
        "Pressure",
    ):
        assert name in CATALOG.quantity_kinds


@pytest.mark.parametrize("name", sorted(CATALOG.units))
def test_pint_expression_has_the_qudt_dimension(name: str) -> None:
    unit = CATALOG.units[name]
    assert pint_dimensions(unit.pint) == expected_dimensions(dict(unit.dimensions))


@pytest.mark.parametrize("name", sorted(CATALOG.units))
def test_pint_expression_follows_the_qudt_conversion_rule(name: str) -> None:
    # QUDT: a value v in the unit is (v + offset) * multiplier in SI.
    unit = CATALOG.units[name]
    for value in (0.0, 10.0):
        si = Q_(value, unit.pint).to_base_units().magnitude
        assert si == pytest.approx((value + unit.offset) * unit.multiplier)


@pytest.mark.parametrize("name", sorted(CATALOG.units))
def test_offset_units_are_the_qudt_units_with_an_offset(name: str) -> None:
    unit = CATALOG.units[name]
    assert is_offset_unit(unit.pint) is (unit.offset != 0.0)


#: Interval-scale kinds whose zero is a reference surface rather than a
#: unit: multiplicative units (``offset_units=False`` in the extraction).
SURFACE_ZERO = frozenset({"Altitude"})

#: Temperature points written with or without an offset, in degC or in K
#: (``offset_units="any"`` in the extraction).
ANY_OFFSET = frozenset({"DewPointTemperature", "Temperature", "WetBulbTemperature"})


@pytest.mark.parametrize("name", sorted(CATALOG.quantity_kinds))
def test_applicable_units_follow_the_scale_rule(name: str) -> None:
    kind = CATALOG.quantity_kinds[name]
    assert kind.applicable_units
    offset = kind.scale_type is ScaleType.INTERVAL and name not in SURFACE_ZERO
    for unit_name in kind.applicable_units:
        unit = CATALOG.units[unit_name]
        assert unit.dimensions == kind.dimensions
        assert name in ANY_OFFSET or (unit.offset != 0.0) is offset
    assert set(kind.added_units) <= set(kind.applicable_units)


def test_radio_refractivity_kinds_and_units() -> None:
    kinds, units = CATALOG.quantity_kinds, CATALOG.units
    assert kinds["RefractiveIndex"].applicable_units == ("UNITLESS",)
    assert set(kinds["DimensionlessRatio"].applicable_units) == {
        "PERCENT",
        "PERMILLE",
        "PPM",
        "UNITLESS",
    }
    assert set(kinds["Height"].applicable_units) == {"M", "KiloM"}
    assert kinds["Height"].cf_standard_names == ("height",)
    # QUDT writes PPM; nomogram displays ppm, as ITU-R P.453 does.
    assert units["PPM"].symbol == "ppm"
    assert units["PPM"].multiplier == 1e-6


def test_celsius_is_not_a_unit_of_thermodynamic_temperature() -> None:
    kinds = CATALOG.quantity_kinds
    assert kinds["ThermodynamicTemperature"].applicable_units == ("K",)
    assert "DEG_C" in kinds["CelsiusTemperature"].applicable_units
    assert kinds["CelsiusTemperature"].scale_type is ScaleType.INTERVAL


def test_a_dew_point_is_given_in_degc_or_in_k() -> None:
    # QUDT has one kind for the dew point, which CF gives in K and empirical
    # formulas in degC; nomogram's scale rule would keep only degC and degF.
    kind = CATALOG.quantity_kinds["DewPointTemperature"]
    assert set(kind.applicable_units) == {"DEG_C", "DEG_F", "K"}
    assert kind.scale_type is ScaleType.INTERVAL
    assert not kind.added_units


def test_specific_energy_is_in_joules_per_kilogram() -> None:
    kind = CATALOG.quantity_kinds["SpecificEnergy"]
    assert kind.applicable_units == ("J-PER-KiloGM", "KiloJ-PER-KiloGM")
    assert not kind.added_units


def test_air_temperature_names_both_temperatures() -> None:
    # CF names a temperature by its medium, not by its scale: air_temperature
    # may be in degC, so it names the Celsius temperature too.
    kinds = CATALOG.quantity_kinds
    assert kinds["ThermodynamicTemperature"].cf_standard_names == ("air_temperature",)
    assert kinds["CelsiusTemperature"].cf_standard_names == ("air_temperature",)


def test_temperature_difference_is_the_only_delta_kind() -> None:
    deltas = [k.name for k in CATALOG.quantity_kinds.values() if k.delta]
    assert deltas == ["TemperatureDifference"]


@pytest.mark.parametrize("name", sorted(CATALOG.quantity_kinds))
def test_cf_canonical_units_fit_the_kind(name: str) -> None:
    kind = CATALOG.quantity_kinds[name]
    for cf_name in kind.cf_standard_names:
        cf = CATALOG.cf_standard_names[cf_name]
        assert pint_dimensions(cf.pint) == expected_dimensions(dict(kind.dimensions))


def test_cf_canonical_units_keep_the_udunits_syntax() -> None:
    cf = CATALOG.cf_standard_names["mass_concentration_of_water_vapor_in_air"]
    assert cf.canonical_units == "kg m-3"
    assert ureg.Quantity(1, cf.pint).to("g/m^3").magnitude == pytest.approx(1000)


def test_external_links_carry_their_relation_and_verification_date() -> None:
    kind = CATALOG.quantity_kinds["MassConcentrationOfWaterVapour"]
    checked = datetime.date(2026, 10, 26)
    assert kind.matches == (
        ExternalMatch(
            "http://www.wikidata.org/entity/Q76378808", MatchRelation.CLOSE, checked
        ),
        ExternalMatch(
            f"{CF_NAMESPACE}mass_concentration_of_water_vapor_in_air/",
            MatchRelation.EXACT,
            checked,
        ),
    )
    # CF names the temperature of the air: narrower than the kind.
    temperature = CATALOG.quantity_kinds["ThermodynamicTemperature"].matches[-1]
    assert temperature.target == f"{CF_NAMESPACE}air_temperature/"
    assert temperature.relation is MatchRelation.NARROW
    altitude = CATALOG.quantity_kinds["Altitude"]
    assert [m.relation.value for m in altitude.matches[1:]] == ["exact", "close"]
    assert CATALOG.units["DEG_C"].matches[0].target.endswith("/Q25267")


def test_ambiguous_absolute_humidity_has_no_wikidata_link_in_qudt() -> None:
    assert CATALOG.quantity_kinds["AbsoluteHumidity"].matches == ()


def test_skos_relations() -> None:
    assert MatchRelation.EXACT.skos == "http://www.w3.org/2004/02/skos/core#exactMatch"
    assert {r.value for r in MatchRelation} == {"exact", "close", "broad", "narrow"}


def test_catalog_is_immutable() -> None:
    kind = CATALOG.quantity_kinds["VapourPressure"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        kind.label = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        CATALOG.quantity_kinds["New"] = kind  # type: ignore[index]
    with pytest.raises(TypeError):
        kind.dimensions["mass"] = 2  # type: ignore[index]


def test_invalid_dimension_vector_is_rejected() -> None:
    kind = dataclasses.replace(
        CATALOG.quantity_kinds["VapourPressure"], dimension_vector="L-1M1T-2"
    )
    assert isinstance(kind, QuantityKind)
    with pytest.raises(ValueError, match="invalid QUDT dimension vector"):
        _ = kind.dimensions
