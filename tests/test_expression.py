# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.expression`."""

import math

import numpy as np
import pytest
import sympy

from nomogram.expression import (
    CONSTANTS,
    LATEX_COMMANDS,
    MAX_SOURCE_LENGTH,
    ExpressionError,
    compile_numeric,
    latex_commands,
    parse_expression,
    to_latex,
    upright_symbol,
)

MAGNUS = "C * exp(A * t / (B + t))"
MAGNUS_NAMES = ("A", "B", "C", "t")


def test_parse_and_evaluate_magnus_form() -> None:
    expr = parse_expression(MAGNUS, MAGNUS_NAMES)
    function = compile_numeric(expr, ("t", "A", "B", "C"))
    # Sonntag 1990 coefficients at 20 degC: e_s about 23.33 hPa.
    expected = 6.112 * math.exp(17.62 * 20 / (243.12 + 20))
    assert function(20.0, 17.62, 243.12, 6.112) == pytest.approx(expected)


def test_sonntag_matches_the_iapws_reference_within_its_stated_accuracy() -> None:
    # Saturation vapour pressure over water at 20 degC from the IAPWS
    # reference equation (Wagner and Pruss 1993, IAPWS SR1-86): 23.392 hPa.
    # Sonntag (1990) states an accuracy of 0.6 % from -45 to 60 degC; its
    # known deviation at 20 degC is about -0.28 %.
    iapws_hpa = 23.392
    expr = parse_expression(MAGNUS, MAGNUS_NAMES)
    function = compile_numeric(expr, ("t", "A", "B", "C"))
    deviation = function(20.0, 17.62, 243.12, 6.112) / iapws_hpa - 1
    assert abs(deviation) < 0.006
    assert deviation == pytest.approx(-0.0028, abs=0.0001)


def test_evaluation_is_vectorised() -> None:
    expr = parse_expression(MAGNUS, MAGNUS_NAMES)
    function = compile_numeric(expr, ("t", "A", "B", "C"))
    values = function(np.array([0.0, 20.0, 40.0]), 17.62, 243.12, 6.112)
    assert values.shape == (3,)
    assert values[0] == pytest.approx(6.112)


def test_compiled_functions_are_cached() -> None:
    expr = parse_expression(MAGNUS, MAGNUS_NAMES)
    arguments = ("t", "A", "B", "C")
    assert compile_numeric(expr, arguments) is compile_numeric(expr, arguments)


def test_compile_requires_every_free_symbol() -> None:
    expr = parse_expression(MAGNUS, MAGNUS_NAMES)
    with pytest.raises(ExpressionError, match="missing arguments: C"):
        compile_numeric(expr, ("t", "A", "B"))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2 * x + 1", 7.0),
        ("x ** 2 - x / 4", 8.25),
        ("-x + +x", 0.0),
        ("sqrt(x + 1)", 2.0),
        ("ln(exp(x))", 3.0),
        ("2 * pi * x", 6 * math.pi),
        ("sin(x) ** 2 + cos(x) ** 2", 1.0),
        ("cos(2 * x)", math.cos(6.0)),
    ],
)
def test_supported_syntax(source: str, expected: float) -> None:
    function = compile_numeric(parse_expression(source, ["x"]), ("x",))
    assert function(3.0) == pytest.approx(expected)


def test_decimal_coefficients_keep_their_digits() -> None:
    expr = parse_expression("6.1094 * x", ["x"])
    assert "6.1094" in str(expr)


def test_exact_parsing_reads_decimals_as_rationals() -> None:
    import sympy

    exact = parse_expression(
        "piecewise((1 / (t + 273.15), t < 0.5), (ln(t), t >= 0.5))", ["t"], exact=True
    )
    assert not exact.atoms(sympy.Float)
    assert sympy.Rational(5463, 20) in exact.atoms(sympy.Rational)
    # The same number written in two expressions cancels exactly.
    t, kelvin = sympy.Symbol("t", real=True), sympy.Symbol("T", real=True)
    shifted = parse_expression("T - 273.15", ["T"], exact=True)
    assert (
        parse_expression("t + 273.15", ["t"], exact=True).xreplace({t: shifted})
        == kelvin
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("__import__('os').system('echo')", "only calls to"),
        ("x.real", "Attribute"),
        ("x[0]", "Subscript"),
        ("(lambda: 1)()", "only calls to"),
        ("x if x else 1", "IfExp"),
        ("x < 1", "only as the conditions of piecewise"),
        ("'text'", "unsupported constant"),
        ("True * x", "unsupported constant"),
        ("y + 1", "undeclared name: 'y'"),
        ("exp(x, 2)", "exactly one positional argument"),
        ("sqrt(x=1)", "exactly one positional argument"),
        ("x // 2", "BinOp"),
        ("x +", "invalid syntax"),
        ("[x for x in ()]", "ListComp"),
    ],
)
def test_everything_outside_the_whitelist_is_rejected(
    source: str, message: str
) -> None:
    with pytest.raises(ExpressionError, match=message):
        parse_expression(source, ["x"])


def test_overlong_source_is_rejected() -> None:
    with pytest.raises(ExpressionError, match="longer than"):
        parse_expression("x + " * MAX_SOURCE_LENGTH + "x", ["x"])
    # Built by nomogram from expressions already read, such as a
    # composition, a longer one is accepted.
    name = "x" * (MAX_SOURCE_LENGTH + 1)
    assert parse_expression(name, [name], limit=None) == sympy.Symbol(name, real=True)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        # SymPy would compute 9 ** 387420489 exactly, without end.
        ("9 ** 9 ** 9 * x", "beyond 1000 digits"),
        ("(10 ** 999) ** 999 * x", "beyond 1000 digits"),
        ("-" * 1500 + "x", "nested too deeply"),
        ("1e309 * x", "number too large"),
    ],
)
def test_short_sources_that_would_never_end_are_rejected(
    source: str, message: str
) -> None:
    with pytest.raises(ExpressionError, match=message):
        parse_expression(source, ["x"])
    assert parse_expression("2 ** 10 * x", ["x"]) == 1024 * sympy.Symbol("x", real=True)


def test_functions_and_constants_cannot_be_changed() -> None:
    from nomogram.expression import FUNCTIONS

    with pytest.raises(TypeError):
        CONSTANTS["e"] = sympy.E  # type: ignore[index]
    with pytest.raises(TypeError):
        FUNCTIONS["sin"] = sympy.sin  # type: ignore[index]


@pytest.mark.parametrize("name", ["exp", "pi", "not an identifier"])
def test_reserved_or_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(ExpressionError, match="invalid or reserved name"):
        parse_expression("1", [name])


def test_pi_is_a_constant_written_as_its_greek_letter() -> None:
    expr = parse_expression("pi * x ** 2", ["x"])
    assert {s.name for s in expr.free_symbols} == {"x"}  # pi is no variable
    assert r"\pi" in to_latex(expr)
    assert latex_commands(to_latex(expr)) <= LATEX_COMMANDS
    assert set(CONSTANTS) == {"pi"}


def test_latex_writes_exp_explicitly_never_as_a_power_of_e() -> None:
    latex = to_latex(parse_expression(MAGNUS, MAGNUS_NAMES))
    assert r"\exp\left(" in latex
    assert "e^" not in latex


def test_latex_uses_the_requested_notation() -> None:
    expr = parse_expression("e_s * RH", ["e_s", "RH"])
    latex = to_latex(expr, {"e_s": r"E_{\mathrm{w}}", "RH": r"\phi"})
    assert r"E_{\mathrm{w}}" in latex
    assert r"\phi" in latex
    assert "e_" not in latex


def test_latex_default_notation_and_logarithm() -> None:
    latex = to_latex(parse_expression("ln(x) + exp(x)", ["x"]))
    assert r"\ln" in latex
    assert r"\exp\left(x\right)" in latex


def test_latex_power_of_an_exponential() -> None:
    # SymPy folds exp(x)**2 into exp(2*x); the printer still handles an
    # explicit exponent when asked for one.
    import sympy

    from nomogram.expression import _NotationPrinter

    x = sympy.Symbol("x", real=True)
    printed = _NotationPrinter()._print_ExpBase(sympy.exp(x), exp="2")
    assert printed == r"\exp\left(x\right)^{2}"


def test_latex_stays_within_the_mathtext_and_mathjax_subset() -> None:
    latex = to_latex(parse_expression(MAGNUS, MAGNUS_NAMES), {"t": "t"})
    for unsupported in (r"\textrm", r"\operatorname{e}", r"\mathbb"):
        assert unsupported not in latex


def test_decimal_logarithm_is_written_as_in_the_sources() -> None:
    expr = parse_expression("10 ** (a * log10(x))", ["a", "x"])
    assert r"\log_{10}\left(x\right)" in to_latex(expr)
    function = compile_numeric(expr, ("a", "x"))
    assert function(2.0, 100.0) == pytest.approx(1e4)


def test_latex_power_of_a_decimal_logarithm() -> None:
    import sympy
    from sympy.codegen.cfunctions import log10

    from nomogram.expression import _NotationPrinter

    x = sympy.Symbol("x", real=True)
    printed = _NotationPrinter()._print_log10(log10(x), exp="2")
    assert printed == r"\log_{10}\left(x\right)^{2}"


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("t", "t"),
        ("e_s", r"e_{\mathrm{s}}"),
        ("RH", r"\mathrm{RH}"),
        ("rho_v", r"\rho_{\mathrm{v}}"),
        ("epsilon", r"\epsilon"),
        ("a1", "a_{1}"),
        ("e_i0", r"e_{\mathrm{i0}}"),
        ("x_alpha", r"x_{\alpha}"),
        ("T_celsius_zero", r"T_{\mathrm{celsius},\mathrm{zero}}"),
        ("x__max", r"x^{\mathrm{max}}"),
    ],
)
def test_upright_symbol_follows_iso_80000_2(identifier: str, expected: str) -> None:
    assert upright_symbol(identifier) == expected


def test_to_latex_passes_typography_to_sympy() -> None:
    expr = parse_expression("2.5 * RH * e_s", ["RH", "e_s"])
    assert to_latex(expr) == "2.5 RH e_{s}"
    styled = to_latex(expr, mul_symbol="times", decimal_separator="comma", upright=True)
    assert styled == r"2{,}5 \times \mathrm{RH} \times e_{\mathrm{s}}"
    assert to_latex(expr, {"RH": r"\phi"}, upright=True).startswith(r"2.5 \phi")


@pytest.mark.parametrize(
    ("source", "names", "default", "upright"),
    [
        (
            "C * exp(Tbar)",
            ["C", "Tbar"],
            r"C \exp\left(\mathrm{Tbar}\right)",
            r"C \exp\left(\mathrm{Tbar}\right)",
        ),
        ("k * ell", ["k", "ell"], r"\mathrm{ell} k", r"\mathrm{ell} k"),
        ("k * hbar", ["k", "hbar"], r"\mathrm{hbar} k", r"\mathrm{hbar} k"),
        ("varkappa * x", ["x", "varkappa"], r"\mathrm{varkappa} x", None),
        ("xdot * t", ["t", "xdot"], r"t \mathrm{xdot}", None),
    ],
)
def test_identifiers_sympy_writes_with_other_commands_stay_in_the_subset(
    source: str, names: list[str], default: str, upright: str | None
) -> None:
    expr = parse_expression(source, names)
    for found in (to_latex(expr), to_latex(expr, upright=True)):
        assert latex_commands(found) <= LATEX_COMMANDS, found
    assert to_latex(expr) == default
    if upright is not None:
        assert to_latex(expr, upright=True) == upright
    # A notation still decides when it names that identifier.
    assert r"\Theta" in to_latex(expr, {names[1]: r"\Theta"})


def test_latex_commands_are_listed() -> None:
    assert latex_commands(r"a \times \frac{b}{c}\,d") == {r"\times", r"\frac", r"\,"}
    assert latex_commands("a + b") == set()
