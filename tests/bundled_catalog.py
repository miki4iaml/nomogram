# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""The bundled catalog in part, for the tests that add documents to it.

A test of a mechanism (calls, scales, proportionality) needs the entries
its documents refer to, not the whole catalog: loading only the families
it names, and those they require, keeps it as discriminating and spares
building every formulation of the catalog each time (about 2 s on
2026-11-08, for 390 formulations).
"""

import tomllib
from functools import lru_cache
from importlib.resources import files

from nomogram.catalog import Catalog, load_catalog


@lru_cache(maxsize=1)
def _families() -> dict[str, tuple[str, tuple[str, ...]]]:
    """By family name, its document and the families it requires."""
    found: dict[str, tuple[str, tuple[str, ...]]] = {}
    for entry in files("nomogram.data.catalog").iterdir():
        if entry.name.endswith(".toml"):
            text = entry.read_text(encoding="utf-8")
            header = tomllib.loads(text)["catalog"]
            found[header["name"]] = (text, tuple(header["requires"]))
    return found


def bundled_documents(*families: str) -> list[str]:
    """The documents of the families and of those they require, required first."""
    known = _families()
    order: list[str] = []

    def visit(name: str) -> None:
        if name in order:
            return
        for required in known[name][1]:
            visit(required)
        order.append(name)

    for name in families:
        visit(name)
    return [known[name][0] for name in order]


def with_families(families: tuple[str, ...], *documents: str) -> Catalog:
    """The families of the bundled catalog named, with documents for a test."""
    return load_catalog([*bundled_documents(*families), *documents])
