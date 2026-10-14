# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

import subprocess
import sys
from importlib.metadata import version

import nomogram


def test_version_comes_from_the_metadata() -> None:
    assert nomogram.__version__ == version("nomogram")
    assert nomogram.__all__ == ["__version__"]


def test_import_stays_light() -> None:
    # In a fresh interpreter, importing the package must not pull SymPy
    # or pint: submodules are imported on demand.
    code = "import sys, nomogram; print('sympy' in sys.modules, 'pint' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.split() == ["False", "False"]
