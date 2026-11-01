# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The formulations of the producers of radiosonde humidity: Vaisala (2013)
and Hardy (1998), with the radiosondes the UAII 2022 report names."""

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.relations import verify
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations


def test_the_examples_vaisala_prints() -> None:
    # Dew point (p. 8): Pws(40 degC) * 50 % printed 36.88 hPa, where its
    # equation 6 gives 36.91 and its equation 3 36.93 (0.1 % apart); from
    # 36.88 hPa, the dew point 27.6 degC.
    e = F["vaisala2013_water"].evaluate(t=Q_(40.0, "degC")) * 0.5
    assert e.to("hPa").magnitude == pytest.approx(36.91, abs=0.005)
    assert e.to("hPa").magnitude == pytest.approx(36.88, rel=1e-3)
    t_d = F["vaisala2013_dew_point"].evaluate(e=Q_(36.88, "hPa"))
    assert t_d.to("degC").magnitude == pytest.approx(27.6, abs=0.05)
    # Absolute humidity (p. 14): Pws(20 degC) * 80 % = 1870 Pa, 13.82 g/m3.
    e = F["vaisala2013_water"].evaluate(t=Q_(20.0, "degC")) * 0.8
    assert e.to("Pa").magnitude == pytest.approx(1870.0, abs=0.5)
    rho = F["vaisala2013_absolute_humidity"].evaluate(
        e=Q_(1870.0, "Pa"), T=Q_(293.15, "K")
    )
    assert rho.to("g/m**3").magnitude == pytest.approx(13.82, abs=0.005)


@pytest.mark.parametrize(
    ("key", "stated"),
    [("vaisala2013_water_iapws", 0.083), ("vaisala2013_ice_equation_5", 0.052)],
)
def test_vaisala_fits_its_reference_equations_as_it_states(
    key: str, stated: float
) -> None:
    found = verify(CATALOG.relations[key], CATALOG)
    assert found.status == "reproduced"
    assert found.value == pytest.approx(stated, abs=5e-4)


def test_hardy_keeps_the_triple_point_of_water() -> None:
    # 611.657 Pa at the triple point, over water and over ice (3.1, 3.2).
    triple = Q_(273.16, "K")
    for key in ("hardy1998_water", "hardy1998_ice"):
        assert F[key].evaluate(T=triple).magnitude == pytest.approx(611.657, abs=0.001)


def test_the_inverses_of_hardy_return_the_temperature() -> None:
    # Within 0.3 mK of equation 2 from -100 to 100 degC, 0.1 mK of
    # equation 3 from -150 to 0.01 degC (section 4); the ice formulation
    # is entered from -100 degC.
    water = np.linspace(173.15, 373.15, 201)
    e = F["hardy1998_water"].evaluate(T=Q_(water, "K"))
    back = F["hardy1998_dew_point"].evaluate(e=e).to("K").magnitude
    assert np.max(np.abs(back - water)) < 3e-4
    ice = np.linspace(173.15, 273.16, 101)
    e = F["hardy1998_ice"].evaluate(T=Q_(ice, "K"))
    back = F["hardy1998_frost_point"].evaluate(e=e).to("K").magnitude
    assert np.max(np.abs(back - ice)) < 1e-4


def test_hardy_is_close_to_iapws_and_vaisala_to_hardy() -> None:
    temperatures = Q_(np.linspace(0.01, 50.0, 51), "degC")
    iapws = F["iapws_sr1_86"].evaluate(T=temperatures.to("K"))
    hardy = F["hardy1998_water"].evaluate(T=temperatures.to("K"))
    assert np.max(np.abs((hardy / iapws).to("").magnitude - 1)) < 5e-5
    vaisala = F["vaisala2013_water"].evaluate(t=temperatures)
    assert np.max(np.abs((vaisala / hardy).to("").magnitude - 1)) < 1e-3


def test_the_radiosonde_formulations_are_found_by_search() -> None:
    found = set(CATALOG.search(keyword="radiosonde", section="formulations").refs)
    named = {
        "hardy1998_water",
        "hyland_wexler1983",
        "goff_gratch1946",
        "sonntag1990",
        "bolton1980",
        "buck1981",
    }
    assert {f"formulations.{key}" for key in named} <= found
    assert "references.wmo_iom143" in CATALOG.search("RS41").refs
    assert "formulations.iapws_sr1_86" in CATALOG.used_by("references.vaisala2013").refs
