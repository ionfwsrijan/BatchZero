"""The BatchZero graph model.

This module is the single source of truth for labels, relationship types and
indexes. ``docs/GRAPH_MODEL.md`` mirrors it for humans; the README prints the
same model for judges.

Design rules
------------
1. Epidemiology vocabulary only. A public-health investigator should recognize
   every node and every edge without a translation table.
2. Time lives on edges and on nodes as real FalkorDB temporal values, because
   incubation-window math is what separates a real investigation from a search.
3. Provenance is first class: hypotheses are supported by evidence, evidence is
   derived from tool calls, tool calls live inside sessions. That chain is what
   makes every answer explainable and is itself stored in the graph.
"""

from __future__ import annotations

# --------------------------------------------------------------------- labels
LABELS = {
    "Person": "A case, contact, food worker, inspector or lab technician.",
    "Case": "A reported illness episode under investigation.",
    "ExposureEvent": "A meal, catered event or other shared exposure.",
    "Facility": "Restaurant, caterer, central kitchen or processing site.",
    "MenuItem": "A dish served or prepared at a facility.",
    "Ingredient": "A food ingredient used by one or more menu items.",
    "Lot": "A traceable production/purchase lot of an ingredient.",
    "Supplier": "Distributor, grower or processor that supplies lots.",
    "Farm": "Origin farm for a lot.",
    "Shipment": "A physical movement of lots between nodes of the chain.",
    "TemperatureReading": "A cold-chain sensor reading on a shipment.",
    "Lab": "Laboratory that processed an isolate.",
    "Isolate": "A pathogen isolate (patient, food or environmental).",
    "Inspection": "A regulatory inspection of a facility or supplier.",
    "WastewaterSite": "A wastewater sampling site used for early detection.",
    "PriorIncident": "A historical incident linked to a supplier or facility.",
    "Investigation": "The agent's case file; the root of everything it writes.",
    "Hypothesis": "A candidate source, with status and confidence.",
    "Evidence": "A finding that supports or contradicts a hypothesis.",
    "Task": "An action item (sampling, inspection, interview).",
    "Recall": "A drafted product recall covering lots.",
    "Session": "One agent session (a role working on the case).",
    "Message": "A chat turn, user or agent.",
    "ToolCall": "One executed tool call: the audit trail of the agent.",
    "Fact": "Distilled memory about an entity, with provenance.",
    "ProtocolStep": "A step of the standard epidemiological protocol.",
}

# ------------------------------------------------------------ relationships
RELATIONSHIPS = {
    "HAS_CASE": "(Person)->(Case)",
    "PARTICIPATED": "(Person)->(ExposureEvent)",
    "AT": "(ExposureEvent)->(Facility)",
    "INVOLVES": "(ExposureEvent)->(MenuItem)",
    "CONTAINS": "(MenuItem)->(Ingredient)",
    "CONSUMED": "(ExposureEvent)->(Lot)",
    "PURCHASED": "(Facility)->(Lot)",
    "SUPPLIED_BY": "(Lot)->(Supplier)",
    "ORIGINATES_FROM": "(Lot)->(Farm)",
    "SHIPPED_IN": "(Lot)->(Shipment)",
    "DELIVERED_TO": "(Shipment)->(Facility)",
    "HAS_READING": "(Shipment)->(TemperatureReading)",
    "EMPLOYS": "(Facility)->(Person)",
    "SUBJECT_OF": "(Facility|Supplier)->(Inspection)",
    "IMPLICATED_IN": "(Supplier|Facility)->(PriorIncident)",
    "WORKED_ON": "(Person)->(Investigation)",
    "LINKED_ISOLATE": "(Case)->(Isolate)",
    "PROCESSED": "(Lab)->(Isolate)",
    "SAMPLED_FROM": "(Isolate)->(Lot)",
    "MATCHES": "(Isolate)-[snp_distance]->(Isolate)",
    "DETECTED": "(WastewaterSite)-[on]->(Isolate)",
    "INCLUDES": "(Investigation)->(Case)",
    "HAS_HYPOTHESIS": "(Investigation)->(Hypothesis)",
    "SUPPORTED_BY": "(Hypothesis)->(Evidence)",
    "CONTRADICTED_BY": "(Hypothesis)->(Evidence)",
    "ABOUT": "(Evidence|Task|Fact)->(entity)",
    "DERIVED_FROM": "(Evidence)->(ToolCall)",
    "HAS_TASK": "(Investigation)->(Task)",
    "ASSIGNED_TO": "(Task)->(Person)",
    "HAS_RECALL": "(Investigation)->(Recall)",
    "COVERS": "(Recall)->(Lot)",
    "BELONGS_TO": "(Session)->(Investigation)",
    "HANDOFF": "(Session)->(Session)",
    "HAS_MESSAGE": "(Session)->(Message)",
    "LOGGED": "(Session)->(ToolCall)",
    "FACT_ABOUT": "(Fact)->(entity)",
    "FACT_SUPPORTED_BY": "(Fact)->(Evidence)",
    "RECALLED_IN": "(Fact)->(Session)",
    "NEXT": "(ProtocolStep)->(ProtocolStep)",
    "AT_STEP": "(Session)->(ProtocolStep)",
}

# ------------------------------------------------------------------ indexes
FULLTEXT_INDEXES: list[tuple[str, list[str]]] = [
    ("Person", ["name"]),
    ("Facility", ["name"]),
    ("MenuItem", ["name"]),
    ("Ingredient", ["name"]),
    ("Supplier", ["name"]),
    ("Farm", ["name"]),
    ("Lot", ["lot_id", "product_name"]),
    ("Isolate", ["isolate_id", "pathogen"]),
    ("PriorIncident", ["summary"]),
    ("Fact", ["statement"]),
]

RANGE_INDEXES: list[tuple[str, list[str]]] = [
    ("Case", ["case_id"]),
    ("Case", ["onset"]),
    ("Lot", ["lot_id"]),
    ("Ingredient", ["name"]),
    ("Supplier", ["name"]),
    ("Facility", ["name"]),
    ("Investigation", ["inv_id"]),
    ("Hypothesis", ["hyp_id"]),
    ("Evidence", ["evidence_id"]),
    ("Task", ["task_id"]),
    ("Session", ["session_id"]),
    ("ProtocolStep", ["step_id"]),
]

# Incubation windows (hours) — used by the temporal fit check. Real values from
# CDC guidance; the agent queries these from the protocol graph rather than
# hard-coding them in the prompt, which is the procedural-memory trick.
INCUBATION_WINDOWS = {
    "Salmonella": {"min_hours": 6, "max_hours": 72, "typical_days": "6 hours to 6 days"},
    "Norovirus": {"min_hours": 12, "max_hours": 60, "typical_days": "12 to 48 hours"},
    "E. coli O157:H7": {"min_hours": 24, "max_hours": 240, "typical_days": "3 to 4 days"},
    "Listeria": {"min_hours": 24, "max_hours": 2016, "typical_days": "1 to 4 weeks"},
}


def ensure_schema(db) -> dict[str, str]:
    """Create the indexes the agent depends on. Idempotent, safe to re-run."""
    created: dict[str, str] = {}
    for label, props in RANGE_INDEXES:
        for prop in props:
            stmt = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
            key = f"range:{label}.{prop}"
            try:
                db.query(stmt)
                created[key] = "ok"
            except Exception as exc:  # already exists or unsupported syntax
                created[key] = f"skip ({type(exc).__name__})"
    for label, props in FULLTEXT_INDEXES:
        prop_list = ", ".join(f"n.{p}" for p in props)
        stmt = f"CREATE FULLTEXT INDEX FOR (n:{label}) ON ({prop_list})"
        key = f"fulltext:{label}({','.join(props)})"
        try:
            db.query(stmt)
            created[key] = "ok"
        except Exception as exc:
            created[key] = f"skip ({type(exc).__name__})"
    return created
