"""Seed the synthetic Port Meridian public-health graph.

The dataset is fictional but constructed the way a real investigation works:

* 11 salmonellosis cases across three unrelated restaurants, two weeks of onsets
* one shared supply chain: microgreens lot MG-4417 -> GreenLeaf Distributors ->
  Sunrise Hydroponics, moved on a reefer shipment with a cold-chain breach
* decoy chains: a second common supplier (lettuce), a sprouts lot tied to only
  one facility, and a norovirus wedding cluster that looks related and is not
* a temporal trap: one case's onset predates its recorded meal, so that meal
  cannot be the exposure
* institutional memory: a 2025 cilantro incident implicating the same distributor

Everything is deterministic. Run ``python -m batchzero.seed --reset``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Iterable

from .db import GraphDB
from .schema import ensure_schema

# --------------------------------------------------------------------- people
# (person_id, name, role)
PEOPLE: list[dict[str, Any]] = [
    # salmonellosis cases
    {"person_id": "P-101", "name": "Dana Whitmore", "role": "case"},
    {"person_id": "P-102", "name": "Omar El-Sayed", "role": "case"},
    {"person_id": "P-103", "name": "Priya Raman", "role": "case"},
    {"person_id": "P-104", "name": "Caleb Ortiz", "role": "case"},
    {"person_id": "P-105", "name": "Mia Chen", "role": "case"},
    {"person_id": "P-106", "name": "Theo Almeida", "role": "case"},
    {"person_id": "P-107", "name": "Ruth Kowalski", "role": "case"},
    {"person_id": "P-108", "name": "Jonah Beck", "role": "case"},
    {"person_id": "P-109", "name": "Amara Diallo", "role": "case"},
    {"person_id": "P-110", "name": "Liam Foster", "role": "case"},
    {"person_id": "P-111", "name": "Nadia Petrov", "role": "case"},
    # norovirus wedding cluster (red herring)
    {"person_id": "P-201", "name": "Grace Lin", "role": "case"},
    {"person_id": "P-202", "name": "Victor Hale", "role": "case"},
    {"person_id": "P-203", "name": "Sofia Marchetti", "role": "case"},
    # food workers / staff
    {"person_id": "P-301", "name": "Kenji Tanaka", "role": "staff"},
    {"person_id": "P-302", "name": "Lucia Ferraro", "role": "staff"},
    {"person_id": "P-303", "name": "Andre Boucher", "role": "staff"},
    # inspectors & lab
    {"person_id": "P-401", "name": "Miriam Okafor", "role": "inspector"},
    {"person_id": "P-402", "name": "Roberto Delgado", "role": "inspector"},
    {"person_id": "P-403", "name": "Hana Nguyen", "role": "inspector"},
    {"person_id": "P-501", "name": "Sam Whitfield", "role": "lab_tech"},
]

# (case_id, person_id, onset, pathogen, hospitalized, report_source)
CASES: list[dict[str, Any]] = [
    {"case_id": "C-101", "person_id": "P-101", "onset": "2026-10-04", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": True, "report_source": "hospital"},
    {"case_id": "C-102", "person_id": "P-102", "onset": "2026-10-05", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "clinic"},
    {"case_id": "C-103", "person_id": "P-103", "onset": "2026-10-06", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "self-report"},
    {"case_id": "C-104", "person_id": "P-104", "onset": "2026-10-02", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "clinic"},
    {"case_id": "C-105", "person_id": "P-105", "onset": "2026-10-05", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "clinic"},
    {"case_id": "C-106", "person_id": "P-106", "onset": "2026-10-06", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": True, "report_source": "hospital"},
    {"case_id": "C-107", "person_id": "P-107", "onset": "2026-10-08", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "self-report"},
    {"case_id": "C-108", "person_id": "P-108", "onset": "2026-10-09", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "clinic"},
    {"case_id": "C-109", "person_id": "P-109", "onset": "2026-10-06", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "clinic"},
    {"case_id": "C-110", "person_id": "P-110", "onset": "2026-10-08", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "self-report"},
    {"case_id": "C-111", "person_id": "P-111", "onset": "2026-10-09", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "hospitalized": False, "report_source": "clinic"},
    # norovirus
    {"case_id": "C-201", "person_id": "P-201", "onset": "2026-10-06", "pathogen": "Norovirus", "strain": "GII.4", "hospitalized": False, "report_source": "self-report"},
    {"case_id": "C-202", "person_id": "P-202", "onset": "2026-10-07", "pathogen": "Norovirus", "strain": "GII.4", "hospitalized": False, "report_source": "clinic"},
    {"case_id": "C-203", "person_id": "P-203", "onset": "2026-10-06", "pathogen": "Norovirus", "strain": "GII.4", "hospitalized": False, "report_source": "self-report"},
]

FACILITIES: list[dict[str, Any]] = [
    {"facility_id": "F-HG", "name": "Harbor Grill", "type": "restaurant", "neighborhood": "Waterfront", "permit_id": "FG-1042"},
    {"facility_id": "F-NA", "name": "Noodle Atlas", "type": "restaurant", "neighborhood": "Downtown", "permit_id": "FG-2087"},
    {"facility_id": "F-GF", "name": "Green Fork Cafe", "type": "restaurant", "neighborhood": "Midtown", "permit_id": "FG-3311"},
    {"facility_id": "F-BA", "name": "Blue Anchor Catering", "type": "caterer", "neighborhood": "Old Port", "permit_id": "FG-4402"},
]

MENU_ITEMS: list[dict[str, Any]] = [
    {"menu_id": "M-HHB", "name": "Harbor Harvest Bowl", "category": "bowl"},
    {"menu_id": "M-GS", "name": "Grilled Salmon Plate", "category": "main"},
    {"menu_id": "M-AGR", "name": "Atlas Green Ramen", "category": "ramen"},
    {"menu_id": "M-CT", "name": "Crispy Tofu", "category": "starter"},
    {"menu_id": "M-GPS", "name": "Garden Power Salad", "category": "salad"},
    {"menu_id": "M-WBP", "name": "Wedding Buffet Platter", "category": "catering"},
]

INGREDIENTS: list[dict[str, Any]] = [
    {"ingredient_id": "I-MG", "name": "Microgreens Mix", "category": "produce", "ready_to_eat": True},
    {"ingredient_id": "I-QUI", "name": "Quinoa", "category": "grain", "ready_to_eat": True},
    {"ingredient_id": "I-AVO", "name": "Avocado", "category": "produce", "ready_to_eat": True},
    {"ingredient_id": "I-SAL", "name": "Atlantic Salmon", "category": "seafood", "ready_to_eat": False},
    {"ingredient_id": "I-NOOD", "name": "Ramen Noodles", "category": "grain", "ready_to_eat": False},
    {"ingredient_id": "I-MISO", "name": "Miso Broth", "category": "stock", "ready_to_eat": False},
    {"ingredient_id": "I-KALE", "name": "Kale", "category": "produce", "ready_to_eat": True},
    {"ingredient_id": "I-CHK", "name": "Chicken Thigh", "category": "poultry", "ready_to_eat": False},
    {"ingredient_id": "I-CIL", "name": "Cilantro", "category": "herb", "ready_to_eat": True},
    {"ingredient_id": "I-SPR", "name": "Alfalfa Sprouts", "category": "produce", "ready_to_eat": True},
    {"ingredient_id": "I-LET", "name": "Romaine Lettuce", "category": "produce", "ready_to_eat": True},
]

SUPPLIERS: list[dict[str, Any]] = [
    {"supplier_id": "S-GLD", "name": "GreenLeaf Distributors", "type": "distributor", "risk_tier": "medium"},
    {"supplier_id": "S-CSC", "name": "Coastal Sprout Co.", "type": "grower", "risk_tier": "low"},
    {"supplier_id": "S-VFF", "name": "Valley Field Farms", "type": "grower", "risk_tier": "low"},
    {"supplier_id": "S-BP", "name": "Bay Poultry", "type": "processor", "risk_tier": "low"},
    {"supplier_id": "S-MD", "name": "Meridian Dairy", "type": "processor", "risk_tier": "low"},
]

FARMS: list[dict[str, Any]] = [
    {"farm_id": "FM-SUN", "name": "Sunrise Hydroponics", "location": "Cedar Valley", "practice": "hydroponic"},
    {"farm_id": "FM-VAL", "name": "Valley Field Farms", "location": "Northfield", "practice": "field"},
    {"farm_id": "FM-COA", "name": "Coastal Greens", "location": "Tidewater", "practice": "greenhouse"},
]

LOTS: list[dict[str, Any]] = [
    {"lot_id": "MG-4417", "product_name": "Microgreens Mix", "harvest_date": "2026-09-25", "use_by": "2026-10-03", "supplier_id": "S-GLD", "farm_id": "FM-SUN"},
    {"lot_id": "CIL-3320", "product_name": "Cilantro", "harvest_date": "2026-09-26", "use_by": "2026-10-04", "supplier_id": "S-GLD", "farm_id": "FM-SUN"},
    {"lot_id": "LET-2210", "product_name": "Romaine Lettuce", "harvest_date": "2026-09-24", "use_by": "2026-10-02", "supplier_id": "S-VFF", "farm_id": "FM-VAL"},
    {"lot_id": "SPR-88", "product_name": "Alfalfa Sprouts", "harvest_date": "2026-09-27", "use_by": "2026-10-05", "supplier_id": "S-CSC", "farm_id": "FM-COA"},
    {"lot_id": "CHK-771", "product_name": "Chicken Thigh", "harvest_date": "2026-09-28", "use_by": "2026-10-08", "supplier_id": "S-BP", "farm_id": ""},
    {"lot_id": "TOM-452", "product_name": "Tomato", "harvest_date": "2026-09-29", "use_by": "2026-10-07", "supplier_id": "S-VFF", "farm_id": "FM-VAL"},
]

SHIPMENTS: list[dict[str, Any]] = [
    {"shipment_id": "SH-2291", "carrier": "ColdRoute Logistics", "depart": "2026-09-28T04:00:00", "arrive": "2026-09-28T09:30:00", "temp_min_c": 1.2, "temp_max_c": 12.8, "breached": True},
    {"shipment_id": "SH-2305", "carrier": "ColdRoute Logistics", "depart": "2026-09-30T04:00:00", "arrive": "2026-09-30T08:15:00", "temp_min_c": 1.0, "temp_max_c": 3.9, "breached": False},
    {"shipment_id": "SH-2280", "carrier": "Tidewater Freight", "depart": "2026-09-27T06:00:00", "arrive": "2026-09-27T10:00:00", "temp_min_c": 0.8, "temp_max_c": 4.1, "breached": False},
]

# (reading_id, shipment_id, at, celsius)
READINGS: list[dict[str, Any]] = [
    {"reading_id": "R-2291-1", "shipment_id": "SH-2291", "at": "2026-09-28T04:00:00", "celsius": 2.1},
    {"reading_id": "R-2291-2", "shipment_id": "SH-2291", "at": "2026-09-28T05:30:00", "celsius": 6.4},
    {"reading_id": "R-2291-3", "shipment_id": "SH-2291", "at": "2026-09-28T07:00:00", "celsius": 11.9},
    {"reading_id": "R-2291-4", "shipment_id": "SH-2291", "at": "2026-09-28T08:30:00", "celsius": 12.8},
    {"reading_id": "R-2291-5", "shipment_id": "SH-2291", "at": "2026-09-28T09:30:00", "celsius": 5.2},
    {"reading_id": "R-2305-1", "shipment_id": "SH-2305", "at": "2026-09-30T04:00:00", "celsius": 1.0},
    {"reading_id": "R-2305-2", "shipment_id": "SH-2305", "at": "2026-09-30T08:15:00", "celsius": 3.9},
    {"reading_id": "R-2280-1", "shipment_id": "SH-2280", "at": "2026-09-27T06:00:00", "celsius": 0.8},
    {"reading_id": "R-2280-2", "shipment_id": "SH-2280", "at": "2026-09-27T10:00:00", "celsius": 4.1},
]

# (event_id, facility_id, date, kind, note)
EXPOSURES: list[dict[str, Any]] = [
    # Harbor Grill meals
    {"event_id": "E-101a", "facility_id": "F-HG", "date": "2026-09-30", "kind": "meal", "note": "Early dinner, Harbor Harvest Bowl"},
    {"event_id": "E-101b", "facility_id": "F-HG", "date": "2026-10-02", "kind": "meal", "note": "Lunch, Harbor Harvest Bowl"},
    {"event_id": "E-102", "facility_id": "F-HG", "date": "2026-10-03", "kind": "meal", "note": "Dinner, Harbor Harvest Bowl"},
    {"event_id": "E-103", "facility_id": "F-HG", "date": "2026-10-04", "kind": "meal", "note": "Lunch, Harbor Harvest Bowl"},
    # C-104 is the temporal trap: recorded meal is AFTER onset; valid meal is E-104a on Sep 30.
    {"event_id": "E-104a", "facility_id": "F-HG", "date": "2026-09-30", "kind": "meal", "note": "Late lunch, Harbor Harvest Bowl"},
    {"event_id": "E-104b", "facility_id": "F-HG", "date": "2026-10-03", "kind": "meal", "note": "Recorded meal but AFTER onset date"},
    # Noodle Atlas meals
    {"event_id": "E-105", "facility_id": "F-NA", "date": "2026-10-03", "kind": "meal", "note": "Atlas Green Ramen"},
    {"event_id": "E-106", "facility_id": "F-NA", "date": "2026-10-04", "kind": "meal", "note": "Atlas Green Ramen"},
    {"event_id": "E-107", "facility_id": "F-NA", "date": "2026-10-06", "kind": "meal", "note": "Atlas Green Ramen"},
    {"event_id": "E-108", "facility_id": "F-NA", "date": "2026-10-06", "kind": "meal", "note": "Atlas Green Ramen + side"},
    # Green Fork Cafe meals
    {"event_id": "E-109", "facility_id": "F-GF", "date": "2026-10-04", "kind": "meal", "note": "Garden Power Salad"},
    {"event_id": "E-110", "facility_id": "F-GF", "date": "2026-10-05", "kind": "meal", "note": "Garden Power Salad"},
    {"event_id": "E-111", "facility_id": "F-GF", "date": "2026-10-07", "kind": "meal", "note": "Garden Power Salad"},
    # Wedding (norovirus)
    {"event_id": "E-201", "facility_id": "F-BA", "date": "2026-10-05", "kind": "catered_event", "note": "Wedding reception, 140 guests"},
]

# (event_id, person_id) participation
PARTICIPATION: list[tuple[str, str]] = [
    ("E-101a", "P-101"), ("E-101b", "P-101"),
    ("E-102", "P-102"),
    ("E-103", "P-103"),
    ("E-104a", "P-104"), ("E-104b", "P-104"),
    ("E-105", "P-105"), ("E-106", "P-106"), ("E-107", "P-107"), ("E-108", "P-108"),
    ("E-109", "P-109"), ("E-110", "P-110"), ("E-111", "P-111"),
    ("E-201", "P-201"), ("E-201", "P-202"), ("E-201", "P-203"),
]

# event -> menu item involvement
EVENT_MENU: list[tuple[str, str]] = [
    ("E-101a", "M-HHB"), ("E-101b", "M-HHB"), ("E-102", "M-HHB"), ("E-103", "M-HHB"),
    ("E-104a", "M-HHB"), ("E-104b", "M-HHB"),
    ("E-105", "M-AGR"), ("E-106", "M-AGR"), ("E-107", "M-AGR"), ("E-108", "M-AGR"),
    ("E-108", "M-CT"),
    ("E-109", "M-GPS"), ("E-110", "M-GPS"), ("E-111", "M-GPS"),
    ("E-201", "M-WBP"),
]

# menu -> ingredient
MENU_INGREDIENT: list[tuple[str, str]] = [
    ("M-HHB", "I-MG"), ("M-HHB", "I-QUI"), ("M-HHB", "I-AVO"),
    ("M-GS", "I-SAL"),
    ("M-AGR", "I-MG"), ("M-AGR", "I-NOOD"), ("M-AGR", "I-MISO"),
    ("M-CT", "I-CHK"),
    ("M-GPS", "I-MG"), ("M-GPS", "I-KALE"), ("M-GPS", "I-LET"),
    ("M-HHB", "I-LET"), ("M-AGR", "I-LET"),
    ("M-WBP", "I-CHK"), ("M-WBP", "I-CIL"),
]

# facility -> lot purchases
PURCHASES: list[tuple[str, str]] = [
    ("F-HG", "MG-4417"), ("F-NA", "MG-4417"), ("F-GF", "MG-4417"),
    ("F-HG", "CIL-3320"), ("F-NA", "CIL-3320"), ("F-GF", "CIL-3320"),
    ("F-HG", "LET-2210"), ("F-NA", "LET-2210"), ("F-GF", "LET-2210"),
    ("F-NA", "SPR-88"),
    ("F-HG", "CHK-771"), ("F-NA", "CHK-771"), ("F-HG", "TOM-452"),
    ("F-BA", "CHK-771"), ("F-BA", "CIL-3320"),
]

LABS: list[dict[str, Any]] = [
    {"lab_id": "LAB-HAR", "name": "State Public Health Laboratory — Harbor", "level": "reference"},
    {"lab_id": "LAB-ENV", "name": "PMDPH Environmental Laboratory", "level": "environmental"},
]

# isolate_id, pathogen, strain, source_kind (patient|food|environmental|wastewater), snp_profile
ISOLATES: list[dict[str, Any]] = []
for i, cid in enumerate([f"C-{n}" for n in range(101, 112)], start=101):
    ISOLATES.append({"isolate_id": f"ISO-P-{i}", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "source_kind": "patient", "snp_profile": "SNP-A"})
for i in range(201, 204):
    ISOLATES.append({"isolate_id": f"ISO-P-{i}", "pathogen": "Norovirus", "strain": "GII.4", "source_kind": "patient", "snp_profile": "SNP-NV"})
ISOLATES += [
    {"isolate_id": "ISO-F-MG4417", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "source_kind": "food", "snp_profile": "SNP-A"},
    {"isolate_id": "ISO-F-SWAB-HG", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "source_kind": "environmental", "snp_profile": "SNP-A"},
    {"isolate_id": "ISO-W-001", "pathogen": "Salmonella", "strain": "Enteritidis ST11", "source_kind": "wastewater", "snp_profile": "SNP-A"},
]

WASTEWATER: list[dict[str, Any]] = [
    {"site_id": "WW-WEST", "name": "Westside Treatment Plant", "zone": "Westside"},
    {"site_id": "WW-DT", "name": "Downtown Lift Station", "zone": "Downtown"},
]

# inspector id, facility/supplier scope
INSPECTIONS: list[dict[str, Any]] = [
    {"inspection_id": "INS-HG", "date": "2026-08-14", "score": 88, "violations": ["Handwashing signage missing"]},
    {"inspection_id": "INS-NA", "date": "2026-08-21", "score": 91, "violations": []},
    {"inspection_id": "INS-GF", "date": "2026-08-19", "score": 79, "violations": ["Improper produce storage", "Cooler thermometer missing"]},
    {"inspection_id": "INS-GLD", "date": "2026-07-30", "score": 71, "violations": ["Cold chain monitoring gaps", "Reefer maintenance overdue"]},
    {"inspection_id": "INS-SUN", "date": "2026-07-28", "score": 94, "violations": []},
    {"inspection_id": "INS-BA", "date": "2026-06-11", "score": 95, "violations": []},
    {"inspection_id": "INS-CSC", "date": "2026-07-22", "score": 92, "violations": []},
]

PRIOR_INCIDENTS: list[dict[str, Any]] = [
    {"incident_id": "PRIOR-2025-CIL", "year": 2025, "summary": "Cilantro-associated salmonellosis cluster traced to GreenLeaf Distributors; 6 cases, no hospitalizations.", "outcome": "Voluntary destruction of affected lots; distributor issued corrective action plan."},
]

PROTOCOL_STEPS: list[dict[str, Any]] = [
    {"step_id": "PS-1", "order": 1, "name": "Triage & verify reports", "description": "Confirm case definitions, de-duplicate reports, establish the working case list."},
    {"step_id": "PS-2", "order": 2, "name": "Describe the outbreak", "description": "Person/place/time. Build the epi curve; establish the epidemic period and onset range."},
    {"step_id": "PS-3", "order": 3, "name": "Generate hypotheses", "description": "Find common exposures across cases using shared-exposure traversal and clustering."},
    {"step_id": "PS-4", "order": 4, "name": "Test hypotheses", "description": "Trace each candidate exposure through the supply chain; check temporal fit against incubation windows."},
    {"step_id": "PS-5", "order": 5, "name": "Laboratory & environment", "description": "Match patient isolates to food/environmental isolates; assess cold-chain integrity."},
    {"step_id": "PS-6", "order": 6, "name": "Control measures", "description": "Issue sampling tasks, inspection requests and recall recommendations with evidence."},
    {"step_id": "PS-7", "order": 7, "name": "Brief & report", "description": "Compile the epidemiological brief with every conclusion cited to an evidence path."},
]

FACTS: list[dict[str, Any]] = [
    {"fact_id": "FACT-1", "statement": "GreenLeaf Distributors was implicated in the 2025 cilantro salmonellosis cluster.", "kind": "semantic", "confidence": 0.9},
    {"fact_id": "FACT-2", "statement": "GreenLeaf's July 2026 inspection flagged cold-chain monitoring gaps and overdue reefer maintenance.", "kind": "semantic", "confidence": 0.85},
]


# ---------------------------------------------------------------- seed engine
def _merge_nodes(db: GraphDB, label: str, items: Iterable[dict[str, Any]], key: str,
                 date_props: tuple[str, ...] = (), datetime_props: tuple[str, ...] = ()) -> None:
    items = list(items)
    if not items:
        return
    props = sorted({k for it in items for k in it.keys() if k != key})
    sets = []
    for p in props:
        if p in date_props:
            sets.append(f"n.{p} = date(item.{p})")
        elif p in datetime_props:
            sets.append(f"n.{p} = localdatetime(item.{p})")
        else:
            sets.append(f"n.{p} = item.{p}")
    cypher = (
        f"UNWIND $items AS item "
        f"MERGE (n:{label} {{{key}: item.{key}}}) "
        f"SET {', '.join(sets)}"
    )
    db.query(cypher, {"items": items})


def _merge_edges(db: GraphDB, start_label: str, start_key: str, rel: str, end_label: str,
                 end_key: str, pairs: list[tuple[str, str]], prop_map: dict[tuple[str, str], dict[str, Any]] | None = None) -> None:
    if not pairs:
        return
    items = []
    for s, e in pairs:
        row: dict[str, Any] = {"start": s, "end": e, "props": (prop_map or {}).get((s, e), {})}
        items.append(row)
    cypher = (
        f"UNWIND $items AS item "
        f"MATCH (a:{start_label} {{{start_key}: item.start}}) "
        f"MATCH (b:{end_label} {{{end_key}: item.end}}) "
        f"MERGE (a)-[r:{rel}]->(b) "
        f"SET r += item.props"
    )
    db.query(cypher, {"items": items})


def seed_ops_tenant(db: GraphDB) -> dict[str, Any]:
    """Seed the Port Meridian health-district knowledge graph."""
    _merge_nodes(db, "Person", PEOPLE, "person_id")
    _merge_nodes(db, "Case", CASES, "case_id", date_props=("onset",))
    _merge_nodes(db, "Facility", FACILITIES, "facility_id")
    _merge_nodes(db, "MenuItem", MENU_ITEMS, "menu_id")
    _merge_nodes(db, "Ingredient", INGREDIENTS, "ingredient_id")
    _merge_nodes(db, "Supplier", SUPPLIERS, "supplier_id")
    _merge_nodes(db, "Farm", FARMS, "farm_id")
    _merge_nodes(db, "Lot", LOTS, "lot_id", date_props=("harvest_date", "use_by"))
    _merge_nodes(db, "Shipment", SHIPMENTS, "shipment_id", datetime_props=("depart", "arrive"))
    _merge_nodes(db, "TemperatureReading", READINGS, "reading_id", datetime_props=("at",))
    _merge_nodes(db, "Lab", LABS, "lab_id")
    _merge_nodes(db, "Isolate", ISOLATES, "isolate_id")
    _merge_nodes(db, "WastewaterSite", WASTEWATER, "site_id")
    _merge_nodes(db, "Inspection", INSPECTIONS, "inspection_id", date_props=("date",))
    _merge_nodes(db, "PriorIncident", PRIOR_INCIDENTS, "incident_id")
    _merge_nodes(db, "ProtocolStep", PROTOCOL_STEPS, "step_id")
    _merge_nodes(db, "Fact", FACTS, "fact_id")

    # people <-> cases <-> exposures
    _merge_edges(db, "Person", "person_id", "HAS_CASE", "Case", "case_id",
                 [(c["person_id"], c["case_id"]) for c in CASES])
    _merge_edges(db, "Case", "case_id", "LINKED_ISOLATE", "Isolate", "isolate_id",
                 [(f"C-{i}", f"ISO-P-{i}") for i in range(101, 112)] +
                 [(f"C-{i}", f"ISO-P-{i}") for i in range(201, 204)])

    # ExposureEvent nodes
    _merge_nodes(db, "ExposureEvent", EXPOSURES, "event_id", date_props=("date",))
    _merge_edges(db, "Person", "person_id", "PARTICIPATED", "ExposureEvent", "event_id",
                 [(p, e) for e, p in PARTICIPATION])
    _merge_edges(db, "ExposureEvent", "event_id", "AT", "Facility", "facility_id",
                 [(e["event_id"], e["facility_id"]) for e in EXPOSURES])
    _merge_edges(db, "ExposureEvent", "event_id", "INVOLVES", "MenuItem", "menu_id", EVENT_MENU)
    _merge_edges(db, "MenuItem", "menu_id", "CONTAINS", "Ingredient", "ingredient_id", MENU_INGREDIENT)
    _merge_edges(db, "Facility", "facility_id", "PURCHASED", "Lot", "lot_id", PURCHASES)

    # supply chain
    _merge_edges(db, "Lot", "lot_id", "SUPPLIED_BY", "Supplier", "supplier_id",
                 [(l["lot_id"], l["supplier_id"]) for l in LOTS if l["supplier_id"]])
    _merge_edges(db, "Lot", "lot_id", "ORIGINATES_FROM", "Farm", "farm_id",
                 [(l["lot_id"], l["farm_id"]) for l in LOTS if l["farm_id"]])
    _merge_edges(db, "Lot", "lot_id", "SHIPPED_IN", "Shipment", "shipment_id", [
        ("MG-4417", "SH-2291"), ("CIL-3320", "SH-2291"),
        ("LET-2210", "SH-2280"), ("SPR-88", "SH-2280"),
        ("CHK-771", "SH-2305"),
    ])
    _merge_edges(db, "Shipment", "shipment_id", "DELIVERED_TO", "Facility", "facility_id", [
        ("SH-2291", "F-HG"), ("SH-2291", "F-NA"), ("SH-2291", "F-GF"),
        ("SH-2305", "F-HG"), ("SH-2305", "F-NA"),
        ("SH-2280", "F-NA"),
    ])
    _merge_edges(db, "Shipment", "shipment_id", "HAS_READING", "TemperatureReading", "reading_id",
                 [(r["shipment_id"], r["reading_id"]) for r in READINGS])

    # exposure -> consumed lot (only where food history was traceable)
    _merge_edges(db, "ExposureEvent", "event_id", "CONSUMED", "Lot", "lot_id", [
        ("E-101a", "MG-4417"), ("E-101b", "MG-4417"), ("E-102", "MG-4417"), ("E-103", "MG-4417"),
        ("E-104a", "MG-4417"), ("E-104b", "MG-4417"),
        ("E-105", "MG-4417"), ("E-106", "MG-4417"), ("E-107", "MG-4417"), ("E-108", "MG-4417"),
        # Green Fork Cafe events intentionally have NO explicit lot link (harder path)
        ("E-201", "CHK-771"),
    ])

    # labs & isolates
    _merge_edges(db, "Lab", "lab_id", "PROCESSED", "Isolate", "isolate_id",
                 [("LAB-HAR", i["isolate_id"]) for i in ISOLATES if i["source_kind"] in ("patient", "wastewater")] +
                 [("LAB-ENV", i["isolate_id"]) for i in ISOLATES if i["source_kind"] in ("food", "environmental")])
    _merge_edges(db, "Isolate", "isolate_id", "SAMPLED_FROM", "Lot", "lot_id", [
        ("ISO-F-MG4417", "MG-4417"),
    ])
    _merge_edges(db, "WastewaterSite", "site_id", "DETECTED", "Isolate", "isolate_id", [
        ("WW-WEST", "ISO-W-001"), ("WW-DT", "ISO-W-001"),
    ])
    # genomic MATCHES edges with SNP distances
    matches: list[tuple[str, str]] = []
    match_props: dict[tuple[str, str], dict[str, Any]] = {}
    for i in range(101, 112):
        dist = 0 if i in (101, 105, 109) else (1 if i % 2 == 0 else 2)
        matches.append((f"ISO-P-{i}", "ISO-F-MG4417"))
        match_props[(f"ISO-P-{i}", "ISO-F-MG4417")] = {"snp_distance": dist}
    matches.append(("ISO-F-SWAB-HG", "ISO-F-MG4417"))
    match_props[("ISO-F-SWAB-HG", "ISO-F-MG4417")] = {"snp_distance": 1}
    matches.append(("ISO-W-001", "ISO-F-MG4417"))
    match_props[("ISO-W-001", "ISO-F-MG4417")] = {"snp_distance": 1}
    # norovirus isolates match each other only
    for a, b in (("ISO-P-201", "ISO-P-202"), ("ISO-P-202", "ISO-P-203")):
        matches.append((a, b))
        match_props[(a, b)] = {"snp_distance": 0}
    _merge_edges(db, "Isolate", "isolate_id", "MATCHES", "Isolate", "isolate_id", matches, match_props)

    # inspections & prior incidents
    _merge_edges(db, "Facility", "facility_id", "SUBJECT_OF", "Inspection", "inspection_id",
                 [("F-HG", "INS-HG"), ("F-NA", "INS-NA"), ("F-GF", "INS-GF"), ("F-BA", "INS-BA")])
    _merge_edges(db, "Supplier", "supplier_id", "SUBJECT_OF", "Inspection", "inspection_id",
                 [("S-GLD", "INS-GLD"), ("S-CSC", "INS-CSC")])
    _merge_edges(db, "Farm", "farm_id", "SUBJECT_OF", "Inspection", "inspection_id",
                 [("FM-SUN", "INS-SUN")])
    _merge_edges(db, "Supplier", "supplier_id", "IMPLICATED_IN", "PriorIncident", "incident_id",
                 [("S-GLD", "PRIOR-2025-CIL")])
    _merge_edges(db, "Person", "person_id", "WORKED_ON", "PriorIncident", "incident_id",
                 [("P-401", "PRIOR-2025-CIL")])

    # facts -> provenance
    _merge_edges(db, "Fact", "fact_id", "FACT_ABOUT", "Supplier", "supplier_id",
                 [("FACT-1", "S-GLD"), ("FACT-2", "S-GLD")])

    # protocol chain
    _merge_edges(db, "ProtocolStep", "step_id", "NEXT", "ProtocolStep", "step_id", [
        ("PS-1", "PS-2"), ("PS-2", "PS-3"), ("PS-3", "PS-4"),
        ("PS-4", "PS-5"), ("PS-5", "PS-6"), ("PS-6", "PS-7"),
    ])

    return db.stats()


def seed_training_tenant(db: GraphDB) -> dict[str, Any]:
    """A deliberately tiny second tenant, used to prove per-tenant isolation."""
    _merge_nodes(db, "Facility", [{"facility_id": "F-RB", "name": "Riverside Bistro", "type": "restaurant", "neighborhood": "Riverside", "permit_id": "FG-9001"}], "facility_id")
    _merge_nodes(db, "Person", [
        {"person_id": "TP-1", "name": "Training Case A", "role": "case"},
        {"person_id": "TP-2", "name": "Training Case B", "role": "case"},
    ], "person_id")
    _merge_nodes(db, "Case", [
        {"case_id": "TC-1", "person_id": "TP-1", "onset": "2026-09-01", "pathogen": "Norovirus", "strain": "GII.2", "hospitalized": False, "report_source": "clinic"},
        {"case_id": "TC-2", "person_id": "TP-2", "onset": "2026-09-02", "pathogen": "Norovirus", "strain": "GII.2", "hospitalized": False, "report_source": "clinic"},
    ], "case_id", date_props=("onset",))
    _merge_edges(db, "Person", "person_id", "HAS_CASE", "Case", "case_id", [("TP-1", "TC-1"), ("TP-2", "TC-2")])
    return db.stats()


def seed_all(reset: bool = False) -> dict[str, Any]:
    from .config import get_settings
    settings = get_settings()
    results: dict[str, Any] = {}

    ops = GraphDB(settings.tenant_graph)
    if reset:
        ops.delete_graph()
    ensure_schema(ops)
    results[settings.tenant_graph] = seed_ops_tenant(ops)

    train = GraphDB(settings.training_tenant_graph)
    if reset:
        train.delete_graph()
    ensure_schema(train)
    results[settings.training_tenant_graph] = seed_training_tenant(train)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the BatchZero FalkorDB graphs.")
    parser.add_argument("--reset", action="store_true", help="Delete and rebuild tenants")
    args = parser.parse_args(argv)
    stats = seed_all(reset=args.reset)
    for graph, s in stats.items():
        print(f"[seed] {graph}: {s['nodes']} nodes, {s['relationships']} relationships")
    return 0


if __name__ == "__main__":
    sys.exit(main())
