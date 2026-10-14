# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""nomogram: a repository of scientific formulas.

Submodules are imported on demand, so that ``import nomogram`` stays
light: :mod:`nomogram.units` (pint), :mod:`nomogram.expression`
(SymPy), :mod:`nomogram.semantics` (bundled QUDT and CF subsets),
:mod:`nomogram.model` and :mod:`nomogram.catalog` (formulations),
:mod:`nomogram.comparison`, :mod:`nomogram.inversion` and :mod:`nomogram.plot`.
"""

from importlib.metadata import version

__all__ = ["__version__"]

__version__ = version("nomogram")
