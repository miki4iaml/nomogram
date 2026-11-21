# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The tolerance a source states at the ends of a validity domain.

A fit reproduces the formulation it inverts within a deviation its source
states (0.1 mK for Hardy's frost point); at the ends of its range, the fit
may fall that much beyond them, and still be inside.
"""

import math
from typing import Any

import numpy as np
import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog
from nomogram.inversion import invert
from nomogram.model import Formulation, Variable
from nomogram.units import Q_

F = catalog().formulations

SOURCE = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.f]
label = "f"
expression = "a * t"
fixed_units = true
output = { identifier = "e", kind = "Pressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 2.0 }
"""


def load(domain: str, physical: bool = False) -> Formulation:
    if physical:
        return load_catalog(
            [
                SOURCE
                + "[[formulations.f.domains]]\n"
                + domain
                + '\n[[formulations.f.citations]]\nreference = "src"\n'
            ]
        ).formulations["f"]
    document = (
        SOURCE
        + '\n[[formulations.f.citations]]\nreference = "src"\n\n'
        + "[[formulations.f.citations.domains]]\n"
        + domain
    )
    return load_catalog([document]).formulations["f"]


# --- The fits of the catalog --------------------------------------------------------


@pytest.mark.parametrize(
    ("forward", "variable", "unit", "inverse", "ends"),
    [
        ("hardy1998_water", "T", "K", "hardy1998_dew_point", (173.15, 373.15)),
        ("hardy1998_ice", "T", "K", "hardy1998_frost_point", (173.15, 273.16)),
        ("sonntag1990", "T", "K", "sonntag1994_dew_point", (173.15, 373.15)),
        ("sonntag1990_ice", "T", "K", "sonntag1994_frost_point", (173.15, 273.16)),
    ],
)
def test_a_fit_stays_inside_its_range_within_its_tolerance(
    forward: str, variable: str, unit: str, inverse: str, ends: tuple[float, float]
) -> None:
    # The round trip at each end of the range: the fit gives a value, within
    # the tolerance its source states (Hardy's frost point lands 12 uK beyond
    # 273.16 K, Sonntag's dew point 0.96 mK beyond 100 degC).
    fit = F[inverse]
    (domain,) = fit.domains
    (identifier,) = domain.tolerance
    low_tolerance, high_tolerance = domain.tolerance[identifier]
    at_ends: dict[str, Any] = {variable: Q_(np.array(ends), unit)}
    e = F[forward].evaluate(**at_ends)
    given: dict[str, Any] = {fit.inputs[0].identifier: e}
    back = fit.evaluate(**given).to(unit).magnitude
    assert not np.any(np.isnan(back))
    assert ends[0] - back[0] <= low_tolerance
    assert back[1] - ends[1] <= high_tolerance


def test_beyond_its_tolerance_a_value_is_outside() -> None:
    frost = F["hardy1998_frost_point"]  # 0.1 mK at both ends
    e = 611.657
    assert not frost.outside_mask({"e": e, "T_f": 273.16 + 0.00009})
    assert frost.outside_mask({"e": e, "T_f": 273.16 + 0.00011})
    dew = F["sonntag1994_dew_point"]  # 0.06 K at -100 degC, 0.01 K at 100 degC
    e_hpa = 1013.25
    inside = [-100.05, 100.009]
    outside = [-100.07, 100.011]
    assert not dew.outside_mask({"e": e_hpa, "t_d": np.array(inside)}).any()
    assert dew.outside_mask({"e": e_hpa, "t_d": np.array(outside)}).all()


# --- The rules of the catalog -------------------------------------------------------


def test_a_tolerance_at_both_ends_or_at_each() -> None:
    f = load(
        'bounds = { t = [0, 50] }\ntolerance = { t = [0.5, 0.1] }\ncriterion = "Within 0.5 K, 0.1 K."\n'
    )
    (domain,) = f.domains
    assert domain.tolerance["t"] == (0.5, 0.1)
    f = load(
        'bounds = { t = [0, 50] }\ntolerance = { t = 0.2 }\ncriterion = "Within 0.2 K."\n'
    )
    assert f.domains[0].tolerance["t"] == (0.2, 0.2)
    result = f.evaluate(t=Q_(np.array([-0.1, 50.15, 50.3]), "degC")).magnitude
    assert np.isnan(result).tolist() == [False, False, True]


@pytest.mark.parametrize(
    ("domain", "message"),
    [
        (
            "bounds = { t = [0, 50] }\ntolerance = { t = 0.2 }\n",
            "criterion states the deviation",
        ),
        (
            'bounds = { t = [0, 50] }\ntolerance = { e = 0.2 }\ncriterion = "c"\n',
            "not bounded by this domain",
        ),
        (
            'bounds = { t = [0, inf] }\ntolerance = { t = 0.2 }\ncriterion = "c"\n',
            "infinite end takes no tolerance",
        ),
        (
            'bounds = { t = [0, 50] }\ntolerance = { t = 0 }\ncriterion = "c"\n',
            "widens nothing",
        ),
        (
            'bounds = { t = [0, 50] }\ntolerance = { t = -0.1 }\ncriterion = "c"\n',
            "0 or more",
        ),
        (
            'bounds = { t = [0, 50] }\ntolerance = { t = [0.1] }\ncriterion = "c"\n',
            "a number or \\[low, high\\]",
        ),
    ],
)
def test_a_tolerance_is_refused_without_its_conditions(
    domain: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load(domain)


def test_a_physical_domain_takes_no_tolerance() -> None:
    with pytest.raises(CatalogError, match="a physical domain has none"):
        load(
            'bounds = { t = [0, 50] }\ntolerance = { t = 0.2 }\ncriterion = "c"\n',
            physical=True,
        )


# --- Inversion ----------------------------------------------------------------------


def test_an_inversion_carries_the_tolerance_with_its_bound() -> None:
    f = load(
        "bounds = { t = [0, 50], e = [0, 100] }\n"
        "tolerance = { t = [0.5, 0.1], e = 1.0 }\n"
        'criterion = "Within 0.5 K and 0.1 K; 1 hPa."\n'
    )
    inverse = invert(
        f,
        "t",
        output=Variable("T", "ThermodynamicTemperature", "K", "T"),
        input=Variable("e", "Pressure", "HectoPA", "e"),
    )
    assert isinstance(inverse, Formulation)
    (domain,) = inverse.domains
    assert domain.bounds["T"] == pytest.approx((273.15, 323.15))
    # A difference: the same in K as in degC.
    assert domain.tolerance["T"] == (0.5, 0.1)
    # The source's bound on its output and the image of t coincide: the
    # source's bound wins, with its tolerance.
    assert domain.tolerance["e"] == (1.0, 1.0)
    # 100.15 hPa gives 50.075 degC, within both tolerances; 100.5 hPa gives
    # 50.25 degC, beyond the 0.1 K of T though within the 1 hPa of e.
    assert not math.isnan(float(inverse.evaluate(e=Q_(100.15, "hPa")).magnitude))
    assert math.isnan(float(inverse.evaluate(e=Q_(100.5, "hPa")).magnitude))
