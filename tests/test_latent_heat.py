# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the specific latent heats: ECMWF IFS (CY49R1) and Ambaum (2020)."""

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.model import Formulation
from nomogram.units import Q_

CATALOG = catalog()
VAPORIZATION = CATALOG.formulations["ecmwf_ifs_latent_heat_vaporization"]
SUBLIMATION = CATALOG.formulations["ecmwf_ifs_latent_heat_sublimation"]
AMBAUM = CATALOG.formulations["ambaum2020_latent_heat_vaporization"]
MELTING = CATALOG.formulations["ambaum2020_latent_heat_fusion"]


def latent_heat(formulation: Formulation, kelvin: float) -> float:
    value = formulation.evaluate(T=Q_(kelvin, "K"))
    return float(value.to("J/kg").magnitude)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        # IFS section 12.5: L_v(T_0) = L_v0, L_s(T_0) = L_s0.
        ("ecmwf_ifs_latent_heat_vaporization", 2.5008e6),
        ("ecmwf_ifs_latent_heat_sublimation", 2.8345e6),
        # Ambaum: L_0 (eq. 15) and L_m0 (Figure 4), at the triple point.
        ("ambaum2020_latent_heat_vaporization", 2.501e6),
        ("ambaum2020_latent_heat_fusion", 0.3334e6),
    ],
)
def test_at_the_triple_point_the_latent_heat_is_its_reference(
    key: str, expected: float
) -> None:
    assert latent_heat(CATALOG.formulations[key], 273.16) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("key", "slope"),
    [
        ("ecmwf_ifs_latent_heat_vaporization", 1846.1 - 4218),
        ("ecmwf_ifs_latent_heat_sublimation", 1846.1 - 2106),
        ("ambaum2020_latent_heat_vaporization", -2180),
        ("ambaum2020_latent_heat_fusion", 4220 - 2097),
    ],
)
def test_the_slope_is_the_difference_of_specific_heats(key: str, slope: float) -> None:
    # In J kg-1 K-1, within 0-100 degC where Ambaum's L_v holds.
    f = CATALOG.formulations[key]
    found = (latent_heat(f, 323.16) - latent_heat(f, 283.16)) / 40
    assert found == pytest.approx(slope)


def test_a_celsius_temperature_is_converted() -> None:
    at_triple_point = VAPORIZATION.evaluate(T=Q_(0.01, "degC"))
    assert at_triple_point.to("J/kg").magnitude == pytest.approx(2.5008e6)


def test_ambaum_s_latent_heat_holds_where_its_vapour_pressure_was_fitted() -> None:
    # From 0 to 100 degC, the range over which c_pl - c_pv was chosen.
    values = AMBAUM.evaluate(T=Q_([263.15, 293.15, 383.15], "K")).magnitude
    assert np.isnan(values[0])
    assert not np.isnan(values[1])
    assert np.isnan(values[2])


def test_the_units_ambaum_states_are_those_of_the_coefficients() -> None:
    units = AMBAUM.coefficient_units
    assert str(units["Delta_c"].unit) == "joule / kelvin / kilogram"
    assert str(units["T_0"].unit) == "kelvin"


def test_each_latent_heat_has_its_kind_under_specific_latent_heat() -> None:
    found = {f.key for f in CATALOG.search(kind="SpecificLatentHeat").formulations}
    assert {VAPORIZATION.key, SUBLIMATION.key, AMBAUM.key, MELTING.key} <= found
    # Alternatives side by side, never a sublimation for a vaporization.
    assert CATALOG.formulations_of("SpecificLatentHeatOfVaporization") == (
        VAPORIZATION,
        AMBAUM,
    )
    assert CATALOG.formulations_of("SpecificLatentHeatOfSublimation") == (SUBLIMATION,)
    assert [f.key for f in CATALOG.formulations_of("SpecificLatentHeatOfFusion")] == [
        MELTING.key,
        "latent_heat_fusion_identity",
        "ecmwf_ifs_latent_heat_fusion",
    ]
    for name in ("Vaporization", "Sublimation", "Fusion"):
        kind = CATALOG.kinds[f"SpecificLatentHeatOf{name}"]
        assert kind.specialization_of == "SpecificLatentHeat"
    assert CATALOG.kinds["SpecificLatentHeat"].specialization_of == "SpecificEnergy"


def test_the_specific_latent_heat_is_linked_to_wikidata() -> None:
    (match,) = CATALOG.kinds["SpecificLatentHeat"].matches
    assert match.target == "http://www.wikidata.org/entity/Q104217205"
    assert match.relation.value == "exact"


def test_the_latent_heats_are_found_by_name_and_by_source() -> None:
    found = {f.key for f in CATALOG.search("latent heat").formulations}
    assert {VAPORIZATION.key, SUBLIMATION.key, AMBAUM.key, MELTING.key} <= found
    cited = CATALOG.search(source="ecmwf_ifs_cy49r1", equation="12.1").formulations
    assert [f.key for f in cited] == [VAPORIZATION.key]
    ambaum = {f.key for f in CATALOG.search(source="ambaum2020").formulations}
    assert ambaum == {
        AMBAUM.key,
        MELTING.key,
        "latent_heat_fusion_identity",
        "ambaum2020",
        "ambaum2020_constant_latent_heat",
        "ambaum2020_ice",
    }
    melting = {f.key for f in CATALOG.search("melting").formulations}
    assert MELTING.key in melting
