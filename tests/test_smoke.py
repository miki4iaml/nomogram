# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

import importlib
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

import nomogram

SUBMODULES = [
    "catalog",
    "comparison",
    "dimensions",
    "display",
    "expression",
    "inversion",
    "model",
    "plot",
    "relations",
    "search",
    "semantics",
    "units",
]


def test_version_comes_from_the_metadata() -> None:
    assert nomogram.__version__ == version("nomogram")
    assert nomogram.__all__ == ["__version__", *SUBMODULES]


def test_every_submodule_is_listed() -> None:
    package = Path(nomogram.__file__).parent
    found = sorted(p.stem for p in package.glob("*.py") if not p.stem.startswith("_"))
    assert found == SUBMODULES


def test_submodules_are_attributes_of_the_package() -> None:
    # import nomogram as nomo, then nomo.catalog: imported on first use. Here
    # the other tests have imported them already, so the package's
    # __getattr__ is called directly; test_import_stays_light checks the
    # first use in a fresh interpreter.
    for name in SUBMODULES:
        module = importlib.import_module(f"nomogram.{name}")
        assert nomogram.__getattr__(name) is module
        assert getattr(nomogram, name) is module
    assert set(SUBMODULES) <= set(dir(nomogram))


def test_an_unknown_attribute_is_refused() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'catalogue'"):
        _ = nomogram.catalogue


def test_import_stays_light() -> None:
    # In a fresh interpreter, importing the package must not pull SymPy,
    # pint or matplotlib: submodules are imported on demand, even when
    # listed by dir() or reached as attributes, and nomogram.plot imports
    # matplotlib only when drawing.
    code = (
        "import sys, nomogram as nomo; dir(nomo);"
        "print('sympy' in sys.modules, 'pint' in sys.modules);"
        "nomo.units; print('sympy' in sys.modules, 'pint' in sys.modules);"
        "nomo.plot; print('matplotlib' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.split() == ["False", "False", "False", "True", "False"]
