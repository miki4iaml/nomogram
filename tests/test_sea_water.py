# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Vapour pressure of sea water: formulations against the values their sources print."""

from __future__ import annotations

from typing import Any

import pytest

from nomogram.catalog import catalog
from nomogram.model import ScaleConversionError
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
#: TEOS-10 Manual, section 3.37 (p. 59): vapour pressures at 25 degC of pure
#: water and of the standard ocean, S_SO = 35.16504 g/kg.
TEOS10_PURE_25C = 3169.93
TEOS10_SEA_25C = 3110.57
S_SO = Q_(35.16504, "g/kg")
#: Chlorinity of the standard ocean, S = 1.80655 Cl with S_P = 35.
CL_SO = Q_(35 / 1.80655, "permille")

RATIOS = [
    "witting1908_vapour_pressure_ratio",
    "sverdrup1942_vapour_pressure_ratio",
    "robinson1954_vapour_pressure_ratio",
    "raoult_sharqawy2010",
    "nayar2016_vapour_pressure_ratio",
    "coare36_salinity_factor",
]


def ratio(name: str) -> float:
    """The relative vapour pressure at the standard ocean, each on its scale."""
    formulation = F[name]
    inputs: dict[str, Any] = (
        {"Cl": CL_SO}
        if "Cl" in [v.identifier for v in formulation.inputs]
        else {"S": S_SO}
    )
    # Absolute Salinity, which the ITTC states for Raoult's law, is taken as
    # given.
    if formulation is F["raoult_sharqawy2010"]:
        return float(formulation.evaluate(scale="ignore", **inputs).magnitude)
    return float(formulation.evaluate(**inputs).magnitude)


def test_robinson_and_witting_at_standard_sea_water() -> None:
    # Robinson (1954), p. 452: at 19.386 per mille Cl, lowerings of 0.01874
    # (his fit, which gives 0.018734) and 0.01879 (Witting).
    cl = Q_(19.386, "permille")
    robinson = F["robinson1954_vapour_pressure_ratio"].evaluate(Cl=cl).magnitude
    witting = F["witting1908_vapour_pressure_ratio"].evaluate(Cl=cl).magnitude
    assert 1 - robinson == pytest.approx(0.01874, abs=1e-5)
    assert 1 - witting == pytest.approx(0.01879, abs=1e-5)
    # p. 450: p = 23.295 mm at 20.02 per mille Cl, with p_0 = 23.756 mm.
    worked = F["robinson1954_vapour_pressure_ratio"].evaluate(Cl=Q_(20.02, "permille"))
    assert 23.756 * worked.magnitude == pytest.approx(23.295, abs=1e-3)


def test_ittc_worked_example() -> None:
    # ITTC 7.5-02-01-03, p. 13: standard seawater at 15 degC, 1.671 kPa.
    ittc = F["ittc2011_vapour_pressure"]
    found = ittc.evaluate(S=S_SO, T=Q_(288.15, "K"), scale="ignore")
    assert found.to("kPa").magnitude == pytest.approx(1.671, abs=5e-4)
    # Absolute Salinity cannot be converted: the formulation says so.
    with pytest.raises(ScaleConversionError):
        ittc.evaluate(S=S_SO, T=Q_(288.15, "K"))
    with pytest.raises(ScaleConversionError):
        F["raoult_sharqawy2010"].evaluate(S=S_SO)


#: Millero and Leung (1976), Table 20 (p. 1063): vapour pressure of sea
#: water, mm Hg, by temperature (degC) for S = 0, 10, 20, 30 and 40.
TABLE_20 = {
    0.0: [4.5806, 4.5566, 4.5328, 4.5084, 4.4831],
    10.0: [9.2078, 9.1596, 9.1113, 9.0619, 9.0106],
    20.0: [17.5393, 17.4474, 17.3553, 17.2606, 17.1622],
    25.0: [23.7665, 23.6419, 23.5169, 23.3884, 23.2548],
    40.0: [55.3639, 55.0743, 54.7831, 54.4831, 54.1708],
}


def test_millero_leung_against_their_table() -> None:
    millero = F["millero_leung1976_vapour_pressure"]

    def deviation(t: float) -> list[float]:
        row = TABLE_20[t]
        return [
            millero.evaluate(
                p_0=Q_(row[0], "mmHg"),
                t=Q_(t, "degC"),
                S=Q_(s, "permille"),
                scale="ignore",
            ).magnitude
            - p
            for s, p in zip((0.0, 10.0, 20.0, 30.0, 40.0), row, strict=True)
        ]

    # Within 0.0015 mm Hg up to 10 degC (std deviation of the fit: 0.001).
    for t in (0.0, 10.0):
        assert max(abs(d) for d in deviation(t)) < 0.0015, t
    # The disagreement the note records: eq. 108 departs from Table 20 as
    # the temperature rises, by up to 0.029 mm Hg at 40 degC.
    assert max(deviation(20.0)) == pytest.approx(0.0031, abs=2e-4)
    assert max(deviation(25.0)) == pytest.approx(0.0045, abs=2e-4)
    assert max(deviation(40.0)) == pytest.approx(0.0289, abs=2e-4)


def test_ratios_against_teos10() -> None:
    teos10 = TEOS10_SEA_25C / TEOS10_PURE_25C
    found = {key: ratio(key) / teos10 - 1 for key in RATIOS}
    # The measurement-based forms agree with TEOS-10 within 0.03 %; the
    # Raoult estimate is 0.18 % lower, COARE's 0.98 at 35 is 0.13 % lower.
    for key in (
        "witting1908_vapour_pressure_ratio",
        "sverdrup1942_vapour_pressure_ratio",
        "robinson1954_vapour_pressure_ratio",
        "nayar2016_vapour_pressure_ratio",
    ):
        assert abs(found[key]) < 3e-4, key
    assert found["raoult_sharqawy2010"] == pytest.approx(-1.78e-3, abs=5e-5)
    assert found["coare36_salinity_factor"] == pytest.approx(-1.30e-3, abs=5e-5)


def test_vapour_pressures_against_teos10() -> None:
    t = Q_(25.0, "degC")
    weiss = F["weiss_price1980_vapour_pressure"].evaluate(T=t.to("K"), S=S_SO)
    millero = F["millero_leung1976_vapour_pressure"].evaluate(
        p_0=Q_(TEOS10_PURE_25C, "Pa"), t=t, S=S_SO
    )
    assert weiss.to("Pa").magnitude / TEOS10_SEA_25C - 1 == pytest.approx(
        -5.7e-4, abs=5e-5
    )
    assert millero.to("Pa").magnitude / TEOS10_SEA_25C - 1 == pytest.approx(
        1.6e-4, abs=5e-5
    )


def test_scales_of_the_salinity_inputs() -> None:
    def scale(key: str, identifier: str) -> tuple[str | None, str | None]:
        variable = next(v for v in F[key].inputs if v.identifier == identifier)
        basis = variable.scale_basis.value if variable.scale_basis else None
        return (variable.scale.key if variable.scale else None, basis)

    assert scale("sverdrup1942_vapour_pressure_ratio", "S") == (
        "knudsen1901",
        "inferred-from-numbers",
    )
    assert scale("raoult_sharqawy2010", "S") == ("absolute_salinity2010", "stated")
    assert scale("nayar2016_vapour_pressure_ratio", "S") == (
        "reference_salinity2008",
        "stated",
    )
    assert scale("coare36_salinity_factor", "S") == ("pss78", "stated")
    assert scale("millero_leung1976_vapour_pressure", "S") == ("cox1967", "stated")
    assert scale("weiss_price1980_vapour_pressure", "T") == ("ipts48", "stated")


def test_surface_humidity_and_search() -> None:
    q = F["sea_surface_saturation_specific_humidity"]
    assert [c.reference for c in q.citations] == [
        "ecmwf_ifs_cy49r1",
        "beljaars1998",
        "fairall1996",
    ]
    assert q.evaluate(q_sat=Q_(20.0, "g/kg")).to("g/kg").magnitude == pytest.approx(
        19.6
    )
    ratios = CATALOG.search(output="RelativeVapourPressureOfSeaWater").refs
    assert {f"formulations.{key}" for key in RATIOS} <= set(ratios)
    pressures = CATALOG.search(kind="VapourPressure", section="formulations").refs
    assert "formulations.ittc2011_vapour_pressure" in pressures
    assert "formulations.raoult_sharqawy2010" in CATALOG.search("raoult").refs
    assert "families.sea-water" in CATALOG.search("evaporation").refs
