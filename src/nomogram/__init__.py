# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""nomogram: a repository of scientific formulas.

Submodules are imported on demand, so that ``import nomogram`` stays
light: :mod:`nomogram.units` (pint), :mod:`nomogram.expression`
(SymPy), :mod:`nomogram.semantics` (bundled QUDT and CF subsets),
:mod:`nomogram.model` and :mod:`nomogram.catalog` (formulations),
:mod:`nomogram.dimensions`, :mod:`nomogram.comparison`,
:mod:`nomogram.inversion`, :mod:`nomogram.relations`,
:mod:`nomogram.search`, :mod:`nomogram.display` and :mod:`nomogram.plot`.

Each is also an attribute of the package, imported the first time it is
used (PEP 562)::

    import nomogram as nom

    formulations = nom.catalog.catalog().formulations_of("VapourPressure")
"""

from importlib import import_module
from importlib.metadata import version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nomogram import catalog as catalog
    from nomogram import comparison as comparison
    from nomogram import dimensions as dimensions
    from nomogram import display as display
    from nomogram import expression as expression
    from nomogram import inversion as inversion
    from nomogram import model as model
    from nomogram import plot as plot
    from nomogram import relations as relations
    from nomogram import search as search
    from nomogram import semantics as semantics
    from nomogram import units as units

__all__ = [
    "__version__",
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

#: Submodules reachable as attributes of the package.
_SUBMODULES = frozenset(__all__) - {"__version__"}

__version__ = version("nomogram")


def __getattr__(name: str) -> object:
    """Import a submodule the first time it is used as an attribute."""
    if name in _SUBMODULES:
        return import_module(f"{__name__}.{name}")
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """The names of the package, submodules included before their import."""
    return sorted({*globals(), *_SUBMODULES})
