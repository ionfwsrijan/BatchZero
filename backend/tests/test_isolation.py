"""Tenant isolation: each agency is a separate FalkorDB graph key.

The README claims a session can never read across tenants. This suite proves the
storage half of that claim on a live FalkorDB:

  * seeding the same fixture into two tenants is deterministic,
  * an investigation written to one tenant leaves the other byte-for-byte
    unchanged and creates no nodes in it,
  * both tenants stay independently addressable.
"""

from __future__ import annotations

import asyncio

import pytest

from batchzero.agent import run_investigation
from batchzero.db import GraphDB
from batchzero.seed import seed_ops_tenant

WRITER = "batchzero_isolation_writer"
READER = "batchzero_isolation_reader"


@pytest.fixture(scope="module")
def tenants():
    writer = GraphDB(WRITER)
    writer.delete_graph()
    seed_ops_tenant(writer)
    seeded_writer = writer.stats()

    reader = GraphDB(READER)
    reader.delete_graph()
    seed_ops_tenant(reader)
    seeded_reader = reader.stats()

    run = asyncio.run(run_investigation(writer, tenant=WRITER, roles=["intake", "cluster"]))
    return writer, reader, seeded_writer, seeded_reader, run


def test_seed_is_deterministic_across_tenants(tenants):
    _writer, _reader, seeded_writer, seeded_reader, _run = tenants
    shape = lambda stats: (stats["nodes"], stats["relationships"])  # noqa: E731
    assert shape(seeded_writer) == shape(seeded_reader)
    assert seeded_writer["nodes"] > 0
    assert seeded_writer["relationships"] > 0


def test_investigation_only_writes_to_its_own_tenant(tenants):
    writer, reader, seeded_writer, seeded_reader, run = tenants

    assert writer.node_count() > seeded_writer["nodes"], "the run should add provenance nodes"
    assert (reader.node_count(), reader.rel_count()) == (
        seeded_reader["nodes"],
        seeded_reader["relationships"],
    ), "the other tenant must not change at all"

    query = "MATCH (i:Investigation {inv_id:$inv_id}) RETURN count(i) AS c"
    written = writer.ro_query(query, {"inv_id": run.inv_id}).first()["c"]
    leaked = reader.ro_query(query, {"inv_id": run.inv_id}).first()["c"]
    assert written == 1
    assert leaked == 0


def test_both_tenants_stay_addressable(tenants):
    writer, reader, _seeded_writer, _seeded_reader, _run = tenants
    graphs = set(writer.list_graphs())
    assert {WRITER, READER} <= graphs
    assert writer.graph_name == WRITER
    assert reader.graph_name == READER
