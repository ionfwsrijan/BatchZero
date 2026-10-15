"""Deterministic role plans — the offline demo brain.

These are what :class:`~batchzero.agent.llm.MockLLM` replays when no LLM API
key is configured. They are written against the seeded Port Meridian fixture,
so the demo (and the benchmark) is reproducible and never fails live. Every
step is a genuine MCP tool call against FalkorDB — only the *decision* of which
tool to call next is pre-seeded rather than model-generated.
"""

from __future__ import annotations

from typing import Any

from .llm import MockLLM, ScriptStep

CASES = [f"C-1{n:02d}" for n in range(1, 12)]  # C-101 .. C-111
FACILITIES = ["F-HG", "F-NA", "F-GF"]
LOT = "MG-4417"
ISOLATE = "ISO-F-MG4417"


# ----------------------------------------------------------------- helpers
def _rows(history: dict[str, Any], tool: str) -> list[dict[str, Any]]:
    return (history.get(tool) or {}).get("rows") or []


def _first(history: dict[str, Any], tool: str) -> dict[str, Any]:
    rows = _rows(history, tool)
    return rows[0] if rows else {}


def _tcid(history: dict[str, Any], tool: str) -> str | None:
    return (history.get(tool) or {}).get("tool_call_id")


def _last_hyp(history: dict[str, Any]) -> str:
    return ((history.get("add_hypothesis") or {}).get("hypothesis") or {}).get("hyp_id", "HYP-?")


def _report(history: dict[str, Any]) -> dict[str, Any]:
    return ((history.get("investigation_report") or {}).get("report")) or {}


def _hyp_id(history: dict[str, Any], needle: str) -> str:
    for hyp in _report(history).get("hypotheses", []):
        if needle.lower() in (hyp.get("statement") or "").lower():
            return hyp["hyp_id"]
    return _last_hyp(history)


def _bullet(rows: list[dict], fmt) -> str:
    return "\n".join("  - " + fmt(row) for row in rows)


# ------------------------------------------------------------------ intake
def _intake_final(h: dict[str, Any]) -> str:
    confirmed = (h.get("list_recent_cases") or {}).get("row_count", 0)
    curve = _rows(h, "epi_curve")
    onset_lo = curve[0]["onset"] if curve else "?"
    onset_hi = curve[-1]["onset"] if curve else "?"
    ings = _rows(h, "find_common_ingredients")[:3]
    facs = _rows(h, "find_common_facilities")
    sup = _first(h, "find_common_suppliers")
    clusters = _rows(h, "cluster_by_exposure")
    return f"""## Intake — Port Meridian gastrointestinal cluster

**{confirmed} laboratory-confirmed *Salmonella* Enteritidis ST11 cases**
(C-101 … C-111), onsets **{onset_lo} → {onset_hi}** — one continuous epi curve,
no second wave. Three Waterfront/Downtown/Midtown food premises are implicated.

**Shared exposure (intersection over all {confirmed} cases)**
{_bullet(ings, lambda r: f"**{r.get('ingredient')}** — {r.get('cases')} cases")}
  - Note: Microgreens Mix and Romaine Lettuce are tied at {confirmed} cases —
    the tie must be broken by evidence, not by count.

**Facilities**
{_bullet(facs, lambda r: f"{r.get('facility')} ({r.get('facility_id')}) — {r.get('cases')} cases")}

**Upstream candidate suppliers**
{_bullet(_rows(h, "find_common_suppliers")[:2], lambda r: f"{r.get('supplier')} ({r.get('supplier_id')}) — {r.get('cases')} cases across {r.get('facilities')} facilities, lots {r.get('lots')}")}

**Exposure communities (label propagation)**
{_bullet(clusters, lambda r: f"community {r.get('community')}: {', '.join(r.get('facilities') or [])} cases")}

Case file opened and all {confirmed} cases attached. Handing to the Cluster
Analyst to break the Microgreens/Romaine tie with genomics — **no source is
concluded at intake.**
"""


def intake_plan(inv_id: str) -> list[ScriptStep]:
    return [
        ScriptStep("get_protocol"),
        ScriptStep("list_recent_cases", {"pathogen": "Salmonella"}),
        ScriptStep("epi_curve", {"pathogen": "Salmonella"}),
        ScriptStep("find_common_ingredients", {"case_ids": CASES}),
        ScriptStep("find_common_facilities", {"case_ids": CASES}),
        ScriptStep("find_common_suppliers", {"case_ids": CASES}),
        ScriptStep("cluster_by_exposure", {"pathogen": "Salmonella"}),
        ScriptStep("include_cases", lambda h: {"inv_id": inv_id, "case_ids": CASES}),
        ScriptStep("set_investigation_stage", lambda h: {"inv_id": inv_id, "stage": "hypotheses"}),
    ]


# ----------------------------------------------------------------- cluster
def _cluster_final(h: dict[str, Any]) -> str:
    rank = _first(h, "lot_source_ranking")
    iso = _rows(h, "match_isolates")
    match_cases = sorted({c for r in iso for c in (r.get("cases") or [])})
    sup = _first(h, "find_common_suppliers")
    exposures = _rows(h, "case_exposures")
    trap = next((e for e in exposures if e.get("meal_after_onset")), None)
    main = _hyp_id(h, "MG-4417")
    decoy = _hyp_id(h, "LET-2210")
    hyps = _report(h).get("hypotheses", [])
    main_hyp = next((x for x in hyps if x.get("hyp_id") == main), {})
    return f"""## Cluster analysis — source attribution

Two signals tie on exposure frequency; genomics breaks the tie.

| Candidate | Exposure count | Genomic support |
|---|---|---|
| **Microgreens Mix lot {rank.get('lot_id')}** (GreenLeaf) | 11 cases | **{rank.get('matched_cases')} isolates matched**, SNP {rank.get('min_snp')}–{rank.get('max_snp')} |
| Romaine Lettuce lot LET-2210 (Valley Field Farms) | 11 cases | none |

- Environmental isolate **{rank.get('source_isolate')}** from lot {rank.get('lot_id')}
  is identical/near-identical to patient isolates across {len(match_cases)} cases
  (SNP distance {rank.get('min_snp')}–{rank.get('max_snp')}) — a single-source outbreak.
- The supplier behind {sup.get('cases', '?')}/11 cases is **{sup.get('supplier')}**
  ({sup.get('supplier_id')}), lots {sup.get('lots')}.

**Temporal hygiene:** C-104's record
{f"shows a meal ({trap.get('event_id')}, {trap.get('meal_date')}) logged AFTER onset — rejected by temporal_fit; the valid meal (E-104a, 2026-09-30) fits the incubation window." if trap else "is clean."}

**Hypotheses on the case file**
{_bullet(hyps, lambda r: f"{r.get('hyp_id')} [{r.get('status')}] {round((r.get('confidence') or 0) * 100)}% — {r.get('statement')}")}

Handing to the Supply Chain Tracer to walk {LOT} back to the farm and check the
cold chain. Confidence on the microgreens hypothesis is **{main_hyp.get('confidence')}**.
"""


def cluster_plan(inv_id: str) -> list[ScriptStep]:
    main_statement = (
        f"Microgreens Mix lot {LOT} (GreenLeaf Distributors, Sunrise Hydroponics) "
        "is the outbreak source"
    )
    decoy_statement = "Romaine lettuce lot LET-2210 (Valley Field Farms) is the source"
    return [
        ScriptStep("investigation_report", lambda h: {"inv_id": inv_id}),
        ScriptStep("cluster_by_exposure", {"pathogen": "Salmonella"}),
        ScriptStep("find_common_ingredients", {"case_ids": CASES}),
        ScriptStep("find_common_suppliers", {"case_ids": CASES}),
        ScriptStep("lot_source_ranking", {"pathogen": "Salmonella"}),
        ScriptStep("match_isolates", {"isolate_id": ISOLATE}),
        ScriptStep("ingredient_to_lots", {"ingredient_name": "Microgreens Mix", "facility_ids": FACILITIES}),
        ScriptStep("case_exposures", {"case_id": "C-104"}),
        ScriptStep("temporal_fit", {"case_id": "C-104", "event_id": "E-104b", "pathogen": "Salmonella"}),
        ScriptStep("add_hypothesis", lambda h: {
            "inv_id": inv_id,
            "statement": f"Salmonella cases are caused by contaminated microgreens lot {LOT} distributed by GreenLeaf Distributors.",
            "confidence": 0.6,
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _last_hyp(h), "kind": "genomic",
            "summary": f"Environmental isolate {ISOLATE} from lot {LOT} matches patient isolates "
                       f"across {_first(h, 'lot_source_ranking').get('matched_cases')} cases at SNP "
                       f"{_first(h, 'lot_source_ranking').get('min_snp')}-{_first(h, 'lot_source_ranking').get('max_snp')}.",
            "supports": True, "weight": 0.95,
            "about_label": "Lot", "about_value": LOT,
            "tool_call_id": _tcid(h, "match_isolates"),
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417") or _last_hyp(h), "kind": "exposure",
            "summary": "All 11 cases ate at facilities supplied by GreenLeaf Distributors; "
                       "microgreens lot MG-4417 is the only purchased lot shared by all three premises.",
            "supports": True, "weight": 0.8,
            "about_label": "Supplier", "about_value": "S-GLD",
            "tool_call_id": _tcid(h, "find_common_suppliers"),
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417") or _last_hyp(h), "kind": "supply",
            "summary": "Microgreens Mix sold at Harbor Grill, Noodle Atlas and Green Fork Cafe "
                       "traces to a single lot MG-4417 from GreenLeaf.",
            "supports": True, "weight": 0.7,
            "about_label": "Lot", "about_value": LOT,
            "tool_call_id": _tcid(h, "ingredient_to_lots"),
        }),
        ScriptStep("add_hypothesis", lambda h: {
            "inv_id": inv_id,
            "statement": "Romaine lettuce lot LET-2210 from Valley Field Farms is the outbreak source.",
            "confidence": 0.5,
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _last_hyp(h), "kind": "genomic",
            "summary": "No isolate associated with lot LET-2210 matches any patient; "
                       "lot_source_ranking shows zero genomic support despite equal exposure counts.",
            "supports": False, "weight": 0.9,
            "about_label": "Lot", "about_value": "LET-2210",
            "tool_call_id": _tcid(h, "lot_source_ranking"),
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _hyp_id(h, "LET-2210") or _last_hyp(h), "kind": "exposure",
            "summary": "Two suppliers tie on case overlap (11 cases, 3 facilities each); "
                       "frequency alone cannot separate them — only MG-4417 has genomics.",
            "supports": False, "weight": 0.6,
            "about_label": "Supplier", "about_value": "S-VFF",
            "tool_call_id": _tcid(h, "find_common_suppliers"),
        }),
        ScriptStep("update_hypothesis", lambda h: {
            "hyp_id": _hyp_id(h, "LET-2210"), "status": "refuted", "confidence": 0.05,
        }),
        ScriptStep("investigation_report", lambda h: {"inv_id": inv_id}),
        ScriptStep("update_hypothesis", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417"), "status": "likely", "confidence": 0.9,
        }),
    ]


# ------------------------------------------------------------------ tracer
def _tracer_final(h: dict[str, Any]) -> str:
    chain = _first(h, "trace_supply_chain")
    cold = _first(h, "cold_chain")
    lot_cold = _rows(h, "lot_cold_chain")
    sup = h.get("supplier_profile") or {}
    prior = _rows(h, "prior_incidents")
    choke = _rows(h, "find_chokepoints")
    tasks = _report(h).get("tasks", [])
    return f"""## Supply-chain trace — how MG-4417 reached three premises

**Provenance chain**
Sunrise Hydroponics ({chain.get('farm')}, {chain.get('farm_practice')})
→ lot {chain.get('lot_id')} *{chain.get('product')}* (harvest {chain.get('harvest_date')},
use-by {chain.get('use_by')})
→ supplier **{chain.get('supplier')}** ({chain.get('supplier_id')})
→ shipment(s) {chain.get('shipments')}
→ delivered to {chain.get('delivered_to')}
→ purchased by {chain.get('purchased_by')}.

**Cold chain failure (contributing factor)**
Shipment {cold.get('shipment_id')} ({cold.get('carrier')}) peaked at
**{cold.get('peak_c')} °C** against a ≤4 °C requirement — {len(cold.get('excursions') or [])}
excursions logged, declared breach={cold.get('declared_breach')}. Other lots
({[r.get('shipment_id') for r in lot_cold if r.get('shipment_id') and r.get('shipment_id') != cold.get('shipment_id')]})
stayed within range, isolating the failure to the MG-4417 run.

**Distributor record**
{sup.get('name', 'GreenLeaf Distributors')} — risk tier {sup.get('risk_tier')},
prior incidents: {_bullet(prior, lambda r: f"{r.get('incident_id')} ({r.get('year')}): {r.get('summary')}") or '  - none'}

**Graph chokepoints (betweenness)**
{_bullet(choke[:3], lambda r: f"{r.get('label')} {r.get('ident')} — {r.get('betweenness')}")}

**Actions filed**
{_bullet(tasks, lambda r: f"{r.get('task_id')} [{r.get('type')}] {r.get('instructions')} (assigned: {r.get('assigned_to')})") or '  - (none)'}

Hypothesis MG-4417 upgraded to **confirmed (0.95)**; the distributor and farm are
now on the sampling plan.
"""


def tracer_plan(inv_id: str) -> list[ScriptStep]:
    return [
        ScriptStep("investigation_report", lambda h: {"inv_id": inv_id}),
        ScriptStep("trace_supply_chain", {"lot_id": LOT}),
        ScriptStep("lot_cold_chain", {"lot_id": LOT}),
        ScriptStep("cold_chain", {"shipment_id": "SH-2291"}),
        ScriptStep("supplier_profile", {"supplier_id": "S-GLD"}),
        ScriptStep("prior_incidents", {"entity_name": "GreenLeaf Distributors"}),
        ScriptStep("facility_sources", {"facility_id": "F-HG"}),
        ScriptStep("find_chokepoints", {"top": 6}),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417"), "kind": "supply",
            "summary": "Lot MG-4417 moved from Sunrise Hydroponics via GreenLeaf Distributors "
                       "on shipment SH-2291 to Harbor Grill, Noodle Atlas and Green Fork Cafe.",
            "supports": True, "weight": 0.9,
            "about_label": "Lot", "about_value": LOT,
            "tool_call_id": _tcid(h, "trace_supply_chain"),
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417"), "kind": "environmental",
            "summary": f"Shipment SH-2291 breached cold chain: peak {_first(h, 'cold_chain').get('peak_c')} °C, "
                       f"{len(_first(h, 'cold_chain').get('excursions') or [])} excursions above 4 °C on the "
                       "MG-4417 run — an amplification factor for the contamination.",
            "supports": True, "weight": 0.7,
            "about_label": "Shipment", "about_value": "SH-2291",
            "tool_call_id": _tcid(h, "cold_chain"),
        }),
        ScriptStep("attach_evidence", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417"), "kind": "history",
            "summary": "GreenLeaf Distributors was implicated in the 2025 cilantro salmonellosis "
                       "cluster and its 2026 inspection flagged cold-chain monitoring gaps.",
            "supports": True, "weight": 0.6,
            "about_label": "Supplier", "about_value": "S-GLD",
            "tool_call_id": _tcid(h, "prior_incidents"),
        }),
        ScriptStep("create_task", lambda h: {
            "inv_id": inv_id, "task_type": "sample",
            "instructions": f"Collect retained samples of lot {LOT} (microgreens) from Harbor Grill, "
                            "Noodle Atlas and Green Fork Cafe cold stores; hold for PCR confirmation.",
            "about_label": "Lot", "about_value": LOT, "assigned_person_id": "P-401",
        }),
        ScriptStep("create_task", lambda h: {
            "inv_id": inv_id, "task_type": "inspect",
            "instructions": "On-site verification at Sunrise Hydroponics: irrigation water, seed stock "
                            "and post-harvest wash water — swab for Salmonella.",
            "about_label": "Farm", "about_value": "FM-SUN",
        }),
        ScriptStep("create_task", lambda h: {
            "inv_id": inv_id, "task_type": "interview",
            "instructions": "Interview GreenLeaf reefer driver/ops about the SH-2291 temperature breach "
                            "(peak 12.8 °C) and corrective action on reefer maintenance.",
            "about_label": "Supplier", "about_value": "S-GLD",
            "assigned_person_id": "P-402",
        }),
        ScriptStep("investigation_report", lambda h: {"inv_id": inv_id}),
        ScriptStep("update_hypothesis", lambda h: {
            "hyp_id": _hyp_id(h, "MG-4417"), "status": "confirmed", "confidence": 0.96,
        }),
    ]


# ---------------------------------------------------------------- briefing
def _briefing_final(h: dict[str, Any]) -> str:
    recall = (h.get("draft_recall") or {}).get("recall") or {}
    facts = _rows(h, "recall_facts")
    report = _report(h)
    inv = report.get("investigation", {})
    hyps = report.get("hypotheses", [])
    tasks = report.get("tasks", [])
    confirmed = next((x for x in hyps if x.get("status") == "confirmed"), hyps[0] if hyps else {})
    return f"""## INCIDENT BRIEF — Port Meridian salmonellosis, October 2026

**Status:** source identified and controlled. Decision-ready.

### Bottom line
The cluster is a **single-source outbreak of *Salmonella* Enteritidis ST11** caused by
**microgreens lot {LOT}** (product *Microgreens Mix*) produced by Sunrise Hydroponics and
distributed by **GreenLeaf Distributors (S-GLD)** to Harbor Grill, Noodle Atlas and
Green Fork Cafe.

### Causal chain (each link is evidence-backed)
1. 11 cases share one strain and one exposure; two suppliers tied on frequency.
2. Environmental isolate **{ISOLATE}** from lot {LOT} matches patient isolates
   across 11 cases at **SNP 0–2** — the only candidate with genomic support.
3. Romaine lot LET-2210 (Valley Field Farms) had equal exposure but no genomic match →
   **hypothesis refuted**.
4. Provenance: Sunrise Hydroponics → {LOT} → GreenLeaf → shipment SH-2291 → three premises.
5. Aggravating factor: **cold-chain breach on SH-2291 (peak 12.8 °C, 4 excursions)** PLUS
   a 2025 cilantro cluster and a 2026 cold-chain inspection finding at the distributor.

### Evidence integrity
- Hypothesis status: **{confirmed.get('status')} at {confirmed.get('confidence')}**
  with {len(confirmed.get('supporting') or [])} supporting and
  {len(confirmed.get('contradicting') or [])} contradicting evidence items;
  every item links to the tool call that produced it (Hypothesis → Evidence → ToolCall).
- 1 temporal artifact (a post-onset meal record) was caught and excluded by protocol,
  not silently ignored.

### Actions
- **Recall:** {recall.get('recall_id')} drafted, scope: {recall.get('scope')} covering {recall.get('lots')}.
- **Sampling & inspection tasks filed:** {len(tasks)} — environmental sampling at the farm,
  product sampling at the premises, distributor interview.
- Semantic memory updated: GreenLeaf's cold-chain risks are now prior knowledge for
  future clusters.
{f"{chr(10)}**Institutional memory consulted**{chr(10)}" + _bullet(facts, lambda r: r.get('statement', '')) if facts else ""}
"""


def briefing_plan(inv_id: str) -> list[ScriptStep]:
    return [
        ScriptStep("investigation_report", lambda h: {"inv_id": inv_id}),
        ScriptStep("recall_facts", {"query": "GreenLeaf"}),
        ScriptStep("draft_recall", lambda h: {
            "inv_id": inv_id, "lot_ids": [LOT],
            "scope": "Regional — all premises supplied by GreenLeaf Distributors in the Waterfront, Downtown and Midtown districts (Harbor Grill, Noodle Atlas, Green Fork Cafe)",
            "rationale": "Lot MG-4417 is the only candidate with a genomic match to patient isolates "
                         "(11 cases, SNP 0-2), a confirmed supply path to all three premises and a "
                         "documented cold-chain breach on SH-2291. Romaine LET-2210 was refuted.",
        }),
        ScriptStep("set_investigation_stage", lambda h: {"inv_id": inv_id, "stage": "control"}),
        ScriptStep("set_investigation_summary", lambda h: {
            "inv_id": inv_id,
            "summary": "Single-source Salmonella Enteritidis ST11 outbreak caused by microgreens lot "
                       "MG-4417 (Sunrise Hydroponics, distributed by GreenLeaf Distributors). Genomic "
                       "match SNP 0-2 across 11 cases; romaine LET-2210 refuted. Recall drafted; "
                       "environmental sampling and distributor interview filed.",
        }),
        ScriptStep("remember_fact", lambda h: {
            "statement": "In October 2026, microgreens lot MG-4417 (GreenLeaf Distributors / Sunrise "
                         "Hydroponics) caused an 11-case Salmonella Enteritidis ST11 outbreak in Port Meridian.",
            "about_label": "Supplier", "about_value": "S-GLD", "confidence": 0.95,
        }),
    ]


PLANS = {
    "intake": (intake_plan, _intake_final),
    "cluster": (cluster_plan, _cluster_final),
    "tracer": (tracer_plan, _tracer_final),
    "briefing": (briefing_plan, _briefing_final),
}


def role_plan(role: str, inv_id: str, briefs: dict[str, str] | None = None) -> MockLLM:
    builder, final = PLANS.get(role, PLANS["cluster"])
    return MockLLM(script=builder(inv_id), final=final)
