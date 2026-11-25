# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Relative bounds, calls in the check of units, systems without a loop.

The case is the threshold temperature of contrail formation (Schumann
1996): the maximum threshold temperature T_LM, where the slope of the
saturation vapour pressure over water equals the slope G of the mixing
line (equation 10), and the threshold temperature T_LC, below it, of
equation 11, which has a second root above T_LM.
"""

import warnings
from typing import Any

import numpy as np
import pytest
from bundled_catalog import with_families

from nomogram.catalog import Catalog, CatalogError
from nomogram.display import FormulaTable
from nomogram.graph import system_graph
from nomogram.model import RootWarning
from nomogram.units import Q_

EQUATION_11 = "T_LC == T_LM - (p_liq(T=T_LM) - U * p_liq(T=T_LC)) / G"

THRESHOLD_INPUTS = """inputs = [
  {{ identifier = "T_LM", kind = "ContrailMaximumThresholdTemperature", unit = "K", description = "T_LM" }},
  {{ identifier = "U", kind = "RelativeHumidity", unit = "UNITLESS", description = "U" }},
  {{ identifier = "G", kind = "MixingLineSlope", unit = "PA-PER-K", description = "G" }},
]"""

DOCUMENT = """
[formulations.probe_t_lm]
label = "Maximum threshold temperature"
expression = "dp_liq(T=T_LM) == G"
calls = { dp_liq = "schumann2012_saturation_vapour_pressure_slope_liquid" }
fixed_units = true
output = { identifier = "T_LM", kind = "ContrailMaximumThresholdTemperature", unit = "K", description = "T_LM" }
inputs = [ { identifier = "G", kind = "MixingLineSlope", unit = "PA-PER-K", description = "G" } ]

[formulations.probe_t_lc]
label = "Threshold temperature"
expression = "EQUATION_11"
calls = { p_liq = "schumann2012_saturation_vapour_pressure_liquid" }
fixed_units = true
output = { identifier = "T_LC", kind = "ContrailThresholdTemperature", unit = "K", description = "T_LC" }
THRESHOLD_INPUTS

[[formulations.probe_t_lc.domains]]
at_most = { T_LC = "T_LM" }
criterion = "The threshold temperature never exceeds its maximum."

[formulations.probe_t_lc_unbounded]
label = "Threshold temperature, without the relative bound"
expression = "G * (T_LM - T_LC) == p_liq(T=T_LM) - U * p_liq(T=T_LC)"
calls = { p_liq = "schumann2012_saturation_vapour_pressure_liquid" }
fixed_units = true
output = { identifier = "T_LC", kind = "ContrailThresholdTemperature", unit = "K", description = "T_LC" }
THRESHOLD_INPUTS

[formulations.probe_u_lc]
label = "Critical relative humidity"
expression = "(G * (T - T_LM) + p_liq(T=T_LM)) / p_liq(T=T)"
calls = { p_liq = "schumann2012_saturation_vapour_pressure_liquid" }
fixed_units = true
output = { identifier = "U_LC", kind = "DimensionlessRatio", unit = "UNITLESS", description = "U_LC" }
inputs = [
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" },
  { identifier = "T_LM", kind = "ContrailMaximumThresholdTemperature", unit = "K", description = "T_LM" },
  { identifier = "G", kind = "MixingLineSlope", unit = "PA-PER-K", description = "G" },
]

[[formulations.probe_u_lc.domains]]
at_most = { T = "T_LM" }

[formulations.probe_fit]
label = "Threshold temperature, explicit fit calling the saturation"
expression = "T_LM - (1 - U) * p_liq(T=T_LM) / G - (x1 + x3 * ln(G)) * U * ((1 - U ** 2) ** x2 - (1 / 4 - (U - 1 / 2) ** 2) ** 4 * (1 - (1 - U ** 2) ** x2))"
calls = { p_liq = "schumann2012_saturation_vapour_pressure_liquid" }
fixed_units = true
output = { identifier = "T_LC", kind = "ContrailThresholdTemperature", unit = "K", description = "T_LC" }
THRESHOLD_INPUTS
coefficients = { x1 = 5.686, x2 = 0.3840, x3 = 0.6594 }

[systems.probe_threshold]
label = "Threshold temperature from G and U"
equations = [ { formulation = "probe_t_lm" }, { formulation = "probe_t_lc" } ]
""".replace("EQUATION_11", EQUATION_11).replace(
    "THRESHOLD_INPUTS", THRESHOLD_INPUTS.format()
)


def catalog_with(*documents: str) -> Catalog:
    return with_families(("contrail",), *documents)


CATALOG = catalog_with(DOCUMENT)
F = CATALOG.formulations
KEROSENE: dict[str, Any] = {"G": Q_(1.49, "Pa/K")}


def t_lm() -> Any:
    return F["probe_t_lm"].evaluate(**KEROSENE)


def test_a_call_is_checked_in_the_unit_of_the_output_called() -> None:
    # An implicit equation equating a call of a derivative in fixed units to
    # an input: its exponential holds the pascals, which the developed
    # expression would read as a pure number.
    assert F["probe_t_lm"].evaluate(**KEROSENE).to("degC").magnitude == pytest.approx(
        -42.910, abs=5e-4
    )
    # A sum of a call and of terms with coefficients: x1 and x3 are kelvins,
    # the coefficients of the formulation called keep their own units.
    units = F["probe_fit"].coefficient_units
    assert f"{units['x1'].unit:~}" == "K"
    called = units["a0__schumann2012_saturation_vapour_pressure_liquid"]
    assert (f"{called.unit:~}", called.reason) == (
        "K",
        "as in schumann2012_saturation_vapour_pressure_liquid, which it calls",
    )


def test_a_relative_bound_ends_the_search_for_a_root() -> None:
    inputs = {"T_LM": t_lm(), "U": Q_(0.42, ""), **KEROSENE}
    found = F["probe_t_lc"].evaluate(**inputs).to("degC").magnitude
    assert found == pytest.approx(-50.641, abs=5e-4)  # Table 3: -50.6 degC
    # Without it, the second root of equation 11, above T_LM, makes two.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert np.isnan(F["probe_t_lc_unbounded"].evaluate(**inputs).magnitude)
    assert any(
        issubclass(w.category, RootWarning) and "several roots" in str(w.message)
        for w in caught
    )


def test_a_double_root_on_a_relative_bound_is_its_end() -> None:
    # At liquid saturation, the mixing line touches the saturation curve:
    # T_LC = T_LM, a root without a change of sign.
    maximum = t_lm()
    found = F["probe_t_lc"].evaluate(T_LM=maximum, U=Q_([1.0, 0.999], ""), **KEROSENE)
    assert found.to("K").magnitude[0] == pytest.approx(
        maximum.to("K").magnitude, abs=1e-9
    )
    assert found.to("K").magnitude[1] < maximum.to("K").magnitude


def test_a_relative_bound_between_inputs_bounds_the_evaluation() -> None:
    maximum = t_lm()
    temperatures = Q_([214.15, 235.0], "K")
    # A physical domain, which evaluation applies with basis "physical" or
    # "all", as any other.
    found = F["probe_u_lc"].evaluate(
        T=temperatures, T_LM=maximum, basis="all", **KEROSENE
    )
    assert found.magnitude[0] == pytest.approx(-4.5026, abs=5e-4)
    assert np.isnan(found.magnitude[1])  # above T_LM, equation 12 does not hold
    mask = F["probe_u_lc"].outside_mask(
        {"T": temperatures.magnitude, "T_LM": maximum.to("K").magnitude, "G": 1.49},
        basis="physical",
    )
    assert mask.tolist() == [False, True]


def test_a_system_without_a_loop_is_solved_in_order() -> None:
    system = CATALOG.systems["probe_threshold"]
    assert system.unknowns == ()
    assert system.outputs == ("T_LM", "T_LC")
    solution = system.evaluate(G=Q_([1.49, 2.31, 3.82], "Pa/K"), U=Q_(0.42, ""))
    # Table 3 of Schumann (1996): -50.6, -46.3 and -41.2 degC.
    assert solution["T_LC"].to("degC").magnitude.tolist() == pytest.approx(
        [-50.641, -46.346, -41.175], abs=5e-4
    )
    document = system_graph(system)
    names = {"T_LM", "T_LC", "G", "U"}
    assert {n["id"] for n in document["nodes"]} >= {f"variables.{n}" for n in names}
    # No loop: no read closes one.
    assert not [e for e in document["edges"] if e.get("role") == "nomogram:closing"]


def test_relative_bounds_are_shown_with_the_domains() -> None:
    text = FormulaTable((F["probe_t_lc"].render(),)).to_markdown()
    assert r"\leq" in text
    assert "(physical)" in text


@pytest.mark.parametrize(
    ("domain", "message"),
    [
        ('at_most = { T_LC = "T_X" }', "'T_X' is not a variable of the formulation"),
        ('at_most = { T_LC = "T_LC" }', "a variable does not bound itself"),
        ('at_most = { T_LC = "G" }', "the same unit, not K and PA-PER-K"),
        ("at_most = { T_LC = 1 }", "expected the identifier of a variable"),
        ('at_least = { U = "T_LM" }', "the same unit, not UNITLESS and K"),
        ('criterion = "nothing"', "a domain gives bounds, at_most or at_least"),
        (
            'at_most = { T_LC = "T_LM" }\n#',
            "a bound on the output T_LC states its criterion",
        ),
    ],
)
def test_invalid_relative_bounds_are_refused(domain: str, message: str) -> None:
    document = f"""
[formulations.probe_bad]
label = "Bad"
expression = "{EQUATION_11}"
calls = {{ p_liq = "schumann2012_saturation_vapour_pressure_liquid" }}
fixed_units = true
output = {{ identifier = "T_LC", kind = "ContrailThresholdTemperature", unit = "K", description = "T_LC" }}
{THRESHOLD_INPUTS.format()}

[[formulations.probe_bad.domains]]
{domain}
"""
    with pytest.raises(CatalogError, match=message):
        catalog_with(document)
