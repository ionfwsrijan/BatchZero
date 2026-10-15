"""Procedural memory: the standard epidemiological protocol, as a graph.

The protocol is not a prompt. It is a chain of ``ProtocolStep`` nodes joined by
``NEXT`` edges, and each agent session is pinned to a step via ``AT_STEP``. The
agent asks the graph "where am I in the protocol, what comes next" — so the
procedure itself is persistent, inspectable memory, not LLM guesswork.
"""

from __future__ import annotations

from ..db import GraphDB
from .base import QueryOutcome, run_read


def get_protocol(db: GraphDB) -> QueryOutcome:
    """The full ordered protocol with each step's next pointer."""
    cypher = (
        "MATCH (ps:ProtocolStep) "
        "OPTIONAL MATCH (ps)-[:NEXT]->(next:ProtocolStep) "
        "RETURN ps.step_id AS step_id, ps.order AS step_order, ps.name AS name, "
        "       ps.description AS description, next.step_id AS next_step "
        "ORDER BY ps.order"
    )
    return run_read(db, "protocol", cypher)


def first_step(db: GraphDB) -> dict:
    row = run_read(
        db, "first protocol step",
        "MATCH (ps:ProtocolStep) WHERE NOT ()-[:NEXT]->(ps) "
        "RETURN ps.step_id AS step_id, ps.name AS name, ps.description AS description "
        "LIMIT 1",
    ).first()
    return row or {}


def step_detail(db: GraphDB, step_id: str) -> dict:
    cypher = (
        "MATCH (ps:ProtocolStep {step_id:$step_id}) "
        "OPTIONAL MATCH (ps)-[:NEXT]->(next:ProtocolStep) "
        "RETURN ps.step_id AS step_id, ps.order AS step_order, ps.name AS name, "
        "       ps.description AS description, next.step_id AS next_step"
    )
    return run_read(db, f"protocol step {step_id}", cypher, {"step_id": step_id}).first() or {}


def next_step(db: GraphDB, step_id: str) -> dict:
    row = run_read(
        db, "next protocol step",
        "MATCH (ps:ProtocolStep {step_id:$step_id})-[:NEXT]->(n:ProtocolStep) "
        "RETURN n.step_id AS step_id, n.name AS name, n.description AS description",
        {"step_id": step_id},
    ).first()
    return row or {}


def current_session_step(db: GraphDB, session_id: str) -> dict:
    cypher = (
        "MATCH (s:Session {session_id:$sid})-[:AT_STEP]->(ps:ProtocolStep) "
        "OPTIONAL MATCH (ps)-[:NEXT]->(next:ProtocolStep) "
        "RETURN ps.step_id AS step_id, ps.order AS step_order, ps.name AS name, "
        "       ps.description AS description, next.step_id AS next_step"
    )
    return run_read(db, "session step", cypher, {"sid": session_id}).first() or {}
