# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Monotonicity proven, refuted or left unproven by interval arithmetic."""

import math
import sys
import threading
import warnings

import pytest

from nomogram.catalog import catalog, load_catalog
from nomogram.model import Formulation
from nomogram.monotonicity import (
    BOX_BUDGET,
    JUNCTION_TOLERANCE,
    Monotonicity,
    monotonicity,
)

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""

T = '{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }'
P = '{ identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }'
E = '{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "e" }'


def one(expression: str, inputs: str = T, extra: str = "") -> Formulation:
    """A formulation of the given expression, in a catalog of its own."""
    document = (
        SOURCE
        + f"""
[formulations.f]
label = "f"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "y", kind = "VapourPressure", unit = "HectoPA", description = "y" }}
inputs = [{inputs}]
{extra}
[[formulations.f.citations]]
reference = "src"
"""
    )
    return load_catalog([document]).formulations["f"]


def test_a_saturation_vapour_pressure_is_proven_increasing() -> None:
    f = catalog().formulations["alduchov_eskridge1996"]
    found = monotonicity(f, "t", (-40.0, 50.0))
    assert isinstance(found, Monotonicity)
    assert found.status == "proven"
    assert found.direction == "increasing"
    assert found.input == "t"
    assert dict(found.over) == {"t": (-40.0, 50.0)}
    assert "mpmath.iv" in found.method
    assert not found.at
    assert not found.steps


@pytest.mark.parametrize(
    ("expression", "interval", "direction"),
    [
        ("1 / t", (1.0, 1e6), "decreasing"),
        ("atan(t)", (-5.0, 5.0), "increasing"),
        ("tanh(t / 10)", (-30.0, 30.0), "increasing"),
        ("-log10(t) + sqrt(t)", (0.01, 0.1), "decreasing"),
        ("sin(t / 10)", (-10.0, 10.0), "increasing"),
        ("cos(t / 10)", (1.0, 20.0), "decreasing"),
        ("exp(1) * t + pi", (0.0, 1.0), "increasing"),
    ],
)
def test_every_function_of_the_syntax_is_bounded(
    expression: str, interval: tuple[float, float], direction: str
) -> None:
    found = monotonicity(one(expression), "t", interval)
    assert (found.status, found.direction) == ("proven", direction)


def test_an_identifier_named_after_eulers_number() -> None:
    found = monotonicity(one("e ** 2 + exp(1)", E), "e", (1.0, 2.0))
    assert (found.status, found.direction) == ("proven", "increasing")


def test_a_derivative_that_changes_sign_refutes() -> None:
    found = monotonicity(one("(t - 1) ** 2"), "t", (0.0, 3.0))
    assert found.status == "refuted"
    assert found.direction is None
    assert "changes sign" in found.method
    assert set(found.at) == {"t"}


@pytest.mark.parametrize(
    ("expression", "interval", "reason"),
    [
        # The derivative is negative everywhere, but the function has a pole.
        ("1 / (t - 1)", (0.0, 2.0), "pole"),
        # Strictly increasing, but the derivative vanishes at 0.
        ("t ** 3", (-1.0, 1.0), "pole"),
        # A constant has no sign.
        ("piecewise((2, t < 5), (3, t >= 5))", (0.0, 1.0), "identically zero"),
    ],
)
def test_unproven_without_a_counterexample(
    expression: str, interval: tuple[float, float], reason: str
) -> None:
    found = monotonicity(one(expression), "t", interval)
    assert (found.status, found.direction) == ("unproven", None)
    assert reason in found.method


def test_the_budget_bounds_the_search() -> None:
    found = monotonicity(one("t ** 3"), "t", (-1.0, 1.0), budget=3)
    assert found.status == "unproven"
    assert "within 3 sub-boxes" in found.method
    assert BOX_BUDGET > 3


def test_a_continuous_piecewise_definition_is_proven() -> None:
    f = one(
        "piecewise((C * exp(A_i * t / (B_i + t)), t < 0), (C * exp(A * t / (B + t)), t >= 0))",
        extra="coefficients = { C = 6.112, A = 17.62, B = 243.12, A_i = 22.46, B_i = 272.62 }",
    )
    found = monotonicity(f, "t", (-40.0, 40.0))
    assert (found.status, found.direction) == ("proven", "increasing")


def test_a_step_forward_at_a_junction_is_monotonic() -> None:
    found = monotonicity(one("piecewise((t, t < 1), (t + 5, t >= 1))"), "t", (0.0, 2.0))
    assert (found.status, found.direction) == ("proven", "increasing")


def test_a_step_back_at_a_junction_is_measured() -> None:
    found = monotonicity(
        one("piecewise((-t + 100, t < 1), (-t + 100 + 2e-3, t >= 1))"), "t", (0.0, 2.0)
    )
    assert found.status == "refuted"
    assert found.direction == "decreasing"
    assert "steps back at 1 junction" in found.method
    assert dict(found.at) == {"t": 1.0}
    assert found.steps[1.0] == pytest.approx(2e-3 / 99.0, rel=1e-9)
    # Both slopes are -1: the step is reached twice over 2e-3 of t.
    assert found.widths[1.0] == pytest.approx(2e-3, rel=1e-9)


def test_a_gentle_slope_widens_a_small_step() -> None:
    # A step back of 1e-6 of the value, where the second branch rises by
    # 1e-3 per unit of t: reached twice over 0.1 of t.
    found = monotonicity(
        one("piecewise((t + 100, t < 1), (1e-3 * t + 101 - 1e-3 - 1e-4, t >= 1))"),
        "t",
        (0.0, 2.0),
    )
    assert (found.status, found.direction) == ("refuted", "increasing")
    assert found.steps[1.0] == pytest.approx(1e-4 / 101.0, rel=1e-6)
    assert found.widths[1.0] == pytest.approx(0.1, rel=1e-6)


def test_a_step_back_within_the_rounding_is_none() -> None:
    step = 99.0 * JUNCTION_TOLERANCE / 10
    found = monotonicity(
        one(f"piecewise((-t + 100, t < 1), (-t + 100 + {step!r}, t >= 1))"),
        "t",
        (0.0, 2.0),
    )
    assert (found.status, found.direction) == ("proven", "decreasing")


def test_a_step_back_of_exactly_the_tolerance_is_none() -> None:
    for expression in (
        "piecewise((t, t < 1), (t - 1e-12, t >= 1))",
        "piecewise((2 * t, t < 1), (2 * t - 2e-12, t >= 1))",
    ):
        found = monotonicity(one(expression), "t", (0.0, 2.0))
        assert (found.status, found.direction) == ("proven", "increasing")


@pytest.mark.parametrize(
    "key",
    [
        "large_yeager2004_profile_function_momentum",
        "large_yeager2004_profile_function_heat",
        "coare36_profile_function_momentum",
        "ecmwf_ifs_profile_function_momentum",
    ],
)
def test_a_junction_where_the_value_is_0(key: str) -> None:
    # psi(0) = 0 on both sides: no relative step to measure, and none.
    found = monotonicity(catalog().formulations[key], "zeta", (-1.0, 1.0))
    assert (found.status, found.direction) == ("proven", "decreasing")
    found = monotonicity(
        one("piecewise((t, t < 0), (2 * t, t >= 0))"), "t", (-1.0, 1.0)
    )
    assert found.status == "proven"


def test_an_end_of_the_box_held_by_another_branch() -> None:
    # The end t = 1 belongs to the second branch: a junction too.
    found = monotonicity(
        one("piecewise((t + 100, t < 1), (t, t >= 1))"), "t", (0.0, 1.0)
    )
    assert (found.status, found.direction) == ("refuted", "increasing")
    assert found.steps[1.0] == pytest.approx(100.0 / 101.0, rel=1e-9)
    assert found.widths[1.0] == pytest.approx(100.0, rel=1e-9)
    # Held by the branch of the box: nothing to measure.
    found = monotonicity(one("piecewise((t, t <= 1), (t + 5, t > 1))"), "t", (0.0, 1.0))
    assert found.status == "proven"
    # Held by no branch: no value there.
    found = monotonicity(one("piecewise((t, t < 1))"), "t", (0.0, 1.0))
    assert found.status == "proven"


def test_a_face_of_the_box_held_by_another_branch() -> None:
    # At p = 1, the end of the box, the function decreases in t.
    f = one("piecewise((t, p < 1), (-t, p >= 1))", f"{T}, {P}")
    found = monotonicity(f, "t", {"t": (0.0, 1.0), "p": (0.0, 1.0)})
    assert (found.status, found.direction) == ("refuted", None)
    found = monotonicity(f, "t", {"t": (0.0, 1.0), "p": (0.0, 0.5)})
    assert found.status == "proven"


def test_concurrent_calls_change_no_global_state() -> None:
    import mpmath
    from mpmath import iv

    from nomogram.monotonicity import _interval_namespace

    # atan bounded with a precision of its own; no warning filter.
    f = one("atan(t)")
    precision, filters = mpmath.mp.prec, list(warnings.filters)
    interval = sys.getswitchinterval()

    atan = _interval_namespace()["atan"]

    def work() -> None:
        for _ in range(50):
            monotonicity(f, "t", (0.5, 5.0))
        for _ in range(1000):
            atan(iv.mpf([0.1, 0.2]))

    sys.setswitchinterval(1e-5)
    try:
        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(interval)
    assert mpmath.mp.prec == precision
    assert warnings.filters == filters


def test_branches_in_opposite_directions_refute() -> None:
    found = monotonicity(one("piecewise((t, t < 1), (-t, t >= 1))"), "t", (0.0, 2.0))
    assert (found.status, found.direction) == ("refuted", None)
    assert "between branches" in found.method


def test_no_branch_in_part_of_the_box() -> None:
    found = monotonicity(one("piecewise((t, t < 1))"), "t", (0.0, 2.0))
    assert found.status == "unproven"
    assert "no branch holds" in found.method


def test_several_inputs() -> None:
    f = one("t * p", f"{T}, {P}")
    found = monotonicity(f, "t", {"t": (0.0, 10.0), "p": (1.0, 2.0)})
    assert (found.status, found.direction) == ("proven", "increasing")
    # Increasing for a positive p, decreasing for a negative one.
    found = monotonicity(f, "t", {"t": (0.0, 10.0), "p": (-1.0, 2.0)})
    assert found.status == "refuted"
    assert set(found.at) == {"t", "p"}


def test_a_junction_with_several_inputs() -> None:
    forward = one("piecewise((t * p, t < 1), (t * p + p, t >= 1))", f"{T}, {P}")
    box = {"t": (0.0, 2.0), "p": (1.0, 2.0)}
    assert monotonicity(forward, "t", box).status == "proven"
    back = one("piecewise((t * p, t < 1), (t * p - p, t >= 1))", f"{T}, {P}")
    found = monotonicity(back, "t", box)
    assert (found.status, found.direction) == ("refuted", "increasing")
    assert found.at["t"] == 1.0
    assert found.steps[1.0] == pytest.approx(1.0, rel=1e-9)
    assert found.widths[1.0] == pytest.approx(1.0, rel=1e-9)


def test_the_largest_step_back_over_the_other_inputs() -> None:
    # Forward for p < 0.5, back beyond: the largest step, 0.75 of the
    # value, is at p = 1, whatever the point a search meets first.
    f = one("piecewise((t + 2, t < 0), (t + 1.5 - p, t >= 0))", f"{T}, {P}")
    found = monotonicity(f, "t", {"t": (-1.0, 1.0), "p": (-1.0, 1.0)})
    assert (found.status, found.direction) == ("refuted", "increasing")
    assert found.steps[0.0] == pytest.approx(0.75, rel=1e-3)
    assert found.at["p"] == pytest.approx(1.0, abs=2e-3)


def test_an_implicit_equation_is_proven_over_the_unknown_too() -> None:
    # KEYPS: Phi_M increases with zeta on the unstable side, where its
    # source applies it.
    f = catalog().formulations["businger1971_keyps"]
    box = {"zeta": (-1000.0, 0.0), "Phi_M": (1e-3, 1e3)}
    found = monotonicity(f, "zeta", box)
    assert (found.status, found.direction) == ("proven", "increasing")
    assert "-h_x / h_y" in found.method
    assert set(found.over) == {"zeta", "Phi_M"}
    # Over a box wider than the solutions, a change of sign does not refute.
    found = monotonicity(f, "zeta", {"zeta": (-10.0, 10.0), "Phi_M": (1e-3, 1e3)})
    assert found.status == "unproven"


def test_an_implicit_equation_needs_a_finite_interval_of_its_unknown() -> None:
    f = catalog().formulations["businger1971_keyps"]
    if math.isfinite(f._search_interval(None)[1]):
        pytest.skip("the unknown has a finite interval")
    with pytest.raises(ValueError, match="interval of the unknown"):
        monotonicity(f, "zeta", {"zeta": (-1.0, 0.0)})


@pytest.mark.parametrize(
    ("input", "over", "message"),
    [
        ("x", (0.0, 1.0), "has no input 'x'"),
        ("t", {"t": (0.0, 1.0), "q": (0.0, 1.0)}, "has no variable q"),
        ("t", {}, "give an interval for t"),
        ("t", (0.0, math.inf), "finite and not empty"),
        ("t", (1.0, 1.0), "finite and not empty"),
    ],
)
def test_invalid_requests(input: str, over: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        monotonicity(one("t"), input, over)  # type: ignore[arg-type]


def test_a_pair_needs_a_single_input_and_a_positive_budget() -> None:
    with pytest.raises(ValueError, match="several inputs"):
        monotonicity(one("t * p", f"{T}, {P}"), "t", (0.0, 1.0))
    with pytest.raises(ValueError, match="budget must be positive"):
        monotonicity(one("t"), "t", (0.0, 1.0), budget=0)
