# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.plot` (extra ``viz``)."""

import sys
from collections.abc import Iterator

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.mathtext import MathTextParser

from nomogram.catalog import catalog
from nomogram.comparison import Comparison, compare
from nomogram.display import (
    DisplayOptions,
    axis_label,
    display_options,
    reference_scale,
)
from nomogram.expression import LATEX_COMMANDS
from nomogram.plot import plot_deviations, plot_values
from nomogram.units import Q_

CATALOG = catalog()
FORMULATIONS = CATALOG.formulations
IAPWS = FORMULATIONS["iapws_sr1_86"]
SATURATION = CATALOG.formulations_of("SaturationVapourPressureOverWater")
GRID = Q_(np.array([-50.0, 0.01, 20.0, 40.0]), "degC")


@pytest.fixture(autouse=True)
def close_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture
def comparison() -> Comparison:
    return compare(SATURATION, IAPWS, {"ThermodynamicTemperature": GRID})


def test_deviations_one_curve_per_formulation_with_domain_gaps(
    comparison: Comparison,
) -> None:
    ax = plot_deviations(comparison)
    # One curve per formulation but the reference, plus the zero line.
    assert len(ax.lines) == len(SATURATION)
    curve = ax.lines[0].get_ydata()
    # -50 degC is outside the IAPWS domain: a gap, not a value.
    assert np.isnan(curve[0])
    assert "IAPWS" in ax.get_ylabel()
    assert ax.get_ylabel().endswith(r"$\delta$/%")
    # The values are in degC: a Celsius temperature, on ITS-90.
    assert ax.get_xlabel() == "Celsius temperature $t_{90}$/°C"
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert "Magnus form, Sonntag (1990) coefficients" in labels


def test_values_with_a_notation(comparison: Comparison) -> None:
    ax = plot_values(comparison, notation=CATALOG.notations["wmo"])
    assert ax.get_ylabel() == (
        r"Saturation vapour pressure over water $e_{\mathrm{w}}$/Pa"
    )
    assert len(ax.lines) == len(SATURATION)
    reference = next(line for line in ax.lines if line.get_linestyle() == "--")
    assert reference.get_label() == IAPWS.label


def test_existing_axes_are_used(comparison: Comparison) -> None:
    _, ax = plt.subplots()
    assert plot_deviations(comparison, ax=ax) is ax
    assert plot_values(comparison, ax=ax) is ax


def test_input_kind_must_be_clear() -> None:
    two = Comparison(
        "r",
        {
            "ThermodynamicTemperature": Q_(np.array([1.0, 2.0]), "K"),
            "RelativeHumidity": Q_(np.array([0.1, 0.2]), ""),
        },
        {"r": Q_(np.array([1.0, 2.0]), "Pa")},
        {"r": np.zeros(2)},
    )
    with pytest.raises(ValueError, match="choose the input"):
        plot_deviations(two)
    with pytest.raises(ValueError, match="no input of kind 'Nope'"):
        plot_deviations(two, input_kind="Nope")
    # Without the formulations, keys serve as labels and no symbol is shown.
    ax = plot_values(two, input_kind="ThermodynamicTemperature")
    assert ax.get_ylabel() == "Pa"
    assert ax.get_xlabel() == "Thermodynamic temperature $T_{90}$/K"
    assert ax.lines[0].get_label() == "r"
    other = Comparison(
        "r", {"Custom": Q_([1.0, 2.0], "K")}, two.values, two.relative_deviations
    )
    assert plot_values(other).get_xlabel() == "Custom / K"


def test_missing_extra_gives_an_explicit_message(
    monkeypatch: pytest.MonkeyPatch, comparison: Comparison
) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    with pytest.raises(ImportError, match=r"nomogram\[viz\]"):
        plot_deviations(comparison)


@pytest.mark.parametrize("notation", [None, *sorted(CATALOG.notations)])
@pytest.mark.parametrize(
    "options",
    [
        DisplayOptions(),
        DisplayOptions.SYMPY,
        DisplayOptions(mul_symbol="dot", values=True),
    ],
    ids=["default", "sympy", "values"],
)
def test_every_formulation_renders_in_mathtext(
    notation: str | None, options: DisplayOptions
) -> None:
    parser = MathTextParser("path")
    chosen = CATALOG.notations[notation] if notation else None
    for formulation in FORMULATIONS.values():
        parser.parse(formulation.render(chosen, options=options).mathtext)


@pytest.mark.parametrize("command", sorted(LATEX_COMMANDS))
def test_every_supported_latex_command_renders_in_mathtext(command: str) -> None:
    pair = r"\left(a\right)"
    samples = {r"\frac": r"\frac{a}{b}", r"\left": pair, r"\right": pair}
    MathTextParser("path").parse(f"$x {samples.get(command, command + '{a}')}$")


@pytest.mark.parametrize(
    "tex", ["T_d", r"\theta_\mathrm{d}", r"T^{a_{b}}", r"T_{\mathrm{d}}^{2}"]
)
def test_scale_marks_render_in_mathtext(tex: str) -> None:
    label = axis_label(None, tex, "K", scale=reference_scale("CelsiusTemperature"))
    MathTextParser("path").parse(label)


def test_curves_beyond_ten_change_line_style(comparison: Comparison) -> None:
    ax = plot_deviations(comparison)
    styles = [line.get_linestyle() for line in ax.lines[:-1]]
    assert styles[:10] == ["-"] * 10
    assert set(styles[10:]) == {"-."}


def test_abscissa_symbol_from_the_reference_formulation() -> None:
    from nomogram.comparison import compare

    vapour = CATALOG.formulations["vapour_pressure_from_relative_humidity"]
    found = compare(
        [vapour],
        vapour,
        {
            "RelativeHumidity": Q_(np.array([0.2, 0.5, 0.8]), ""),
            "SaturationVapourPressureOverWater": Q_(2000.0, "Pa"),
        },
    )
    label = plot_values(found, input_kind="RelativeHumidity").get_xlabel()
    assert label == r"Relative humidity $\mathrm{RH}$"
    # The input of the reference matching the kind gives the symbol, in the
    # notation of the plot (ASHRAE writes the saturation pressure p_ws).
    found_es = compare(
        [vapour],
        vapour,
        {
            "RelativeHumidity": Q_(0.5, ""),
            "SaturationVapourPressureOverWater": Q_(np.array([1.0e3, 2.0e3]), "Pa"),
        },
    )
    ashrae = CATALOG.notations["ashrae"]
    assert plot_values(found_es, notation=ashrae).get_xlabel() == (
        r"Saturation vapour pressure over water $p_{\mathrm{ws}}$/Pa"
    )


def test_axes_follow_the_display_options(comparison: Comparison) -> None:
    with display_options(axis_labels="explicit"):
        ax = plot_values(comparison)
    assert ax.get_xlabel() == "Celsius temperature - $t$ [°C] {ITS-90}"
    with display_options(axis_labels="simple"):
        ax = plot_deviations(comparison)
    assert ax.get_xlabel() == "Celsius temperature $t$ [°C]"
    assert ax.get_ylabel().endswith(r"$\delta$ [%]")


@pytest.mark.parametrize(
    ("unit", "values", "expected"),
    [
        # Fahrenheit is neither a Celsius nor a thermodynamic temperature.
        ("degF", [32.0, 90.0], "Temperature / °F"),
        ("degR", [492.0, 560.0], "Thermodynamic temperature $T_{90}$/°R"),
    ],
)
def test_temperature_axis_follows_the_unit(
    unit: str, values: list[float], expected: str
) -> None:
    found = compare(SATURATION, IAPWS, {"ThermodynamicTemperature": Q_(values, unit)})
    assert plot_values(found).get_xlabel() == expected


def test_without_scale_conversion_the_axes_claim_no_scale() -> None:
    # Weiss and Price took the values as given, on IPTS-48 and PSS-78:
    # neither T_90 nor S_R may label them.
    weiss = FORMULATIONS["weiss_price1980_vapour_pressure"]
    inputs = {
        "ThermodynamicTemperature": Q_(np.array([10.0, 20.0]), "degC"),
        "SeaWaterSalinity": Q_(np.array([30.0, 35.0]), "g/kg"),
    }
    ignored = compare([weiss], weiss, inputs, scale="ignore")
    ax = plot_values(ignored, input_kind="ThermodynamicTemperature")
    assert ax.get_xlabel() == "Celsius temperature $t$/°C"
    salinity = plot_values(ignored, input_kind="SeaWaterSalinity").get_xlabel()
    assert salinity.endswith("$S$/(g/kg)")
    with display_options(axis_labels="explicit"):
        ax = plot_values(ignored, input_kind="SeaWaterSalinity")
    assert ax.get_xlabel().endswith("$S$ [g/kg]")
    converted = compare([weiss], weiss, inputs)
    ax = plot_values(converted, input_kind="SeaWaterSalinity")
    assert ax.get_xlabel().endswith(r"$S_{\mathrm{R}}$/(g/kg)")


def test_units_are_written_as_the_si_brochure_does() -> None:
    # A temperature difference is in degC, never a qualified "delta degC";
    # a product unit goes in parentheses.
    values = {"r": Q_([1.0, 2.0], "Pa*s")}
    found = Comparison(
        "r",
        {"TemperatureDifference": Q_([1.0, 2.0], "delta_degC")},
        values,
        {"r": np.zeros(2)},
    )
    ax = plot_values(found)
    assert ax.get_xlabel() == "Temperature difference / °C"
    assert ax.get_ylabel() == "Pa⋅s"
