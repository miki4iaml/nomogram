# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""nomogram: a repository of scientific formulas.

Submodules are imported on demand, so that ``import nomogram`` stays
light: :mod:`nomogram.units` (pint) and :mod:`nomogram.expression`
(SymPy).
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__ = version("nomogram")
