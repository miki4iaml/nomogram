# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for cross-checks: values computed once by other implementations.

The first test is the authority: every recorded case is computed again,
so that a change of a formulation cannot silently depart from what an
independent implementation gave.
"""

import dataclasses
import datetime

import pytest

from nomogram.catalog import CatalogError, catalog, load_catalog, main
from nomogram.model import CheckCase, CrossCheck
from nomogram.relations import replay

CATALOG = catalog()


def test_bundled_cross_checks_agree() -> None:
    assert CATALOG.cross_checks
    for check in CATALOG.cross_checks.values():
        for result in replay(check, CATALOG):
            assert result.agrees, (check.key, result.case, result.value)


def test_the_itu_rpy_check_is_recorded_with_its_version_and_date() -> None:
    check = CATALOG.cross_checks["itu_rpy_p453"]
    assert check.implementation == "ITU-Rpy"
    assert "f739993" in check.version
    assert check.checked == datetime.date(2026, 10, 21)
    assert {c.formulation for c in check.cases} >= {
        "itu_r_p453_refractivity",
        "itu_r_p453_refractivity_dry",
        "itu_r_p453_refractivity_wet",
        "itu_r_p453_es_water",
        "itu_r_p453_es_ice",
        "itu_r_p453_vapour_pressure",
    }
    assert CATALOG.families["radio"].contents["cross_checks"] == ("itu_rpy_p453",)


def test_a_departure_is_detected() -> None:
    check = CATALOG.cross_checks["itu_rpy_p453"]
    case = dataclasses.replace(check.cases[0], value=check.cases[0].value * (1 + 1e-6))
    (result,) = replay(dataclasses.replace(check, cases=(case,)), CATALOG)
    assert not result.agrees
    assert result.deviation == pytest.approx(1e-6, rel=1e-3)


def test_a_zero_value_is_compared_absolutely() -> None:
    case = CheckCase("itu_r_p453_vapour_pressure", {"H": 0.0, "e_s": 20.0}, 0.0)
    check = CrossCheck("zero", "Hand", "1", datetime.date(2026, 10, 21), (case,))
    (result,) = replay(check, CATALOG)
    assert result.agrees
    assert result.deviation == 0.0


def test_the_command_line_lists_the_cross_checks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["verify"]) == 0
    assert "itu_rpy_p453: 16 of 16 cases agree with ITU-Rpy" in capsys.readouterr().out


DOCUMENT = """
[references.src]
authors = "Author, A."
title = "A title"
status = "verified"

[formulations.f]
label = "Test formulation"
expression = "a * t"
fixed_units = true
output = { identifier = "e", kind = "VapourPressure", unit = "HectoPA", description = "out" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "in" }]
coefficients = { a = 2.0 }

[cross_checks.c]
implementation = "Other"
version = "1.0"
checked = {checked}
cases = {cases}
"""

CASE = '[{ formulation = "f", inputs = { t = 3.0 }, value = 6.0 }]'


def document(checked: str, cases: str) -> str:
    return DOCUMENT.replace("{checked}", checked).replace("{cases}", cases)


def test_a_valid_cross_check_loads() -> None:
    loaded = load_catalog([document("2026-10-21", CASE)])
    check = loaded.cross_checks["c"]
    assert check.cases[0].rtol == 1e-12
    assert all(r.agrees for r in replay(check, loaded))


@pytest.mark.parametrize(
    ("checked", "cases", "message"),
    [
        ('"2026-10-21"', CASE, "checked: expected a date"),
        ("2026-10-21", "[]", "cases: expected a non-empty list"),
        (
            "2026-10-21",
            '[{ formulation = "g", inputs = { t = 3.0 }, value = 6.0 }]',
            "unknown formulation 'g'",
        ),
        (
            "2026-10-21",
            '[{ formulation = "f", inputs = { x = 3.0 }, value = 6.0 }]',
            "expected a value for each input of f: t",
        ),
        (
            "2026-10-21",
            '[{ formulation = "f", inputs = { t = 3.0 }, value = 6.0, rtol = 0.0 }]',
            "rtol: expected a positive tolerance",
        ),
        (
            "2026-10-21",
            '[{ formulation = "f", inputs = { t = 3.0 }, value = 6.0, extra = 1 }]',
            "unknown keys: extra",
        ),
    ],
)
def test_invalid_cross_checks_are_refused(
    checked: str, cases: str, message: str
) -> None:
    with pytest.raises(CatalogError, match=message):
        load_catalog([document(checked, cases)])
