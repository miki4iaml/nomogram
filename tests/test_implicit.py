# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Implicit equations, ``left == right``, solved for their output.

The solver (``nomogram._roots``) on the cases that defeat a naive search,
the checks of the catalog, and the KEYPS formula of Businger et al. (1971)
against its exact inverse.
"""

import math
import warnings

import numpy as np
import pytest

from nomogram import _roots
from nomogram.catalog import Catalog, CatalogError, catalog, load_catalog
from nomogram.expression import ExpressionError, _opaque_members, _split_equation
from nomogram.inversion import InversionError, invert
from nomogram.model import OutOfDomainError, RootWarning, Variable
from nomogram.units import Q_

CATALOG = catalog()
F = CATALOG.formulations
ONE = "dimensionless"


def solve(
    members: object, low: float, high: float, *inputs: object
) -> tuple[np.ndarray, np.ndarray]:
    roots, status = _roots.solve(members, list(inputs), low, high)  # type: ignore[arg-type]
    return np.atleast_1d(roots), np.atleast_1d(status)


# --- The solver ------------------------------------------------------------


def test_a_pole_is_no_root() -> None:
    # 1/(y - 2) = 0.5 changes sign at the pole 2 and at the root 4.
    roots, status = solve(lambda y: (1 / (y - 2), 0.5 + 0 * y), -math.inf, math.inf)
    assert roots[0] == pytest.approx(4.0, rel=1e-15)
    assert status[0] == _roots.ONE


def test_a_jump_between_pieces_is_no_root() -> None:
    roots, status = solve(lambda y: (np.where(y < 3, -1.0, 1.0), 0 * y), 0.0, 10.0)
    assert math.isnan(roots[0])
    assert status[0] == _roots.NONE


def test_a_root_near_where_the_residual_becomes_undefined() -> None:
    # sqrt(3 - y) = 0.1: the root 2.99 lies between a sample and NaN.
    roots, _ = solve(lambda y: (np.sqrt(3 - y), 0.1 + 0 * y), 0.0, math.inf)
    assert roots[0] == pytest.approx(2.99, rel=1e-14)


def test_roots_at_any_scale_and_on_a_bound() -> None:
    tiny, _ = solve(lambda y: (y, 1e-200 + 0 * y), -1.0, 1.0)
    assert tiny[0] == pytest.approx(1e-200, rel=1e-14)
    zero, status = solve(lambda y: (y, 0 * y), 0.0, math.inf)
    assert zero[0] == 0.0
    assert status[0] == _roots.ONE


def test_several_roots_and_roots_beyond_the_sweep_give_nan() -> None:
    two, status = solve(lambda y: ((y - 1) * (y - 5), 0 * y), 0.0, 10.0)
    assert math.isnan(two[0])
    assert status[0] == _roots.SEVERAL
    far, status = solve(lambda y: (y, 1e15 + 0 * y), 0.0, math.inf)
    assert math.isnan(far[0])
    assert status[0] == _roots.NONE


def test_a_residual_undefined_inside_a_bracket_is_undetermined() -> None:
    def members(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        left = np.where(y < 1.0, -1.0, np.where(y < 1.5, np.nan, 1.0))
        return left + 0 * y, 0 * y

    roots, status = solve(members, 0.0, 1.0)
    assert status[0] == _roots.NONE  # the residual stays negative on [0, 1)
    # A change of sign across a hole: the root, if any, is not trusted.
    roots, status = solve(
        lambda y: (np.where(np.abs(y - 1.0) < 1e-6, np.nan, y - 1.0), 0 * y), 0.0, 2.0
    )
    assert math.isnan(roots[0])


def test_the_stable_root_of_fairall_is_the_closed_form() -> None:
    # z = A (1 + beta z / L) has the positive root A/(1 - beta A/L) while
    # beta A/L < 1, none beyond (equation 25, phi_T stable).
    a, beta = 10.0, 6.4
    lengths = np.array([1000.0, 100.0, 64.0, 50.0])
    roots, status = solve(
        lambda y, length: (y, a * (1 + beta * y / length)), 0.0, math.inf, lengths
    )
    expected = a / (1 - beta * a / lengths[:2])
    np.testing.assert_allclose(roots[:2], expected, rtol=1e-12)
    assert np.isnan(roots[2:]).all()
    assert status.tolist() == [_roots.ONE, _roots.ONE, _roots.NONE, _roots.NONE]


def test_many_points_are_solved_in_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_roots, "MAX_ELEMENTS", 1000)  # several blocks
    z = np.linspace(-3.0, 0.5, 50)
    roots, _ = solve(
        lambda y, zeta: (y**4 - 9 * zeta * y**3, 1.0 + 0 * y), 0.0, math.inf, z
    )
    np.testing.assert_allclose(roots**4 - 9 * z * roots**3, 1.0, rtol=1e-12)


def test_an_empty_interval_has_no_sample() -> None:
    assert _roots.grid(1.0, 1.0).tolist() == [1.0]
    assert _roots.grid(2.0, 1.0).size == 0
    roots, status = solve(lambda y: (y, 0 * y), 2.0, 1.0)
    assert math.isnan(roots[0])
    assert status[0] == _roots.NONE


# --- Writing and checking an implicit equation ------------------------------


def test_the_members_of_an_equation() -> None:
    assert _split_equation("y**2 + a*y == x") == ("y ** 2 + a * y", "x")
    assert _split_equation("a * x") is None
    assert _split_equation("x < 1") is None
    with pytest.raises(ExpressionError, match="one =="):
        _split_equation("y == x == 1")


SOURCE = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"
"""

EQUATION = """
[formulations.f]
label = "f"
expression = "{expression}"
fixed_units = true
citations = [{{ reference = "src" }}]
output = {{ identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }}
inputs = [{{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }}]
coefficients = {{ a = 2.0 }}
"""


def load(expression: str, extra: str = "") -> Catalog:
    return load_catalog([SOURCE + EQUATION.format(expression=expression) + extra])


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("y == y + a * x", "the output y vanishes from the equation"),
        ("y == a * x", "y is alone on one side: write the explicit expression"),
        ("a * x == y", "y is alone on one side"),
        ("y**2 == x == a", "one =="),
        ("y**2 == piecewise((x, x == 1))", "a condition of piecewise"),
        ("y**3 == x", "declared but not used: a"),
    ],
)
def test_invalid_equations_are_refused(expression: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load(expression)


def test_an_implicit_equation_is_no_part_of_another() -> None:
    composed = """
[formulations.g]
label = "g"
expression = "b * u"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }
inputs = [{ identifier = "u", kind = "DimensionlessRatio", unit = "UNITLESS", description = "u" }]
coefficients = { b = 3.0 }

[formulations.c]
label = "c"
composition = { outer = "f", inner = { x = "g" } }
"""
    with pytest.raises(CatalogError, match="f is an implicit equation"):
        load("y**3 + a * y == x", composed)
    relation = """
[relations.r]
kind = "equivalent"
subject = "f"
object = "h"

[formulations.h]
label = "h"
expression = "x / a"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]
coefficients = { a = 2.0 }
"""
    with pytest.raises(CatalogError, match="f is an implicit equation"):
        load("y**3 + a * y == x", relation)


def test_an_option_of_evaluate_names_no_variable() -> None:
    with pytest.raises(CatalogError, match="search names an option of evaluate"):
        load_catalog(
            [
                SOURCE
                + EQUATION.format(expression="a * search").replace('"x"', '"search"')
            ]
        )


def test_the_members_of_a_quantity_equation_share_a_dimension() -> None:
    document = (
        SOURCE
        + """
[formulations.q]
label = "q"
expression = "p + k * p**2 == t"
fixed_units = false
citations = [{ reference = "src" }]
output = { identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }
inputs = [{ identifier = "t", kind = "ThermodynamicTemperature", unit = "K", description = "t" }]
coefficients = { k = 1.0 }
"""
    )
    with pytest.raises(CatalogError, match="not dimensionally homogeneous"):
        load_catalog([document])


def test_a_quantity_equation_takes_the_factor_between_its_members() -> None:
    # y (1 + k) = x, y in hPa, x in Pa: y = 1500 Pa / 1.5 = 10 hPa.
    document = (
        SOURCE
        + """
[formulations.q]
label = "q"
expression = "y + k * y == x"
fixed_units = false
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "Pressure", unit = "HectoPA", description = "y" }
inputs = [{ identifier = "x", kind = "Pressure", unit = "PA", description = "x" }]
coefficients = { k = 0.5 }
"""
    )
    q = load_catalog([document]).formulations["q"]
    assert q.evaluate(x=Q_(1500.0, "Pa")).to("hPa").magnitude == pytest.approx(10.0)


def test_members_in_units_with_an_offset_between_them_are_refused() -> None:
    # No factor brings degC into K: 1 degC is 274.15 K, not a factor.
    document = (
        SOURCE
        + """
[formulations.q]
label = "q"
expression = "T - a == t"
fixed_units = false
citations = [{ reference = "src", units = { a = "K" } }]
output = { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]
coefficients = { a = 273.15 }
"""
    )
    with pytest.raises(CatalogError, match="an offset between them"):
        load_catalog([document])


# --- Evaluation ---------------------------------------------------------------


def test_search_narrows_the_interval_and_is_refused_for_an_explicit_formulation() -> (
    None
):
    f = load("y**2 == a * x").formulations["f"]  # y = +-2 at x = 2
    with pytest.warns(RootWarning, match="several roots"):
        assert math.isnan(f.evaluate(x=Q_(2.0, ONE)).magnitude)
    assert f.evaluate(x=Q_(2.0, ONE), search=(0.0, 10.0)).magnitude == pytest.approx(
        2.0
    )
    assert f.evaluate(x=Q_(2.0, ONE), search=(-10.0, 0.0)).magnitude == pytest.approx(
        -2.0
    )
    with pytest.warns(RootWarning, match="no root in the interval searched"):
        f.evaluate(x=Q_(-1.0, ONE), search=(0.0, 10.0))
    with pytest.raises(TypeError, match="search= applies to an implicit equation only"):
        F["tetens1930"].evaluate(t=Q_(20.0, "degC"), search=(0.0, 1.0))


def test_an_implicit_equation_is_not_inverted() -> None:
    with pytest.raises(InversionError, match="solved for its output, not inverted"):
        invert(
            F["businger1971_keyps"],
            "zeta",
            output=Variable("zeta", "StabilityParameter", "UNITLESS", "zeta"),
            input=Variable("Phi_M", "GradientFunctionForMomentum", "UNITLESS", "phi"),
        )


# --- KEYPS (Businger et al. 1971, equation 7) -------------------------------


KEYPS = F["businger1971_keyps"]


def test_keyps_is_the_exact_inverse_of_its_explicit_form() -> None:
    # zeta = (phi^4 - 1)/(gamma_1 phi^3) is explicit in zeta.
    phi = np.linspace(0.2, 5.0, 25)
    zeta = (phi**4 - 1) / (9.0 * phi**3)
    back = KEYPS.evaluate(zeta=Q_(zeta, ONE)).magnitude
    np.testing.assert_allclose(back, phi, rtol=1e-12)


def test_keyps_slope_at_neutral_and_its_departure_from_equation_8() -> None:
    # The slope at zeta = 0 is gamma_1/4 = 2.25 (p. 184).
    h = 1e-6
    ends = KEYPS.evaluate(zeta=Q_([-h, h], ONE)).magnitude
    assert (ends[1] - ends[0]) / (2 * h) == pytest.approx(2.25, rel=1e-6)
    # KEYPS departs from equation 8 by +4.7 % at -0.1, -12.2 % at -2.5.
    zeta = Q_([-0.1, -2.5], ONE)
    keyps = KEYPS.evaluate(zeta=zeta).magnitude
    dyer = F["fairall1978_gradient_function_momentum_unstable"].evaluate(zeta=zeta)
    departure = 100 * (keyps - dyer.magnitude) / dyer.magnitude
    np.testing.assert_allclose(departure, [4.693, -12.222], atol=1e-3)


def test_keyps_without_its_physical_domain_has_two_roots() -> None:
    # Its physical domain keeps the positive root, which search= cannot
    # widen; written without it, the negative root comes too.
    assert KEYPS.evaluate(
        zeta=Q_(-0.5, ONE), search=(-math.inf, math.inf)
    ).magnitude == pytest.approx(0.5816543231151448, rel=1e-12)
    bare = load("y**4 - a * x * y**3 == 1".replace("a *", "a * 4.5 *")).formulations[
        "f"
    ]
    with pytest.warns(RootWarning, match="several roots"):
        both = bare.evaluate(x=Q_(-0.5, ONE))
    assert math.isnan(both.magnitude)
    domain = KEYPS.physical_domains[0]
    assert dict(domain.bounds) == {"Phi_M": (0.0, math.inf)}


def test_keyps_is_written_as_printed_and_found_as_an_implicit_equation() -> None:
    tex = KEYPS.latex()
    assert tex.endswith("= 1")
    assert r"\gamma_{1}" in tex
    implicit = {f.key for f in F.values() if f.implicit}
    assert "businger1971_keyps" in implicit
    assert {f.key for f in CATALOG.search(implicit=True).formulations} == implicit
    explicit = CATALOG.search(implicit=False).formulations
    assert KEYPS not in explicit
    assert len(explicit) == len(F) - len(implicit)
    assert KEYPS in CATALOG.formulations_of("GradientFunctionForMomentum")


def test_keyps_has_no_warning_where_it_has_one_root() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        KEYPS.evaluate(zeta=Q_(np.linspace(-5.0, 0.5, 30), ONE))


def test_the_catalog_guide_shows_keyps_as_written_in_the_catalog() -> None:
    import re
    import tomllib
    from importlib.resources import files
    from pathlib import Path

    guide = (Path(__file__).parents[1] / "docs" / "catalog.md").read_text(
        encoding="utf-8"
    )
    blocks = re.findall(r"```toml\n(.*?)```", guide, re.DOTALL)
    shown = [b for b in blocks if "[formulations.businger1971_keyps]" in b]
    assert len(shown) == 1
    example = tomllib.loads(shown[0])["formulations"]["businger1971_keyps"]
    bundled_text = (
        files("nomogram") / "data" / "catalog" / "boundary-layer.toml"
    ).read_text(encoding="utf-8")
    bundled = tomllib.loads(bundled_text)["formulations"]["businger1971_keyps"]
    for key, value in example.items():
        assert bundled[key] == value, key


def test_an_explicit_formulation_has_no_members_and_an_implicit_one_no_expression() -> (
    None
):
    with pytest.raises(
        ExpressionError, match="an explicit formulation has no equation"
    ):
        _ = F["tetens1930"].equation_members
    with pytest.raises(ExpressionError, match="no explicit expression of its output"):
        _ = KEYPS.sympy_expression


CALLED = """
[formulations.g]
label = "g"
expression = "b * u"
fixed_units = true
output = { identifier = "v", kind = "DimensionlessRatio", unit = "UNITLESS", description = "v" }
inputs = [{ identifier = "u", kind = "DimensionlessRatio", unit = "UNITLESS", description = "u" }]
coefficients = { b = 3.0 }

[[formulations.g.citations]]
reference = "src"

[[formulations.g.citations.domains]]
bounds = { u = [0.0, 1.0] }

[formulations.k]
label = "k"
expression = "EXPRESSION"
calls = { d = "g" }
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]
"""


def calling(expression: str) -> Catalog:
    """g, and k written with ``expression``, which calls g as d."""
    return load_catalog([SOURCE + CALLED.replace("EXPRESSION", expression)])


def test_an_implicit_equation_passes_its_unknown_to_a_call() -> None:
    # y = x - 3 y, hence y = x / 4: the unknown reaches g through u.
    loaded = calling("y == x - d(u=y)")
    k = loaded.formulations["k"]
    assert k.implicit
    assert k.evaluate(x=Q_(2.0, ONE)).magnitude == pytest.approx(0.5, rel=1e-14)
    left, right = k.written_members
    assert str(left) == "y"
    assert str(right) == "x - d(y)"
    assert k.render().latex == r"y = x - d\left(y\right)"
    assert "formulations.k" in loaded.used_by("formulations.g").refs
    # Developed, the equation is the one solved: y == x - b*y.
    assert str(k.equation_members[1]) == "-b__g*y + x"


def test_members_as_written_belong_to_an_implicit_equation() -> None:
    explicit = calling("x - d(u=x)").formulations["k"]
    with pytest.raises(ExpressionError, match="an explicit formulation has no"):
        _ = explicit.written_members
    implicit = calling("y == x - d(u=y)").formulations["k"]
    with pytest.raises(ExpressionError, match="no explicit expression of its output"):
        _ = implicit.written_expression
    with pytest.raises(ExpressionError, match="expected an implicit equation"):
        _opaque_members("x + 1", ["x"], [])


def test_the_domains_of_a_formulation_called_apply_at_the_root() -> None:
    # x = 8 gives y = 2, which g receives outside its domain, [0, 1].
    k = calling("y == x - d(u=y)").formulations["k"]
    assert math.isnan(k.evaluate(x=Q_(8.0, ONE)).magnitude)
    with pytest.warns(match="1 value\\(s\\) outside its stated domain"):
        warned = k.evaluate(x=Q_(8.0, ONE), outside="warn")
    assert warned.magnitude == pytest.approx(2.0, rel=1e-14)
    assert k.evaluate(x=Q_(4.0, ONE)).magnitude == pytest.approx(1.0, rel=1e-14)


def test_only_an_implicit_equation_passes_its_output_to_a_call() -> None:
    with pytest.raises(CatalogError, match="the argument u is an expression of"):
        calling("x - d(u=y)")


def test_search_never_widens_the_physical_domains_and_inputs_keep_theirs() -> None:
    # Phi_M >= 0: a search below it leaves no interval, hence no root.
    with pytest.warns(RootWarning, match="1 with no root in the interval searched"):
        empty = KEYPS.evaluate(zeta=Q_(-0.5, ONE), search=(-10.0, -1.0))
    assert math.isnan(empty.magnitude)
    # A physical domain on an input bounds it, not the search of the root.
    on_input = """
[[formulations.f.domains]]
bounds = { x = [0, 10] }
"""
    f = load("y**3 + a * y == x", on_input).formulations["f"]
    roots = f.evaluate(x=Q_([3.0, 20.0], ONE), basis="physical").magnitude
    assert roots[0] == pytest.approx(1.0)
    assert math.isnan(roots[1])


# --- Roots by cancellation, jumps and poles of large members ----------------


def test_a_root_found_by_cancellation_or_beside_a_member_zero() -> None:
    # KEYPS written h == 0, and its stable roots, near 9 zeta, where
    # phi^4 and 9 zeta phi^3 cancel.
    for zeta in (np.linspace(-5.0, 0.5, 201), np.geomspace(1.0, 1e6, 201)):
        roots, status = solve(
            lambda y, z: (y**4 - 9 * z * y**3 - 1, 0 * y), 0.0, math.inf, zeta
        )
        assert (status == _roots.ONE).all()
        back = (roots**4 - 1) / (9 * roots**3)
        np.testing.assert_allclose(back, zeta, rtol=1e-12)
    # A root a millionth of a kelvin from 273.15 K, and Clausius-Clapeyron
    # next to its reference vapour pressure, where both members are tiny.
    offset, _ = solve(lambda y, x: (y - 273.15, x), 0.0, math.inf, np.array([1e-6]))
    assert offset[0] - 273.15 == pytest.approx(1e-6, rel=1e-6)
    ratio = np.array([1 + 1e-9, 1 - 1e-7])
    t, status = solve(
        lambda y, q: (np.log(q) + 0 * y, 5420.0 * (1 / 273.15 - 1 / y)),
        0.0,
        math.inf,
        ratio,
    )
    closed = 1 / (1 / 273.15 - np.log(ratio) / 5420.0)
    np.testing.assert_allclose(t, closed, rtol=1e-14)
    assert (status == _roots.ONE).all()


def test_jumps_and_poles_of_large_members_are_no_roots() -> None:
    def d(y: np.ndarray) -> np.ndarray:
        return np.exp(y) - 3

    cases = [
        # Members with a double pole, the residual a simple one at ln 3.
        (lambda y: (1 / d(y) + 1 / d(y) ** 2, 1 / d(y) ** 2), -10.0, 10.0),
        # Small jumps across zero, on large members.
        (lambda y: (300 + np.where(y < 3, -1e-7, 1e-7), 300 + 0 * y), 0.0, 10.0),
        (lambda y: (1e10 + np.where(y < 3, -1.0, 1.0), 1e10 + 0 * y), 0.0, 10.0),
    ]
    for members, low, high in cases:
        roots, status = solve(members, low, high)
        assert math.isnan(roots[0])
        assert status[0] == _roots.NONE


def test_keyps_has_its_stable_root_too() -> None:
    zeta = np.geomspace(1.0, 1e6, 400)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        phi = KEYPS.evaluate(zeta=Q_(zeta, ONE)).magnitude
    np.testing.assert_allclose((phi**4 - 1) / (9 * phi**3), zeta, rtol=1e-12)


# --- Members and units ------------------------------------------------------

QUANTITY = """
[formulations.q]
label = "q"
expression = "{expression}"
fixed_units = false
citations = [{{ reference = "src" }}]
output = {{ identifier = "y", kind = "Pressure", unit = "HectoPA", description = "y" }}
inputs = [{{ identifier = "x", kind = "Pressure", unit = "PA", description = "x" }}]
coefficients = {coefficients}
"""


PASCALS = '{{ value = {value}, unit = "PA", unit_basis = "added", note = "Test." }}'


def quantity(expression: str, coefficients: str) -> Catalog:
    text = QUANTITY.format(expression=expression, coefficients=coefficients)
    return load_catalog([SOURCE + text])


def test_a_member_by_pieces_in_a_quantity_equation() -> None:
    q = quantity(
        "y * piecewise((k_1, x <= x_0), (k_2, x > x_0)) == x",
        "{ k_1 = 2.0, k_2 = 4.0, x_0 = " + PASCALS.format(value=1000.0) + " }",
    ).formulations["q"]
    y = q.evaluate(x=Q_([1000.0, 3000.0], "Pa")).to("hPa").magnitude
    np.testing.assert_allclose(y, [5.0, 7.5])
    with pytest.raises(CatalogError, match="not dimensionally homogeneous"):
        quantity(
            "piecewise((y, x <= x_0), (y * k, x > x_0)) == x",
            "{ k = "
            + PASCALS.format(value=1.0)
            + ", x_0 = "
            + PASCALS.format(value=1000.0)
            + " }",
        )


def test_a_member_zero_in_a_quantity_equation() -> None:
    # y^2 + k y - x^2 = 0 with y, x and k in pascals, y >= 0.
    document = (
        SOURCE
        + """
[formulations.z]
label = "z"
expression = "y**2 + k * y - x**2 == 0"
fixed_units = false
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "Pressure", unit = "PA", description = "y" }
inputs = [{ identifier = "x", kind = "Pressure", unit = "PA", description = "x" }]
coefficients = { k = { value = 1.0, unit = "PA", unit_basis = "added", note = "Test." } }

[[formulations.z.domains]]
bounds = { y = [0, inf] }
criterion = "The positive root."
"""
    )
    z = load_catalog([document]).formulations["z"]
    value = z.evaluate(x=Q_(10.0, "Pa")).magnitude
    assert value == pytest.approx((-1 + math.sqrt(401)) / 2, rel=1e-14)


def test_the_terms_of_a_sum_are_in_one_unit() -> None:
    explicit = """
[formulations.s]
label = "s"
expression = "x + z"
fixed_units = false
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "Pressure", unit = "PA", description = "y" }
inputs = [
  { identifier = "x", kind = "Pressure", unit = "PA", description = "x" },
  { identifier = "z", kind = "Pressure", unit = "HectoPA", description = "z" },
]
"""
    with pytest.raises(CatalogError, match="adds Pa and hPa"):
        load_catalog([SOURCE + explicit])
    with pytest.raises(CatalogError, match="write the terms of a sum in one unit"):
        quantity("y + k * y == 2 * x + y", "{ k = 0.5 }")
    # In one unit, a sum is computed as written.
    same = explicit.replace('unit = "HectoPA"', 'unit = "PA"')
    s = load_catalog([SOURCE + same]).formulations["s"]
    assert s.evaluate(x=Q_(1500.0, "Pa"), z=Q_(15.0, "hPa")).magnitude == 3000.0


LOGARITHM = """
[formulations.f]
label = "f"
expression = "ln(p / p_0)"
fixed_units = false
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }]
coefficients = { p_0 = { value = 100000, unit = "PA", unit_basis = "added", note = "Test." } }
"""


def test_a_function_takes_a_pure_number_whose_units_leave_no_factor() -> None:
    # ln(1000 hPa / 100000 Pa) would give -4.6, the logarithm of the numbers.
    with pytest.raises(CatalogError, match="worth 100 times its numbers"):
        load_catalog([SOURCE + LOGARITHM])
    # In units whose ratio is 1, the function is computed as written.
    same = LOGARITHM.replace(
        'value = 100000, unit = "PA"', 'value = 1000, unit = "HectoPA"'
    )
    f = load_catalog([SOURCE + same]).formulations["f"]
    assert float(f.evaluate(p=Q_(1000.0, "hPa")).magnitude) == pytest.approx(0.0)
    # In a member of an implicit equation as well: y in hPa, x in Pa.
    with pytest.raises(CatalogError, match="worth 100 times its numbers"):
        quantity("exp(y / x) == k", "{ k = 2.0 }")


def test_an_expression_too_long_is_refused_before_it_is_read() -> None:
    long = " + ".join(["a * x"] * 600)
    with pytest.raises(CatalogError, match="longer than 2000 characters"):
        load(long)


def test_an_implicit_equation_twice_is_refused() -> None:
    twin = """
[formulations.g]
label = "g"
expression = "x == b * z + z**3"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "z", kind = "DimensionlessRatio", unit = "UNITLESS", description = "z" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]
coefficients = { b = 2.0 }
"""
    with pytest.raises(CatalogError, match="identical to formulations.f"):
        load("y**3 + a * y == x", twin)
    # Another coefficient is another equation.
    other = load("y**3 + a * y == x", twin.replace("2.0", "3.0"))
    assert len(other.formulations) == 2


# --- Scales, NaN and domains --------------------------------------------------


def test_the_bounds_of_the_kind_select_the_root_on_another_scale() -> None:
    # Roots 10 degC and -300 degC, below 0 K: on IPTS-68 too, one root.
    document = (
        SOURCE
        + """
[formulations.t]
label = "t"
expression = "(t_d + a) * (t_d - x) == 0"
fixed_units = true
output = { identifier = "t_d", kind = "CelsiusTemperature", unit = "DEG_C", description = "t_d" }
inputs = [{ identifier = "x", kind = "CelsiusTemperature", unit = "DEG_C", description = "x" }]
coefficients = { a = 300.0 }

[[formulations.t.citations]]
reference = "src"
scales = { t_d = "ipts68", x = "ipts68" }
"""
    )
    from importlib.resources import files

    core = (files("nomogram.data.catalog") / "core.toml").read_text(encoding="utf-8")
    t = load_catalog([core, document]).formulations["t"]
    # Not in its own unit on another scale, but carried onto it to search.
    assert t.output.bounds_in_unit() is None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        value = t.evaluate(x=Q_(10.0, "degC")).magnitude
    assert value == pytest.approx(10.0, abs=1e-12)


DOMAIN = """
[formulations.r]
label = "r"
expression = "y**2 == x"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]

[[formulations.r.domains]]
bounds = { x = [0, 10], y = [0, inf] }
criterion = "The positive root of a positive number."
"""


def test_no_root_is_sought_for_inputs_nan_or_outside_the_domains() -> None:
    r = load_catalog([SOURCE + DOMAIN]).formulations["r"]
    x = Q_([np.nan, -1.0, 4.0], ONE)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        y = r.evaluate(x=x, basis="physical").magnitude
    assert np.isnan(y[:2]).all()
    assert y[2] == pytest.approx(2.0)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(OutOfDomainError, match="1 value"):
            r.evaluate(x=x, basis="physical", outside="raise")
    # Asked to compute anyway, the search reports what it found.
    with pytest.warns(RootWarning, match="1 with no root"):
        r.evaluate(x=x, basis="physical", outside="ignore")


def test_the_warning_counts_each_case_where_the_caller_called() -> None:
    f = load("y**2 == a * x").formulations["f"]
    with pytest.warns(RootWarning) as caught:
        f.evaluate(x=Q_([2.0, -1.0, -2.0], ONE))
    message = str(caught[0].message)
    assert "2 with no root in the interval searched" in message
    assert "1 with several roots" in message
    assert caught[0].filename == __file__


@pytest.mark.parametrize(
    "interval", [(5.0, 1.0), (math.nan, 1.0), (1.0, 2.0, 3.0), "ab"]
)
def test_search_is_an_interval(interval: object) -> None:
    with pytest.raises(ValueError, match="search= takes two numbers"):
        KEYPS.evaluate(zeta=Q_(-0.5, ONE), search=interval)  # type: ignore[arg-type]


# --- Catalog checks -----------------------------------------------------------


def test_a_chained_equation_with_calls_and_an_odd_search_filter() -> None:
    called = """
[formulations.g]
label = "g"
expression = "b * u"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "v", kind = "DimensionlessRatio", unit = "UNITLESS", description = "v" }
inputs = [{ identifier = "u", kind = "DimensionlessRatio", unit = "UNITLESS", description = "u" }]
coefficients = { b = 3.0 }

[formulations.k]
label = "k"
expression = "y == d(x) == x"
calls = { d = "g" }
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]
"""
    with pytest.raises(CatalogError, match="one =="):
        load_catalog([SOURCE + called])
    with pytest.raises(TypeError, match="expected a pattern, or True or False"):
        CATALOG.search(implicit=1)  # type: ignore[arg-type]


def test_the_output_names_no_option_and_the_indicator_counts_keyps() -> None:
    from nomogram.catalog import _bounded_unknown, stats

    named = EQUATION.format(expression="search**3 + a * search == x").replace(
        'identifier = "y"', 'identifier = "search"'
    )
    with pytest.raises(CatalogError, match="search names an option of evaluate"):
        load_catalog([SOURCE + named])
    implicit = [f for f in F.values() if f.implicit]
    bounded = [f.key for f in implicit if _bounded_unknown(f)]
    line = (
        "  implicit equations with their unknown bounded by a physical domain"
        f" or its kind: {len(bounded)} of {len(implicit)}"
    )
    assert line in stats(CATALOG).splitlines()
    assert "businger1971_keyps" in bounded
    # The Obukhov length of IFS 3.25 is bounded by neither: its root is
    # unique, Ri_b(L) monotonic on either side of neutral.
    assert "ecmwf_ifs_obukhov_length_from_bulk_richardson_number" not in bounded


def test_an_approximation_of_an_implicit_equation_is_verified() -> None:
    from nomogram.relations import verify

    approximation = """
[formulations.h]
label = "h"
expression = "x / b"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "y", kind = "DimensionlessRatio", unit = "UNITLESS", description = "y" }
inputs = [{ identifier = "x", kind = "DimensionlessRatio", unit = "UNITLESS", description = "x" }]
coefficients = { b = 2.0 }

[relations.r]
kind = "approximates"
subject = "h"
object = "f"
citation = "src"
accuracy = 0.01
bounds = { x = [0, 0.1] }
"""
    c = load("y**3 + a * y == x", approximation)
    verdict = verify(c.relations["r"], c)
    # y^3 + 2 y = x near 0: y = x/2 departs most at x = 0.1.
    root = min(r.real for r in np.roots([1.0, 0.0, 2.0, -0.1]) if abs(r.imag) < 1e-12)
    assert verdict.status == "exceeded"
    assert verdict.value == pytest.approx(100 * (0.05 - root) / root, rel=1e-6)
    assert verdict.at["x"] == pytest.approx(0.1)


def test_the_bounds_of_the_kind_select_the_root() -> None:
    # Roots 10 K and -300 K: 0 K keeps one. Its variable has its bounds.
    document = (
        SOURCE
        + """
[formulations.k]
label = "k"
expression = "(T + a) * (T - x) == 0"
fixed_units = true
citations = [{ reference = "src" }]
output = { identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "T" }
inputs = [{ identifier = "x", kind = "ThermodynamicTemperature", unit = "K", description = "x" }]
coefficients = { a = 300.0 }
"""
    )
    k = load_catalog([document]).formulations["k"]
    assert k.output.bounds_in_unit() == (0.0, math.inf)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert k.evaluate(x=Q_(10.0, "K")).magnitude == pytest.approx(10.0)
        # An input NaN alone: nothing sought, nothing to report.
        assert math.isnan(k.evaluate(x=Q_(math.nan, "K")).magnitude)


def test_the_units_inside_the_members_of_a_quantity_equation() -> None:
    percent = '{ value = 1.0, unit = "PERCENT", unit_basis = "added", note = "Test." }'
    with pytest.raises(CatalogError, match="give values in different units"):
        quantity(
            "piecewise((y, x <= x_0), (y * k, x > x_0)) == x",
            "{ k = " + percent + ", x_0 = " + PASCALS.format(value=1000.0) + " }",
        )
    hectopascals = PASCALS.format(value=10.0).replace('"PA"', '"HectoPA"')
    with pytest.raises(CatalogError, match="write a bound in the unit of its input"):
        quantity(
            "y * piecewise((k_1, x <= x_0), (k_2, x > x_0)) == x",
            "{ k_1 = 2.0, k_2 = 4.0, x_0 = " + hectopascals + " }",
        )


def test_units_alike_give_one_number() -> None:
    from nomogram.model import _coherent, _same_unit
    from nomogram.units import ureg

    assert _same_unit(ureg.degC, ureg.degC)
    assert not _same_unit(ureg.degC, ureg.kelvin)
    assert _same_unit(ureg("J/kg").units, ureg("m**2/s**2").units)
    assert _coherent(ureg.pascal)
    assert not _coherent(ureg.hectopascal)
    assert not _coherent(ureg.degC)
