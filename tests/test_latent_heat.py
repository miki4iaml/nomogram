# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the specific latent heats of the ECMWF IFS (CY49R1, 12.1 and 12.2)."""

import pytest

from nomogram.catalog import catalog
from nomogram.model import Formulation
from nomogram.units import Q_

CATALOG = catalog()
VAPORIZATION = CATALOG.formulations["ecmwf_ifs_latent_heat_vaporization"]
SUBLIMATION = CATALOG.formulations["ecmwf_ifs_latent_heat_sublimation"]


def latent_heat(formulation: Formulation, kelvin: float) -> float:
    value = formulation.evaluate(T=Q_(kelvin, "K"))
    return float(value.to("J/kg").magnitude)


def test_at_the_triple_point_the_latent_heats_are_lv0_and_ls0() -> None:
    # IFS section 12.5: L_v(T_0) = L_v0, L_s(T_0) = L_s0, T_0 = 273.16 K.
    assert latent_heat(VAPORIZATION, 273.16) == pytest.approx(2.5008e6)
    assert latent_heat(SUBLIMATION, 273.16) == pytest.approx(2.8345e6)


@pytest.mark.parametrize(
    ("key", "slope"),
    [
        ("ecmwf_ifs_latent_heat_vaporization", 1846.1 - 4218),
        ("ecmwf_ifs_latent_heat_sublimation", 1846.1 - 2106),
    ],
)
def test_the_slope_is_the_difference_of_specific_heats(key: str, slope: float) -> None:
    # c_pv - c_l and c_pv - c_s, in J kg-1 K-1.
    f = CATALOG.formulations[key]
    found = (latent_heat(f, 303.16) - latent_heat(f, 253.16)) / 50
    assert found == pytest.approx(slope)


def test_a_celsius_temperature_is_converted() -> None:
    at_triple_point = VAPORIZATION.evaluate(T=Q_(0.01, "degC"))
    assert at_triple_point.to("J/kg").magnitude == pytest.approx(2.5008e6)


def test_each_latent_heat_has_its_kind_under_specific_latent_heat() -> None:
    found = {f.key for f in CATALOG.search(kind="SpecificLatentHeat").formulations}
    assert {VAPORIZATION.key, SUBLIMATION.key} <= found
    # Vaporization and sublimation are never alternatives of one another.
    assert CATALOG.formulations_of("SpecificLatentHeatOfVaporization") == (
        VAPORIZATION,
    )
    assert CATALOG.formulations_of("SpecificLatentHeatOfSublimation") == (SUBLIMATION,)
    kind = CATALOG.kinds["SpecificLatentHeatOfVaporization"]
    assert kind.specialization_of == "SpecificLatentHeat"
    assert CATALOG.kinds["SpecificLatentHeat"].specialization_of == "SpecificEnergy"


def test_the_specific_latent_heat_is_linked_to_wikidata() -> None:
    (match,) = CATALOG.kinds["SpecificLatentHeat"].matches
    assert match.target == "http://www.wikidata.org/entity/Q104217205"
    assert match.relation.value == "exact"


def test_the_latent_heats_are_found_by_name_and_by_source() -> None:
    found = {f.key for f in CATALOG.search("latent heat").formulations}
    assert {VAPORIZATION.key, SUBLIMATION.key} <= found
    cited = CATALOG.search(source="ecmwf_ifs_cy49r1", equation="12.1").formulations
    assert [f.key for f in cited] == [VAPORIZATION.key]
