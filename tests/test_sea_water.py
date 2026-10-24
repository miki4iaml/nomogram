# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Vapour pressure of sea water: formulations against the values their sources print."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import catalog
from nomogram.comparison import compare
from nomogram.inversion import NumericalInverse, invert
from nomogram.model import ScaleConversionError, Variable
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
SCALES = CATALOG.scales
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


def test_dickson_against_the_values_printed() -> None:
    # Dickson et al. (2007), chapter 5: 3.1698 kPa for pure water (eq. 1)
    # and 3.1106 kPa for sea water of S = 35 (eqs. 2-4), at 25 degC.
    # S = 35 is Practical Salinity: as given, or converted from the
    # Reference Salinity of the standard ocean, the same value.
    t = Q_(298.15, "K")
    pure = F["iapws_sr1_86"].evaluate(T=t)
    dickson = F["dickson2007_vapour_pressure"]
    sea = dickson.evaluate(T=t, S=Q_(35.0), scale="ignore")
    assert pure.to("kPa").magnitude == pytest.approx(3.1698, abs=5e-5)
    assert sea.to("kPa").magnitude == pytest.approx(3.1106, abs=5e-5)
    # Within 0.001 % of TEOS-10 at the standard ocean.
    on_teos10 = dickson.evaluate(T=t, S=S_SO).to("Pa").magnitude
    assert on_teos10 == pytest.approx(sea.to("Pa").magnitude, rel=1e-12)
    assert on_teos10 / TEOS10_SEA_25C - 1 == pytest.approx(0.0, abs=1e-5)
    # The osmotic coefficient holds for S = 16-40.
    assert np.isnan(dickson.evaluate(T=t, S=Q_(10.0, "g/kg")).magnitude)
    assert "kinds.OsmoticCoefficient" in CATALOG.search(kind="OsmoticCoefficient").refs


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
    # Dickson et al. name no scale: S = 35 for Cl = 19.374 is Practical
    # Salinity, and the composed formulations take it from their part.
    for key in (
        "dickson2007_total_molality",
        "dickson2007_osmotic_coefficient_of_salinity",
        "dickson2007_vapour_pressure",
    ):
        assert scale(key, "S") == ("pss78", "inferred-from-numbers"), key


def test_where_the_scale_conversions_end() -> None:
    # Cox and Knudsen salinities convert below S = 2: the domains stated
    # from S = 0 hold under the default evaluation.
    zero = Q_(0.0, "g/kg")
    millero = F["millero_leung1976_vapour_pressure"].evaluate(
        p_0=Q_(23.7665, "mmHg"), t=Q_(25.0, "degC"), S=zero
    )
    assert millero.to("mmHg").magnitude == pytest.approx(23.7665)
    sverdrup = F["sverdrup1942_vapour_pressure_ratio"].evaluate(S=zero).magnitude
    assert sverdrup == pytest.approx(1.0, abs=2e-5)
    # PSS-78 keeps its limits, 2 to 42: COARE gives 1 for fresh water only
    # with the salinity taken as given, which its note says.
    coare = F["coare36_salinity_factor"]
    assert np.isnan(coare.evaluate(S=zero).magnitude)
    assert coare.evaluate(S=Q_(0.0), scale="ignore").magnitude == 1.0
    assert "scale='ignore'" in (coare.note or "")
    # IPTS-48 is converted over -2 to 30 degC: Weiss and Price, stated up
    # to 313 K, gives NaN beyond, and its note and the scale's say so.
    weiss = F["weiss_price1980_vapour_pressure"]
    t = Q_([302.5, 303.15, 313.0], "K")
    found = weiss.evaluate(T=t, S=S_SO).magnitude
    assert not np.isnan(found[0])
    assert np.isnan(found[1:]).all()
    as_written = weiss.evaluate(T=t, S=Q_(35.0), scale="ignore")
    assert not np.isnan(as_written.magnitude).any()
    assert "scale='ignore'" in (weiss.note or "")
    # Taken as given, an ITS-90 temperature is read as a lower t48: the note
    # says about 0.09 % lower near 30 degC.
    ratio = as_written.magnitude[0] / found[0] - 1
    assert ratio == pytest.approx(-9.2e-4, abs=5e-5)
    assert "0.09 % lower" in (weiss.note or "")
    assert "30 degC" in (CATALOG.scales["ipts48"].note or "")


def test_raoult_note_figures() -> None:
    # The note: 0.9796 against about 0.9813 at S = 35, a lowering about 9 %
    # larger than Robinson's measurement-based one.
    raoult = F["raoult_sharqawy2010"]
    r = raoult.evaluate(S=Q_(35.0, "g/kg"), scale="ignore").magnitude
    robinson = F["robinson1954_vapour_pressure_ratio"].evaluate(Cl=CL_SO).magnitude
    assert round(float(r), 4) == 0.9796
    assert round(float(robinson), 4) == 0.9813
    assert round((1 - r) / (1 - robinson) - 1, 2) == 0.09
    assert "0.9796 against about 0.9813 at S = 35" in (raoult.note or "")
    assert "about 9 %" in (raoult.note or "")


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


def test_the_sea_surface_page() -> None:
    # Figures of docs/sea-water.md. Beljaars (1998, p. 46): an equivalent
    # decrease of the sea surface temperature of "about .27 K at 0 degC to
    # about .35 K at 30 degC".
    buck = F["buck1981_magnus"]
    inverse = invert(
        buck,
        "t",
        output=Variable("t", "CelsiusTemperature", "DEG_C", "Celsius temperature"),
        input=Variable("e", "VapourPressure", "HectoPA", "Vapour pressure"),
    )
    decrease = {}
    for value in (0.0, 10.0, 20.0, 30.0):
        t = Q_(value, "degC")
        found = t - inverse.evaluate(e=0.98 * buck.evaluate(t=t))
        decrease[value] = found.to("delta_degC").magnitude
    assert decrease == pytest.approx(
        {0.0: 0.278, 10.0: 0.301, 20.0: 0.326, 30.0: 0.351}, abs=5e-4
    )
    # Radio refractivity at the surface, ITU-R P.453 eq. 2, 25 degC.
    refractivity = F["itu_r_p453_refractivity"]
    t = Q_(298.15, "K")
    p = Q_(1013.25, "hPa")
    e_w = F["iapws_sr1_86"].evaluate(T=t).to("hPa")
    r = F["robinson1954_vapour_pressure_ratio"].evaluate(Cl=CL_SO).magnitude

    def n(e: Any) -> float:
        return float(refractivity.evaluate(P_d=p - e, e=e, T=t).magnitude)

    pure, sea, air = n(e_w), n(r * e_w), n(0.8 * e_w)
    assert (e_w.magnitude, (r * e_w).magnitude, 0.8 * e_w.magnitude) == pytest.approx(
        (31.698, 31.105, 25.359), abs=5e-4
    )
    assert (pure, sea, air) == pytest.approx((396.85, 394.35, 370.22), abs=5e-3)
    assert (sea - air) / (pure - air) == pytest.approx(0.906, abs=5e-4)


def test_practical_salinity_is_a_number() -> None:
    # COARE 3.6 at the standard ocean: 0.98 from its Reference Salinity, or
    # from S_P = 35 taken as given.
    coare = F["coare36_salinity_factor"]
    assert coare.evaluate(S=S_SO).magnitude == pytest.approx(0.98)
    assert coare.evaluate(S=Q_(35.0), scale="ignore").magnitude == pytest.approx(0.98)
    # In per mille or in g/kg, S_P = 35 would be read as 0.035.
    for unit in ("permille", "g/kg"):
        with pytest.raises(ScaleConversionError, match="whose values are numbers"):
            coare.evaluate(S=Q_(35.0, unit), scale="ignore")
    # Knudsen salinity is a mass ratio: per mille and g/kg are its units.
    sverdrup = F["sverdrup1942_vapour_pressure_ratio"]
    in_per_mille = sverdrup.evaluate(S=Q_(35.0, "permille"), scale="ignore")
    in_g_per_kg = sverdrup.evaluate(S=Q_(35.0, "g/kg"), scale="ignore")
    assert in_per_mille.magnitude == pytest.approx(in_g_per_kg.magnitude)
    # A bare number would be read as a fraction: 35, not 35 per mille.
    with pytest.raises(ScaleConversionError, match="give it with its unit"):
        sverdrup.evaluate(S=Q_(35.0), scale="ignore")
    # One value cannot be S_P = 35 and S_K = 35 per mille at once: taken as
    # given, a comparison of both scales fails instead of misreading one.
    inputs = {"SeaWaterSalinity": Q_(35.0)}
    with pytest.raises(ScaleConversionError, match="give it with its unit"):
        compare([coare, sverdrup], coare, inputs, scale="ignore")
    assert compare([coare, sverdrup], coare, {"SeaWaterSalinity": S_SO}).values


def test_an_inverse_takes_practical_salinity_as_a_number() -> None:
    # No source output is on PSS-78 yet: an inverse of Knudsen's formula,
    # its input put on PSS-78, stands for one.
    inverse = invert(
        F["knudsen1901_salinity"],
        "Cl",
        output=Variable("Cl", "Chlorinity", "PERMILLE", "Chlorinity"),
        input=Variable("S", "SeaWaterSalinity", "PERMILLE", "Salinity"),
        method="numerical",
        search=(1.0, 25.0),
    )
    assert isinstance(inverse, NumericalInverse)
    number = dataclasses.replace(inverse.input, unit="UNITLESS", scale=SCALES["pss78"])
    on_pss78 = dataclasses.replace(inverse, input=number)
    with pytest.raises(ScaleConversionError, match="whose values are numbers"):
        on_pss78.evaluate(S=Q_(35.0, "permille"), scale="ignore")
    # On the Knudsen scale, the salinity comes with its unit.
    with pytest.raises(ScaleConversionError, match="give it with its unit"):
        inverse.evaluate(S=Q_(35.0), scale="ignore")
