# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the extraction tool ``scripts/extract_semantics.py``."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "extract_semantics.py"
SPEC = importlib.util.spec_from_file_location("extract_semantics", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
extract_semantics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract_semantics)

DATA = Path(__file__).parent / "data"
KINDS_TTL = DATA / "qudt-kinds.ttl"
UNITS_TTL = DATA / "qudt-units.ttl"
CF_XML = DATA / "cf-standard-names.xml"
KindSpec = extract_semantics.KindSpec


@pytest.fixture(autouse=True)
def small_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Select only what the excerpts define."""
    monkeypatch.setattr(
        extract_semantics,
        "KINDS",
        {
            "ThermodynamicTemperature": KindSpec(
                "ratio", delta=False, cf_standard_names=(("air_temperature", "narrow"),)
            ),
            "CelsiusTemperature": KindSpec("interval", delta=False),
            "VapourPressure": KindSpec(
                "ratio",
                delta=False,
                cf_standard_names=(("water_vapor_partial_pressure_in_air", "exact"),),
                added_units=("PA", "HectoPA"),
            ),
        },
    )
    monkeypatch.setattr(extract_semantics, "SCALE_CF_NAMES", ())
    monkeypatch.setattr(extract_semantics, "LOCAL_KIND_CF_NAMES", ())
    monkeypatch.setattr(
        extract_semantics,
        "UNITS",
        {"K": "K", "DEG_C": "degC", "HectoPA": "hPa", "PA": "Pa"},
    )


def run() -> dict[str, object]:
    result: dict[str, object] = extract_semantics.extract(
        KINDS_TTL, UNITS_TTL, CF_XML, "3.5.2", "2026-10-14"
    )
    return result


def test_units_are_extracted_with_qudt_conversions() -> None:
    units = run()["units"]
    assert isinstance(units, dict)
    assert units["DEG_C"]["offset"] == 273.15
    assert units["DEG_C"]["multiplier"] == 1.0
    assert units["HectoPA"]["multiplier"] == 100.0
    assert units["PA"]["multiplier"] == 1.0  # QUDT default when absent
    assert units["PA"]["offset"] == 0.0
    assert units["K"]["ucum"] == "K"
    assert units["DEG_C"]["udunits"] is None
    assert units["K"]["matches"] == [
        {
            "target": "http://www.wikidata.org/entity/Q11579",
            "relation": "close",
            "verified": "2026-10-14",
        }
    ]
    assert units["DEG_C"]["matches"] == []


def test_symbols_declared_by_nomogram_replace_qudt_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extract_semantics, "SYMBOLS", {"K": "kelvin"})
    units = run()["units"]
    assert isinstance(units, dict)
    assert units["K"]["symbol"] == "kelvin"
    assert units["PA"]["symbol"] is None  # no symbol in the fixture


def test_kinds_inherit_units_and_follow_the_scale_rule() -> None:
    kinds = run()["quantity_kinds"]
    assert isinstance(kinds, dict)
    # DEG_C is declared for Temperature, which both kinds specialize.
    assert kinds["ThermodynamicTemperature"]["applicable_units"] == ["K"]
    assert kinds["CelsiusTemperature"]["applicable_units"] == ["DEG_C"]
    # HectoPA reaches VapourPressure through Pressure; PA is added.
    assert kinds["VapourPressure"]["applicable_units"] == ["HectoPA", "PA"]
    assert kinds["VapourPressure"]["added_units"] == ["PA"]
    assert kinds["VapourPressure"]["specialization_of"] == "Pressure"


def test_an_interval_scale_may_take_multiplicative_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = extract_semantics.KINDS["VapourPressure"]
    interval = spec._replace(scale_type="interval", added_units=())
    kinds = dict(extract_semantics.KINDS, VapourPressure=interval)
    monkeypatch.setattr(extract_semantics, "KINDS", kinds)
    found = run()["quantity_kinds"]
    assert isinstance(found, dict)
    assert found["VapourPressure"]["applicable_units"] == []
    kinds["VapourPressure"] = interval._replace(offset_units=False)
    found = run()["quantity_kinds"]
    assert isinstance(found, dict)
    assert found["VapourPressure"]["applicable_units"] == ["HectoPA"]


def test_a_kind_may_take_units_with_and_without_an_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A temperature point written in degC or in K, as the dew point is.
    spec = extract_semantics.KINDS["CelsiusTemperature"]
    kinds = dict(
        extract_semantics.KINDS, CelsiusTemperature=spec._replace(offset_units="any")
    )
    monkeypatch.setattr(extract_semantics, "KINDS", kinds)
    found = run()["quantity_kinds"]
    assert isinstance(found, dict)
    assert found["CelsiusTemperature"]["applicable_units"] == ["DEG_C", "K"]
    assert found["CelsiusTemperature"]["added_units"] == []


def test_english_label_is_preferred_and_plain_label_accepted() -> None:
    kinds = run()["quantity_kinds"]
    assert isinstance(kinds, dict)
    assert kinds["ThermodynamicTemperature"]["label"] == "Thermodynamic Temperature"
    assert kinds["CelsiusTemperature"]["label"] == "Celsius Temperature"


def test_cf_names_and_versions_are_recorded() -> None:
    data = run()
    assert data["cf_standard_names"] == {
        "air_temperature": {"canonical_units": "K", "pint": "K"},
        "water_vapor_partial_pressure_in_air": {"canonical_units": "Pa", "pint": "Pa"},
    }
    sources = data["sources"]
    assert isinstance(sources, dict)
    assert sources["qudt"]["version"] == "3.5.2"
    assert sources["cf_standard_names"]["version"] == "95"
    assert sources["extracted"] == "2026-10-14"


@pytest.mark.parametrize(
    ("udunits", "pint"),
    [
        ("1", "dimensionless"),
        ("K", "K"),
        ("kg m-3", "kg * m ** -3"),
        ("m2 s-2", "m ** 2 * s ** -2"),
        ("1e-3", "1e-3"),
    ],
)
def test_udunits_to_pint(udunits: str, pint: str) -> None:
    assert extract_semantics.udunits_to_pint(udunits) == pint


def test_udunits_outside_the_cf_syntax_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported UDUNITS factor"):
        extract_semantics.udunits_to_pint("kg/m3")


def test_missing_kind_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(extract_semantics.KINDS, "Missing", KindSpec("ratio", False))
    with pytest.raises(ValueError, match="not found in the source"):
        run()


def test_missing_label_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(extract_semantics.KINDS, "Unlabelled", KindSpec("ratio", False))
    with pytest.raises(ValueError, match="no label"):
        run()


def test_missing_cf_name_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        extract_semantics.KINDS,
        "CelsiusTemperature",
        KindSpec("interval", False, cf_standard_names=(("no_such_name", "exact"),)),
    )
    with pytest.raises(ValueError, match="CF standard names not found: no_such_name"):
        run()


def test_cf_table_without_version_is_rejected(tmp_path: Path) -> None:
    table = tmp_path / "table.xml"
    table.write_text("<standard_name_table/>", encoding="utf-8")
    with pytest.raises(ValueError, match="no version_number"):
        extract_semantics.extract_cf(table, set())


def arguments(output: Path) -> list[str]:
    return [
        "--kinds",
        str(KINDS_TTL),
        "--units",
        str(UNITS_TTL),
        "--cf",
        str(CF_XML),
        "--qudt-version",
        "3.5.2",
        "--date",
        "2026-10-14",
        "--output",
        str(output),
    ]


def test_main_writes_deterministic_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "semantics.json"
    assert extract_semantics.main(arguments(output)) == 0
    first = output.read_bytes()
    assert extract_semantics.main(arguments(output)) == 0
    assert output.read_bytes() == first
    assert b"\r\n" not in first
    assert json.loads(first)["units"]["K"]["pint"] == "K"
    assert "wrote" in capsys.readouterr().out


def test_main_reports_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setitem(extract_semantics.KINDS, "Missing", KindSpec("ratio", False))
    output = tmp_path / "semantics.json"
    assert extract_semantics.main(arguments(output)) == 1
    assert not output.exists()
    assert "error: not found in the source" in capsys.readouterr().err


def test_cf_names_of_scales_are_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    kinds = dict(extract_semantics.KINDS)
    kinds["ThermodynamicTemperature"] = kinds["ThermodynamicTemperature"]._replace(
        cf_standard_names=()
    )
    monkeypatch.setattr(extract_semantics, "KINDS", kinds)
    monkeypatch.setattr(extract_semantics, "SCALE_CF_NAMES", ("air_temperature",))
    names = run()["cf_standard_names"]
    assert isinstance(names, dict)
    assert "air_temperature" in names


def test_cf_names_of_local_kinds_are_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    kinds = dict(extract_semantics.KINDS)
    kinds["ThermodynamicTemperature"] = kinds["ThermodynamicTemperature"]._replace(
        cf_standard_names=()
    )
    monkeypatch.setattr(extract_semantics, "KINDS", kinds)
    monkeypatch.setattr(extract_semantics, "LOCAL_KIND_CF_NAMES", ("air_temperature",))
    names = run()["cf_standard_names"]
    assert isinstance(names, dict)
    assert "air_temperature" in names
