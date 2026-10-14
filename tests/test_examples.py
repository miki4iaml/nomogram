# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The documentation examples run, so that they never go stale."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

EXAMPLES = Path(__file__).parents[1] / "docs" / "examples"


def test_saturation_vapour_pressure_example_writes_its_plot(tmp_path: Path) -> None:
    script = EXAMPLES / "saturation_vapour_pressure.py"
    spec = importlib.util.spec_from_file_location("saturation_vapour_pressure", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "plot.png"
    module.main(str(output))
    assert output.read_bytes().startswith(b"\x89PNG")
