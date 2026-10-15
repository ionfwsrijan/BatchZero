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

from batchzero.db import GraphDB
from batchzero.mcp_client import MCPToolSession
from batchzero.queries import actions

pytestmark = pytest.mark.asyncio


def _session_id(tenant: str, inv_id: str) -> str:
    session_id = f"S-{uuid.uuid4().hex[:8]}"
    actions.record_session(GraphDB(tenant), inv_id, session_id, role="intake")
    return session_id


async def test_tools_are_role_scoped(mcp_tenant: str):
    async with MCPToolSession(tenant=mcp_tenant, role="briefing") as mcp:
        names = {t["name"] for t in mcp.tools}
        assert "draft_recall" in names and "create_task" in names
        assert "find_common_ingredients" not in names, "exposure maths is the analyst's job"
        assert "Briefing Officer" in (mcp.instructions or "")


async def test_analyst_cannot_file_a_recall(mcp_tenant: str):
    async with MCPToolSession(tenant=mcp_tenant, role="cluster") as mcp:
        names = {t["name"] for t in mcp.tools}
        assert "draft_recall" not in names
        spec = next(t for t in mcp.tools if t["name"] == "list_recent_cases")
        assert "pathogen" in spec["inputSchema"]["properties"], "schema survives the transport"


async def test_tool_execution_returns_provenance(mcp_tenant: str):
    inv = actions.open_investigation(GraphDB(mcp_tenant), "MCP provenance session", "low")
    async with MCPToolSession(
        tenant=mcp_tenant, role="cluster",
        session_id=_session_id(mcp_tenant, inv["inv_id"]),
        investigation_id=inv["inv_id"],
    ) as mcp:
        res = await mcp.call_tool("list_recent_cases", {"pathogen": "Salmonella"})
        assert res["ok"] is True
        assert res["row_count"] == 11
        assert res["tool_call_id"].startswith("TC")

        ranked = await mcp.call_tool("lot_source_ranking", {})
        assert ranked["ok"] is True
        assert any(r.get("lot_id") == "MG-4417" for r in ranked["rows"])

        bad = await mcp.call_tool("describe_case", {"case_id": "C-999"})
        assert bad["ok"] is True  # unknown case is an empty result, not a crash


async def test_tool_calls_land_under_the_session(mcp_tenant: str):
    inv = actions.open_investigation(GraphDB(mcp_tenant), "MCP log test", "low")
    sid = _session_id(mcp_tenant, inv["inv_id"])
    async with MCPToolSession(
        tenant=mcp_tenant, role="cluster",
        session_id=sid, investigation_id=inv["inv_id"],
    ) as mcp:
        await mcp.call_tool("list_recent_cases", {})
        await mcp.call_tool("lot_source_ranking", {})

    rows = GraphDB(mcp_tenant).ro_query(
        "MATCH (t:ToolCall)-[:LOGGED]->(s:Session {session_id:$sid}) "
        "RETURN t.tool AS tool, t.tool_call_id AS tcid",
        {"sid": sid},
    ).rows
    assert {r["tool"] for r in rows} == {"list_recent_cases", "lot_source_ranking"}
    assert all(r["tcid"].startswith("TC") for r in rows)


async def test_error_surface_does_not_kill_the_session(mcp_tenant: str):
    inv = actions.open_investigation(GraphDB(mcp_tenant), "MCP error surface test", "low")
    async with MCPToolSession(
        tenant=mcp_tenant, role="intake",
        session_id=_session_id(mcp_tenant, inv["inv_id"]),
        investigation_id=inv["inv_id"],
    ) as mcp:
        bad = await mcp.call_tool("describe_case", {"case_id": 12345})
        assert isinstance(bad, dict)
        after = await mcp.call_tool("list_recent_cases", {})
        assert after["ok"] is True
