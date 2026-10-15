"""Integration tests: real MCP server <-> client over stdio.

These spawn ``python -m batchzero.mcp_server`` as an external process, exactly
the way an MCP host (or the BatchZero agent) does, and assert that:
  * the tool-set is role-scoped and carries the patched JSON schemas,
  * tool execution returns payloads with provenance ids,
  * ToolCall nodes land in the graph under the right session.
"""

from __future__ import annotations

import uuid

import pytest

from batchzero.config import get_settings
from batchzero.db import GraphDB
from batchzero.mcp_client import MCPToolSession
from batchzero.queries import actions

pytestmark = pytest.mark.asyncio

TENANT = get_settings().tenant_graph


def _session_id(inv_id: str) -> str:
    session_id = f"ses-test-{uuid.uuid4().hex[:8]}"
    actions.record_session(GraphDB(TENANT), inv_id, session_id, "cluster")
    return session_id


async def test_mcp_stdio_roundtrip_logs_tool_calls():
    inv = actions.open_investigation(GraphDB(TENANT), "MCP roundtrip test", "low")
    session_id = _session_id(inv["inv_id"])

    async with MCPToolSession(
        tenant=TENANT, role="cluster", session_id=session_id,
        investigation_id=inv["inv_id"],
    ) as mcp:
        names = [t["name"] for t in mcp.tools]
        assert "lot_source_ranking" in names
        assert "trace_supply_chain" in names
        assert "draft_recall" not in names, "cluster analyst must not draft recalls"

        # schemas survived the signature patch
        spec = next(t for t in mcp.tools if t["name"] == "list_recent_cases")
        assert "pathogen" in spec["inputSchema"]["properties"]

        res = await mcp.call_tool("list_recent_cases", {"pathogen": "Salmonella"})
        assert res["ok"] is True
        assert res["row_count"] == 11
        assert res["tool_call_id"].startswith("TC")

        res2 = await mcp.call_tool("lot_source_ranking", {})
        assert res2["ok"] is True
        assert any(r.get("lot_id") == "MG-4417" for r in res2["rows"])

        bad = await mcp.call_tool("describe_case", {"case_id": "C-999"})
        assert bad["ok"] is True  # unknown case is an empty result, not a crash

    db = GraphDB(TENANT)
    rows = db.ro_query(
        "MATCH (t:ToolCall)-[:LOGGED]->(s:Session {session_id:$sid}) "
        "RETURN t.tool AS tool, t.tool_call_id AS tcid",
        {"sid": session_id},
    ).rows
    assert {r["tool"] for r in rows} == {"list_recent_cases", "lot_source_ranking", "describe_case"}
    assert all(r["tcid"].startswith("TC") for r in rows)


async def test_role_scoping_differs_between_roles():
    async with MCPToolSession(tenant=TENANT, role="briefing") as mcp:
        names = [t["name"] for t in mcp.tools]
        assert "draft_recall" in names and "create_task" in names
        assert "lot_source_ranking" in names, "the brief cites the genomic chain"
        assert "find_common_ingredients" not in names, "exposure maths is the analyst's job"
        assert "Briefing Officer" in (mcp.instructions or "")


async def test_error_surface_does_not_kill_the_session():
    inv = actions.open_investigation(GraphDB(TENANT), "MCP error surface test", "low")
    async with MCPToolSession(
        tenant=TENANT, role="intake",
        session_id=_session_id(inv["inv_id"]),
        investigation_id=inv["inv_id"],
    ) as mcp:
        bad = await mcp.call_tool("describe_case", {"case_id": 12345})
        assert isinstance(bad, dict)
        after = await mcp.call_tool("list_recent_cases", {})
        assert after["ok"] is True
