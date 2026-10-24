# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The documentation examples run, so that they never go stale."""

import ast
import importlib.util
import re
from pathlib import Path

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "docs" / "examples" / "saturation_vapour_pressure.py"
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


def test_display_guide_code_runs() -> None:
    namespace: dict[str, object] = {}
    for block in python_blocks(DISPLAY):
        exec(compile(block, str(DISPLAY), "exec"), namespace)  # noqa: S102
    assert namespace["label"] == r"$e_{\mathrm{w}}$/hPa"
    assert namespace["simple"] == "Celsius temperature $t$ [°C]"
    assert "6{,}112" in str(namespace["french"])


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
