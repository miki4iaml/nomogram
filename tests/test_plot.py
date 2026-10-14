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
    assert ax.get_xlabel() == "Thermodynamic Temperature [°C]"
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert "Magnus form, Sonntag (1990) coefficients" in labels


def test_values_with_a_notation(comparison: Comparison) -> None:
    ax = plot_values(comparison, notation=CATALOG.notations["wmo"])
    assert ax.get_ylabel() == r"$e_{\mathrm{w}}$ [Pa]"
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
    assert ax.get_ylabel() == "[Pa]"
    assert ax.lines[0].get_label() == "r"
    other = Comparison(
        "r", {"Custom": Q_([1.0, 2.0], "K")}, two.values, two.relative_deviations
    )
    assert plot_values(other).get_xlabel() == "Custom [K]"


def test_missing_extra_gives_an_explicit_message(
    monkeypatch: pytest.MonkeyPatch, comparison: Comparison
) -> None:
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    with pytest.raises(ImportError, match=r"nomogram\[viz\]"):
        plot_deviations(comparison)


@pytest.mark.parametrize("notation", [None, *sorted(CATALOG.notations)])
def test_every_formulation_renders_in_mathtext(notation: str | None) -> None:
    parser = MathTextParser("path")
    chosen = CATALOG.notations[notation] if notation else None
    for formulation in FORMULATIONS.values():
        parser.parse(f"${formulation.latex(chosen)}$")


def test_curves_beyond_ten_change_line_style(comparison: Comparison) -> None:
    ax = plot_deviations(comparison)
    styles = [line.get_linestyle() for line in ax.lines[:-1]]
    assert styles[:10] == ["-"] * 10
    assert set(styles[10:]) == {"-."}
