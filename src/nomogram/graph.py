# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Graphs of the catalog, as node-link documents to exchange and draw.

:func:`kind_graph` gives the tree of quantity kinds, each linked to the
kind it specializes and to its matches in external vocabularies (CF
standard names, Wikidata items, quantities of the SI Digital Framework of
the BIPM). :func:`system_graph` gives a system of
equations: its equations, its variables, which equation gives which
variable and which variables each equation reads.

Both return a document of the node-link format of NetworkX
(``networkx.node_link_data(G, edges="edges")``), with the conventions of
:data:`FORMAT`, a plain ``dict`` ready for :func:`json.dumps`:

- ``graph`` names the format, the producer (nomogram and its version), the
  language of the labels, the prefixes used and the declared values of
  each attribute (``vocabulary``): the type of each node and edge, the
  origin of a kind, the role of a variable;
- a node ``id`` is opaque and stable from one version of nomogram to the
  next: the reference of the entry (``kinds.RelativeHumidity``), the name
  of an equation or a variable in its system, or the IRI of an external
  entity;
- the order of the nodes and edges is stable, for reproducible figures;
  the edges are grouped by source, in the order of the nodes, then by
  target, as NetworkX lists them: a document read and written again by
  NetworkX comes back unchanged.

Types are prefixed by the vocabulary that defines their meaning:
``qudt:specializationOf`` between kinds, ``skos:exactMatch`` and its
siblings towards external vocabularies; ``nomogram:`` only for what exists
in nomogram alone, such as the edges of a system. nomogram has no
published namespace yet: its prefix maps to ``null``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nomogram.catalog import Catalog
    from nomogram.search import Entry
    from nomogram.semantics import ExternalMatch, QuantityKind
    from nomogram.systems import System

__all__ = ["FORMAT", "kind_graph", "system_graph"]

#: Name and version of the node-link conventions the documents follow.
FORMAT = "protee-node-link/0"

_PREFIXES: Mapping[str, str | None] = {
    "qudt": "http://qudt.org/schema/qudt/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "wikibase": "http://wikiba.se/ontology#",
    "nomogram": None,
}

_WIKIDATA = "http://www.wikidata.org/entity/"
#: The SI Digital Framework of the BIPM, the target of QUDT's siExactMatch.
_SI_FRAMEWORK = "https://si-digital-framework.org/"

#: Declared values, by attribute and value: where it applies, label and
#: description.
_VOCABULARY: Mapping[str, Mapping[str, dict[str, Any]]] = {
    "type": {
        "qudt:QuantityKind": {"on": "node", "label": "quantity kind"},
        "nomogram:cfStandardName": {
            "on": "node",
            "label": "CF standard name",
            "description": "a standard name of the CF conventions",
        },
        "wikibase:Item": {"on": "node", "label": "Wikidata item"},
        "skos:Concept": {"on": "node", "label": "external concept"},
        "nomogram:equation": {
            "on": "node",
            "label": "equation",
            "description": "a formulation of the catalog, giving one variable",
        },
        "nomogram:variable": {"on": "node", "label": "variable"},
        "qudt:specializationOf": {"on": "edge", "label": "specializes"},
        "skos:exactMatch": {"on": "edge", "label": "exact match", "symmetric": True},
        "skos:closeMatch": {"on": "edge", "label": "close match", "symmetric": True},
        "skos:broadMatch": {"on": "edge", "label": "broad match"},
        "skos:narrowMatch": {"on": "edge", "label": "narrow match"},
        "nomogram:gives": {
            "on": "edge",
            "label": "gives",
            "description": "from an equation to the variable it gives",
        },
        "nomogram:reads": {
            "on": "edge",
            "label": "reads",
            "description": "from a variable to an equation that takes it",
        },
    },
    "origin": {
        "qudt": {"on": "node", "label": "QUDT kind"},
        "nomogram": {
            "on": "node",
            "label": "nomogram kind",
            "description": (
                "a kind QUDT lacks, declared by nomogram as a specialization "
                "of a QUDT kind"
            ),
        },
        "provisional": {
            "on": "node",
            "label": "provisional kind",
            "description": (
                "a kind with no QUDT kind to specialize, admitted while a "
                "pull request adding it to QUDT is open"
            ),
        },
    },
    "role": {
        "nomogram:input": {
            "on": "node",
            "label": "input",
            "description": "a variable no equation gives",
        },
        "nomogram:unknown": {
            "on": "node",
            "label": "unknown",
            "description": (
                "a variable read before the equation that gives it: what the "
                "source iterates on"
            ),
        },
        "nomogram:intermediate": {
            "on": "node",
            "label": "intermediate",
            "description": "a variable given by an equation and read only after it",
        },
        "nomogram:closing": {
            "on": "edge",
            "label": "closes a loop",
            "description": (
                "a read of a variable by an equation that comes before the "
                "equation giving it, or is that equation: what the source "
                "iterates on"
            ),
        },
    },
}

_RELATIONS = {
    "exact": "skos:exactMatch",
    "close": "skos:closeMatch",
    "broad": "skos:broadMatch",
    "narrow": "skos:narrowMatch",
}


def kind_graph(
    kinds: str | Entry | Iterable[str | Entry] | None = None,
    *,
    catalog: Catalog | None = None,
    matches: bool = True,
) -> dict[str, Any]:
    """The tree of quantity kinds, as a node-link document.

    Parameters
    ----------
    kinds : str, Entry, iterable of them, or None
        The kinds to draw: names (``"RelativeHumidity"``), references
        (``"kinds.RelativeHumidity"``) or entries a search found
        (``catalog().search(kind="*humidity*", section="kinds")``); all the kinds of the
        catalog by default. The kinds they specialize, directly or not, are
        added, as far as the catalog holds them, so that the tree is
        connected.
    catalog : Catalog, optional
        The catalog; the bundled one by default.
    matches : bool
        Also draw the matches of each kind in external vocabularies, as
        nodes whose ``id`` is their IRI, linked by their SKOS relation and
        the date of their last verification (``verified``): a CF standard
        name, labelled by its name; a Wikidata item, by its identifier; a
        quantity of the SI Digital Framework, by its code (``PRES``).

    Returns
    -------
    dict
        The document (see the module docstring). A kind node has its
        reference as ``id``, its label, the type ``qudt:QuantityKind``, its
        ``origin`` (``qudt``, ``nomogram`` or ``provisional``), its
        ``family`` if a family of the catalog declares it, its ``iri`` if
        QUDT has one, and ``pending``, the pull request to QUDT, if it is
        provisional.

    Raises
    ------
    KeyError
        For a kind the catalog does not have.
    ValueError
        For an entry of another section than the kinds.
    TypeError
        For a kind given as anything else than a name, a reference or an
        entry.
    """
    found = _catalog(catalog)
    names = _kind_names(kinds, found)
    wanted = set(names)
    for name in names:
        parent = found.kinds[name].specialization_of
        while parent is not None and parent in found.kinds and parent not in wanted:
            wanted.add(parent)
            parent = found.kinds[parent].specialization_of
    families = {
        kind: family
        for family, entry in reversed(list(found.families.items()))
        for kind in entry.contents["kinds"]
    }
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    external: dict[str, dict[str, Any]] = {}
    for name, kind in found.kinds.items():
        if name not in wanted:
            continue
        nodes.append(_kind_node(name, kind, families.get(name)))
        if kind.specialization_of in wanted:
            edges.append(
                {
                    "source": f"kinds.{name}",
                    "target": f"kinds.{kind.specialization_of}",
                    "type": "qudt:specializationOf",
                }
            )
        if not matches:
            continue
        for match in kind.matches:
            external.setdefault(match.target, _external_node(match))
            edges.append(
                {
                    "source": f"kinds.{name}",
                    "target": match.target,
                    "type": _RELATIONS[match.relation.value],
                    "verified": match.verified.isoformat(),
                }
            )
    nodes.extend(external.values())
    return _document({}, nodes, edges)


def system_graph(
    system: str | Entry | System, *, catalog: Catalog | None = None
) -> dict[str, Any]:
    """A system of equations, as a node-link document.

    Parameters
    ----------
    system : str, Entry or System
        The system, or its key (``"coare36_surface_layer"``), its reference
        (``"systems.coare36_surface_layer"``) or the entry a search found.
    catalog : Catalog, optional
        The catalog that holds the system named; the bundled one by
        default.

    Returns
    -------
    dict
        The document (see the module docstring), whose ``graph`` also has
        the ``label`` and ``description`` (the note) of the system and its
        ``reference``. The equations come first, in the order the source
        computes them: ``id`` ``equations.<variable given>``, the label and
        the reference (``formulation``) of the formulation, its ``rank`` in
        that order (1 for the first) and ``outside``, if the source's
        practice for its domains is stated. The variables follow, in order
        of first reading: ``id`` ``variables.<name>``, their ``role``
        (``nomogram:input``, ``nomogram:unknown``,
        ``nomogram:intermediate``), the reference of their ``kind``, their
        ``unit`` (its QUDT name) and its symbol (``unit_symbol``), and their
        description. An edge ``nomogram:reads`` goes from a
        variable to each equation that takes it, with the role
        ``nomogram:closing`` where the equation comes before the one giving
        the variable, or is that one (the reads the source iterates); an
        edge ``nomogram:gives`` from an equation to its variable.

    Raises
    ------
    KeyError
        For a system the catalog does not have.
    ValueError
        For an entry of another section than the systems.
    TypeError
        For a system given as anything else than a system, a name, a
        reference or an entry.
    """
    from nomogram.systems import System

    if not isinstance(system, System):
        found = _catalog(catalog)
        key = _key(system, "systems")
        if key not in found.systems:
            msg = f"no system {key!r}"
            raise KeyError(msg)
        system = found.systems[key]
    roles = {
        **dict.fromkeys(system.inputs, "nomogram:input"),
        **dict.fromkeys(system.intermediates, "nomogram:intermediate"),
        **dict.fromkeys(system.unknowns, "nomogram:unknown"),
    }
    giver = {e.output: rank for rank, e in enumerate(system.equations, start=1)}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    variables: dict[str, dict[str, Any]] = {}
    for rank, equation in enumerate(system.equations, start=1):
        formulation = equation.formulation
        node: dict[str, Any] = {
            "id": f"equations.{equation.output}",
            "label": formulation.label,
            "type": "nomogram:equation",
            "rank": rank,
            "formulation": f"formulations.{formulation.key}",
        }
        if equation.outside is not None:
            node["outside"] = equation.outside
        nodes.append(node)
        for name in (*equation.reads, equation.output):
            if name not in variables:
                variables[name] = _variable_node(system, name, roles[name])
        for name in equation.reads:
            edge = {
                "source": f"variables.{name}",
                "target": f"equations.{equation.output}",
                "type": "nomogram:reads",
            }
            if giver.get(name, 0) >= rank:
                edge["role"] = "nomogram:closing"
            edges.append(edge)
        edges.append(
            {
                "source": f"equations.{equation.output}",
                "target": f"variables.{equation.output}",
                "type": "nomogram:gives",
            }
        )
    nodes.extend(variables.values())
    header: dict[str, Any] = {"label": system.label}
    if system.note:
        header["description"] = system.note
    if system.reference is not None:
        header["reference"] = f"references.{system.reference}"
    return _document(header, nodes, edges)


def _catalog(catalog: Catalog | None) -> Catalog:
    """The catalog given, or the bundled one."""
    if catalog is not None:
        return catalog
    from nomogram.catalog import catalog as bundled

    return bundled()


def _key(entry: str | Entry, section: str) -> str:
    """The key of an entry of a section, given as a key, a reference or an Entry."""
    from nomogram.search import Entry

    value: object = entry  # checked at run time, whatever the caller passes
    if isinstance(value, Entry):
        if value.section != section:
            msg = f"{value.ref} is not an entry of {section}"
            raise ValueError(msg)
        return value.key
    if isinstance(value, str):
        return value.removeprefix(f"{section}.")
    msg = f"expected a key, a reference '{section}.key' or an Entry, not {type(value).__name__}"
    raise TypeError(msg)


def _kind_names(
    kinds: str | Entry | Iterable[str | Entry] | None, catalog: Catalog
) -> list[str]:
    """The names of the kinds asked, checked, in the order given."""
    from nomogram.search import Entry

    if kinds is None:
        return list(catalog.kinds)
    given = [kinds] if isinstance(kinds, str | Entry) else list(kinds)
    names = [_key(item, "kinds") for item in given]
    missing = [name for name in names if name not in catalog.kinds]
    if missing:
        msg = f"no quantity kind {', '.join(repr(name) for name in missing)}"
        raise KeyError(msg)
    return names


def _kind_node(name: str, kind: QuantityKind, family: str | None) -> dict[str, Any]:
    """The node of a quantity kind."""
    node: dict[str, Any] = {
        "id": f"kinds.{name}",
        "label": kind.label,
        "type": "qudt:QuantityKind",
        "origin": kind.origin,
    }
    if family is not None:
        node["family"] = family
    if kind.iri:
        node["iri"] = kind.iri
    if kind.pending is not None:
        node["pending"] = kind.pending.pull_request
    return node


def _external_node(match: ExternalMatch) -> dict[str, Any]:
    """The node of an external entity: its IRI as ``id``, a short label."""
    from nomogram.semantics import CF_NAMESPACE

    target = match.target
    if target.startswith(CF_NAMESPACE):
        label, kind = (
            target.removeprefix(CF_NAMESPACE).rstrip("/"),
            "nomogram:cfStandardName",
        )
    elif target.startswith(_WIKIDATA):
        label, kind = target.removeprefix(_WIKIDATA), "wikibase:Item"
    elif target.startswith(_SI_FRAMEWORK):
        # The quantity or unit of the SI Digital Framework, by its code:
        # PRES, kelvin.
        label, kind = target.rstrip("/").rsplit("/", 1)[-1], "skos:Concept"
    else:
        label, kind = target, "skos:Concept"
    return {"id": target, "label": label, "type": kind, "iri": target}


def _variable_node(system: System, name: str, role: str) -> dict[str, Any]:
    """The node of a variable of a system."""
    from nomogram.semantics import semantic_catalog

    variable = system.variable(name)
    node: dict[str, Any] = {
        "id": f"variables.{name}",
        "label": name,
        "type": "nomogram:variable",
        "role": role,
        "kind": f"kinds.{variable.kind}",
        "unit": variable.unit,
        "unit_symbol": semantic_catalog().units[variable.unit].symbol,
    }
    if variable.description:
        node["description"] = variable.description
    return node


def _document(
    header: Mapping[str, Any],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """The node-link document: edges in the order of NetworkX, with their keys;
    prefixes and vocabulary used."""
    from nomogram import __version__

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {n["id"]: {} for n in nodes}
    for edge in edges:
        grouped[edge["source"]].setdefault(edge["target"], []).append(edge)
    edges = [
        {"source": source, "target": target, "key": key}
        | {k: v for k, v in edge.items() if k not in {"source", "target"}}
        for source, targets in grouped.items()
        for target, parallel in targets.items()
        for key, edge in enumerate(parallel)
    ]
    used = {
        attribute: [
            value
            for value in values
            if any(item.get(attribute) == value for item in (*nodes, *edges))
        ]
        for attribute, values in _VOCABULARY.items()
    }
    vocabulary = {
        attribute: [{"id": value, **_VOCABULARY[attribute][value]} for value in values]
        for attribute, values in used.items()
        if values
    }
    prefixes = {
        value.split(":", 1)[0]
        for values in used.values()
        for value in values
        if ":" in value
    }
    return {
        "directed": True,
        "multigraph": True,
        "graph": {
            "format": FORMAT,
            "producer": {"name": "nomogram", "version": __version__},
            "language": "en",
            **header,
            "prefixes": {
                prefix: iri
                for prefix, iri in _PREFIXES.items()
                if prefix in prefixes or prefix == "nomogram"
            },
            "vocabulary": vocabulary,
        },
        "nodes": nodes,
        "edges": edges,
    }
