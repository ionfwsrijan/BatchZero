"""Memory & navigation queries: semantic recall, subgraph extraction, state.

Implements the memory side of the agent: distilled facts, prior incidents, and
the ability to pull the investigation sub-graph the frontend renders. FalkorDB's
traversals are the retrieval mechanism — there is no separate vector store.
"""

from __future__ import annotations

from typing import Any

from ..db import GraphDB
from .base import QueryOutcome, run_read


def search_entities(db: GraphDB, query: str, limit: int = 15) -> QueryOutcome:
    """Fuzzy-ish entity lookup across the main labels (name / ids / summaries)."""
    cypher = (
        "MATCH (n) "
        "WHERE (n.name CONTAINS $q) OR (n.case_id CONTAINS $q) "
        "   OR (n.lot_id CONTAINS $q) OR (n.facility_id CONTAINS $q) "
        "   OR (n.supplier_id CONTAINS $q) OR (n.isolate_id CONTAINS $q) "
        "   OR (n.summary CONTAINS $q) OR (n.statement CONTAINS $q) "
        "RETURN labels(n)[0] AS label, id(n) AS node_id, "
        "       coalesce(n.name, n.case_id, n.lot_id, n.facility_id, "
        "                n.supplier_id, n.isolate_id, n.statement) AS ident, "
        "       n.pathogen AS pathogen "
        "LIMIT $limit"
    )
    return run_read(db, f"search '{query}'", cypher, {"q": query, "limit": limit})


def recall_facts(db: GraphDB, query: str) -> QueryOutcome:
    """Semantic memory: search distilled Fact nodes (what the agency already knows)."""
    cypher = (
        "MATCH (f:Fact) "
        "WHERE f.statement CONTAINS $q OR f.kind CONTAINS $q "
        "OPTIONAL MATCH (f)-[:FACT_ABOUT]->(about) "
        "OPTIONAL MATCH (f)-[:FACT_SUPPORTED_BY]->(e:Evidence) "
        "RETURN f.fact_id AS fact_id, f.statement AS statement, "
        "       f.kind AS kind, f.confidence AS confidence, "
        "       labels(about)[0] AS about_label, "
        "       coalesce(about.name, about.supplier_id, about.lot_id) AS about, "
        "       collect(e.summary) AS supporting_evidence "
        "LIMIT 10"
    )
    return run_read(db, f"recall facts '{query}'", cypher, {"q": query.upper() if query.isupper() else query})


def prior_incidents(db: GraphDB, entity_name: str) -> QueryOutcome:
    """Episodic history: past incidents involving a supplier or facility name."""
    cypher = (
        "MATCH (s)-[:IMPLICATED_IN]->(pi:PriorIncident) "
        "WHERE s.name = $name OR s.supplier_id = $name "
        "OPTIONAL MATCH (p:Person)-[:WORKED_ON]->(pi) "
        "RETURN labels(s)[0] AS entity_label, s.name AS entity, "
        "       pi.incident_id AS incident_id, pi.year AS year, "
        "       pi.summary AS summary, pi.outcome AS outcome, "
        "       collect(p.name) AS investigators"
    )
    return run_read(db, f"prior incidents '{entity_name}'", cypher, {"name": entity_name})


def subgraph(
    db: GraphDB, root_node_ids: list[int], hops: int = 2, limit: int = 250
) -> dict[str, Any]:
    """Extract a bounded sub-graph around the given nodes, for the canvas.

    Two traversals: first collect nodes within ``hops`` of any root, then pull
    every relationship whose endpoints both landed in that set. Returns plain
    node/edge dicts ready for cytoscape.js.
    """
    node_res = db.ro_query(
        "MATCH (root) WHERE id(root) IN $roots "
        f"MATCH path = (root)-[*1..{hops}]-(n) "
        "UNWIND nodes(path) AS node "
        "WITH DISTINCT node LIMIT $limit "
        "RETURN id(node) AS id, labels(node) AS labels, node AS props",
        {"roots": root_node_ids, "limit": limit},
    )
    node_ids = [row["id"] for row in node_res.rows]
    if not node_ids:
        return {"nodes": [], "edges": [], "ms": node_res.ms, "roots": root_node_ids}

    edge_res = db.ro_query(
        "MATCH (a)-[r]->(b) WHERE id(a) IN $ids AND id(b) IN $ids "
        "RETURN id(r) AS id, id(a) AS source, id(b) AS target, "
        "       type(r) AS type, r AS props",
        {"ids": node_ids},
    )

    from ..db import _serialize

    nodes = []
    for row in node_res.rows:
        props = row["props"] if isinstance(row["props"], dict) else _serialize(row["props"])
        nodes.append({"id": row["id"], "labels": row["labels"], "props": props})
    edges = [
        {
            "id": row["id"],
            "source": row["source"],
            "target": row["target"],
            "type": row["type"],
            "props": row["props"] if isinstance(row["props"], dict) else _serialize(row["props"]),
        }
        for row in edge_res.rows
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "ms": round(node_res.ms + edge_res.ms, 3),
        "roots": root_node_ids,
        "truncated": len(node_ids) >= limit,
    }


# ------------------------------------------------------------- investigation IO
def list_investigations(db: GraphDB) -> QueryOutcome:
    cypher = (
        "MATCH (i:Investigation) "
        "OPTIONAL MATCH (i)-[:INCLUDES]->(c:Case) "
        "OPTIONAL MATCH (i)-[:HAS_HYPOTHESIS]->(h:Hypothesis) "
        "RETURN i.inv_id AS inv_id, i.title AS title, i.status AS status, "
        "       i.stage AS stage, i.opened AS opened, i.priority AS priority, "
        "       count(DISTINCT c) AS cases, count(DISTINCT h) AS hypotheses "
        "ORDER BY i.opened DESC"
    )
    return run_read(db, "investigations", cypher)


def investigation_digest(db: GraphDB, inv_id: str) -> dict[str, Any]:
    """A compact, context-friendly view of an investigation.

    Meant to be handed to the agent (and re-read repeatedly), so it stays small:
    hypothesis ids/statements/status, evidence summaries, task and recall headers,
    session/handoff chain, and counters — never the full tool-call firehose.
    """
    inv = run_read(
        db,
        "investigation header",
        "MATCH (i:Investigation {inv_id:$inv_id}) "
        "OPTIONAL MATCH (i)-[:INCLUDES]->(c:Case) "
        "RETURN i.inv_id AS inv_id, i.title AS title, i.status AS status, "
        "       i.stage AS stage, i.priority AS priority, i.summary AS summary, "
        "       count(DISTINCT c) AS cases",
        {"inv_id": inv_id},
    ).first() or {"inv_id": inv_id}

    hyps = run_read(
        db,
        "hypotheses digest",
        "MATCH (i:Investigation {inv_id:$inv_id})-[:HAS_HYPOTHESIS]->(h:Hypothesis) "
        "OPTIONAL MATCH (h)-[:SUPPORTED_BY]->(e:Evidence) "
        "OPTIONAL MATCH (e)-[:DERIVED_FROM]->(tc:ToolCall) "
        "WITH h, collect(DISTINCT e) AS es, collect(DISTINCT tc) AS tcs "
        "OPTIONAL MATCH (h)-[:CONTRADICTED_BY]->(ce:Evidence) "
        "RETURN h.hyp_id AS hyp_id, h.statement AS statement, h.status AS status, "
        "       h.confidence AS confidence, size(es) AS support_count, "
        "       size([x IN tcs WHERE x IS NOT NULL]) AS support_tools, "
        "       [x IN es WHERE x IS NOT NULL | x.kind] AS support_kinds, "
        "       count(DISTINCT ce) AS contradict_count, h.created AS created "
        "ORDER BY created",
        {"inv_id": inv_id},
    ).rows

    tasks = run_read(
        db,
        "tasks digest",
        "MATCH (i:Investigation {inv_id:$inv_id})-[:HAS_TASK]->(t:Task) "
        "OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(p:Person) "
        "RETURN t.task_id AS task_id, t.type AS type, t.instructions AS instructions, "
        "       t.status AS status, p.name AS assigned_to, t.created AS created "
        "ORDER BY created",
        {"inv_id": inv_id},
    ).rows

    recalls = run_read(
        db,
        "recalls digest",
        "MATCH (i:Investigation {inv_id:$inv_id})-[:HAS_RECALL]->(r:Recall) "
        "OPTIONAL MATCH (r)-[:COVERS]->(l:Lot) "
        "RETURN r.recall_id AS recall_id, r.scope AS scope, r.rationale AS rationale, "
        "       r.status AS status, collect(DISTINCT l.lot_id) AS lots, r.created AS created "
        "ORDER BY created",
        {"inv_id": inv_id},
    ).rows

    sessions = run_read(
        db,
        "sessions digest",
        "MATCH (s:Session)-[:BELONGS_TO]->(i:Investigation {inv_id:$inv_id}) "
        "OPTIONAL MATCH (s)-[:AT_STEP]->(ps:ProtocolStep) "
        "OPTIONAL MATCH (s)-[ho:HANDOFF]->(t:Session) "
        "RETURN s.session_id AS session_id, s.role AS role, ps.name AS protocol_step, "
        "       t.session_id AS handed_to, ho.reason AS handoff_reason, s.started AS started "
        "ORDER BY started",
        {"inv_id": inv_id},
    ).rows

    return {
        "investigation": inv,
        "hypotheses": hyps,
        "tasks": tasks,
        "recalls": recalls,
        "sessions": sessions,
    }


def investigation_state(db: GraphDB, inv_id: str) -> dict[str, Any]:
    """Everything about an investigation: cases, hypotheses + evidence, tasks,
    recalls, sessions + tool calls, active protocol step."""
    inv = run_read(
        db,
        "investigation header",
        "MATCH (i:Investigation {inv_id:$inv_id}) "
        "OPTIONAL MATCH (i)-[:INCLUDES]->(c:Case)<-[:HAS_CASE]-(p:Person) "
        "RETURN i.inv_id AS inv_id, i.title AS title, i.status AS status, "
        "       i.stage AS stage, i.opened AS opened, i.priority AS priority, "
        "       i.summary AS summary, "
        "       collect(DISTINCT CASE WHEN c IS NULL THEN NULL ELSE "
        "         {case_id: c.case_id, person: p.name, "
        "          onset: c.onset, pathogen: c.pathogen} END) AS cases",
        {"inv_id": inv_id},
    ).first() or {}

    hyps = run_read(
        db,
        "hypotheses",
        "MATCH (i:Investigation {inv_id:$inv_id})-[:HAS_HYPOTHESIS]->(h:Hypothesis) "
        "OPTIONAL MATCH (h)-[:SUPPORTED_BY]->(e:Evidence) "
        "OPTIONAL MATCH (h)-[:CONTRADICTED_BY]->(ce:Evidence) "
        "OPTIONAL MATCH (e)-[:DERIVED_FROM]->(tc:ToolCall) "
        "OPTIONAL MATCH (ce)-[:DERIVED_FROM]->(ct:ToolCall) "
        "RETURN h.hyp_id AS hyp_id, h.statement AS statement, h.status AS status, "
        "       h.confidence AS confidence, "
        "       collect(DISTINCT CASE WHEN e IS NULL THEN NULL ELSE "
        "         {evidence_id: e.evidence_id, kind: e.kind, summary: e.summary, "
        "          weight: e.weight, supports: true, tool: tc.tool} END) AS supporting, "
        "       collect(DISTINCT CASE WHEN ce IS NULL THEN NULL ELSE "
        "         {evidence_id: ce.evidence_id, kind: ce.kind, summary: ce.summary, "
        "          weight: ce.weight, supports: false, tool: ct.tool} END) AS contradicting",
        {"inv_id": inv_id},
    ).rows

    tasks = run_read(
        db,
        "tasks",
        "MATCH (i:Investigation {inv_id:$inv_id})-[:HAS_TASK]->(t:Task) "
        "OPTIONAL MATCH (t)-[:ASSIGNED_TO]->(p:Person) "
        "OPTIONAL MATCH (t)-[:ABOUT]->(about) "
        "RETURN t.task_id AS task_id, t.type AS type, t.instructions AS instructions, "
        "       t.status AS status, t.due AS due, "
        "       p.name AS assigned_to, "
        "       labels(about)[0] AS about_label, "
        "       coalesce(about.name, about.lot_id, about.facility_id, about.supplier_id) AS about "
        "ORDER BY t.created",
        {"inv_id": inv_id},
    ).rows

    recalls = run_read(
        db,
        "recalls",
        "MATCH (i:Investigation {inv_id:$inv_id})-[:HAS_RECALL]->(r:Recall) "
        "OPTIONAL MATCH (r)-[:COVERS]->(l:Lot) "
        "RETURN r.recall_id AS recall_id, r.scope AS scope, r.rationale AS rationale, "
        "       r.status AS status, r.created AS created, "
        "       collect(DISTINCT l.lot_id) AS lots",
        {"inv_id": inv_id},
    ).rows

    sessions = run_read(
        db,
        "sessions",
        "MATCH (s:Session)-[:BELONGS_TO]->(i:Investigation {inv_id:$inv_id}) "
        "OPTIONAL MATCH (s)-[:AT_STEP]->(ps:ProtocolStep) "
        "OPTIONAL MATCH (s)-[ho:HANDOFF]->(t:Session) "
        "RETURN s.session_id AS session_id, s.role AS role, s.started AS started, "
        "       s.summary AS summary, ps.name AS protocol_step, "
        "       t.session_id AS handed_to, ho.reason AS handoff_reason "
        "ORDER BY s.started",
        {"inv_id": inv_id},
    ).rows

    tool_calls = run_read(
        db,
        "tool calls",
        "MATCH (tc:ToolCall)-[:LOGGED]->(s:Session)-[:BELONGS_TO]->(:Investigation {inv_id:$inv_id}) "
        "RETURN tc.tool AS tool, tc.args AS args, tc.result_summary AS result_summary, "
        "       tc.ms AS ms, tc.at AS at, tc.session_id AS session_id "
        "ORDER BY tc.at",
        {"inv_id": inv_id},
    ).rows

    return {
        "investigation": inv,
        "hypotheses": hyps,
        "tasks": tasks,
        "recalls": recalls,
        "sessions": sessions,
        "tool_calls": tool_calls,
    }


def graph_stats(db: GraphDB) -> dict[str, Any]:
    labels = run_read(
        db,
        "label counts",
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC",
    ).rows
    rels = run_read(
        db,
        "relationship counts",
        "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC",
    ).rows
    return {
        "graph": db.graph_name,
        "nodes": sum(r["count"] for r in labels),
        "relationships": sum(r["count"] for r in rels),
        "labels": labels,
        "relationship_types": rels,
    }
