# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Units: a private pint registry and the scale rules nomogram relies on.

nomogram uses `pint <https://pint.readthedocs.io/>`_ as its unit engine,
so that quantity values coming from MetPy or xarray (pint-xarray) are
accepted as they are. A pint ``Quantity`` (magnitude and unit) is what
QUDT calls a ``QuantityValue`` and the VIM a *quantity value* (1.19).
nomogram's own registry is created once, here, and never modified
afterwards: nomogram never touches pint's global application registry.

Scale semantics follow the SI Brochure (9th edition, section 2.3.1): the
degree Celsius is equal in magnitude to the kelvin; what is offset is the
quantity *Celsius temperature*, t = T - T0 with T0 = 273.15 K. pint, like
QUDT (``qudt:conversionOffset``), carries that offset in the unit. In
pint terms, a Celsius temperature is a *point* expressed in ``degC`` and
a temperature difference is expressed in ``delta_degC`` or ``K`` (OM's
``Point`` and ``Measure``; QUDT's *delta quantity*). pint refuses
ambiguous operations such as adding two temperature points
(:class:`pint.errors.OffsetUnitCalculusError`).

Quantity kinds (thermodynamic temperature, Celsius temperature,
temperature difference...) come with the bundled QUDT and CF subsets.
``docs/rosetta.md`` maps this vocabulary across QUDT, the SI, pint, SymPy,
CF and OM.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import pint

__all__ = ["Q_", "ScaleType", "convert", "is_offset_unit", "ureg"]

#: The registry used by nomogram. Created once; never modified afterwards.
ureg: pint.UnitRegistry = pint.UnitRegistry()

#: Shortcut for building quantities in nomogram's registry.
Q_ = ureg.Quantity


class ScaleType(Enum):
    """Type of quantity-value scale (VIM 1.27; QUDT ``qudt:ScaleType``).

    A ratio scale has a natural zero (kelvin, pascal): ratios of values are
    meaningful. An interval scale has a conventional origin (Celsius
    temperature): only differences are meaningful, and its values are
    points relative to that origin. QUDT also has ordinal and nominal
    scales; formulas do not need them, so they are left out.
    """

    RATIO = "ratio"
    INTERVAL = "interval"


def is_offset_unit(unit: object) -> bool:
    """Tell whether a unit carries an offset, i.e. expresses points of an interval scale.

    A unit carries an offset (QUDT ``conversionOffset``; pint's
    non-multiplicative units) when its zero is not the zero of the
    corresponding base unit: 0 degC is 273.15 K, whereas 0 delta_degC is
    0 K. The test relies on pint's public conversion only.

    Parameters
    ----------
    unit : str or pint.Unit
        Unit name or unit object; it is read by name in nomogram's
        registry.

    Returns
    -------
    bool
        ``True`` for units such as ``degC`` or ``degF``; ``False`` for
        multiplicative units such as ``K``, ``Pa`` or ``delta_degC``.
    """
    zero = Q_(0.0, str(unit)).to_base_units().magnitude
    return bool(zero != 0.0)


def convert(quantity: Any, unit: str) -> Any:
    """Convert a quantity value to ``unit``, accepting other pint registries.

    Values built with another pint registry (MetPy's, for instance) are
    first rebuilt in nomogram's registry from their magnitude and unit
    name, so that pint does not reject the mix of registries.

    Parameters
    ----------
    quantity : pint.Quantity
        The quantity value to convert (pint's name for it is kept); its
        magnitude may be a number or a numpy array.
    unit : str
        Target unit, for example ``"K"``, ``"hPa"`` or ``"delta_degC"``.

    Returns
    -------
    pint.Quantity
        The converted quantity value, in nomogram's registry.

    Raises
    ------
    pint.errors.DimensionalityError
        If the target unit does not have the dimension of the value.
    TypeError
        If ``quantity`` is not a pint quantity.
    """
    if not isinstance(quantity, pint.Quantity):
        msg = f"expected a pint quantity, got {type(quantity).__name__}"
        raise TypeError(msg)
    native = (
        quantity
        if quantity._REGISTRY is ureg
        else Q_(quantity.magnitude, str(quantity.units))
    )
    return native.to(unit)
