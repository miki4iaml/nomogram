# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for signatures, refusal of duplicates and the check report."""

from pathlib import Path

import pytest

from nomogram.catalog import CatalogError, catalog, check, load_catalog, main
from nomogram.relations import form, report, signature

CATALOG = catalog()

MAGNUS = """
[formulations.{key}]
label = "A Magnus form"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "{output}", kind = "VapourPressure", unit = "HectoPA", description = "out" }}
inputs = [{{ identifier = "{input}", kind = "CelsiusTemperature", unit = "{unit}", description = "in" }}]
coefficients = {{ A = 17.62, B = 243.12, C = {c} }}
"""


def magnus(
    key: str,
    *,
    expression: str = "C * exp(A * t / (B + t))",
    output: str = "e_s",
    input: str = "t",
    unit: str = "DEG_C",
    c: str = "6.112",
) -> str:
    return MAGNUS.format(
        key=key, expression=expression, output=output, input=input, unit=unit, c=c
    )


def one(document: str) -> object:
    return next(iter(load_catalog([document]).formulations.values()))


def test_signature_ignores_writing_and_names() -> None:
    reference = signature(one(magnus("a")))  # type: ignore[arg-type]
    rewritten = magnus(
        "b", expression="exp(A * u / (u + B)) * C", input="u", output="E", c="6.1120"
    )
    assert signature(one(rewritten)) == reference  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "change",
    [
        {"c": "6.1121"},  # another coefficient
        {"expression": "C * 10 ** (A * t / (B + t))"},  # another expression
        {"expression": "C * exp(A - A * B / (B + t))"},  # equal after algebra only
    ],
)
def test_signature_differs_for_another_formulation(change: dict[str, str]) -> None:
    reference = signature(one(magnus("a")))  # type: ignore[arg-type]
    assert signature(one(magnus("b", **change))) != reference  # type: ignore[arg-type]


def test_inputs_of_the_same_kind_and_unit_are_renamed_whatever_their_order() -> None:
    template = """
[formulations.{key}]
label = "Difference"
expression = "{expression}"
fixed_units = false
output = {{ identifier = "d", kind = "Pressure", unit = "HectoPA", description = "out" }}
inputs = [
  {{ identifier = "{first}", kind = "Pressure", unit = "HectoPA", description = "a" }},
  {{ identifier = "{second}", kind = "Pressure", unit = "HectoPA", description = "b" }},
]
"""
    a = one(template.format(key="a", expression="p - q", first="p", second="q"))
    b = one(template.format(key="b", expression="y - x", first="x", second="y"))
    assert signature(a) == signature(b)  # type: ignore[arg-type]


def test_form_leaves_coefficients_aside() -> None:
    magnus_forms = {
        "sonntag1990_magnus",
        "alduchov_eskridge1996",
        "buck1981_magnus",
        "bolton1980",
    }
    shapes = {form(CATALOG.formulations[k]) for k in magnus_forms}
    assert len(shapes) == 1
    assert form(CATALOG.formulations["tetens1930"]) not in shapes


def test_identical_formulations_are_refused_with_a_suggestion() -> None:
    document = magnus("a") + magnus(
        "b", input="u", expression="C * exp(A * u / (B + u))"
    )
    with pytest.raises(
        CatalogError,
        match="formulations.b: identical to formulations.a.*add a citation to a",
    ):
        load_catalog([document])


def test_two_writings_that_round_apart_are_still_refused() -> None:
    # a (T - b) and a T - a b nearly cancel at the probe value 260: their
    # values differ in the seventh digit, and the prefilter lets them meet.
    template = """
[formulations.{key}]
label = "A linear form"
expression = "{expression}"
fixed_units = true
output = {{ identifier = "y", kind = "Pressure", unit = "HectoPA", description = "out" }}
inputs = [{{ identifier = "T", kind = "ThermodynamicTemperature", unit = "K", description = "in" }}]
coefficients = {{ a = 3.0, b = 259.9999999 }}
"""
    document = template.format(key="a", expression="a * (T - b)") + template.format(
        key="b", expression="a * T - a * b"
    )
    with pytest.raises(
        CatalogError, match="formulations.b: identical to formulations.a"
    ):
        load_catalog([document])


def test_the_bundled_catalog_has_no_duplicates() -> None:
    signatures = [signature(f) for f in CATALOG.formulations.values()]
    assert len(set(signatures)) == len(signatures)


def test_report_gives_observations() -> None:
    text = report(CATALOG, ["alduchov_eskridge1996"])
    assert text.startswith("alduchov_eskridge1996 (SaturationVapourPressureOverWater)")
    assert (
        "same form, other coefficients: sonntag1990_magnus, buck1981_magnus, bolton1980"
        in text
    )
    assert "observed max deviation from goff1957: 0.3843 % at t = -30.18" in text
    # The domain where both are valid: IAPWS starts at the triple point.
    assert "observed max deviation from iapws_sr1_86" in text


PERSONAL = """
[catalog]
name = "mylab"
format = 2
requires = ["water-vapour"]

[formulations."mylab:magnus"]
label = "Magnus with Sonntag coefficients, written another way"
expression = "exp(A * t / (t + B)) * C"
fixed_units = true
output = { identifier = "e_s", kind = "SaturationVapourPressureOverWater", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { A = 17.62, B = 243.12, C = 6.1121 }

[[formulations."mylab:magnus".domains]]
bounds = { t = [-40.0, 50.0] }
"""


def test_check_reports_on_a_new_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "mylab.toml"
    path.write_text(PERSONAL, encoding="utf-8")
    text = check(path)
    assert "mylab:magnus (SaturationVapourPressureOverWater)" in text
    assert "same form, other coefficients:" in text
    assert "observed max deviation from sonntag1990_magnus: 0.001636 %" in text
    assert main(["check", str(path)]) == 0
    assert "mylab:magnus" in capsys.readouterr().out


def test_check_refuses_a_duplicate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "mylab.toml"
    path.write_text(PERSONAL.replace("C = 6.1121", "C = 6.112"), encoding="utf-8")
    with pytest.raises(CatalogError, match="add a citation to sonntag1990_magnus"):
        check(path)
    assert main(["check", str(path)]) == 1
    assert "add a citation to sonntag1990_magnus" in capsys.readouterr().err


def test_check_on_a_bundled_family() -> None:
    folder = Path(__file__).parents[1] / "src" / "nomogram" / "data" / "catalog"
    text = check(folder / "moist-air.toml")
    assert (
        text.splitlines()[0]
        == "mass_concentration_ideal_gas (MassConcentrationOfWaterVapour)"
    )


def test_numerically_identical_formulations_are_pointed_out() -> None:
    document = (
        magnus("a")
        + magnus("b", expression="C * exp(A - A * B / (B + t))")
        + ("\n[[formulations.a.domains]]\nbounds = { t = [-40.0, 50.0] }\n")
    )
    loaded = load_catalog([document])
    text = report(loaded, ["b"])
    assert "numerically identical" in text


def vapour(
    key: str,
    factor: int,
    input: str = "t",
    kind: str = "CelsiusTemperature",
    unit: str = "DEG_C",
    domain: str = "",
) -> str:
    text = (
        f'\n[formulations.{key}]\nlabel = "{key}"\nexpression = "{factor} * {input}"\n'
        "fixed_units = true\n"
        'output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", '
        'description = "out" }\n'
        f'inputs = [{{ identifier = "{input}", kind = "{kind}", unit = "{unit}", '
        'description = "in" }]\n'
    )
    if domain:
        text += f"[[formulations.{key}.domains]]\nbounds = {{ {input} = {domain} }}\n"
    return text


def test_report_skips_pairs_without_a_common_domain() -> None:
    humid = vapour(
        "humid",
        6,
        input="RH",
        kind="RelativeHumidity",
        unit="PERCENT",
        domain="[0.0, 100.0]",
    )
    document = (
        vapour("cold", 2, domain="[-40.0, 0.0]")
        + vapour("warm", 3, domain="[10.0, 50.0]")
        + vapour("free", 4)
        + vapour("other_free", 5, input="u")
        + humid
    )
    loaded = load_catalog([document])
    cold = report(loaded, ["cold"])
    assert "from free" in cold  # the domain of either side serves
    assert "from warm" not in cold  # disjoint domains
    assert "from humid" not in cold  # an input of another kind
    assert "from other_free" not in report(loaded, ["free"])  # no domain at all
