# SPDX-FileCopyrightText: 2026 Miki
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the node-link documents of nomogram.graph."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

import nomogram
from nomogram.catalog import catalog
from nomogram.graph import FORMAT, kind_graph, system_graph


def _deviations(document: dict[str, Any]) -> list[str]:
    """The deviations of a document from the rules of protee-node-link/0."""
    found: list[str] = []
    if document["directed"] is not True or not isinstance(document["multigraph"], bool):
        found.append("directed, multigraph")
    graph = document["graph"]
    if graph["format"] != FORMAT:
        found.append("format")
    prefixes = graph.get("prefixes", {})
    declared: dict[str, dict[str, str]] = {}
    for attribute, values in graph.get("vocabulary", {}).items():
        declared[attribute] = {}
        for value in values:
            if not {"id", "on", "label"} <= set(value) or value["on"] not in {
                "node",
                "edge",
            }:
                found.append(f"vocabulary {attribute}: {value}")
            if ":" in value["id"] and value["id"].split(":", 1)[0] not in prefixes:
                found.append(f"undeclared prefix: {value['id']}")
            if "symmetric" in value and value["on"] != "edge":
                found.append(f"symmetric node value: {value['id']}")
            declared[attribute][value["id"]] = value["on"]
    ids = [node["id"] for node in document["nodes"]]
    if len(ids) != len(set(ids)):
        found.append("duplicate id")
    pairs: set[tuple[str, str, int]] = set()
    for on, items in (("node", document["nodes"]), ("edge", document["edges"])):
        for item in items:
            for attribute, values in declared.items():
                if attribute in item and values.get(item[attribute]) != on:
                    found.append(f"{on} {attribute}={item[attribute]} undeclared")
            if any(value is None for value in item.values()):
                found.append(f"null in {item}")
    for edge in document["edges"]:
        if edge["source"] not in ids or edge["target"] not in ids:
            found.append(f"edge to no node: {edge}")
        pair = (edge["source"], edge["target"], edge["key"])
        if pair in pairs:
            found.append(f"duplicate key: {pair}")
        pairs.add(pair)
    json.dumps(document, allow_nan=False)
    return found


def test_kind_graph_of_a_branch() -> None:
    document = kind_graph(["RelativeHumidity", "RelativeHumidityWithRespectToIce"])
    assert _deviations(document) == []
    graph = document["graph"]
    assert graph["producer"] == {"name": "nomogram", "version": nomogram.__version__}
    assert graph["language"] == "en"
    assert graph["prefixes"] == {
        "qudt": "http://qudt.org/schema/qudt/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "wikibase": "http://wikiba.se/ontology#",
        "nomogram": None,
    }
    assert [v["id"] for v in graph["vocabulary"]["origin"]] == ["qudt", "nomogram"]
    cf = "http://vocab.nerc.ac.uk/standard_name/relative_humidity/"
    wikidata = "http://www.wikidata.org/entity/Q2499617"
    assert document["nodes"] == [
        {
            "id": "kinds.RelativeHumidity",
            "label": "Relative Humidity",
            "type": "qudt:QuantityKind",
            "origin": "qudt",
            "iri": "http://qudt.org/vocab/quantitykind/RelativeHumidity",
        },
        {
            "id": "kinds.RelativePartialPressure",
            "label": "Relative Partial Pressure",
            "type": "qudt:QuantityKind",
            "origin": "qudt",
            "iri": "http://qudt.org/vocab/quantitykind/RelativePartialPressure",
        },
        {
            "id": "kinds.RelativeHumidityWithRespectToIce",
            "label": "Relative Humidity with respect to Ice",
            "type": "qudt:QuantityKind",
            "origin": "nomogram",
            "family": "moist-air",
        },
        {"id": wikidata, "label": "Q2499617", "type": "wikibase:Item", "iri": wikidata},
        {
            "id": cf,
            "label": "relative_humidity",
            "type": "nomogram:cfStandardName",
            "iri": cf,
        },
    ]
    assert document["edges"] == [
        {
            "source": "kinds.RelativeHumidity",
            "target": "kinds.RelativePartialPressure",
            "key": 0,
            "type": "qudt:specializationOf",
        },
        {
            "source": "kinds.RelativeHumidity",
            "target": wikidata,
            "key": 0,
            "type": "skos:closeMatch",
            "verified": "2026-11-25",
        },
        {
            "source": "kinds.RelativeHumidity",
            "target": cf,
            "key": 0,
            "type": "skos:exactMatch",
            "verified": "2026-11-25",
        },
        {
            "source": "kinds.RelativeHumidityWithRespectToIce",
            "target": "kinds.RelativePartialPressure",
            "key": 0,
            "type": "qudt:specializationOf",
        },
    ]


def test_kind_graph_takes_names_references_and_entries() -> None:
    c = catalog()
    entry = next(e for e in c.search("relative", "humidity") if e.section == "kinds")
    one = kind_graph("RelativeHumidity")
    assert kind_graph("kinds.RelativeHumidity") == one
    assert kind_graph(entry) == kind_graph(entry.key)
    assert kind_graph(["RelativeHumidity"], catalog=c) == one
    assert [n["id"] for n in one["nodes"][:2]] == [
        "kinds.RelativeHumidity",
        "kinds.RelativePartialPressure",
    ]


def test_kind_graph_refuses_what_is_not_a_kind() -> None:
    formulation = next(
        e for e in catalog().search("magnus") if e.section == "formulations"
    )
    with pytest.raises(ValueError, match="not an entry of kinds"):
        kind_graph(formulation)
    with pytest.raises(KeyError, match="no quantity kind 'Humidness'"):
        kind_graph(["RelativeHumidity", "Humidness"])
    with pytest.raises(TypeError, match="expected a key"):
        kind_graph([3])  # type: ignore[list-item]


def test_kind_graph_without_matches() -> None:
    document = kind_graph(["RelativeHumidity"], matches=False)
    assert _deviations(document) == []
    assert [n["id"] for n in document["nodes"]] == [
        "kinds.RelativeHumidity",
        "kinds.RelativePartialPressure",
    ]
    assert document["graph"]["prefixes"] == {
        "qudt": "http://qudt.org/schema/qudt/",
        "nomogram": None,
    }


def test_kind_graph_of_every_kind() -> None:
    c = catalog()
    document = kind_graph()
    assert _deviations(document) == []
    kinds = [n for n in document["nodes"] if n["type"] == "qudt:QuantityKind"]
    assert [n["id"] for n in kinds] == [f"kinds.{name}" for name in c.kinds]
    assert {"qudt", "nomogram", "provisional"} == {n["origin"] for n in kinds}
    assert all("iri" not in n for n in kinds if n["origin"] != "qudt")
    relations = {e["type"] for e in document["edges"]}
    assert {"skos:exactMatch", "skos:closeMatch", "skos:narrowMatch"} <= relations


def test_a_provisional_kind_gives_its_pull_request() -> None:
    import dataclasses
    import datetime

    from nomogram.graph import _kind_node
    from nomogram.semantics import PendingPullRequest

    # None is left since QUDT 3.5.4: one made from a kind of QUDT.
    pending = PendingPullRequest(
        "https://github.com/qudt/qudt-public-repo/pull/1612", datetime.date(2026, 11, 8)
    )
    kind = dataclasses.replace(
        catalog().kinds["KinematicHeatFlux"],
        origin="provisional",
        iri=None,
        pending=pending,
    )
    node = _kind_node("KinematicHeatFlux", kind, None)
    assert node["origin"] == "provisional"
    assert node["pending"] == pending.pull_request
    assert "iri" not in node


def test_kind_graph_labels_si_quantities_by_their_code() -> None:
    document = kind_graph(["Pressure"])
    si = "https://si-digital-framework.org/quantities/PRES"
    (node,) = [n for n in document["nodes"] if n["id"] == si]
    assert node == {"id": si, "label": "PRES", "type": "skos:Concept", "iri": si}
    (edge,) = [e for e in document["edges"] if e["target"] == si]
    assert edge["type"] == "skos:exactMatch"


def test_kind_graph_labels_other_external_concepts_by_iri() -> None:
    from nomogram.graph import _external_node
    from nomogram.semantics import ExternalMatch, MatchRelation

    iri = "https://example.org/concept/7"
    node = _external_node(
        ExternalMatch(
            iri,
            MatchRelation.CLOSE,
            catalog().kinds["RelativeHumidity"].matches[0].verified,
        )
    )
    assert node == {"id": iri, "label": iri, "type": "skos:Concept", "iri": iri}


def test_system_graph_of_coare() -> None:
    c = catalog()
    system = c.systems["coare36_surface_layer"]
    document = system_graph("coare36_surface_layer")
    assert _deviations(document) == []
    graph = document["graph"]
    assert graph["label"] == system.label
    assert graph["description"] == system.note
    assert graph["reference"] == "references.coare36"
    equations = [n for n in document["nodes"] if n["type"] == "nomogram:equation"]
    variables = [n for n in document["nodes"] if n["type"] == "nomogram:variable"]
    assert document["nodes"] == equations + variables
    assert [n["id"] for n in equations] == [
        f"equations.{e.output}" for e in system.equations
    ]
    assert [n["rank"] for n in equations] == list(range(1, 14))
    assert (
        equations[1]["formulation"]
        == "formulations.edson2013_roughness_length_momentum"
    )
    assert equations[1]["outside"] == "ignore"
    assert "outside" not in equations[0]
    roles = {n["label"]: n["role"] for n in variables}
    assert [name for name, role in roles.items() if role == "nomogram:unknown"] == [
        "u_s",
        "T_s",
        "q_s",
        "alpha",
        "S",
    ]
    assert {name for name, role in roles.items() if role == "nomogram:input"} == set(
        system.inputs
    )
    assert {
        name for name, role in roles.items() if role == "nomogram:intermediate"
    } == set(system.intermediates)
    u_s = next(n for n in variables if n["id"] == "variables.u_s")
    assert u_s["kind"] == "kinds.FrictionVelocity"
    assert u_s["unit"] == "M-PER-SEC"
    assert u_s["unit_symbol"] == "m/s"
    assert u_s["description"]
    reads = [e for e in document["edges"] if e["type"] == "nomogram:reads"]
    gives = [e for e in document["edges"] if e["type"] == "nomogram:gives"]
    assert len(reads) == sum(len(e.reads) for e in system.equations)
    assert [(e["source"], e["target"]) for e in gives] == [
        (f"equations.{e.output}", f"variables.{e.output}") for e in system.equations
    ]
    assert [(v["id"], v["on"]) for v in graph["vocabulary"]["role"]] == [
        ("nomogram:input", "node"),
        ("nomogram:unknown", "node"),
        ("nomogram:intermediate", "node"),
        ("nomogram:closing", "edge"),
    ]
    rank = {e.output: i for i, e in enumerate(system.equations)}
    closing = {
        (name, e.output)
        for i, e in enumerate(system.equations)
        for name in e.reads
        if rank.get(name, -1) >= i
    }
    assert {
        (e["source"].removeprefix("variables."), e["target"].removeprefix("equations."))
        for e in reads
        if e.get("role") == "nomogram:closing"
    } == closing
    assert ("u_s", "L") in closing
    assert ("u_s", "Q_0v") not in closing
    assert {name for name, _ in closing} == set(system.unknowns)


def test_system_graph_takes_a_system_a_reference_or_an_entry() -> None:
    c = catalog()
    document = system_graph("coare36_surface_layer", catalog=c)
    entry = next(e for e in c.search("coare") if e.section == "systems")
    assert system_graph(c.systems["coare36_surface_layer"]) == document
    assert system_graph("systems.coare36_surface_layer") == document
    assert system_graph(entry) == document
    with pytest.raises(KeyError, match="no system 'coare99'"):
        system_graph("coare99")


def test_system_graph_without_note_or_reference() -> None:
    import dataclasses

    system = dataclasses.replace(
        catalog().systems["coare36_surface_layer"], note="", reference=None
    )
    graph = system_graph(system)["graph"]
    assert "description" not in graph
    assert "reference" not in graph


def test_edges_are_grouped_by_source_in_the_order_of_the_nodes() -> None:
    for document in (kind_graph(), system_graph("coare36_surface_layer")):
        rank = {node["id"]: i for i, node in enumerate(document["nodes"])}
        sources = [rank[edge["source"]] for edge in document["edges"]]
        assert sources == sorted(sources)


def test_graphs_guide_code_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    guide = Path(__file__).parents[1] / "docs" / "graphs.md"
    blocks = re.findall(
        r"```python\n(.*?)```", guide.read_text(encoding="utf-8"), re.DOTALL
    )
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {}
    for block in blocks:
        exec(compile(block, str(guide), "exec"), namespace)  # noqa: S102
    shown = re.search(
        r"```json\n(.*?)```", guide.read_text(encoding="utf-8"), re.DOTALL
    )
    assert shown is not None
    assert json.loads("{" + shown.group(1) + "}") == {
        key: namespace["branch"][key]  # type: ignore[index]
        for key in ("nodes", "edges")
    }
    written = json.loads((tmp_path / "coare36.json").read_text(encoding="utf-8"))
    assert written == namespace["coare"]


def test_documents_pass_the_checks_of_protee() -> None:
    # The format belongs to protee (protee-node-link/0): its own check, its
    # JSON schema and its reading and writing back, from the development
    # group, as a consumer of these documents would use them.
    jsonschema = pytest.importorskip("jsonschema")
    node_link = pytest.importorskip("protee.io")
    schema = node_link.node_link_schema()
    for document in (
        kind_graph(),
        kind_graph(["RelativeHumidity", "RelativeHumidityWithRespectToIce"]),
        system_graph("coare36_surface_layer"),
    ):
        assert node_link.check_node_link(document) == ()
        jsonschema.validate(document, schema)
        table = node_link.from_node_link(document)
        written = node_link.to_node_link(
            table.graph,
            table.arcs,
            table.nodes,
            attributes=table.attributes,
            multigraph=table.multigraph,
            ids=table.ids,
        )
        assert written == document
