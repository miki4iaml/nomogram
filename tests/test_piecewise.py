# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for piecewise definitions: syntax, checks, units, rendering, inversion."""

import time
import warnings

import numpy as np
import pytest
import sympy
from matplotlib.mathtext import MathTextParser

from nomogram.catalog import CatalogError, load_catalog
from nomogram.expression import (
    LATEX_COMMANDS,
    ExpressionError,
    _pieces,
    latex_commands,
    parse_expression,
    to_latex,
)
from nomogram.inversion import InversionError, NumericalInverse, dew_point, invert
from nomogram.model import Variable
from nomogram.relations import signature, verify
from nomogram.units import Q_

NAMES = ["T", "p", "T_ice", "T_0"]

SOURCE = """
[references.src]
authors = "A."
title = "T"
status = "verified"
"""

MIXED_PHASE = (
    "piecewise((0, T <= T_ice), (((T - T_ice) / (T_0 - T_ice)) ** 2, "
    "T_ice < T < T_0), (1, T >= T_0))"
)

#: Magnus forms over ice below 0 degC and over water above (Sonntag 1990).
MAGNUS = (
    "piecewise((C * exp(A_i * t / (B_i + t)), t < 0), "
    "(C * exp(A * t / (B + t)), t >= 0))"
)


def formulation(
    expression: str,
    *,
    key: str = "f",
    fixed_units: bool = True,
    output: str = 'kind = "DimensionlessRatio", unit = "UNITLESS"',
    inputs: str = (
        '{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", '
        'description = "T" }'
    ),
    extra: str = "",
) -> str:
    """A formulation written for a test."""
    return f"""
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = {"true" if fixed_units else "false"}
output = {{ identifier = "y", {output}, description = "y" }}
inputs = [{inputs}]
{extra}
[[formulations.{key}.citations]]
reference = "src"
"""


def magnus() -> str:
    return formulation(
        MAGNUS,
        key="magnus",
        output='kind = "VapourPressure", unit = "HectoPA"',
        inputs=(
            '{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", '
            'description = "t" }'
        ),
        extra=(
            "coefficients = { C = 6.112, A = 17.62, B = 243.12, A_i = 22.46, "
            "B_i = 272.62 }\n"
            "[[formulations.magnus.domains]]\nbounds = { t = [-65.0, 60.0] }\n"
        ),
    )


# --- Syntax ----------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "piecewise((p, T < 273.15), (2 * p, T >= 273.15))",
        "piecewise((p, 273.15 <= T))",
        MIXED_PHASE,
        "piecewise((p, T_0 > T >= T_ice))",
        "p * piecewise((1, T < T_0), (piecewise((2, T < 300), (3, T >= 300)), T >= T_0))",
    ],
)
def test_piecewise_definitions_are_parsed(source: str) -> None:
    expr = parse_expression(source, NAMES)
    assert expr.has(sympy.Piecewise)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("piecewise()", r"takes \(expression, condition\) pairs"),
        ("piecewise(p)", r"takes \(expression, condition\) pairs"),
        ("piecewise((p, T < 1, 2))", r"takes \(expression, condition\) pairs"),
        ("piecewise((p, T < 1), x=1)", r"takes \(expression, condition\) pairs"),
        ("piecewise((p, T))", "a condition of piecewise.. is a comparison"),
        ("piecewise((p, T == 1))", "a condition of piecewise.. is a comparison"),
        ("piecewise((p, True))", "a condition of piecewise.. is a comparison"),
        (
            "piecewise((p, T < 1 and T > 0))",
            "a condition of piecewise.. is a comparison",
        ),
        ("piecewise((p, 0 < T < 1 < 2))", "chains at most two comparisons"),
        ("piecewise((p, 0 < T > 1))", "go in one direction"),
        ("p < 1", "only as the conditions of piecewise"),
    ],
)
def test_conditions_outside_the_allowed_forms_are_refused(
    source: str, message: str
) -> None:
    with pytest.raises(ExpressionError, match=message):
        parse_expression(source, NAMES)


def test_piecewise_is_a_reserved_name() -> None:
    with pytest.raises(ExpressionError, match="reserved name"):
        parse_expression("piecewise", ["piecewise"])


def test_conditions_are_kept_as_written() -> None:
    # SymPy would rewrite the second condition, which completes the first,
    # as True ("otherwise").
    expr = parse_expression("piecewise((p, T < 273.15), (2 * p, T >= 273.15))", NAMES)
    assert expr.args[1][1] == sympy.GreaterThan(
        sympy.Symbol("T", real=True), sympy.Float("273.15"), evaluate=False
    )


def test_each_branch_is_an_interval_of_one_input() -> None:
    expr = parse_expression(MIXED_PHASE, NAMES)
    pieces = _pieces(expr, ["T", "p"])
    assert [p.variable.name for p in pieces] == ["T", "T", "T"]
    assert (pieces[0].low, pieces[0].high_closed) == (-sympy.oo, True)
    assert (pieces[1].low_closed, pieces[1].high_closed) == (False, False)
    assert (pieces[2].low_closed, pieces[2].high) == (True, sympy.oo)
    chained = _pieces(
        parse_expression("piecewise((p, T_0 > T >= T_ice))", NAMES), ["T"]
    )
    assert (chained[0].low.name, chained[0].low_closed) == ("T_ice", True)
    assert (chained[0].high.name, chained[0].high_closed) == ("T_0", False)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("piecewise((p, T < p))", "does not bound one input alone"),
        ("piecewise((p, T + 1 < 2))", "does not bound one input alone"),
        ("piecewise((p, T < 1 < p))", "bounds two inputs"),
        ("piecewise((p, T < 1), (p, p >= 1))", "the conditions bound T and p"),
    ],
)
def test_a_branch_bounds_one_input_alone(source: str, message: str) -> None:
    with pytest.raises(ExpressionError, match=message):
        _pieces(parse_expression(source, NAMES), ["T", "p"])


# --- Catalog checks -----------------------------------------------------------


def test_a_formulation_may_be_defined_by_pieces() -> None:
    document = SOURCE + formulation(
        MIXED_PHASE, extra="coefficients = { T_ice = 250.16, T_0 = 273.16 }"
    )
    f = load_catalog([document]).formulations["f"]
    values = f.evaluate(T=Q_([240.0, 250.16, 260.0, 273.16, 280.0], "K")).magnitude
    assert values == pytest.approx([0.0, 0.0, ((260 - 250.16) / 23) ** 2, 1.0, 1.0])


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("piecewise((1, T < 300), (2, T < 280))", "the intervals of T overlap"),
        ("piecewise((1, T <= 280), (2, T >= 280))", "the intervals of T overlap"),
        ("piecewise((1, 300 < T < 280))", "an empty interval of T"),
        ("piecewise((T, 280 < T <= 280), (1, T > 300))", "reduces to False"),
        ("piecewise((1, T < y_0))", "undeclared name"),
    ],
)
def test_intervals_must_not_overlap(expression: str, message: str) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([SOURCE + formulation(expression)])


def test_a_condition_on_two_inputs_is_refused_when_loading() -> None:
    inputs = (
        '{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", '
        'description = "T" }, { identifier = "U", kind = "ThermodynamicTemperature", '
        'unit = "K", description = "U" }'
    )
    document = SOURCE + formulation("piecewise((1, T < U))", inputs=inputs)
    with pytest.raises(CatalogError, match="does not bound one input alone"):
        load_catalog([document])


def test_where_no_condition_holds_the_value_is_nan() -> None:
    # A gap between two intervals, and beyond the last one.
    expression = "piecewise((1, T < 280), (2, 290 <= T < 300))"
    f = load_catalog([SOURCE + formulation(expression)]).formulations["f"]
    values = f.evaluate(T=Q_([270.0, 285.0, 295.0, 310.0], "K")).magnitude
    assert values[[0, 2]] == pytest.approx([1.0, 2.0])
    assert np.isnan(values[[1, 3]]).all()


def test_branches_are_evaluated_without_warnings() -> None:
    # ln(T - 273.15) is computed on every value, then discarded below 273.15.
    expression = "piecewise((0, T < 273.15), (ln(T - 273.15), T >= 273.15))"
    f = load_catalog([SOURCE + formulation(expression)]).formulations["f"]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        values = f.evaluate(T=Q_([200.0, 274.15], "K")).magnitude
    assert values == pytest.approx([0.0, 0.0])


# --- Units ------------------------------------------------------------------------


def test_thresholds_take_the_unit_of_their_input() -> None:
    document = SOURCE + formulation(
        MIXED_PHASE, extra="coefficients = { T_ice = 250.16, T_0 = 273.16 }"
    )
    units = load_catalog([document]).formulations["f"].coefficient_units
    assert {k: str(u.unit) for k, u in units.items()} == {
        "T_ice": "kelvin",
        "T_0": "kelvin",
    }
    assert units["T_ice"].reason == "T <= T_ice"


def test_a_single_piece_is_enough() -> None:
    document = SOURCE + formulation(
        "piecewise((T / T_0, T < T_0))", extra="coefficients = { T_0 = 273.15 }"
    )
    f = load_catalog([document]).formulations["f"]
    assert str(f.coefficient_units["T_0"].unit) == "kelvin"
    assert np.isnan(f.evaluate(T=Q_(300.0, "K")).magnitude)


def test_units_found_only_together_go_through_the_pieces() -> None:
    # a * b is a pure number: neither unit follows alone, and linear algebra,
    # which reads the piecewise definition too, does not fix them.
    expression = "piecewise((a * b, T < 300), (2 * a * b, T >= 300))"
    document = SOURCE + formulation(
        expression, extra="coefficients = { a = 2.0, b = 3.0 }"
    )
    with pytest.raises(CatalogError, match="does not determine the unit of a, b"):
        load_catalog([document])


def test_branches_share_one_dimension() -> None:
    # In a numerical value equation, a coefficient is held to every branch.
    expression = "piecewise((a * T, T < 273.15), (a, T >= 273.15))"
    document = SOURCE + formulation(expression, extra="coefficients = { a = 2.0 }")
    with pytest.raises(CatalogError, match="units contradict the expression"):
        load_catalog([document])


#: Inputs of the quantity equations, by identifier.
QUANTITY_INPUTS = {
    "T": '{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", '
    'description = "T" }',
    "p": '{ identifier = "p", kind = "Pressure", unit = "HectoPA", description = "p" }',
    "q": '{ identifier = "q", kind = "Pressure", unit = "PA", description = "q" }',
}
THRESHOLD = (
    'coefficients = { T_0 = { value = 273.15, unit = "K", unit_basis = "added", '
    'note = "n" } }'
)


def quantity(expression: str, extra: str = THRESHOLD, inputs: str = "Tp") -> str:
    return SOURCE + formulation(
        expression,
        fixed_units=False,
        output='kind = "Pressure", unit = "PA"',
        inputs=", ".join(QUANTITY_INPUTS[name] for name in inputs),
        extra=extra,
    )


def test_a_quantity_equation_is_checked_branch_by_branch() -> None:
    expression = "piecewise((p, T < T_0), (2 * p, T >= T_0))"
    f = load_catalog([quantity(expression)]).formulations["f"]
    assert f.output_factor == 100.0
    found = f.evaluate(T=Q_([270.0, 280.0], "K"), p=Q_(1.0, "hPa"))
    assert found.magnitude == pytest.approx([100.0, 200.0])


@pytest.mark.parametrize(
    ("expression", "extra", "inputs", "message"),
    [
        # A bare number has no unit: the threshold of a quantity equation does.
        ("piecewise((p, T < 273.15), (2 * p, T >= 273.15))", "", "Tp", "kelvin"),
        ("piecewise((p, T < T_0), (T, T >= T_0))", THRESHOLD, "Tp", "kelvin"),
        ("piecewise((p, T < T_0), (q, T >= T_0))", THRESHOLD, "Tpq", "different units"),
    ],
)
def test_a_quantity_equation_with_mismatched_pieces_is_refused(
    expression: str, extra: str, inputs: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([quantity(expression, extra, inputs)])


# --- Rendering -------------------------------------------------------------------


def test_a_piecewise_definition_is_written_on_one_line() -> None:
    tex = to_latex(parse_expression(MIXED_PHASE, NAMES), upright=True)
    assert tex.startswith(r"\left\{0 \;\mathrm{if}\; T \leq T_{\mathrm{ice}},\; ")
    assert r"\;\mathrm{if}\; T_{\mathrm{ice}} < T < T_{0},\; " in tex
    assert tex.endswith(r"1 \;\mathrm{if}\; T \geq T_{0}\right.")
    # A chain written downward is written upward, lower bound first.
    downward = to_latex(parse_expression("piecewise((p, T_0 > T >= T_ice))", NAMES))
    assert r"T_{ice} \leq T < T_{0}" in downward


def test_one_string_serves_latex_markdown_and_mathtext() -> None:
    document = SOURCE + magnus()
    rendering = load_catalog([document]).formulations["magnus"].render()
    assert latex_commands(rendering.latex) <= LATEX_COMMANDS
    assert latex_commands(rendering.markdown) <= LATEX_COMMANDS
    assert rendering.latex in rendering.markdown
    assert rendering.mathtext == f"${rendering.latex}$"
    MathTextParser("path").parse(rendering.mathtext)


# --- Inversion -------------------------------------------------------------------


def test_a_piecewise_definition_is_inverted_branch_by_branch() -> None:
    f = load_catalog([SOURCE + magnus()]).formulations["magnus"]
    frost_dew = dew_point(f, method="symbolic")
    assert not isinstance(frost_dew, NumericalInverse)
    assert frost_dew.expression.startswith("piecewise((")
    # The image of each interval is the condition of its inverse branch.
    assert "e < 6.112), (" in frost_dew.expression
    assert frost_dew.expression.endswith("e >= 6.112))")
    t = Q_([-30.0, -0.5, 0.0, 25.0], "degC")
    back = frost_dew.evaluate(e=f.evaluate(t=t)).to("degC").magnitude
    assert back == pytest.approx(t.magnitude, abs=1e-9)


def test_an_unbounded_branch_has_a_one_sided_image() -> None:
    # Increasing on (-inf, 0) and [0, inf): e < f(0) and e >= f(0).
    f = load_catalog([SOURCE + magnus()]).formulations["magnus"]
    inverse = invert(
        f,
        "t",
        output=Variable("t", "CelsiusTemperature", "DEG_C", "t"),
        input=Variable("e", "VapourPressure", "HectoPA", "e"),
    )
    assert not isinstance(inverse, NumericalInverse)
    assert inverse.expression.count(" < ") + inverse.expression.count(" >= ") == 2


def test_a_bounded_branch_has_a_bounded_image() -> None:
    # Ice below -20 degC, supercooled water from -20 to 0, water above: the
    # middle image is bounded on both sides, and the gap between the ice and
    # the supercooled water values has no inverse.
    expression = MAGNUS.replace("t < 0)", "t < -20)").replace(
        "t >= 0))", "-20 <= t < 0), (C * exp(A * t / (B + t)), t >= 0))"
    )
    document = SOURCE + magnus().replace(MAGNUS, expression)
    f = load_catalog([document]).formulations["magnus"]
    inverse = dew_point(f, method="symbolic")
    assert not isinstance(inverse, NumericalInverse)
    assert " <= e < 6.112), (" in inverse.expression
    t = Q_([-30.0, -10.0, 10.0], "degC")
    back = inverse.evaluate(e=f.evaluate(t=t)).to("degC").magnitude
    assert back == pytest.approx(t.magnitude, abs=1e-9)
    gap = f.evaluate(t=Q_(-20.0001, "degC")).magnitude * 1.05
    assert np.isnan(inverse.evaluate(e=Q_(gap, "hPa")).magnitude)


@pytest.mark.parametrize(
    "expression",
    [
        # A branch without a closed form (SymPy needs LambertW).
        "piecewise((t + exp(t / 10), t < 0), (t + 2 + exp(t / 10), t >= 0))",
        # Images both unbounded: ln(t + 30) covers every value.
        "piecewise((ln(t + 30), t > -30))",
        # Not monotonic on its interval: (t - 10)**2 + 1 on t >= 0.
        "piecewise((exp(t / 10), t < 0), ((t - 10) ** 2 + 1, t >= 0))",
        # Images that overlap: the second branch starts below the first.
        "piecewise((t + 100, t < 0), (t + 50, t >= 0))",
        # Two piecewise definitions.
        "piecewise((t + 1, t < 0), (t + 2, t >= 0)) * piecewise((1, t < 5), (2, t >= 5))",
    ],
)
def test_without_a_closed_form_the_inverse_is_numerical(expression: str) -> None:
    document = SOURCE + formulation(
        expression,
        output='kind = "VapourPressure", unit = "HectoPA"',
        inputs=(
            '{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", '
            'description = "t" }'
        ),
        extra="[[formulations.f.domains]]\nbounds = { t = [-20.0, 20.0] }\n",
    )
    f = load_catalog([document]).formulations["f"]
    output = Variable("t", "CelsiusTemperature", "DEG_C", "t")
    given = Variable("e", "VapourPressure", "HectoPA", "e")
    found = invert(f, "t", output=output, input=given, search=(-20.0, 20.0))
    assert isinstance(found, NumericalInverse)
    with pytest.raises(InversionError, match="each branch monotonic on its interval"):
        invert(
            f, "t", output=output, input=given, method="symbolic", search=(-20.0, 20.0)
        )


# --- Relations ------------------------------------------------------------------


PAIR = """
[formulations.{key}]
label = "{key}"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "q", kind = "Pressure", unit = "PA", description = "q" }}
inputs = [{{ identifier = "P", kind = "Pressure", unit = "HectoPA", description = "P" }}]
[[formulations.{key}.citations]]
reference = "src"
"""

RELATION = """
[relations.r]
kind = "equivalent"
subject = "a"
object = "b"
citation = "src"
"""


def pair(first: str, second: str, bounds: str = "") -> str:
    return (
        SOURCE
        + PAIR.format(key="a", expression=first)
        + PAIR.format(key="b", expression=second)
        + RELATION
        + bounds
    )


def test_two_writings_of_one_definition_share_a_signature() -> None:
    document = SOURCE + PAIR.format(
        key="a", expression="piecewise(((P + 1) ** 2, P < 10), (P, P >= 10))"
    )
    first = load_catalog([document]).formulations["a"]
    second = load_catalog(
        [document.replace("P < 10", "P < 20").replace("P >= 10", "P >= 20")]
    )
    assert signature(first) != signature(second.formulations["a"])
    with pytest.raises(CatalogError, match="identical to formulations.a"):
        load_catalog([document + PAIR.format(key="b", expression=first.expression)])


def test_an_equivalence_of_pieces_is_proved_branch_by_branch() -> None:
    loaded = load_catalog(
        [
            pair(
                "piecewise(((P + 1) ** 2, P < 10), (P, P >= 10))",
                "piecewise((P ** 2 + 2 * P + 1, P < 10), (P, P >= 10))",
            )
        ]
    )
    verdict = verify(loaded.relations["r"], loaded)
    assert verdict.status == "proven"
    assert "compared branch by branch" in verdict.method


def test_a_differing_branch_refutes_an_equivalence() -> None:
    loaded = load_catalog(
        [
            pair(
                "piecewise(((P + 1) ** 2, P < 10), (P, P >= 10))",
                "piecewise((P ** 2 + 2 * P + 1, P < 10), (2 * P, P >= 10))",
                # Samples reach the second branch only within such bounds.
                "bounds = { P = [0.0, 20.0] }\n",
            )
        ]
    )
    verdict = verify(loaded.relations["r"], loaded)
    assert verdict.status == "refuted"
    assert "compared branch by branch" in verdict.method


def test_pieces_with_other_conditions_are_compared_on_samples() -> None:
    loaded = load_catalog(
        [
            pair(
                "piecewise(((P + 1) ** 2, P < 10), (P, P >= 10))",
                "piecewise(((P + 1) ** 2, P < 20), (P, P >= 20))",
            )
        ]
    )
    verdict = verify(loaded.relations["r"], loaded)
    assert verdict.status in ("refuted", "unproven")
    assert "not simplified, compared on samples" in verdict.method


# --- Compositions --------------------------------------------------------------------


OUTER_INPUTS = (
    '{ identifier = "e", kind = "VapourPressure", unit = "HectoPA", '
    'description = "e" }, { identifier = "t", kind = "CelsiusTemperature", '
    'unit = "DEG_C", description = "t" }'
)
COMPOSED = """
[formulations.both]
label = "both"
composition = { outer = "outer", inner = { e = "magnus" } }
"""


def outer(expression: str) -> str:
    return formulation(
        expression,
        key="outer",
        output='kind = "VapourPressure", unit = "HectoPA"',
        inputs=OUTER_INPUTS,
    )


def test_composing_two_piecewise_definitions_solves_no_inequality() -> None:
    written = outer("piecewise((e, t < 10), (2 * e, t >= 10))")
    start = time.perf_counter()
    loaded = load_catalog([SOURCE + magnus() + written + COMPOSED])
    both = loaded.formulations["both"]
    t = Q_([-10.0, 5.0, 20.0], "degC")
    values = both.evaluate(t=t).magnitude
    elapsed = time.perf_counter() - start
    inner = loaded.formulations["magnus"].evaluate(t=t).magnitude
    assert values == pytest.approx(np.where(t.magnitude < 10, inner, 2 * inner))
    # Substituted in the text: the outer piecewise definition holds the inner
    # one twice, conditions as written, nothing solved.
    expr = both.sympy_expression
    assert (
        sum(isinstance(n, sympy.Piecewise) for n in sympy.preorder_traversal(expr)) == 3
    )
    assert "ITE" not in sympy.srepr(expr)
    assert elapsed < 10.0


def test_a_condition_on_a_computed_value_is_refused() -> None:
    # SymPy would rewrite e < 10, e computed by a piecewise definition, as
    # conditions on t: no longer an interval of an input.
    written = formulation(
        "piecewise((e, e < 10), (2 * e, e >= 10))",
        key="outer",
        output='kind = "VapourPressure", unit = "HectoPA"',
        inputs=OUTER_INPUTS.split(', { identifier = "t"')[0],
    )
    with pytest.raises(CatalogError, match="bounds e, which magnus computes"):
        load_catalog([SOURCE + magnus() + written + COMPOSED])
