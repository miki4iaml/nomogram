# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Relative bounds, calls in the check of units, systems without a loop.

The case is the threshold temperature of contrail formation (Schumann
1996): the maximum threshold temperature T_LM, where the slope of the
saturation vapour pressure over water equals the slope G of the mixing
line (equation 10), and the threshold temperature T_LC, below it, of
equation 11, which has a second root above T_LM.
"""

import dataclasses
import warnings
from typing import Any

import numpy as np
import pytest
from bundled_catalog import with_families

from nomogram.catalog import Catalog, CatalogError
from nomogram.display import FormulaTable
from nomogram.graph import system_graph
from nomogram.inversion import invert
from nomogram.model import Formulation, RootWarning
from nomogram.units import Q_

EQUATION_11 = "T_LC == T_LM - (p_liq(T=T_LM) - U * p_liq(T=T_LC)) / G"

THRESHOLD_INPUTS = """inputs = [
  {{ identifier = "T_LM", kind = "ContrailMaximumThresholdTemperature", unit = "K", description = "T_LM" }},
  {{ identifier = "U", kind = "RelativeHumidity", unit = "UNITLESS", description = "U" }},
  {{ identifier = "G", kind = "MixingLineSlope", unit = "PA-PER-K", description = "G" }},
]"""

# The equation of the catalog without its relative bound, written apart
# so that it is no copy of it.
DOCUMENT = """
[formulations.probe_t_lc_unbounded]
label = "Threshold temperature, without the relative bound"
expression = "G * (T_LM - T_LC) == p_liq(T=T_LM) - U * p_liq(T=T_LC)"
calls = { p_liq = "schumann2012_saturation_vapour_pressure_liquid" }
fixed_units = true
output = { identifier = "T_LC", kind = "ContrailThresholdTemperature", unit = "K", description = "T_LC" }
THRESHOLD_INPUTS
""".replace("THRESHOLD_INPUTS", THRESHOLD_INPUTS.format())

T_LM = "schumann1996_maximum_threshold_temperature_liquid"
T_LC = "schumann1996_threshold_temperature_liquid"
U_LC = "schumann2012_critical_relative_humidity"
FIT = "schumann2012_threshold_temperature_fit"


def catalog_with(*documents: str) -> Catalog:
    return with_families(("contrail",), *documents)


CATALOG = catalog_with(DOCUMENT)
F = CATALOG.formulations
KEROSENE: dict[str, Any] = {"G": Q_(1.49, "Pa/K")}


def t_lm() -> Any:
    return F[T_LM].evaluate(**KEROSENE)


def test_a_call_is_checked_in_the_unit_of_the_output_called() -> None:
    # An implicit equation equating a call of a derivative in fixed units to
    # an input: its exponential holds the pascals, which the developed
    # expression would read as a pure number.
    assert F[T_LM].evaluate(**KEROSENE).to("degC").magnitude == pytest.approx(
        -42.910, abs=5e-4
    )
    # A sum of a call and of terms with coefficients: x1 and x3 are kelvins,
    # the coefficients of the formulation called keep their own units.
    units = F[FIT].coefficient_units
    assert f"{units['x1'].unit:~}" == "K"
    called = units["a0__schumann2012_saturation_vapour_pressure_liquid"]
    assert (f"{called.unit:~}", called.reason) == (
        "K",
        "as in schumann2012_saturation_vapour_pressure_liquid, which it calls",
    )


def test_a_relative_bound_ends_the_search_for_a_root() -> None:
    inputs = {"T_LM": t_lm(), "U": Q_(0.42, ""), **KEROSENE}
    found = F[T_LC].evaluate(**inputs).to("degC").magnitude
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
    found = F[T_LC].evaluate(T_LM=maximum, U=Q_([1.0, 0.999], ""), **KEROSENE)
    assert found.to("K").magnitude[0] == pytest.approx(
        maximum.to("K").magnitude, abs=1e-9
    )
    assert found.to("K").magnitude[1] < maximum.to("K").magnitude


def test_a_relative_end_outside_the_interval_searched_is_not_taken() -> None:
    inputs = {"T_LM": t_lm(), "U": Q_(1.0, ""), **KEROSENE}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        found = F[T_LC].evaluate(**inputs, search=(200.0, 220.0))
    assert np.isnan(found.magnitude)
    assert any("no root in the interval searched" in str(w.message) for w in caught)


def test_a_relative_bound_between_inputs_bounds_the_evaluation() -> None:
    maximum = t_lm()
    temperatures = Q_([214.15, 235.0], "K")
    # A physical domain, which evaluation applies with basis "physical" or
    # "all", as any other; Ponater et al. (2002) state it too, which the
    # default basis applies.
    found = F[U_LC].evaluate(T=temperatures, T_LM=maximum, basis="all", **KEROSENE)
    assert found.magnitude[0] == pytest.approx(-4.5026, abs=5e-4)
    assert np.isnan(found.magnitude[1])  # above T_LM, equation 12 does not hold
    mask = F[U_LC].outside_mask(
        {"T": temperatures.magnitude, "T_LM": maximum.to("K").magnitude, "G": 1.49},
        basis="physical",
    )
    assert mask.tolist() == [False, True]


def test_a_system_without_a_loop_is_solved_in_order() -> None:
    system = CATALOG.systems["schumann1996_threshold_temperature"]
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
    text = FormulaTable((F[T_LC].render(),)).to_markdown()
    assert r"\leq" in text
    assert "(physical)" in text


@pytest.mark.parametrize(
    ("domain", "message"),
    [
        ('at_most = { T_LC = "T_X" }', "'T_X' is not a variable of the formulation"),
        ('at_most = { T_LC = "T_LC" }', "a variable does not bound itself"),
        (
            'at_most = { T_LC = "G" }\ncriterion = "A probe."',
            "the same unit, not K and PA-PER-K",
        ),
        ("at_most = { T_LC = 1 }", "expected the identifier of a variable"),
        ("at_most = 1", "expected a table of variable to the variable bounding it"),
        ('at_least = { U = "T_LM" }', "the same unit, not UNITLESS and K"),
        ('criterion = "nothing"', "a domain gives bounds, at_most or at_least"),
        (
            'at_least = { T_LM = "T_LC" }',
            'a bound involving the output is written on it: at_most = { T_LC = "T_LM" }',
        ),
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


SCALED = """
[formulations.probe_scaled]
label = "Scaled"
expression = "a * T - b * T_m"
fixed_units = true
output = { identifier = "y", kind = "Pressure", unit = "PA", description = "y" }
inputs = [
  { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" },
  { identifier = "T_m", kind = "ThermodynamicTemperature", unit = "K", description = "T_m", scale = "SCALE", scale_basis = "inferred-from-date" },
]
coefficients = { a = 1.0, b = 1.5 }

[[formulations.probe_scaled.domains]]
at_most = { T = "T_m" }

[[formulations.probe_scaled.citations]]
reference = "schumann1996"
scales = { T = "ipts68" }
"""


def test_relative_bounds_compare_the_scales_citations_state() -> None:
    # T is on IPTS-68 by its citation: T_m inferred on IPTS-68 compares
    # with it, T_m on ITS-90 does not.
    catalog_with(SCALED.replace("SCALE", "ipts68"))
    with pytest.raises(CatalogError, match="different scales: ipts68, its90"):
        catalog_with(SCALED.replace("SCALE", "its90"))


COMPOSED = """
[formulations.probe_outer]
label = "Outer"
expression = "(T_LM - T) * G"
fixed_units = true
output = { identifier = "y", kind = "Pressure", unit = "PA", description = "y" }
inputs = [
  { identifier = "T", kind = "CelsiusTemperature", unit = "DEG_C", description = "T" },
  { identifier = "T_LM", kind = "ContrailMaximumThresholdTemperature", unit = "DEG_C", description = "T_LM" },
  { identifier = "G", kind = "MixingLineSlope", unit = "PA-PER-K", description = "G" },
]

[[formulations.probe_outer.domains]]
at_most = { T = "T_LM" }

[formulations.probe_inner]
label = "Inner"
expression = "a0 + a1 * ln(G) + b * (T_cap - T_low)"
fixed_units = true
output = { identifier = "T_LM", kind = "ContrailMaximumThresholdTemperature", unit = "DEG_C", description = "T_LM" }
inputs = [
  { identifier = "G", kind = "MixingLineSlope", unit = "PA-PER-K", description = "G" },
  { identifier = "T_cap", kind = "CelsiusTemperature", unit = "DEG_C", description = "T_cap" },
  { identifier = "T_low", kind = "CelsiusTemperature", unit = "DEG_C", description = "T_low" },
]
coefficients = { a0 = -46.46, a1 = 9.43, b = 1e-9 }

[[formulations.probe_inner.domains]]
at_least = { T_cap = "T_low", T_LM = "T_low" }
criterion = "A probe."

[formulations.probe_composed]
label = "Composed"
composition = { outer = "probe_outer", inner = { T_LM = "probe_inner" }, bind = { T_cap = "T" } }
output = { identifier = "y2", kind = "Pressure", unit = "PA", description = "y2" }
"""


def test_a_composition_keeps_relative_bounds_under_its_names() -> None:
    composed = catalog_with(COMPOSED).formulations["probe_composed"]
    assert {v.identifier for v in composed.inputs} == {"T", "G", "T_low"}
    # T_cap is T in the composition; T_LM, an intermediate value, is
    # checked on the parts, which evaluation still does.
    relative = [
        (side, dict(table))
        for d in composed.physical_domains
        for side, table in (("most", d.at_most), ("least", d.at_least))
        if table
    ]
    assert relative == [("least", {"T": "T_low"})]
    found = composed.evaluate(
        T=Q_([-60.0, -30.0], "degC"),
        T_low=Q_(-80.0, "degC"),
        G=Q_(1.49, "Pa/K"),
        basis="physical",
    )
    assert np.isfinite(found.magnitude[0])
    assert np.isnan(found.magnitude[1])  # T above T_LM, about -42.7 degC


INVERTED = """
[formulations.probe_one_input]
label = "One input"
expression = "2 * x - c"
fixed_units = true
output = { identifier = "y", kind = "ThermodynamicTemperature", unit = "K", description = "y" }
inputs = [ { identifier = "x", kind = "ThermodynamicTemperature", unit = "K", description = "x" } ]
coefficients = { c = 300.0 }

[[formulations.probe_one_input.domains]]
at_most = { y = "x" }
criterion = "A probe: y <= x, that is x <= 300 K."
"""


def test_a_closed_form_inverse_writes_a_relative_bound_on_its_output() -> None:
    source = catalog_with(INVERTED).formulations["probe_one_input"]
    inverse = invert(
        source, "x", output=source.inputs[0], input=source.output, search=(0.0, 1000.0)
    )
    assert isinstance(inverse, Formulation)
    assert [dict(d.at_least) for d in inverse.physical_domains] == [{"x": "y"}]
    found = inverse.evaluate(y=Q_([250.0, 400.0], "K"), basis="physical")
    assert found.to("K").magnitude[0] == pytest.approx(275.0)
    assert np.isnan(found.magnitude[1])  # x = 350 K, where y > x
    # A change from K to degC: the numerical inverse, which keeps it.
    celsius = invert(
        source,
        "x",
        output=dataclasses.replace(
            source.inputs[0], unit="DEG_C", kind="CelsiusTemperature"
        ),
        input=source.output,
        search=(0.0, 1000.0),
    )
    assert not isinstance(celsius, Formulation)


def test_a_closed_form_inverse_writes_on_its_output_a_bound_of_its_input() -> None:
    # Built directly, a source may bound its input by its output, x <= y:
    # the inverse writes it on its output, x, as it is.
    from types import MappingProxyType

    from nomogram.model import DomainBasis, ValidityDomain

    source = dataclasses.replace(
        catalog_with(INVERTED).formulations["probe_one_input"],
        physical_domains=(
            ValidityDomain(
                DomainBasis.PHYSICAL,
                MappingProxyType({}),
                "A probe: x <= y, that is x >= 300 K.",
                None,
                at_most=MappingProxyType({"x": "y"}),
            ),
        ),
    )
    inverse = invert(
        source, "x", output=source.inputs[0], input=source.output, search=(0.0, 1000.0)
    )
    assert isinstance(inverse, Formulation)
    assert [dict(d.at_most) for d in inverse.physical_domains] == [{"x": "y"}]
