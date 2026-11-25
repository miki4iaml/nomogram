# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Systems of equations: unknowns, Newton's method, the fixed point, domains."""

import math
import sys
import threading
import warnings
from typing import Any, NoReturn

import numpy as np
import pytest

from nomogram.catalog import load_catalog
from nomogram.model import Formulation, OutOfDomainError, ValidityWarning
from nomogram.systems import (
    CONVERGED,
    ITERATED,
    NOT_CONVERGED,
    OUTSIDE,
    SINGULAR,
    STATUS,
    TOLERANCE,
    UNDEFINED,
    ConvergenceWarning,
    Equation,
    Solution,
    System,
)
from nomogram.units import Q_

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""

ONE = 'kind = "DimensionlessRatio", unit = "UNITLESS"'


def variable(identifier: str, kind: str = ONE) -> str:
    return f'{{ identifier = "{identifier}", {kind}, description = "{identifier}" }}'


def entry(
    key: str,
    expression: str,
    output: str,
    inputs: list[str],
    *,
    output_kind: str = ONE,
    input_kinds: dict[str, str] | None = None,
    stated: str = "",
) -> str:
    kinds = input_kinds or {}
    declared = ", ".join(variable(i, kinds.get(i, ONE)) for i in inputs)
    domain = (
        f"[[formulations.{key}.citations.domains]]\nbounds = {{ {stated} }}\n"
        if stated
        else ""
    )
    return f"""
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = true
output = {variable(output, output_kind)}
inputs = [{declared}]

[[formulations.{key}.citations]]
reference = "src"
{domain}"""


def formulations(*entries: str) -> dict[str, Formulation]:
    return dict(load_catalog([SOURCE + "".join(entries)]).formulations)


F = formulations(
    entry("fx", "(a - y) / 2", "x", ["a", "y"]),
    entry("fy", "(b - x) / 3", "y", ["b", "x"]),
    entry("root", "sqrt(c - y)", "x", ["c", "y"]),
    entry("line", "k * x", "y", ["k", "x"]),
    entry("cubic", "x ** 3 + x == y", "x", ["y"]),
    entry("rest", "c - x", "y", ["c", "x"]),
    entry("shift", "y + 1", "x", ["y"]),
    entry("same", "x", "y", ["x"]),
    entry("square", "y ** 2 + 1", "x", ["y"]),
    entry("parabola", "y ** 2", "x", ["y"]),
    entry("cubic_zero", "x ** 3 + 2 * x - y == 0", "x", ["y"]),
    entry("tiny", "y / 1e15 + 1", "x", ["y"]),
    entry("huge", "1e15 * z", "y", ["z"]),
    entry("half", "x / 2", "z", ["x"]),
    entry(
        "root_bounded",
        "sqrt(c / 100 - y)",
        "x",
        ["c", "y"],
        input_kinds={"c": 'kind = "DimensionlessRatio", unit = "PERCENT"'},
        stated="c = [0.0, 1000.0]",
    ),
    entry(
        "square_root_of",
        "x ** 2 == y",
        "x",
        ["y"],
        output_kind='kind = "VapourPressure", unit = "HectoPA"',
    ),
    entry(
        "two_less",
        "2 - x",
        "y",
        ["x"],
        input_kinds={"x": 'kind = "VapourPressure", unit = "HectoPA"'},
    ),
    entry(
        "temperature_of_pressure",
        "p / 10",
        "T",
        ["p"],
        output_kind='kind = "ThermodynamicTemperature", unit = "K"',
        input_kinds={"p": 'kind = "ThermodynamicTemperature", unit = "K"'},
    ),
    entry(
        "hectopascals",
        "q / 100 + 1",
        "p",
        ["q"],
        output_kind='kind = "Pressure", unit = "HectoPA"',
        input_kinds={"q": 'kind = "Pressure", unit = "PA"'},
    ),
    entry(
        "pascals",
        "500 * p + 3",
        "q",
        ["p"],
        output_kind='kind = "Pressure", unit = "PA"',
        input_kinds={"p": 'kind = "Pressure", unit = "KiloPA"'},
    ),
    entry(
        "kelvins",
        "t + 278.15",
        "T",
        ["t"],
        output_kind='kind = "ThermodynamicTemperature", unit = "K"',
        input_kinds={"t": 'kind = "CelsiusTemperature", unit = "DEG_C"'},
    ),
    entry(
        "celsius",
        "0.5 * u + 10",
        "t",
        ["u"],
        output_kind='kind = "CelsiusTemperature", unit = "DEG_C"',
        input_kinds={"u": 'kind = "CelsiusTemperature", unit = "DEG_C"'},
    ),
    entry("ga", "b + c", "a", ["b", "c"]),
    entry(
        "vapour_a",
        "a - x",
        "y",
        ["a", "x"],
        input_kinds={"a": 'kind = "VapourPressure", unit = "HectoPA"'},
    ),
    entry(
        "bounded",
        "(a / 100 - y) / 2",
        "x",
        ["a", "y"],
        input_kinds={"a": 'kind = "DimensionlessRatio", unit = "PERCENT"'},
        stated="a = [0.0, 500.0]",
    ),
)
ONES = Q_(1.0, "dimensionless")


def linear(first: str = "fx", **options: Any) -> System:
    return System(
        "linear",
        "Two linear equations",
        (Equation(F[first], **options), Equation(F["fy"])),
        start={"y": "0"},
        iterations=60,
    )


def one(value: Any) -> Any:
    return Q_(value, "dimensionless")


def test_the_unknowns_are_read_before_they_are_given() -> None:
    system = linear()
    assert system.unknowns == ("y",)
    assert system.intermediates == ("x",)
    assert system.inputs == ("a", "b")
    assert system.outputs == ("x", "y")
    assert system.variable("a").identifier == "a"
    with pytest.raises(KeyError, match="no variable 'z'"):
        system.variable("z")


@pytest.mark.parametrize("method", ["newton", "fixed-point"])
def test_a_linear_system(method: str) -> None:
    solution = linear().evaluate(method=method, a=one(7.0), b=one(4.0))  # type: ignore[arg-type]
    assert isinstance(solution, Solution)
    assert solution["x"].magnitude == pytest.approx(3.4, rel=1e-12)
    assert solution["y"].magnitude == pytest.approx(0.2, rel=1e-12)
    assert solution.method == method
    assert solution.status == (CONVERGED if method == "newton" else ITERATED)
    assert solution.residual <= TOLERANCE
    # Newton solves a linear system in one step, with an exact Jacobian.
    assert solution.iterations == (1 if method == "newton" else 60)


def test_a_nonlinear_system_and_its_fixed_point() -> None:
    system = System(
        "nonlinear",
        "x = sqrt(c - y), y = k x",
        (Equation(F["root"]), Equation(F["line"])),
        start={"y": "c / 2"},
    )
    solution = system.evaluate(c=one(6.0), k=one(1.0))
    assert solution["x"].magnitude == pytest.approx(2.0, rel=1e-13)
    assert solution["y"].magnitude == pytest.approx(2.0, rel=1e-13)
    assert solution.iterations <= 6
    # The passes of the fixed point, as a loop over the formulations does.
    y = 3.0
    for _ in range(40):
        x = F["root"].evaluate(c=one(6.0), y=one(y)).magnitude
        y = F["line"].evaluate(k=one(1.0), x=one(x)).magnitude
    passes = system.evaluate(
        method="fixed-point", iterations=40, c=one(6.0), k=one(1.0)
    )
    assert passes["x"].magnitude == pytest.approx(x, rel=1e-15)
    assert passes["y"].magnitude == pytest.approx(y, rel=1e-15)
    assert passes.status == ITERATED
    with pytest.raises(ValueError, match="give iterations"):
        system.evaluate(method="fixed-point", c=one(6.0), k=one(1.0))


@pytest.mark.parametrize("order", [("cubic", "rest"), ("rest", "cubic")])
def test_an_implicit_equation_intermediate_or_unknown(order: tuple[str, str]) -> None:
    # x**3 + x = y and y = c - x: x = 1, y = 2 for c = 3.
    system = System(
        "implicit",
        "With an implicit equation",
        tuple(Equation(F[key]) for key in order),
        start={("y" if order[0] == "cubic" else "x"): "1.5"},
        iterations=80,
    )
    assert system.unknowns == (("y",) if order[0] == "cubic" else ("x",))
    for method in ("newton", "fixed-point"):
        solution = system.evaluate(method=method, c=one(3.0))
        assert solution["x"].magnitude == pytest.approx(1.0, rel=1e-12)
        assert solution["y"].magnitude == pytest.approx(2.0, rel=1e-12)


def test_units_and_their_conversions_enter_the_jacobian() -> None:
    # p in hPa from q in Pa; q in Pa from p in kPa: p = 2.06 hPa, q = 106 Pa.
    system = System(
        "pressures",
        "Two units",
        (Equation(F["hectopascals"]), Equation(F["pascals"])),
        start={"q": "0"},
    )
    solution = system.evaluate()
    assert solution["p"].to("hPa").magnitude == pytest.approx(2.06, rel=1e-12)
    assert solution["q"].to("Pa").magnitude == pytest.approx(106.0, rel=1e-12)
    assert solution.iterations == 1


def test_an_offset_between_units() -> None:
    # T = t + 278.15 K (t in degC), t = 0.5 T + 10 (T taken in degC):
    # t = 25 degC, T = 303.15 K.
    system = System(
        "offset",
        "degC and K",
        (Equation(F["kelvins"]), Equation(F["celsius"], bind={"u": "T"})),
        start={"t": "0"},
    )
    solution = system.evaluate()
    assert solution["t"].to("degC").magnitude == pytest.approx(25.0, rel=1e-12)
    assert solution["T"].to("K").magnitude == pytest.approx(303.15, rel=1e-12)
    assert solution.iterations == 1


def test_a_singular_jacobian_gives_nan_and_a_warning() -> None:
    system = System(
        "singular",
        "x = y + 1, y = x",
        (Equation(F["shift"]), Equation(F["same"])),
        start={"y": "0"},
    )
    with pytest.warns(ConvergenceWarning, match="1 singular"):
        solution = system.evaluate()
    assert solution.status == SINGULAR
    assert math.isnan(solution["x"].magnitude)
    assert math.isnan(solution["y"].magnitude)


def test_no_solution_gives_nan_and_a_warning() -> None:
    # y = y**2 + 1 has no real root.
    system = System(
        "none",
        "x = y**2 + 1, y = x",
        (Equation(F["square"]), Equation(F["same"])),
        start={"y": "3"},
    )
    with pytest.warns(ConvergenceWarning, match="not solved"):
        solution = system.evaluate()
    assert solution.status in (NOT_CONVERGED, SINGULAR)
    assert math.isnan(solution["y"].magnitude)


def test_the_root_found_depends_on_the_start() -> None:
    # y = y**2: 0 and 1, each found from a start near it.
    system = System(
        "two",
        "x = y**2, y = x",
        (Equation(F["parabola"]), Equation(F["same"])),
        start={"y": "0.8"},
    )
    assert system.evaluate()["y"].magnitude == pytest.approx(1.0, rel=1e-12)
    near_zero = system.evaluate(start={"y": one(0.2)})["y"].magnitude
    assert near_zero == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(ValueError, match="not an unknown: x"):
        system.evaluate(start={"x": one(0.2)})


def test_an_infinite_derivative_is_never_converged() -> None:
    # At the first guess b = 1, a = 2 = d: the derivative of sqrt(d - a)
    # is infinite, and so are the terms. The residual relative to them is
    # not 0: undefined, Newton's method starts again from passes of the
    # fixed point, and finds the solution, b = (sqrt(5) - 1) / 2.
    system = System(
        "infinite",
        "a = b + c, b = sqrt(d - a)",
        (
            Equation(F["ga"]),
            Equation(F["root"], bind={"c": "d", "y": "a", "x": "b"}),
        ),
        start={"b": "1"},
    )
    solution = system.evaluate(c=one(1.0), d=one(2.0))
    assert solution.status == CONVERGED
    b = solution["b"].magnitude
    assert b == pytest.approx((math.sqrt(5.0) - 1.0) / 2.0, rel=1e-12)
    assert b == pytest.approx(math.sqrt(2.0 - (b + 1.0)), rel=1e-12)


def test_an_undefined_start_is_reported() -> None:
    with pytest.warns(ConvergenceWarning, match="1 undefined"):
        solution = linear().evaluate(start={"y": one(np.nan)}, a=one(7.0), b=one(4.0))
    assert solution.status == UNDEFINED


def test_rows_are_solved_together() -> None:
    a = one(np.array([[7.0, 7.0, 7.0], [2.0, 2.0, 2.0]]))
    b = one(np.array([4.0, 9.0, 1.0]))
    solution = linear().evaluate(a=a, b=b)
    assert solution["x"].magnitude.shape == (2, 3)
    expected = (3 * a.magnitude - b.magnitude) / 5
    assert solution["x"].magnitude == pytest.approx(expected, rel=1e-12)
    assert (solution.status == CONVERGED).all()


def test_domains_apply_once_solved() -> None:
    # a = 7 (700 %) lies outside the domain [0, 500] % of the first equation.
    with pytest.warns(ValidityWarning, match="outside"):
        warned = linear("bounded").evaluate(outside="warn", a=one(7.0), b=one(4.0))
    assert warned["x"].magnitude == pytest.approx(3.4, rel=1e-12)
    blank = linear("bounded").evaluate(a=one(7.0), b=one(4.0))
    assert math.isnan(blank["x"].magnitude)
    assert math.isnan(blank["y"].magnitude)
    with pytest.raises(OutOfDomainError, match="linear: bounded"):
        linear("bounded").evaluate(outside="raise", a=one(7.0), b=one(4.0))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        practice = linear("bounded", outside="ignore").evaluate(a=one(7.0), b=one(4.0))
    assert practice["y"].magnitude == pytest.approx(0.2, rel=1e-12)
    inside = linear("bounded").evaluate(a=one(np.array([2.0, 7.0])), b=one(4.0))
    assert np.isnan(inside["x"].magnitude).tolist() == [False, True]


def test_statuses_are_named() -> None:
    assert STATUS[CONVERGED] == "converged"
    assert STATUS[NOT_CONVERGED] == "not converged"
    assert STATUS[OUTSIDE] == "inputs outside a domain"
    assert len(STATUS) == 6


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: System("s", "s", (), start={}), "needs equations"),
        (
            lambda: System(
                "s", "s", (Equation(F["fx"]), Equation(F["bounded"])), start={}
            ),
            "two equations give x",
        ),
        (
            lambda: System("s", "s", linear().equations, start={}),
            "missing: y",
        ),
        (
            lambda: System("s", "s", (Equation(F["fy"]),), start={"y": "0"}),
            "not an unknown: y",
        ),
        (
            lambda: System("s", "s", linear().equations, start={"y": "0", "x": "0"}),
            "not an unknown: x",
        ),
        (
            lambda: System("s", "s", linear().equations, start={"y": "z"}),
            "the first guess of y",
        ),
        (
            lambda: System(
                "s", "s", linear().equations, start={"y": "0"}, iterations=0
            ),
            "iterations must be positive",
        ),
        (lambda: Equation(F["fx"], bind={"z": "w"}), "has no variable z"),
        (lambda: Equation(F["fx"], outside="never"), "outside: expected"),  # type: ignore[arg-type]
    ],
)
def test_invalid_systems_are_refused(build: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build()


def test_a_chain_without_a_loop_is_a_system() -> None:
    # No equation reads a variable before the one giving it: no unknown,
    # no first guess; solved in order.
    chain = System("s", "s", (Equation(F["fy"]),), start={})
    assert (chain.unknowns, chain.inputs, chain.outputs) == ((), ("b", "x"), ("y",))
    solution = chain.evaluate(b=Q_(7.0, ""), x=Q_(1.0, ""))
    assert solution["y"].magnitude == pytest.approx(2.0)
    passes = chain.evaluate(
        b=Q_(7.0, ""), x=Q_(1.0, ""), method="fixed-point", iterations=1
    )
    assert passes["y"].magnitude == pytest.approx(2.0)


def test_invalid_calls_are_refused() -> None:
    system = linear()
    with pytest.raises(TypeError, match="missing inputs: b; unexpected: c"):
        system.evaluate(a=one(1.0), c=one(1.0))
    with pytest.raises(ValueError, match="method: expected"):
        system.evaluate(method="bisection", a=one(1.0), b=one(1.0))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="iterations must be positive"):
        system.evaluate(iterations=0, a=one(1.0), b=one(1.0))
    with pytest.raises(ValueError, match="outside: expected"):
        system.evaluate(outside="never", a=one(1.0), b=one(1.0))  # type: ignore[arg-type]


def test_conventional_scales_enter_the_jacobian() -> None:
    # S on the Knudsen scale from the chlorinity (Knudsen, 1901), r from S
    # taken on that scale (Sverdrup, 1942), and a chlorinity from r: the
    # system holds S on the reference scale, converted at each end.
    from nomogram.catalog import catalog

    bundled = catalog().formulations
    from bundled_catalog import with_families

    test_entry = entry(
        "chlorinity",
        "19 + r / 2",
        "Cl",
        ["r"],
        output_kind='kind = "Chlorinity", unit = "PERMILLE"',
        input_kinds={
            "r": 'kind = "RelativeVapourPressureOfSeaWater", unit = "UNITLESS"'
        },
    )
    chlorinity = with_families(
        ("sea-water",),
        SOURCE.replace("references.src", "references.test_source")
        + test_entry.replace('reference = "src"', 'reference = "test_source"'),
    ).formulations["chlorinity"]
    system = System(
        "salinity",
        "Through the Knudsen scale",
        (
            Equation(bundled["knudsen1901_salinity"]),
            Equation(bundled["sverdrup1942_vapour_pressure_ratio"]),
            Equation(chlorinity),
        ),
        start={"Cl": "19"},
        iterations=30,
    )
    assert system.unknowns == ("Cl",)
    solution = system.evaluate()
    assert solution.status == CONVERGED
    assert solution.iterations <= 3
    cl = solution["Cl"]
    s = bundled["knudsen1901_salinity"].evaluate(Cl=cl)
    r = bundled["sverdrup1942_vapour_pressure_ratio"].evaluate(S=s)
    assert solution["S"].magnitude == pytest.approx(s.magnitude, rel=1e-12)
    assert chlorinity.evaluate(r=r).magnitude == pytest.approx(cl.magnitude, rel=1e-12)
    passes = system.evaluate(method="fixed-point")
    assert passes["Cl"].magnitude == pytest.approx(cl.magnitude, rel=1e-12)


# --- Found in review ------------------------------------------------------


def test_an_implicit_unknown_stays_where_its_root_is_sought() -> None:
    # KEYPS has a negative root too; its physical domain keeps phi_M >= 0,
    # as Formulation.evaluate searches.
    from bundled_catalog import with_families

    document = SOURCE.replace("references.src", "references.test_source") + entry(
        "zeta_of",
        "z0 + 0.01 * Phi_M",
        "zeta",
        ["z0", "Phi_M"],
        output_kind='kind = "StabilityParameter", unit = "UNITLESS"',
        input_kinds={
            "Phi_M": 'kind = "GradientFunctionForMomentum", unit = "UNITLESS"'
        },
    ).replace('reference = "src"', 'reference = "test_source"')
    loaded = with_families(("boundary-layer",), document).formulations
    keyps = loaded["businger1971_keyps"]
    system = System(
        "keyps",
        "KEYPS with a stability depending on it",
        (Equation(loaded["zeta_of"]), Equation(keyps)),
        start={"Phi_M": "1"},
    )
    solution = system.evaluate(z0=one(-0.1))
    assert solution.status == CONVERGED
    phi = solution["Phi_M"].magnitude
    assert phi > 0
    assert keyps.evaluate(zeta=solution["zeta"]).magnitude == pytest.approx(
        phi, rel=1e-12
    )
    with pytest.warns(ConvergenceWarning, match="1 undefined"):
        outside = system.evaluate(start={"Phi_M": one(-3.0)}, z0=one(-0.1))
    assert outside.status == UNDEFINED


def test_newton_steps_are_not_the_passes_of_the_source() -> None:
    system = System(
        "nonlinear",
        "x = sqrt(c - y), y = k x",
        (Equation(F["root"]), Equation(F["line"])),
        start={"y": "c / 2"},
        iterations=2,
    )
    assert system.evaluate(c=one(6.0), k=one(1.0)).status == CONVERGED
    with pytest.warns(ConvergenceWarning, match="1 not converged"):
        capped = system.evaluate(iterations=2, c=one(6.0), k=one(1.0))
    assert capped.status == NOT_CONVERGED


def test_a_solution_at_zero_and_a_member_at_zero_converge() -> None:
    # y = (b - x) / 3 with x = (a - y) / 2: y = 0 for a = 7, b = 3.5.
    at_zero = linear().evaluate(a=one(7.0), b=one(3.5))
    assert at_zero.status == CONVERGED
    assert at_zero["y"].magnitude == pytest.approx(0.0, abs=1e-15)
    # x**3 + 2 x - y == 0 and y = c - x: x = 1, y = 3 for c = 4.
    system = System(
        "zero_member",
        "An equation written == 0",
        (Equation(F["rest"]), Equation(F["cubic_zero"])),
        start={"x": "0.5"},
    )
    solution = system.evaluate(c=one(4.0))
    assert solution.status == CONVERGED
    assert solution["x"].magnitude == pytest.approx(1.0, rel=1e-12)


def test_one_pass_of_the_fixed_point_is_one_pass_of_a_loop() -> None:
    system = System(
        "nonlinear",
        "x = sqrt(c - y), y = k x",
        (Equation(F["root"]), Equation(F["line"])),
        start={"y": "3"},
    )
    x = F["root"].evaluate(c=one(6.0), y=one(3.0)).magnitude
    y = F["line"].evaluate(k=one(1.0), x=one(x)).magnitude
    solution = system.evaluate(
        method="fixed-point", iterations=1, c=one(6.0), k=one(1.0)
    )
    assert solution["x"].magnitude == x
    assert solution["y"].magnitude == y


def test_inputs_outside_a_domain_are_not_solved() -> None:
    system = System(
        "bounded_root",
        "x = sqrt(c - y), y = k x, c in [0, 10]",
        (Equation(F["root_bounded"]), Equation(F["line"])),
        start={"y": "1"},
    )
    with pytest.raises(OutOfDomainError, match="bounded_root: root_bounded"):
        system.evaluate(outside="raise", c=one(-5.0), k=one(1.0))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        solution = system.evaluate(c=one(np.array([6.0, -5.0, 12.0])), k=one(1.0))
    assert solution.status.tolist() == [CONVERGED, OUTSIDE, OUTSIDE]
    assert np.isnan(solution["x"].magnitude).tolist() == [False, True, True]


def test_a_singular_jacobian_does_not_depend_on_units() -> None:
    # Unknowns y and z, of magnitudes 1e15 apart: x = 2, z = 1, y = 1e15.
    system = System(
        "magnitudes",
        "Unknowns far apart",
        (Equation(F["tiny"]), Equation(F["huge"]), Equation(F["half"])),
        start={"y": "0", "z": "0"},
    )
    assert system.unknowns == ("y", "z")
    solution = system.evaluate()
    assert solution.status == CONVERGED
    assert solution["x"].magnitude == pytest.approx(2.0, rel=1e-12)
    assert solution["y"].magnitude == pytest.approx(1e15, rel=1e-12)


def test_trial_points_raise_no_root_warning() -> None:
    # x**2 = y with x a vapour pressure (never negative) and y = 2 - x:
    # x = 1, y = 1, from a first guess far away.
    from nomogram.model import RootWarning

    system = System(
        "intermediate",
        "An implicit intermediate",
        (Equation(F["square_root_of"]), Equation(F["two_less"])),
        start={"y": "100"},
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", RootWarning)
        solution = system.evaluate()
    assert solution.status == CONVERGED
    assert solution["x"].to("hPa").magnitude == pytest.approx(1.0, rel=1e-12)


def test_concurrent_systems_change_no_warning_filter() -> None:
    # No filter is set to keep trial points quiet: a filter set and reset
    # by one thread while another runs would stay.
    system = System(
        "intermediate",
        "An implicit intermediate",
        (Equation(F["square_root_of"]), Equation(F["two_less"])),
        start={"y": "100"},
    )
    filters = list(warnings.filters)
    interval = sys.getswitchinterval()

    def work() -> None:
        for _ in range(20):
            system.evaluate()
            system.evaluate(method="fixed-point", iterations=3, start={"y": one(1.5)})

    sys.setswitchinterval(1e-5)
    try:
        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(interval)
    assert warnings.filters == filters


def test_scale_slopes_near_the_bounds_of_a_scale() -> None:
    from nomogram.catalog import catalog
    from nomogram.systems import _back, _link

    bundled = catalog().formulations
    taken = bundled["weiss_price1980_vapour_pressure"].inputs[0]
    # 0.1 mK below the end of the scale (30 degC on IPTS-48, 29.98376 on
    # ITS-90): a central difference would leave it.
    assert taken.scale is not None
    end = float(taken.scale.to_reference(np.array(30.0))) + 273.15
    value, slope = _link(taken, taken, "convert")(np.array([end - 1e-4, 290.0]))
    assert np.isfinite(value).all()
    assert slope == pytest.approx([1.0004, 1.0006], abs=1e-4)
    given = bundled["metpy171_dew_point"].output
    back_value, back_slope = _back(given, "convert")(np.array([10.0]))
    assert np.isfinite(back_value).all()
    assert back_slope == pytest.approx([1.0], abs=1e-3)


def test_links_and_first_guesses_are_checked_when_built() -> None:
    with pytest.raises(ValueError, match="x given as DimensionlessRatio cannot feed"):
        System(
            "kinds",
            "A ratio fed to a temperature",
            (
                Equation(F["temperature_of_pressure"], bind={"p": "x", "T": "y"}),
                Equation(F["shift"]),
            ),
            start={"x": "0"},
        )
    system = System(
        "numbers",
        "A number as first guess",
        [Equation(F["fx"]), Equation(F["fy"])],  # type: ignore[arg-type]
        start={"y": 0},  # type: ignore[dict-item]
    )
    assert isinstance(system.equations, tuple)
    assert system.start["y"] == "0.0"
    # One input, two kinds that cannot stand for each other.
    with pytest.raises(
        ValueError,
        match="the input a is taken as DimensionlessRatio in UNITLESS by fx, "
        "as VapourPressure in HectoPA by vapour_a",
    ):
        System(
            "mixed",
            "An input of two kinds",
            (Equation(F["fx"]), Equation(F["vapour_a"])),
            start={"y": "0"},
        )
    with pytest.raises(TypeError, match="not an expression"):
        System("s", "s", system.equations, start={"y": [0]})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="not in the shape of the inputs"):
        system.evaluate(start={"y": one(np.zeros(3))}, a=one(np.zeros(2)), b=one(1.0))


def test_a_nan_input_gives_nan_silently() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        solution = linear().evaluate(a=one(np.array([7.0, np.nan])), b=one(4.0))
    assert solution.status.tolist() == [CONVERGED, UNDEFINED]
    assert np.isnan(solution["x"].magnitude).tolist() == [False, True]


def test_values_taken_as_they_are() -> None:
    system = linear()
    assert system.evaluate(scale="ignore", a=one(7.0), b=one(4.0)).status == CONVERGED


# --- The systems of a catalog --------------------------------------------

SYSTEM_ENTRIES = entry("fx", "(a - y) / 2", "x", ["a", "y"]) + entry(
    "fy", "(b - x) / 3", "y", ["b", "x"]
)
SYSTEM = """
[systems.pair]
label = "Two linear equations"
equations = [{ formulation = "fx" }, { formulation = "fy" }]
start = { y = "0" }
"""


def test_a_system_in_a_catalog() -> None:
    from nomogram.catalog import load_catalog

    loaded = load_catalog(
        [
            SOURCE
            + SYSTEM_ENTRIES
            + SYSTEM.replace(
                'start = { y = "0" }',
                'start = { y = "0" }\niterations = 30\nreference = "src"\nnote = "A test."',
            )
        ]
    )
    system = loaded.systems["pair"]
    assert system.unknowns == ("y",)
    assert (system.iterations, system.reference, system.note) == (30, "src", "A test.")
    assert system.evaluate(a=one(7.0), b=one(4.0))["x"].magnitude == pytest.approx(3.4)
    assert loaded.systems_of("DimensionlessRatio") == (system,)
    assert loaded.links["systems.pair"] == (
        "formulations.fx",
        "formulations.fy",
        "kinds.DimensionlessRatio",
        "references.src",
    )


@pytest.mark.parametrize(
    ("system", "message"),
    [
        (
            SYSTEM.replace("equations = [", "equations = 3 #["),
            "non-empty list of equations",
        ),
        (SYSTEM.replace('"fy"', '"fz"'), "unknown formulation 'fz'"),
        (
            SYSTEM.replace(
                '{ formulation = "fy" }', '{ formulation = "fy", bind = 3 }'
            ),
            "expected a table of names",
        ),
        (
            SYSTEM.replace(
                '{ formulation = "fy" }', '{ formulation = "fy", outside = "no" }'
            ),
            "outside: expected",
        ),
        (
            SYSTEM.replace('start = { y = "0" }', 'start = "0"'),
            "table of first guesses",
        ),
        (
            SYSTEM.replace(
                'start = { y = "0" }', 'start = { y = "0" }\niterations = 2.5'
            ),
            "number of passes",
        ),
        (
            SYSTEM.replace(
                'start = { y = "0" }', 'start = { y = "0" }\nreference = "none"'
            ),
            "none",
        ),
        (
            SYSTEM.replace('label = "Two linear equations"', "label = 3"),
            "expected a string",
        ),
        (SYSTEM.replace('start = { y = "0" }', "start = {}"), "missing: y"),
    ],
)
def test_invalid_systems_of_a_catalog(system: str, message: str) -> None:
    from nomogram.catalog import CatalogError, load_catalog

    with pytest.raises(CatalogError, match=message):
        load_catalog([SOURCE + SYSTEM_ENTRIES + system])


# --- Coverage of the 0.8 modules -------------------------------------------


def test_domains_of_the_values_solved_apply_once_solved() -> None:
    # y = (2 b - a) / 5: 0.8 for a = 4, inside the domain [0.5, 1] the first
    # equation states on it; 0.2 for a = 7, outside.
    stated = formulations(
        entry("fx_y", "(a - y) / 2", "x", ["a", "y"], stated="y = [0.5, 1.0]")
    )["fx_y"]
    system = System(
        "linear",
        "Two linear equations",
        (Equation(stated), Equation(F["fy"])),
        start={"y": "0"},
    )
    with pytest.raises(OutOfDomainError, match="linear: fx_y"):
        system.evaluate(outside="raise", a=one(7.0), b=one(4.0))
    blank = system.evaluate(a=one(np.array([4.0, 7.0])), b=one(4.0))
    assert np.isnan(blank["y"].magnitude).tolist() == [False, True]
    assert blank["y"].magnitude[0] == pytest.approx(0.8, rel=1e-12)


def test_inputs_beyond_the_conversion_of_their_scale() -> None:
    # Weiss and Price take T on IPTS-48, converted up to 30 degC only. The
    # system holds S as Reference Salinity, a mass fraction (S_P about 35).
    from bundled_catalog import with_families

    document = SOURCE.replace("references.src", "references.test_source") + entry(
        "salinity_of",
        "0.035 + p / 100",
        "S",
        ["p"],
        output_kind='kind = "SeaWaterSalinity", unit = "UNITLESS"',
        input_kinds={
            "p": 'kind = "SaturationVapourPressureOverSeaWater", unit = "ATM"'
        },
    ).replace('reference = "src"', 'reference = "test_source"')
    loaded = with_families(("sea-water",), document).formulations
    system = System(
        "sea",
        "A salinity from the vapour pressure",
        (
            Equation(loaded["weiss_price1980_vapour_pressure"]),
            Equation(loaded["salinity_of"]),
        ),
        start={"S": "0.035"},
    )
    with pytest.raises(OutOfDomainError, match="T beyond the conversion of scale"):
        system.evaluate(outside="raise", T=Q_(305.0, "K"))
    assert system.evaluate(T=Q_(290.0, "K")).status == CONVERGED


def test_an_equation_by_branches_takes_an_input_of_the_system() -> None:
    from nomogram.catalog import catalog

    psi = catalog().formulations["coare36_profile_function_momentum"]
    system = System(
        "with_branches",
        "Two linear equations and a profile function",
        (Equation(psi), Equation(F["fx"]), Equation(F["fy"])),
        start={"y": "0"},
    )
    solution = system.evaluate(zeta=one(0.5), a=one(7.0), b=one(4.0))
    assert solution.status == CONVERGED
    expected = psi.evaluate(zeta=one(0.5)).magnitude
    assert solution["Psi_M"].magnitude == pytest.approx(expected, rel=1e-12)


def test_an_implicit_unknown_takes_an_input_of_the_system() -> None:
    # x**3 + x = y + c with y = k x: x**3 = 8 for k = 1 and c = 8.
    cubic = formulations(entry("cubic_c", "x ** 3 + x == y + c", "x", ["y", "c"]))[
        "cubic_c"
    ]
    system = System(
        "cubic",
        "An implicit unknown",
        (Equation(F["line"]), Equation(cubic)),
        start={"x": "1"},
    )
    assert system.unknowns == ("x",)
    solution = system.evaluate(c=one(8.0), k=one(1.0))
    assert solution.status == CONVERGED
    assert solution["x"].magnitude == pytest.approx(2.0, rel=1e-12)


def test_units_of_no_common_dimension_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Kinds check the dimension first; the conversion is the last guard.
    from pint.errors import DimensionalityError

    def refuse(*_: object) -> NoReturn:
        raise DimensionalityError("1", "K")

    monkeypatch.setattr("nomogram.systems.convert", refuse)
    with pytest.raises(ValueError, match="linear: the input a is taken"):
        linear()
