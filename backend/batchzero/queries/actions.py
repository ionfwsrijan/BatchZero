"""Action queries: how the agent writes its investigation back into the graph.

The distinction that matters for explainability: ``log_tool_call`` records every
tool the agent invoked (the audit trail), and ``attach_evidence`` links a finding
to the exact tool call that produced it. So a hypothesis is never an unsupported
claim — it is a chain: Hypothesis -[:SUPPORTED_BY]-> Evidence -[:DERIVED_FROM]-> ToolCall.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..db import GraphDB
from .base import QueryOutcome, run_write

# Primary identifying property per label, for resolving an "about" reference.
PRIMARY_ID = {
    "Lot": "lot_id",
    "Facility": "facility_id",
    "Supplier": "supplier_id",
    "Farm": "farm_id",
    "Shipment": "shipment_id",
    "Ingredient": "ingredient_id",
    "MenuItem": "menu_id",
    "Case": "case_id",
    "Isolate": "isolate_id",
    "Person": "person_id",
    "ExposureEvent": "event_id",
    "WastewaterSite": "site_id",
    "PriorIncident": "incident_id",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


def _resolve_node_id(db: GraphDB, label: str, value: str) -> int | None:
    key = PRIMARY_ID.get(label)
    if not key:
        return None
    row = db.ro_query(
        f"MATCH (n:{label}) WHERE n.{key} = $v RETURN id(n) AS id", {"v": value}
    ).first()
    return row["id"] if row else None


def _is_valid_identifier(value: str) -> bool:
    return bool(value) and value.replace("_", "").replace("-", "").isalnum() and not value[0].isdigit()


# ------------------------------------------------------------- investigations
def open_investigation(
    db: GraphDB, title: str, priority: str = "high", stage: str = "intake",
    inv_id: str | None = None,
) -> dict[str, Any]:
    inv_id = inv_id or _new_id("INV")
    res = run_write(
        db,
        "open investigation",
        "MERGE (i:Investigation {inv_id:$inv_id}) "
        "SET i.title = $title, i.priority = $priority, i.stage = $stage, "
        "    i.status = 'open', i.opened = date($opened) "
        "RETURN i.inv_id AS inv_id, i.title AS title, i.stage AS stage",
        {"inv_id": inv_id, "title": title, "priority": priority, "stage": stage,
         "opened": datetime.now(timezone.utc).date().isoformat()},
    )
    return res.first() or {"inv_id": inv_id}


def set_investigation_stage(db: GraphDB, inv_id: str, stage: str) -> None:
    run_write(
        db, "set stage",
        "MATCH (i:Investigation {inv_id:$inv_id}) SET i.stage = $stage",
        {"inv_id": inv_id, "stage": stage},
    )


def set_investigation_summary(db: GraphDB, inv_id: str, summary: str) -> None:
    run_write(
        db, "set summary",
        "MATCH (i:Investigation {inv_id:$inv_id}) SET i.summary = $summary",
        {"inv_id": inv_id, "summary": summary},
    )


def include_cases(db: GraphDB, inv_id: str, case_ids: list[str]) -> QueryOutcome:
    return run_write(
        db, "include cases",
        "MATCH (i:Investigation {inv_id:$inv_id}) "
        "UNWIND $case_ids AS cid MATCH (c:Case {case_id:cid}) "
        "MERGE (i)-[:INCLUDES]->(c) RETURN count(c) AS linked",
        {"inv_id": inv_id, "case_ids": case_ids},
    )


# ---------------------------------------------------------------- hypotheses
def add_hypothesis(
    db: GraphDB, inv_id: str, statement: str, confidence: float = 0.5,
    hyp_id: str | None = None,
) -> dict[str, Any]:
    hyp_id = hyp_id or _new_id("HYP")
    res = run_write(
        db, "add hypothesis",
        "MATCH (i:Investigation {inv_id:$inv_id}) "
        "MERGE (h:Hypothesis {hyp_id:$hyp_id}) "
        "SET h.statement = $statement, h.confidence = $confidence, "
        "    h.status = 'open', h.created = $created "
        "MERGE (i)-[:HAS_HYPOTHESIS]->(h) "
        "RETURN h.hyp_id AS hyp_id, h.statement AS statement, h.status AS status",
        {"inv_id": inv_id, "hyp_id": hyp_id, "statement": statement,
         "confidence": confidence, "created": _now()},
    )
    return res.first() or {"hyp_id": hyp_id, "statement": statement}


def update_hypothesis(
    db: GraphDB, hyp_id: str, status: str | None = None, confidence: float | None = None,
    statement: str | None = None,
) -> None:
    sets, params = [], {"hyp_id": hyp_id}
    if status is not None:
        sets.append("h.status = $status")
        params["status"] = status
    if confidence is not None:
        sets.append("h.confidence = $confidence")
        params["confidence"] = confidence
    if statement is not None:
        sets.append("h.statement = $statement")
        params["statement"] = statement
    if not sets:
        return
    run_write(
        db, "update hypothesis",
        f"MATCH (h:Hypothesis {{hyp_id:$hyp_id}}) SET {', '.join(sets)}",
        params,
    )


# ------------------------------------------------------------------ evidence
def attach_evidence(
    db: GraphDB, hyp_id: str, kind: str, summary: str,
    supports: bool = True, weight: float = 1.0,
    about_label: str | None = None, about_value: str | None = None,
    tool_call_id: str | None = None, evidence_id: str | None = None,
) -> dict[str, Any]:
    evidence_id = evidence_id or _new_id("EVD")
    rel = "SUPPORTED_BY" if supports else "CONTRADICTED_BY"
    # The evidence node carries an inline about_text so it is legible even if the
    # referenced entity is missing; we additionally wire an ABOUT edge when found.
    run_write(
        db, "create evidence",
        "MATCH (h:Hypothesis {hyp_id:$hyp_id}) "
        "MERGE (e:Evidence {evidence_id:$evidence_id}) "
        "SET e.kind = $kind, e.summary = $summary, e.weight = $weight, "
        "    e.about_label = $about_label, e.about_value = $about_value, "
        "    e.created = $created "
        f"MERGE (h)-[:{rel}]->(e) "
        "RETURN e.evidence_id AS evidence_id",
        {"hyp_id": hyp_id, "evidence_id": evidence_id, "kind": kind,
         "summary": summary, "weight": weight, "about_label": about_label,
         "about_value": about_value, "created": _now()},
    )
    if about_label and about_value:
        node_id = _resolve_node_id(db, about_label, about_value)
        if node_id is not None:
            run_write(
                db, "link evidence about",
                "MATCH (e:Evidence {evidence_id:$eid}), (x) WHERE id(x) = $nid "
                "MERGE (e)-[:ABOUT]->(x)",
                {"eid": evidence_id, "nid": node_id},
            )
    if tool_call_id:
        run_write(
            db, "link evidence to tool call",
            "MATCH (e:Evidence {evidence_id:$eid}), (tc:ToolCall {tool_call_id:$tcid}) "
            "MERGE (e)-[:DERIVED_FROM]->(tc)",
            {"eid": evidence_id, "tcid": tool_call_id},
        )
    return {"evidence_id": evidence_id, "hyp_id": hyp_id, "supports": supports}


# --------------------------------------------------------------------- tasks
def create_task(
    db: GraphDB, inv_id: str, task_type: str, instructions: str,
    about_label: str | None = None, about_value: str | None = None,
    assigned_person_id: str | None = None, due: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    task_id = task_id or _new_id("TSK")
    run_write(
        db, "create task",
        "MATCH (i:Investigation {inv_id:$inv_id}) "
        "MERGE (t:Task {task_id:$task_id}) "
        "SET t.type = $type, t.instructions = $instructions, t.status = 'open', "
        "    t.about_label = $about_label, t.about_value = $about_value, "
        "    t.created = $created, t.due = $due "
        "MERGE (i)-[:HAS_TASK]->(t) RETURN t.task_id AS task_id",
        {"inv_id": inv_id, "task_id": task_id, "type": task_type,
         "instructions": instructions, "about_label": about_label,
         "about_value": about_value, "created": _now(), "due": due},
    )
    if about_label and about_value:
        node_id = _resolve_node_id(db, about_label, about_value)
        if node_id is not None:
            run_write(
                db, "link task about",
                "MATCH (t:Task {task_id:$tid}), (x) WHERE id(x) = $nid "
                "MERGE (t)-[:ABOUT]->(x)",
                {"tid": task_id, "nid": node_id},
            )
    if assigned_person_id:
        node_id = _resolve_node_id(db, "Person", assigned_person_id)
        if node_id is not None:
            run_write(
                db, "assign task",
                "MATCH (t:Task {task_id:$tid}), (p:Person) WHERE id(p) = $nid "
                "MERGE (t)-[:ASSIGNED_TO]->(p)",
                {"tid": task_id, "nid": node_id},
            )
    return {"task_id": task_id, "type": task_type, "instructions": instructions}


def assign_inspectors(db: GraphDB) -> list[str]:
    """List inspectors (people with role='inspector') for task assignment."""
    res = db.ro_query(
        "MATCH (p:Person {role:'inspector'}) RETURN p.person_id AS person_id, p.name AS name"
    )
    return [f"{r['person_id']} ({r['name']})" for r in res.rows]


# ------------------------------------------------------------------- recall
def draft_recall(
    db: GraphDB, inv_id: str, lot_ids: list[str], scope: str, rationale: str,
    recall_id: str | None = None,
) -> dict[str, Any]:
    recall_id = recall_id or _new_id("RCL")
    run_write(
        db, "draft recall",
        "MATCH (i:Investigation {inv_id:$inv_id}) "
        "MERGE (r:Recall {recall_id:$recall_id}) "
        "SET r.scope = $scope, r.rationale = $rationale, r.status = 'drafted', "
        "    r.created = $created "
        "MERGE (i)-[:HAS_RECALL]->(r) "
        "WITH r UNWIND $lot_ids AS lid MATCH (l:Lot {lot_id:lid}) MERGE (r)-[:COVERS]->(l) "
        "RETURN r.recall_id AS recall_id",
        {"inv_id": inv_id, "recall_id": recall_id, "scope": scope,
         "rationale": rationale, "lot_ids": lot_ids, "created": _now()},
    )
    return {"recall_id": recall_id, "lots": lot_ids, "scope": scope}


# ------------------------------------------------------------------- memory
def remember_fact(
    db: GraphDB, statement: str, about_label: str | None = None,
    about_value: str | None = None, confidence: float = 0.8,
    supported_by_evidence: str | None = None, fact_id: str | None = None,
) -> dict[str, Any]:
    fact_id = fact_id or _new_id("FACT")
    run_write(
        db, "remember fact",
        "MERGE (f:Fact {fact_id:$fact_id}) "
        "SET f.statement = $statement, f.kind = 'semantic', "
        "    f.confidence = $confidence, f.created = $created "
        "RETURN f.fact_id AS fact_id",
        {"fact_id": fact_id, "statement": statement, "confidence": confidence,
         "created": _now()},
    )
    if about_label and about_value:
        node_id = _resolve_node_id(db, about_label, about_value)
        if node_id is not None:
            run_write(
                db, "link fact about",
                "MATCH (f:Fact {fact_id:$fid}), (x) WHERE id(x) = $nid "
                "MERGE (f)-[:FACT_ABOUT]->(x)",
                {"fid": fact_id, "nid": node_id},
            )
    if supported_by_evidence:
        run_write(
            db, "link fact evidence",
            "MATCH (f:Fact {fact_id:$fid}), (e:Evidence {evidence_id:$eid}) "
            "MERGE (f)-[:FACT_SUPPORTED_BY]->(e)",
            {"fid": fact_id, "eid": supported_by_evidence},
        )
    return {"fact_id": fact_id, "statement": statement}


# --------------------------------------------------------------- provenance
def record_session(
    db: GraphDB, inv_id: str, session_id: str, role: str,
    summary: str | None = None, protocol_step: str | None = None,
) -> dict[str, Any]:
    run_write(
        db, "record session",
        "MERGE (s:Session {session_id:$session_id}) "
        "SET s.role = $role, s.started = $started, s.summary = $summary "
        "WITH s "
        "MATCH (i:Investigation {inv_id:$inv_id}) MERGE (s)-[:BELONGS_TO]->(i) "
        "RETURN s.session_id AS session_id",
        {"session_id": session_id, "role": role, "summary": summary,
         "inv_id": inv_id, "started": _now()},
    )
    if protocol_step:
        link_protocol_step(db, session_id, protocol_step)
    return {"session_id": session_id, "role": role}


def link_protocol_step(db: GraphDB, session_id: str, step_id: str) -> None:
    run_write(
        db, "link protocol step",
        "MATCH (s:Session {session_id:$sid}), (ps:ProtocolStep {step_id:$pid}) "
        "MERGE (s)-[:AT_STEP]->(ps)",
        {"sid": session_id, "pid": step_id},
    )


def record_tool_call(
    db: GraphDB, session_id: str, tool: str, args: dict[str, Any],
    result_summary: str, ms: float, tool_call_id: str | None = None,
) -> str:
    tool_call_id = tool_call_id or _new_id("TC")
    import json

    run_write(
        db, "log tool call",
        "MERGE (tc:ToolCall {tool_call_id:$tcid}) "
        "SET tc.tool = $tool, tc.args = $args, tc.result_summary = $summary, "
        "    tc.ms = $ms, tc.at = $at, tc.session_id = $session_id "
        "WITH tc MATCH (s:Session {session_id:$session_id}) "
        "MERGE (tc)-[:LOGGED]->(s) RETURN tc.tool_call_id AS tcid",
        {"tcid": tool_call_id, "tool": tool, "args": json.dumps(args, default=str),
         "summary": result_summary[:2000], "ms": round(ms, 3), "at": _now(),
         "session_id": session_id},
    )
    return tool_call_id


def handoff(db: GraphDB, from_session: str, to_session: str, reason: str) -> None:
    run_write(
        db, "handoff",
        "MATCH (a:Session {session_id:$from}), (b:Session {session_id:$to}) "
        "MERGE (a)-[h:HANDOFF]->(b) SET h.reason = $reason, h.at = $at",
        {"from": from_session, "to": to_session, "reason": reason, "at": _now()},
    )


def record_message(
    db: GraphDB, session_id: str, role: str, content: str, message_id: str | None = None,
) -> str:
    message_id = message_id or _new_id("MSG")
    run_write(
        db, "record message",
        "MERGE (m:Message {message_id:$mid}) "
        "SET m.role = $role, m.content = $content, m.at = $at "
        "WITH m MATCH (s:Session {session_id:$session_id}) "
        "MERGE (s)-[:HAS_MESSAGE]->(m) RETURN m.message_id AS mid",
        {"mid": message_id, "role": role, "content": content, "at": _now(),
         "session_id": session_id},
    )
    return message_id
