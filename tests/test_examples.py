# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The documentation examples run, so that they never go stale."""

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
