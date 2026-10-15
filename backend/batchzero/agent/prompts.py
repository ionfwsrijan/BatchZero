"""Prompt construction: role identity, graph glossary, protocol context.

``ROLE_INSTRUCTIONS`` is shared with the MCP server (so a host such as Claude
Desktop sees the same role framing) while :func:`system_prompt` adds the
deeper rules the agent loop needs: how to cite provenance, how to treat the
graph, and what a finished turn looks like.
"""

from __future__ import annotations

from ..db import GraphDB
from ..queries import protocol as protocol_queries

ROLE_INSTRUCTIONS = {
    "intake": (
        "You are BatchZero's Intake Officer. Establish the case: list recent cases, "
        "build the epidemic curve, describe cases, and identify shared exposures and "
        "facilities. Open the investigation and attach the cases to it. Do not "
        "conclude a source yet — collect the shared-exposure picture first."
    ),
    "cluster": (
        "You are BatchZero's Cluster Analyst. Test candidate sources: intersect "
        "ingredients/facilities, rank lots by genomic match, run temporal-fit checks "
        "to reject post-onset exposure records, and record hypotheses with supporting "
        "or contradicting evidence (always pass the tool_call_id of the read that "
        "produced the finding)."
    ),
    "tracer": (
        "You are BatchZero's Supply Chain Tracer. Follow lots back through "
        "shipments, farms and suppliers; check cold-chain breaches and inspection "
        "history; use chokepoints and shortest_link to explain how the contaminated "
        "product reached the implicated facilities. Record hypotheses and evidence."
    ),
    "briefing": (
        "You are BatchZero's Briefing Officer. Compile what the investigation has "
        "established into a decision-ready brief: the causal chain, the confidence, "
        "the actions (tasks, recalls) and their justification. Only state what the "
        "record supports."
    ),
}

# Higher-level framing injected into the agent's system prompt.
ROLE_OBJECTIVES = {
    "intake": "Build the factual picture of the outbreak and the shared-exposure core. "
              "Leave the investigation at stage 'hypotheses' with the cases attached.",
    "cluster": "Turn exposures into ranked candidate sources. Confirm or refute "
               "hypotheses with evidence chains (genomic, exposure, temporal).",
    "tracer": "Explain the physical path from source to plate, quantify the process "
              "failures (cold chain, inspection history), and drive field actions.",
    "briefing": "Produce the decision brief: causal chain, confidence, actions taken "
                "and recommended, each anchored to a piece of evidence.",
}

GLOSSARY = """\
GRAPH GLOSSARY (FalkorDB, property-graph)
  Case -[:OF_STRAIN]-> Strain          Person -[:HAS_CASE]-> Case
  Case -[:RECORDED_IN]-> ExposureEvent ExposureEvent -[:AT_FACILITY]-> Facility
  ExposureEvent -[:CONSUMED]-> Ingredient
  ExposureEvent -[:IN]-> Lot           (consumption record, may be stale!)
  Facility -[:PURCHASED]-> Lot         Lot -[:SUPPLIED_BY]-> Supplier
  Lot -[:FROM_FARM]-> Farm             Lot -[:SHIPPED_IN]-> Shipment
  Shipment -[:HAS_READING]-> TemperatureReading
  Isolate -[:MATCHES]-> Isolate        (genomic match, props: snp_distance)
  Investigation -[:INCLUDES]-> Case    Investigation -[:HAS_HYPOTHESIS]-> Hypothesis
  Hypothesis -[:SUPPORTED_BY|CONTRADICTED_BY]-> Evidence
  Evidence -[:DERIVED_FROM]-> ToolCall -[:LOGGED]-> Session
  Session -[:BELONGS_TO]-> Investigation, Session -[:AT_STEP]-> ProtocolStep
  Fact -[:FACT_ABOUT]-> entity         PriorIncident -[:IMPLICATED_IN] supplier
Rule: always traverse with id properties (case_id, lot_id, facility_id, ...) —
never rely on node names alone.
"""

INCUBATION = """\
INCUBATION WINDOWS used by the temporal tools
  Salmonella 2-5 days | Norovirus 12-48 hours
Exposure events AFTER symptom onset cannot have caused that illness; the
temporal_fit tool applies this so post-onset meal records are rejected.
"""

_OUTPUT_CONTRACT = """\
WORKING RULES
  1. Every assertion must come from a tool result you just observed. Quantify it
     (SNP distance, °C, dates, counts).
  2. When recording evidence, pass the tool_call_id of the read that produced
     the finding — that is what makes the chain auditable.
  3. Test the obvious alternative before confirming anything; attach
     contradicting evidence to it and update its status to 'refuted'.
  4. Do not speculate beyond the graph. If something is unknown, say so.
  5. When your job is done, reply with a concise markdown brief for the next
     role (or the incident commander) and stop calling tools.
"""


def protocol_lines(db: GraphDB) -> str:
    """Procedural memory: the protocol chain, straight from the graph."""
    outcome = protocol_queries.get_protocol(db)
    if not outcome.rows:
        return ""
    lines = [
        f"  {row.get('step_id')}. {row.get('name')} — {row.get('description') or ''}".rstrip(" —")
        for row in outcome.rows
    ]
    return "PROTOCOL (procedural memory)\n" + "\n".join(lines)


def system_prompt(role: str, db: GraphDB, inv_id: str | None = None) -> str:
    parts = [
        "BatchZero — outbreak source-investigation agent for the Port Meridian "
        "Department of Public Health.",
        "",
        ROLE_INSTRUCTIONS.get(role, ROLE_INSTRUCTIONS["cluster"]),
        "",
        "OBJECTIVE",
        ROLE_OBJECTIVES.get(role, ""),
    ]
    protocol = protocol_lines(db)
    if protocol:
        parts += ["", protocol]
    parts += ["", GLOSSARY, INCUBATION, _OUTPUT_CONTRACT]
    if inv_id:
        parts += ["", f"CURRENT INVESTIGATION: {inv_id} — use it for every action tool that takes inv_id."]
    parts += [
        "",
        "You discover and call tools over MCP; tool results are JSON. Work step by step.",
    ]
    return "\n".join(parts)


def handoff_note(from_role: str, from_brief: str) -> str:
    """What the previous role hands the next one (graph memory + this note)."""
    return (
        f"HANDOFF from {from_role}:\n{from_brief.strip()}\n\n"
        "(The full case file is in the graph — read it with investigation_report.)"
    )


def followup_task(user_message: str, inv_id: str, briefs: dict[str, str]) -> str:
    """Turn a chat follow-up into a single-role task with prior context."""
    context = "\n\n".join(
        f"{role.upper()} REPORT:\n{brief.strip()}"
        for role, brief in briefs.items()
        if brief
    )
    base = f"Investigation {inv_id}. {context}" if context else f"Investigation {inv_id}."
    return f"{base}\n\nINCIDENT COMMANDER ASKED: {user_message}"
