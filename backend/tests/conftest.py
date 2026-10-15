"""Shared test fixtures.

The graph-algorithm tests (betweenness, label propagation) are sensitive to the
*whole* graph, so they must run against a freshly seeded, isolated tenant rather
than the live ``pmph_ops`` graph that other tests add investigations to.
"""

from __future__ import annotations

import os

# Tests must be deterministic and offline: force the mock provider even if a
# developer's .env points at Groq. Set before importing anything that reads env.
os.environ["LLM_PROVIDER"] = "mock"

import pytest  # noqa: E402

from batchzero.db import GraphDB  # noqa: E402
from batchzero.seed import seed_ops_tenant  # noqa: E402

QUERY_TENANT = "batchzero_query_test"
MCP_TENANT = "batchzero_mcp_test"


@pytest.fixture(scope="session")
def db():
    """A pristine, freshly seeded graph for the query-layer tests."""
    graph = GraphDB(QUERY_TENANT)
    graph.delete_graph()
    seed_ops_tenant(graph)
    return graph


@pytest.fixture(scope="session")
def mcp_tenant():
    """A dedicated tenant for the MCP integration tests (they write to it)."""
    graph = GraphDB(MCP_TENANT)
    graph.delete_graph()
    seed_ops_tenant(graph)
    return MCP_TENANT
