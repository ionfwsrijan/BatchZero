"""End-to-end test for the agent layer.

Runs the full four-role mock investigation once against an isolated tenant and
asserts the *investigative* outcome plus the provenance guarantees:

  * all four roles ran, in protocol order, with a handoff chain,
  * the microgreens hypothesis is confirmed and the lettuce decoy is refuted,
  * every supporting evidence item is attributed to a real tool call,
  * a recall is drafted for the implicated lot and action tasks are filed.
"""

from __future__ import annotations

import asyncio

import pytest

from batchzero.agent import ROLES, route_role, run_investigation
from batchzero.db import GraphDB
from batchzero.seed import seed_ops_tenant

TENANT = "batchzero_agent_test"


@pytest.fixture(scope="module")
def run():
    db = GraphDB(TENANT)
    db.delete_graph()
    seed_ops_tenant(db)
    return db, asyncio.run(run_investigation(db, tenant=TENANT))


def _hyps(state):
    return state["hypotheses"]


def test_all_roles_run_in_protocol_order(run):
    _db, res = run
    assert [r.role for r in res.roles] == ROLES
    assert all(r.content for r in res.roles), "every role produces a brief"
    assert res.tool_calls >= 40


def test_main_hypothesis_confirmed_and_decoy_refuted(run):
    _db, res = run
    by_status = {h["status"]: h for h in _hyps(res.state)}
    assert by_status["confirmed"]["confidence"] >= 0.9
    assert "MG-4417" in by_status["confirmed"]["statement"]
    assert by_status["refuted"]["confidence"] <= 0.1
    assert "LET-2210" in by_status["refuted"]["statement"]


def test_supporting_evidence_is_tool_attributed(run):
    _db, res = run
    confirmed = next(h for h in _hyps(res.state) if h["status"] == "confirmed")
    support = [e for e in confirmed["supporting"] if e.get("evidence_id")]
    assert len(support) >= 4
    assert all(e.get("tool") for e in support), "every evidence item cites a tool"


def test_recall_and_tasks_filed(run):
    _db, res = run
    lots = {lot for r in res.state["recalls"] for lot in r["lots"]}
    assert "MG-4417" in lots
    assert len(res.state["tasks"]) >= 3


def test_session_handoff_chain(run):
    _db, res = run
    sessions = res.state["sessions"]
    assert len(sessions) == len(ROLES)
    handoffs = [s for s in sessions if s.get("handed_to")]
    assert len(handoffs) == len(ROLES) - 1
    assert sessions[-1].get("handed_to") in (None, "")


def test_brief_names_the_source(run):
    _db, res = run
    assert "MG-4417" in res.brief
    assert "GreenLeaf" in res.brief


def test_events_stream_has_lifecycle_and_tool_provenance(run):
    _db, res = run
    events = [e for r in res.roles for e in r.events]
    kinds = {e["type"] for e in events}
    assert {"role_start", "role_end", "tool"} <= kinds
    tool_events = [e for e in events if e["type"] == "tool"]
    assert all(e["tool_call_id"].startswith("TC") for e in tool_events)


def test_followup_router_picks_the_right_role():
    assert route_role("walk the cold chain for this lot") == "tracer"
    assert route_role("what did the genomics say?") == "cluster"
    assert route_role("compile the decision brief and the institutional fact") == "briefing"
