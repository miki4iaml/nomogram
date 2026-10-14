# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for :mod:`nomogram.expression`."""

import math

import numpy as np
import pytest

from nomogram.expression import (
    MAX_SOURCE_LENGTH,
    ExpressionError,
    compile_numeric,
    parse_expression,
    to_latex,
)

MAGNUS = "C * exp(A * t / (B + t))"
MAGNUS_NAMES = ("A", "B", "C", "t")


def test_parse_and_evaluate_magnus_form() -> None:
    expr = parse_expression(MAGNUS, MAGNUS_NAMES)
    function = compile_numeric(expr, ("t", "A", "B", "C"))
    # Sonntag 1990 coefficients at 20 degC: e_s about 23.33 hPa.
    expected = 6.112 * math.exp(17.62 * 20 / (243.12 + 20))
    assert function(20.0, 17.62, 243.12, 6.112) == pytest.approx(expected)


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
    ],
)
def test_supported_syntax(source: str, expected: float) -> None:
    function = compile_numeric(parse_expression(source, ["x"]), ("x",))
    assert function(3.0) == pytest.approx(expected)


def test_decimal_coefficients_keep_their_digits() -> None:
    expr = parse_expression("6.1094 * x", ["x"])
    assert "6.1094" in str(expr)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("__import__('os').system('echo')", "only calls to"),
        ("x.real", "Attribute"),
        ("x[0]", "Subscript"),
        ("(lambda: 1)()", "only calls to"),
        ("x if x else 1", "IfExp"),
        ("x < 1", "Compare"),
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


@pytest.mark.parametrize("name", ["exp", "not an identifier"])
def test_reserved_or_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(ExpressionError, match="invalid or reserved name"):
        parse_expression("1", [name])


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
