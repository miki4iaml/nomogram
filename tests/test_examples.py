# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The documentation examples run, so that they never go stale."""

import ast
import importlib.util
import math
import re
from pathlib import Path

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "docs" / "examples" / "saturation_vapour_pressure.py"
HUMIDITY = ROOT / "docs" / "examples" / "humidity_between_levels.py"
READMES = [ROOT / "README.md", ROOT / "README.fr.md"]
DISPLAY = ROOT / "docs" / "display.md"


def python_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)


def code_lines(block: str) -> list[str]:
    lines = (line.split("  #", 1)[0].strip() for line in block.splitlines())
    return [line for line in lines if line]


def test_saturation_vapour_pressure_example_writes_its_plot(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("saturation_vapour_pressure", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_readme_example_is_the_script_that_draws_the_image(readme: Path) -> None:
    script = code_lines(SCRIPT.read_text(encoding="utf-8"))
    for line in code_lines(python_blocks(readme)[0]):
        assert any(line in candidate for candidate in script), line


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_readme_code_runs(readme: Path) -> None:
    import matplotlib.pyplot as plt

    namespace: dict[str, object] = {}
    for block in python_blocks(readme):
        exec(compile(block, str(readme), "exec"), namespace)  # noqa: S102
    plt.close("all")
    assert "table" in namespace
    assert "ha" in namespace
    # The interpolation scheme, its levels fixed: a function of p alone.
    in_ln_p = namespace["in_ln_p"]
    at_700 = in_ln_p.evaluate(p=namespace["Q_"](700, "hPa"))  # type: ignore[attr-defined, operator]
    assert magnitude(at_700.to("K")) == pytest.approx(268.49, abs=0.005)


def test_display_guide_code_runs() -> None:
    namespace: dict[str, object] = {}
    for block in python_blocks(DISPLAY):
        exec(compile(block, str(DISPLAY), "exec"), namespace)  # noqa: S102
    assert namespace["label"] == r"$e_{\mathrm{w}}$/hPa"
    assert namespace["simple"] == "Celsius temperature $t$ [°C]"
    assert "6{,}112" in str(namespace["french"])


def test_vertical_guide_code_gives_the_values_it_states() -> None:
    import matplotlib.pyplot as plt

    guide = ROOT / "docs" / "vertical.md"
    namespace: dict[str, object] = {}
    for block in python_blocks(guide):
        exec(compile(block, str(guide), "exec"), namespace)  # noqa: S102
    plt.close("all")
    assert magnitude(namespace["at_500_hPa"]) == pytest.approx(5574.44, abs=0.005)
    # MetPy's mixed parcel: its docstring prints 28.750033 and 18.1504239 degC.
    parcel_t = namespace["parcel_t"].to("degC")  # type: ignore[attr-defined]
    parcel_t_d = namespace["parcel_t_d"].to("degC")  # type: ignore[attr-defined]
    assert magnitude(parcel_t) == pytest.approx(28.750033, abs=5e-7)
    assert magnitude(parcel_t_d) == pytest.approx(18.1504235, abs=5e-8)
    assert magnitude(parcel_t_d) == pytest.approx(18.1504239, abs=5e-7)
    # The relative humidity at 700 hPa, by each practice.
    relative = namespace["tables"][2]  # type: ignore[index]
    at_700 = 60  # 850 to 500 hPa by steps of 2.5 hPa
    values = {
        key.split("(")[0]: 100 * float(value.to("").magnitude[at_700])
        for key, value in relative.values.items()
    }
    assert values.pop(relative.reference) == pytest.approx(47.34, abs=0.005)
    assert values == pytest.approx(
        {
            "metpy171_relative_humidity_dew_point_log_pressure": 50.01,
            "metpy171_relative_humidity_dew_point_pressure": 49.76,
            "pressure_interpolation_relative_humidity": 49.76,
            "metpy171_relative_humidity_isentropic": 59.54,
            "metpy171_relative_humidity_specific_humidity_log_pressure": 60.72,
            "relative_humidity_log_specific_humidity_log_pressure": 47.36,
        },
        abs=0.005,
    )


def test_humidity_example_is_the_script_that_draws_the_image() -> None:
    script = code_lines(HUMIDITY.read_text(encoding="utf-8"))
    blocks = python_blocks(ROOT / "docs" / "vertical.md")
    shown = next(b for b in blocks if "plot_profiles(tables" in b)
    for line in code_lines(shown):
        assert any(line in candidate for candidate in script), line


def test_humidity_example_writes_its_plot(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("humidity_between_levels", HUMIDITY)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


def test_search_guide_code_runs() -> None:
    guide = ROOT / "docs" / "search.md"
    namespace: dict[str, object] = {}
    for block in python_blocks(guide):
        exec(compile(block, str(guide), "exec"), namespace)  # noqa: S102
    assert "c" in namespace


#: A number at the start of a comment: the value the line gives, to its last
#: digit (rounded, or truncated when "..." follows).
COMMENTED_VALUE = re.compile(r"#\s*\(?(-?\d+(?:\.\d+)?)")


def magnitude(value: object) -> float:
    """The number a commented line shows: a magnitude, or a tuple's first item."""
    if isinstance(value, tuple):
        value = value[0]
    return float(getattr(value, "magnitude", value))  # type: ignore[arg-type]


def test_sea_water_guide_code_gives_the_values_it_states() -> None:
    guide = ROOT / "docs" / "sea-water.md"
    namespace: dict[str, object] = {}
    checked = []
    for block in python_blocks(guide):
        lines = block.splitlines()
        for statement in ast.parse(block).body:
            code = compile(ast.Module([statement], []), str(guide), "exec")
            if not isinstance(statement, ast.Expr):
                exec(code, namespace)  # noqa: S102
                continue
            value = eval(
                compile(ast.Expression(statement.value), str(guide), "eval"),
                namespace,
            )
            found = COMMENTED_VALUE.search(lines[statement.lineno - 1])
            if found is None:
                continue
            stated = found.group(1)
            digits = len(stated.partition(".")[2])
            assert magnitude(value) == pytest.approx(
                float(stated), abs=10.0**-digits
            ), lines[statement.lineno - 1]
            checked.append(stated)
    assert checked == ["34.99997", "0.981205", "0.98", "0.98", "3110.56", "0.351"]


def test_catalog_guide_personal_catalog_code_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nomogram.catalog import catalog

    # The file the guide assumes: a family of one formulation, my_key.
    (tmp_path / "my_family.toml").write_text(
        """
[catalog]
name = "my_family"
format = 2
requires = ["water-vapour"]

[references."my_family:src"]
authors = "A"
title = "T"
status = "verified"

[formulations."my_family:my_key"]
label = "A Magnus form"
expression = "C * exp(A * t / (B + t))"
fixed_units = true
output = { identifier = "e_s", kind = "SaturationVapourPressureOverWater", unit = "HectoPA", description = "e_s" }
inputs = [{ identifier = "t", kind = "CelsiusTemperature", unit = "DEG_C", description = "t" }]
coefficients = { A = 17.0, B = 240.0, C = 6.0 }

[[formulations."my_family:my_key".citations]]
reference = "my_family:src"
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    guide = ROOT / "docs" / "catalog.md"
    blocks = python_blocks(guide)
    assert len(blocks) == 1
    namespace: dict[str, object] = {}
    exec(compile(blocks[0], str(guide), "exec"), namespace)  # noqa: S102
    mine = namespace["mine"]
    assert "my_family:my_key" in mine.formulations  # type: ignore[attr-defined]
    assert "my_family:my_key" not in catalog().formulations


ALOFT = ROOT / "docs" / "examples" / "humidity_aloft.py"
ALOFT_GUIDE = ROOT / "docs" / "humidity-aloft.md"


def test_humidity_aloft_example_is_the_script_that_draws_the_image() -> None:
    script = code_lines(ALOFT.read_text(encoding="utf-8"))
    (shown,) = python_blocks(ALOFT_GUIDE)
    for line in code_lines(shown):
        assert any(line in candidate for candidate in script), line


def test_humidity_aloft_example_writes_its_plot(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("humidity_aloft", ALOFT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")


def test_humidity_aloft_guide_gives_the_values_it_states() -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    namespace: dict[str, object] = {}
    for block in python_blocks(ALOFT_GUIDE):
        exec(compile(block, str(ALOFT_GUIDE), "exec"), namespace)  # noqa: S102
    plt.close("all")
    at_11_km = 110  # 0 to 14 km by steps of 0.1 km

    def percent(table: object) -> dict[str, float]:
        deviations = table.relative_deviations  # type: ignore[attr-defined]
        return {
            key.split("[")[0]: round(100 * float(np.asarray(value)[at_11_km]), 2)
            for key, value in deviations.items()
        }

    saturation = percent(namespace["saturation"])
    assert saturation["metpy171_saturation_vapour_pressure"] == -0.62
    assert saturation["bolton1980"] == -2.32
    assert saturation["tetens1930"] == -7.73
    assert saturation["buck1996"] == -1.09
    assert saturation["hyland_wexler1983"] == 0.18
    # Each curve stops where its source does: below -45, -50 and -20 degC.
    assert all(
        math.isnan(saturation[key])
        for key in ("sonntag1990_magnus", "goff_gratch1946", "vaisala2013_water")
    )
    decoded = percent(namespace["decoded"])
    assert decoded["metpy171_saturation_vapour_pressure"] == -1.14
    assert decoded["bolton1980"] == -5.33
    assert decoded["tetens1930"] == -13.63
