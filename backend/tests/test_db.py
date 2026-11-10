"""Unit tests for result normalization — no live graph required.

FalkorDB returns nodes, edges and temporal values that are not JSON-friendly.
``_serialize`` is the single choke point that turns them into plain data for the
API and the UI, so it is worth testing directly.
"""

from __future__ import annotations

import datetime as dt

from falkordb.edge import Edge
from falkordb.node import Node

from batchzero.db import QueryResult, _serialize


def test_query_result_helpers():
    res = QueryResult(
        columns=["lot_id"],
        rows=[{"lot_id": "MG-4417"}, {"lot_id": "LET-2210"}],
        ms=1.25,
        graph="pmph_ops",
        query="MATCH (l:Lot) RETURN l.lot_id AS lot_id",
    )
    assert len(res) == 2
    assert res.first() == {"lot_id": "MG-4417"}
    assert res.scalars("lot_id") == ["MG-4417", "LET-2210"]
    assert res.scalars("missing") == [None, None]


def test_empty_query_result():
    res = QueryResult(columns=[], rows=[], ms=0.0, graph="pmph_ops", query="RETURN 1")
    assert len(res) == 0
    assert res.first() is None


def test_serialize_temporal_values_are_iso_strings():
    assert _serialize(dt.date(2026, 11, 10)) == "2026-11-10"
    assert _serialize(dt.datetime(2026, 11, 10, 8, 30)) == "2026-11-10T08:30:00"
    assert _serialize(dt.time(8, 30)) == "08:30:00"


def test_serialize_recurses_into_lists_and_dicts():
    when = dt.date(2026, 11, 10)
    assert _serialize([when, {"onset": when, "n": 3}]) == [
        "2026-11-10",
        {"onset": "2026-11-10", "n": 3},
    ]
    assert _serialize({"nested": [1, 2]}) == {"nested": [1, 2]}
    assert _serialize("MG-4417") == "MG-4417"
    assert _serialize(None) is None


def test_serialize_nodes_and_edges_keep_ids_and_properties():
    node = Node(node_id=7, labels=["Lot"], properties={"lot_id": "MG-4417"})
    assert _serialize(node) == {
        "_type": "node",
        "id": 7,
        "labels": ["Lot"],
        "lot_id": "MG-4417",
    }

    edge = Edge(src_node=7, relation="SUPPLIED_BY", dest_node=9, edge_id=12)
    serialized = _serialize(edge)
    assert serialized["_type"] == "edge"
    assert serialized["id"] == 12
    assert serialized["type"] == "SUPPLIED_BY"
    assert serialized["src"] == 7 and serialized["dst"] == 9
