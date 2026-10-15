"""The agent-facing tool registry.

Each tool wraps one or more queries, executes it, and records a ``ToolCall``
node (the audit trail). A tool result always includes the ``tool_call_id`` so
the agent can later cite the exact call that produced a piece of evidence via
``attach_evidence(tool_call_id=...)`` — closing the provenance loop.

Tools are grouped into role-scoped tool-sets (``ROLE_TOOLSETS``) so the MCP
server exposes only the tools appropriate to the working agent role.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .db import GraphDB
from .queries import actions, epidemiology, memory, protocol, supply
from .queries.base import QueryOutcome


# ------------------------------------------------------------------ context
@dataclass
class ToolContext:
    """Binds a tool session to a tenant graph + session + investigation."""

    db: GraphDB
    session_id: str | None = None
    investigation_id: str | None = None
    role: str = "agent"
    log_calls: bool = True
    last_tool_call_id: str | None = None

    def log(self, tool: str, args: dict, summary: str, ms: float) -> str | None:
        if not self.log_calls or not self.session_id:
            return None
        tcid = actions.record_tool_call(
            self.db, self.session_id, tool, args, summary[:1500], ms
        )
        self.last_tool_call_id = tcid
        return tcid


def _outcome_payload(oc: QueryOutcome) -> dict[str, Any]:
    return {
        "title": oc.title,
        "rows": oc.rows,
        "row_count": len(oc.rows),
        "ms": round(oc.ms, 3),
        "cypher": oc.cypher,
        "algorithm": oc.algorithm,
        "digest": oc.digest(),
    }


# ------------------------------------------------------------------- registry
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema
    impl: Callable[..., dict[str, Any]]


TOOLS: dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: dict[str, Any]):
    def deco(fn):
        parameters.setdefault("type", "object")
        parameters.setdefault("properties", {})
        TOOLS[name] = ToolSpec(name=name, description=description, parameters=parameters, impl=fn)
        return fn
    return deco


_OBJ = {"type": "object"}


def _str(desc, required=True, extra=None):
    schema = {"type": "string", "description": desc}
    if extra:
        schema.update(extra)
    return schema


# -------------------------------------------------------------- read: epi
@tool(
    "list_recent_cases",
    "List reported illness cases, optionally filtered by pathogen (e.g. 'Salmonella') and/or a minimum onset date (ISO). Returns case_id, onset, strain, isolate.",
    {**_OBJ, "properties": {"pathogen": _str("Pathogen filter, e.g. 'Salmonella'"), "since": _str("Earliest onset date, ISO YYYY-MM-DD")}},
)
def _list_recent_cases(ctx, pathogen=None, since=None):
    return _outcome_payload(epidemiology.list_recent_cases(ctx.db, pathogen, since))


@tool(
    "epi_curve",
    "Onset histogram (cases per day) for a pathogen — the classic epidemic curve.",
    {**_OBJ, "properties": {"pathogen": _str("Pathogen, default 'Salmonella'")}},
)
def _epi_curve(ctx, pathogen="Salmonella"):
    return _outcome_payload(epidemiology.epi_curve(ctx.db, pathogen))


@tool(
    "describe_case",
    "Full dossier for one case: person, onset, strain, hospitalization, facilities visited, exposure events.",
    {**_OBJ, "properties": {"case_id": _str("Case id, e.g. 'C-101'")}, "required": ["case_id"]},
)
def _describe_case(ctx, case_id):
    return _outcome_payload(epidemiology.describe_case(ctx.db, case_id))


@tool(
    "case_exposures",
    "Every recorded exposure for a case with menu items, consumed lots, and a meal_after_onset flag (to spot temporal traps).",
    {**_OBJ, "properties": {"case_id": _str("Case id")}, "required": ["case_id"]},
)
def _case_exposures(ctx, case_id):
    return _outcome_payload(epidemiology.case_exposures(ctx.db, case_id))


@tool(
    "valid_exposures",
    "Only a case's exposures inside the pathogen's incubation window (post-onset meals excluded).",
    {**_OBJ, "properties": {"case_id": _str("Case id"), "pathogen": _str("Pathogen for the incubation window")}, "required": ["case_id", "pathogen"]},
)
def _valid_exposures(ctx, case_id, pathogen):
    return _outcome_payload(epidemiology.valid_exposures(ctx.db, case_id, pathogen))


@tool(
    "find_common_ingredients",
    "Ingredients eaten by the most cases in a set — the shared-exposure core. Pass case_ids.",
    {**_OBJ, "properties": {"case_ids": {"type": "array", "items": {"type": "string"}, "description": "Case ids to intersect"}}, "required": ["case_ids"]},
)
def _find_common_ingredients(ctx, case_ids):
    return _outcome_payload(epidemiology.find_common_ingredients(ctx.db, case_ids))


@tool(
    "find_common_facilities",
    "Facilities where the most cases in a set ate. Pass case_ids.",
    {**_OBJ, "properties": {"case_ids": {"type": "array", "items": {"type": "string"}, "description": "Case ids to intersect"}}, "required": ["case_ids"]},
)
def _find_common_facilities(ctx, case_ids):
    return _outcome_payload(epidemiology.find_common_facilities(ctx.db, case_ids))


@tool(
    "find_common_suppliers",
    "Suppliers of lots purchased by the facilities where the cases ate — candidate-source ranking. Pass case_ids.",
    {**_OBJ, "properties": {"case_ids": {"type": "array", "items": {"type": "string"}, "description": "Case ids to intersect"}}, "required": ["case_ids"]},
)
def _find_common_suppliers(ctx, case_ids):
    return _outcome_payload(epidemiology.find_common_suppliers(ctx.db, case_ids))


@tool(
    "ingredient_to_lots",
    "Trace an ingredient through specific facilities to the exact lots they purchased and the suppliers/farms behind them.",
    {**_OBJ, "properties": {"ingredient_name": _str("Ingredient name, e.g. 'Microgreens Mix'"), "facility_ids": {"type": "array", "items": {"type": "string"}, "description": "Facility ids, e.g. ['F-HG','F-NA','F-GF']"}}, "required": ["ingredient_name", "facility_ids"]},
)
def _ingredient_to_lots(ctx, ingredient_name, facility_ids):
    return _outcome_payload(epidemiology.ingredient_to_lots(ctx.db, ingredient_name, facility_ids))


@tool(
    "cluster_by_exposure",
    "Label-propagation community detection: groups cases into exposure communities without being told what a cluster is.",
    {**_OBJ, "properties": {"pathogen": _str("Pathogen, default 'Salmonella'")}},
)
def _cluster_by_exposure(ctx, pathogen="Salmonella"):
    return _outcome_payload(epidemiology.cluster_by_exposure(ctx.db, pathogen))


@tool(
    "temporal_fit",
    "Check whether a meal falls inside the pathogen's incubation window for a case (refutes post-onset exposure records).",
    {**_OBJ, "properties": {"case_id": _str("Case id"), "event_id": _str("Exposure event id"), "pathogen": _str("Pathogen")}, "required": ["case_id", "event_id", "pathogen"]},
)
def _temporal_fit(ctx, case_id, event_id, pathogen):
    return _outcome_payload(epidemiology.temporal_fit(ctx.db, case_id, event_id, pathogen))


# -------------------------------------------------------------- read: labs
@tool(
    "lot_source_ranking",
    "Rank lots by how many patients their source food/environmental isolate matches, with SNP distances — the genomic smoking gun.",
    {**_OBJ, "properties": {"pathogen": _str("Pathogen, default 'Salmonella'")}},
)
def _lot_source_ranking(ctx, pathogen="Salmonella"):
    return _outcome_payload(epidemiology.lot_source_ranking(ctx.db, pathogen))


@tool(
    "match_isolates",
    "Genomic neighbours of an isolate with SNP distances and the cases/lots/wastewater linked to each match.",
    {**_OBJ, "properties": {"isolate_id": _str("Isolate id, e.g. 'ISO-F-MG4417'")}, "required": ["isolate_id"]},
)
def _match_isolates(ctx, isolate_id):
    return _outcome_payload(epidemiology.match_isolates(ctx.db, isolate_id))


@tool(
    "wastewater_detections",
    "Wastewater surveillance detections of the outbreak strain by site/zone/date.",
    {},
)
def _wastewater_detections(ctx):
    return _outcome_payload(epidemiology.wastewater_detections(ctx.db))


# -------------------------------------------------------------- read: supply
@tool(
    "trace_supply_chain",
    "Full provenance of a lot: supplier, farm, shipments, delivery sites, and purchasing facilities.",
    {**_OBJ, "properties": {"lot_id": _str("Lot id, e.g. 'MG-4417'")}, "required": ["lot_id"]},
)
def _trace_supply_chain(ctx, lot_id):
    return _outcome_payload(supply.trace_supply_chain(ctx.db, lot_id))


@tool(
    "facility_sources",
    "Every lot a facility purchased with its supplier, farm and shipments.",
    {**_OBJ, "properties": {"facility_id": _str("Facility id, e.g. 'F-HG'")}, "required": ["facility_id"]},
)
def _facility_sources(ctx, facility_id):
    return _outcome_payload(supply.facility_sources(ctx.db, facility_id))


@tool(
    "cold_chain",
    "Temperature trace of a shipment: peak/min, readings above 4C (excursions), and declared breach flag.",
    {**_OBJ, "properties": {"shipment_id": _str("Shipment id, e.g. 'SH-2291'")}, "required": ["shipment_id"]},
)
def _cold_chain(ctx, shipment_id):
    return _outcome_payload(supply.cold_chain(ctx.db, shipment_id))


@tool(
    "lot_cold_chain",
    "Cold-chain status of every shipment that carried a given lot.",
    {**_OBJ, "properties": {"lot_id": _str("Lot id")}, "required": ["lot_id"]},
)
def _lot_cold_chain(ctx, lot_id):
    return _outcome_payload(supply.lot_cold_chain(ctx.db, lot_id))


@tool(
    "find_chokepoints",
    "Betweenness centrality over the graph: the structural bridges everything routes through (prioritise these for sampling).",
    {**_OBJ, "properties": {"top": {"type": "integer", "description": "How many top chokepoints, default 8"}}},
)
def _find_chokepoints(ctx, top=8):
    return _outcome_payload(supply.find_chokepoints(ctx.db, top))


@tool(
    "connected_components",
    "Weakly connected components — the epidemiologically-linked core vs isolated entities.",
    {},
)
def _connected_components(ctx):
    return _outcome_payload(supply.connected_components(ctx.db))


@tool(
    "shortest_link",
    "Shortest graph path between any two entities (by label + id value) — 'how are these connected'.",
    {**_OBJ, "properties": {"a_label": _str("Label of first entity, e.g. 'Case'"), "a_value": _str("Its id value, e.g. 'C-101'"), "b_label": _str("Label of second entity"), "b_value": _str("Its id value")}, "required": ["a_label", "a_value", "b_label", "b_value"]},
)
def _shortest_link(ctx, a_label, a_value, b_label, b_value):
    a = supply.resolve_entity(ctx.db, a_label, _id_key(a_label), a_value).first()
    b = supply.resolve_entity(ctx.db, b_label, _id_key(b_label), b_value).first()
    if not a or not b:
        return {"ok": False, "error": "entity not found", "a_found": bool(a), "b_found": bool(b)}
    return _outcome_payload(supply.shortest_link(ctx.db, a["node_id"], b["node_id"]))


def _id_key(label: str) -> str:
    from .queries.actions import PRIMARY_ID
    return PRIMARY_ID.get(label, "name")


@tool(
    "supplier_profile",
    "Supplier dossier: lots, deliveries, inspection scores/violations, prior incidents, investigators, known facts.",
    {**_OBJ, "properties": {"supplier_id": _str("Supplier id, e.g. 'S-GLD'")}, "required": ["supplier_id"]},
)
def _supplier_profile(ctx, supplier_id):
    return _outcome_payload(supply.supplier_profile(ctx.db, supplier_id))


@tool(
    "facility_profile",
    "Facility dossier: inspection history, staff, suppliers.",
    {**_OBJ, "properties": {"facility_id": _str("Facility id")}, "required": ["facility_id"]},
)
def _facility_profile(ctx, facility_id):
    return _outcome_payload(supply.facility_profile(ctx.db, facility_id))


# -------------------------------------------------------------- read: memory
@tool(
    "search_entities",
    "Search entities across the graph by name/id/summary substring.",
    {**_OBJ, "properties": {"query": _str("Search text"), "limit": {"type": "integer", "description": "Max results, default 15"}}, "required": ["query"]},
)
def _search_entities(ctx, query, limit=15):
    return _outcome_payload(memory.search_entities(ctx.db, query, limit))


@tool(
    "recall_facts",
    "Semantic memory: search distilled Fact nodes — what the agency already knows about an entity.",
    {**_OBJ, "properties": {"query": _str("Search text")}, "required": ["query"]},
)
def _recall_facts(ctx, query):
    return _outcome_payload(memory.recall_facts(ctx.db, query))


@tool(
    "prior_incidents",
    "Episodic memory: past incidents involving a supplier/facility name, with investigators and outcomes.",
    {**_OBJ, "properties": {"entity_name": _str("Supplier or facility name")}, "required": ["entity_name"]},
)
def _prior_incidents(ctx, entity_name):
    return _outcome_payload(memory.prior_incidents(ctx.db, entity_name))


@tool(
    "get_protocol",
    "Procedural memory: the standard epidemiological protocol as an ordered chain of steps.",
    {},
)
def _get_protocol(ctx):
    return _outcome_payload(protocol.get_protocol(ctx.db))


@tool(
    "current_protocol_step",
    "Where the current agent session is in the protocol, and the next step.",
    {},
)
def _current_protocol_step(ctx):
    detail = protocol.current_session_step(ctx.db, ctx.session_id or "") if ctx.session_id else {}
    if not detail:
        detail = protocol.first_step(ctx.db)
    return {"ok": True, "current_step": detail}


# -------------------------------------------------------------- write: actions
@tool(
    "open_investigation",
    "Open (or continue) an Investigation case file. Returns inv_id.",
    {**_OBJ, "properties": {"title": _str("Investigation title"), "priority": _str("low|medium|high")}, "required": ["title"]},
)
def _open_investigation(ctx, title, priority="high"):
    inv = actions.open_investigation(ctx.db, title, priority)
    ctx.investigation_id = inv.get("inv_id", ctx.investigation_id)
    return {"ok": True, "investigation": inv}


@tool(
    "include_cases",
    "Attach cases to the investigation so they are part of the case file.",
    {**_OBJ, "properties": {"inv_id": _str("Investigation id"), "case_ids": {"type": "array", "items": {"type": "string"}, "description": "Case ids"}}, "required": ["inv_id", "case_ids"]},
)
def _include_cases(ctx, inv_id, case_ids):
    res = actions.include_cases(ctx.db, inv_id, case_ids)
    return {"ok": True, "linked": res.rows, "investigation_id": inv_id}


@tool(
    "add_hypothesis",
    "Record a candidate source hypothesis. Returns hyp_id. Always follow up with attach_evidence.",
    {**_OBJ, "properties": {"inv_id": _str("Investigation id"), "statement": _str("The hypothesis, one sentence"), "confidence": {"type": "number", "description": "0..1"}}, "required": ["inv_id", "statement"]},
)
def _add_hypothesis(ctx, inv_id, statement, confidence=0.5):
    hyp = actions.add_hypothesis(ctx.db, inv_id, statement, confidence)
    return {"ok": True, "hypothesis": hyp}


@tool(
    "update_hypothesis",
    "Update a hypothesis's status (open|likely|confirmed|refuted) and/or confidence.",
    {**_OBJ, "properties": {"hyp_id": _str("Hypothesis id"), "status": _str("open|likely|confirmed|refuted"), "confidence": {"type": "number", "description": "0..1"}}, "required": ["hyp_id"]},
)
def _update_hypothesis(ctx, hyp_id, status=None, confidence=None):
    actions.update_hypothesis(ctx.db, hyp_id, status, confidence)
    return {"ok": True, "hyp_id": hyp_id, "status": status, "confidence": confidence}


@tool(
    "attach_evidence",
    "Attach a finding to a hypothesis. Set supports=true to back it, false to contradict it. Pass the tool_call_id of the read that produced it and an about_label/about_value to wire provenance to a graph entity.",
    {**_OBJ, "properties": {
        "hyp_id": _str("Hypothesis id"),
        "kind": _str("genomic|supply|temporal|inspection|history|environmental|other"),
        "summary": _str("One-sentence finding, specific and quantified where possible"),
        "supports": {"type": "boolean", "description": "true=supports, false=contradicts"},
        "weight": {"type": "number", "description": "0..1 strength"},
        "about_label": _str("Entity label, e.g. 'Lot'"),
        "about_value": _str("Entity id value, e.g. 'MG-4417'"),
        "tool_call_id": _str("The tool_call_id of the supporting read"),
    }, "required": ["hyp_id", "kind", "summary"]},
)
def _attach_evidence(ctx, hyp_id, kind, summary, supports=True, weight=1.0, about_label=None, about_value=None, tool_call_id=None):
    ev = actions.attach_evidence(
        ctx.db, hyp_id, kind, summary, supports, weight,
        about_label, about_value, tool_call_id,
    )
    return {"ok": True, "evidence": ev}


@tool(
    "create_task",
    "Create an action item (sampling, inspection, interview) and optionally assign it.",
    {**_OBJ, "properties": {
        "inv_id": _str("Investigation id"),
        "task_type": _str("sample|inspect|interview|recall|other"),
        "instructions": _str("What to do"),
        "about_label": _str("Entity label the task concerns"),
        "about_value": _str("Entity id value"),
        "assigned_person_id": _str("Person id to assign, e.g. 'P-401'"),
        "due": _str("Due date ISO"),
    }, "required": ["inv_id", "task_type", "instructions"]},
)
def _create_task(ctx, inv_id, task_type, instructions, about_label=None, about_value=None, assigned_person_id=None, due=None):
    t = actions.create_task(ctx.db, inv_id, task_type, instructions, about_label, about_value, assigned_person_id, due)
    return {"ok": True, "task": t}


@tool(
    "draft_recall",
    "Draft a product recall covering specific lots, with scope and rationale. Returns recall_id.",
    {**_OBJ, "properties": {
        "inv_id": _str("Investigation id"),
        "lot_ids": {"type": "array", "items": {"type": "string"}, "description": "Lots to recall"},
        "scope": _str("e.g. 'Regional — Harbor Grill, Noodle Atlas, Green Fork Cafe'"),
        "rationale": _str("Evidence-based justification"),
    }, "required": ["inv_id", "lot_ids", "scope", "rationale"]},
)
def _draft_recall(ctx, inv_id, lot_ids, scope, rationale):
    r = actions.draft_recall(ctx.db, inv_id, lot_ids, scope, rationale)
    return {"ok": True, "recall": r}


@tool(
    "remember_fact",
    "Distill a durable fact into semantic memory, optionally linked to an entity and supporting evidence.",
    {**_OBJ, "properties": {
        "statement": _str("The fact, one sentence"),
        "about_label": _str("Entity label"),
        "about_value": _str("Entity id value"),
        "confidence": {"type": "number", "description": "0..1"},
        "supported_by_evidence": _str("Evidence id backing this fact"),
    }, "required": ["statement"]},
)
def _remember_fact(ctx, statement, about_label=None, about_value=None, confidence=0.8, supported_by_evidence=None):
    f = actions.remember_fact(ctx.db, statement, about_label, about_value, confidence, supported_by_evidence)
    return {"ok": True, "fact": f}


@tool(
    "list_inspectors",
    "List field inspectors available to assign tasks to.",
    {},
)
def _list_inspectors(ctx):
    return {"ok": True, "inspectors": actions.assign_inspectors(ctx.db)}


@tool(
    "set_investigation_stage",
    "Advance the investigation's protocol stage (e.g. 'intake','hypotheses','testing','control','brief').",
    {**_OBJ, "properties": {"inv_id": _str("Investigation id"), "stage": _str("Stage name")}, "required": ["inv_id", "stage"]},
)
def _set_investigation_stage(ctx, inv_id, stage):
    actions.set_investigation_stage(ctx.db, inv_id, stage)
    return {"ok": True, "inv_id": inv_id, "stage": stage}


# -------------------------------------------------------------- role toolsets
READ_TOOLS = [
    "list_recent_cases", "epi_curve", "describe_case", "case_exposures", "valid_exposures",
    "find_common_ingredients", "find_common_facilities", "find_common_suppliers",
    "ingredient_to_lots", "cluster_by_exposure", "temporal_fit",
    "lot_source_ranking", "match_isolates", "wastewater_detections",
    "trace_supply_chain", "facility_sources", "cold_chain", "lot_cold_chain",
    "find_chokepoints", "connected_components", "shortest_link",
    "supplier_profile", "facility_profile",
    "search_entities", "recall_facts", "prior_incidents", "get_protocol", "current_protocol_step",
]

ROLE_TOOLSETS: dict[str, list[str]] = {
    "intake": [
        "list_recent_cases", "epi_curve", "describe_case", "case_exposures", "valid_exposures",
        "find_common_ingredients", "find_common_facilities", "find_common_suppliers",
        "cluster_by_exposure", "search_entities", "get_protocol", "current_protocol_step",
        "open_investigation", "include_cases", "remember_fact", "set_investigation_stage",
    ],
    "cluster": [
        "list_recent_cases", "epi_curve", "describe_case", "case_exposures", "valid_exposures",
        "find_common_ingredients", "find_common_facilities", "find_common_suppliers",
        "ingredient_to_lots", "cluster_by_exposure", "temporal_fit",
        "lot_source_ranking", "match_isolates", "trace_supply_chain", "lot_cold_chain",
        "find_chokepoints", "shortest_link",
        "prior_incidents", "recall_facts", "get_protocol", "current_protocol_step",
        "add_hypothesis", "attach_evidence", "update_hypothesis",
    ],
    "tracer": [
        "trace_supply_chain", "facility_sources", "cold_chain", "lot_cold_chain",
        "find_chokepoints", "connected_components", "shortest_link",
        "supplier_profile", "facility_profile", "ingredient_to_lots",
        "lot_source_ranking", "match_isolates", "search_entities", "recall_facts",
        "prior_incidents", "get_protocol", "current_protocol_step",
        "add_hypothesis", "attach_evidence", "update_hypothesis", "create_task",
    ],
    "briefing": [
        "list_recent_cases", "epi_curve", "describe_case", "trace_supply_chain",
        "lot_source_ranking", "cold_chain", "supplier_profile", "recall_facts",
        "prior_incidents", "get_protocol", "current_protocol_step",
        "create_task", "draft_recall", "remember_fact", "update_hypothesis",
        "set_investigation_stage",
    ],
}


# -------------------------------------------------------------- execution
def execute(ctx: ToolContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one tool with provenance logging. Returns a JSON-serializable dict."""
    spec = TOOLS.get(name)
    if spec is None:
        return {"ok": False, "error": f"unknown tool: {name}"}
    start = time.perf_counter()
    try:
        payload = spec.impl(ctx, **(args or {}))
    except Exception as exc:  # surface tool errors to the agent instead of crashing
        ms = (time.perf_counter() - start) * 1000.0
        return {"ok": False, "tool": name, "error": f"{type(exc).__name__}: {exc}", "ms": round(ms, 3)}
    ms = (time.perf_counter() - start) * 1000.0
    summary = payload.get("digest") or json.dumps(payload, default=str)[:800]
    tcid = ctx.log(name, args or {}, summary, ms)
    if isinstance(payload, dict):
        payload.setdefault("ok", True)
        payload["tool"] = name
        payload["ms"] = round(ms, 3)
        if tcid:
            payload["tool_call_id"] = tcid
    return payload


def tools_for_role(role: str) -> list[ToolSpec]:
    names = ROLE_TOOLSETS.get(role, READ_TOOLS)
    return [TOOLS[n] for n in names if n in TOOLS]
