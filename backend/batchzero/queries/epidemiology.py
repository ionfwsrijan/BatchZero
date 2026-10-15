"""Epidemiological read queries: cases, exposures, clustering, laboratories.

These are the traversals the Cluster Analyst and Intake roles lean on. Each
returns a :class:`QueryOutcome` carrying the exact Cypher for provenance.
"""

from __future__ import annotations

from typing import Any

from ..db import GraphDB
from .base import QueryOutcome, onset_window, run_read


def list_recent_cases(
    db: GraphDB, pathogen: str | None = None, since: str | None = None
) -> QueryOutcome:
    """Triage: recent cases, optionally filtered by pathogen and onset date."""
    where = ["1=1"]
    params: dict[str, Any] = {}
    if pathogen:
        where.append("c.pathogen = $pathogen")
        params["pathogen"] = pathogen
    if since:
        where.append("c.onset >= date($since)")
        params["since"] = since
    cypher = (
        "MATCH (c:Case) "
        f"WHERE {' AND '.join(where)} "
        "OPTIONAL MATCH (c)<-[:HAS_CASE]-(p:Person) "
        "OPTIONAL MATCH (c)-[:LINKED_ISOLATE]->(iso:Isolate) "
        "RETURN c.case_id AS case_id, c.onset AS onset, c.pathogen AS pathogen, "
        "       c.strain AS strain, c.hospitalized AS hospitalized, "
        "       c.report_source AS report_source, p.person_id AS person_id, "
        "       p.name AS person, iso.isolate_id AS isolate "
        "ORDER BY c.onset"
    )
    return run_read(db, "recent cases", cypher, params)


def epi_curve(db: GraphDB, pathogen: str = "Salmonella") -> QueryOutcome:
    """Onset histogram — the classic epi curve, computed in-graph."""
    cypher = (
        "MATCH (c:Case {pathogen:$pathogen}) "
        "RETURN c.onset AS onset, count(*) AS cases "
        "ORDER BY onset"
    )
    return run_read(db, "epi curve", cypher, {"pathogen": pathogen})


def describe_case(db: GraphDB, case_id: str) -> QueryOutcome:
    """Full single-case dossier: person, clinical fields, isolate, facilities."""
    cypher = (
        "MATCH (c:Case {case_id:$case_id})<-[:HAS_CASE]-(p:Person) "
        "OPTIONAL MATCH (c)-[:LINKED_ISOLATE]->(iso:Isolate) "
        "OPTIONAL MATCH (p)-[:PARTICIPATED]->(e:ExposureEvent)-[:AT]->(f:Facility) "
        "RETURN c.case_id AS case_id, c.onset AS onset, c.pathogen AS pathogen, "
        "       c.strain AS strain, c.hospitalized AS hospitalized, "
        "       c.report_source AS report_source, p.person_id AS person_id, "
        "       p.name AS person, iso.isolate_id AS isolate, "
        "       iso.source_kind AS isolate_source, "
        "       collect(DISTINCT f.name) AS facilities_visited, "
        "       collect(DISTINCT e.event_id) AS exposure_events"
    )
    return run_read(db, f"case {case_id}", cypher, {"case_id": case_id})


def case_exposures(db: GraphDB, case_id: str) -> QueryOutcome:
    """Every recorded exposure for a case, with menu items and consumed lots.

    The agent uses this to spot the temporal trap: a meal recorded *after* the
    onset date cannot be the exposure.
    """
    cypher = (
        "MATCH (c:Case {case_id:$case_id})<-[:HAS_CASE]-(p:Person)"
        "-[:PARTICIPATED]->(e:ExposureEvent) "
        "OPTIONAL MATCH (e)-[:AT]->(f:Facility) "
        "OPTIONAL MATCH (e)-[:INVOLVES]->(m:MenuItem) "
        "OPTIONAL MATCH (e)-[:CONSUMED]->(l:Lot) "
        "RETURN e.event_id AS event_id, e.date AS date, e.kind AS kind, "
        "       e.note AS note, f.name AS facility, f.facility_id AS facility_id, "
        "       collect(DISTINCT m.name) AS menu_items, "
        "       collect(DISTINCT l.lot_id) AS consumed_lots, "
        "       e.date > c.onset AS meal_after_onset "
        "ORDER BY e.date"
    )
    return run_read(db, f"exposures for {case_id}", cypher, {"case_id": case_id})


def find_common_ingredients(db: GraphDB, case_ids: list[str]) -> QueryOutcome:
    """Ingredients eaten by the most cases in a set — the shared-exposure core."""
    cypher = (
        "MATCH (c:Case)<-[:HAS_CASE]-(p:Person)-[:PARTICIPATED]->(e:ExposureEvent)"
        "-[:INVOLVES]->(m:MenuItem)-[:CONTAINS]->(i:Ingredient) "
        "WHERE c.case_id IN $case_ids "
        "RETURN i.ingredient_id AS ingredient_id, i.name AS ingredient, "
        "       i.category AS category, i.ready_to_eat AS ready_to_eat, "
        "       count(DISTINCT c) AS cases, "
        "       collect(DISTINCT c.case_id) AS case_ids "
        "ORDER BY cases DESC, ingredient"
    )
    return run_read(db, "common ingredients", cypher, {"case_ids": case_ids})


def find_common_facilities(db: GraphDB, case_ids: list[str]) -> QueryOutcome:
    """Facilities where the most cases in the set ate."""
    cypher = (
        "MATCH (c:Case)<-[:HAS_CASE]-(p:Person)-[:PARTICIPATED]->(e:ExposureEvent)"
        "-[:AT]->(f:Facility) "
        "WHERE c.case_id IN $case_ids "
        "RETURN f.facility_id AS facility_id, f.name AS facility, "
        "       f.neighborhood AS neighborhood, f.permit_id AS permit_id, "
        "       count(DISTINCT c) AS cases, collect(DISTINCT c.case_id) AS case_ids "
        "ORDER BY cases DESC, facility"
    )
    return run_read(db, "common facilities", cypher, {"case_ids": case_ids})


def find_common_suppliers(db: GraphDB, case_ids: list[str]) -> QueryOutcome:
    """Suppliers of lots purchased by facilities the cases ate at.

    This is a candidate-source ranking: a supplier linking to many cases across
    many facilities is a stronger hypothesis than one tied to a single site.
    """
    cypher = (
        "MATCH (c:Case)<-[:HAS_CASE]-(p:Person)-[:PARTICIPATED]->(:ExposureEvent)"
        "-[:AT]->(f:Facility)-[:PURCHASED]->(l:Lot)-[:SUPPLIED_BY]->(s:Supplier) "
        "WHERE c.case_id IN $case_ids "
        "RETURN s.supplier_id AS supplier_id, s.name AS supplier, "
        "       s.risk_tier AS risk_tier, "
        "       count(DISTINCT c) AS cases, count(DISTINCT f) AS facilities, "
        "       collect(DISTINCT l.lot_id) AS lots, "
        "       collect(DISTINCT c.case_id) AS case_ids "
        "ORDER BY cases DESC, facilities DESC"
    )
    return run_read(db, "common suppliers", cypher, {"case_ids": case_ids})


def ingredient_to_lots(
    db: GraphDB, ingredient_name: str, facility_ids: list[str]
) -> QueryOutcome:
    """Trace a specific ingredient through the facilities that served it, to the
    exact lots those facilities purchased and the suppliers behind them."""
    cypher = (
        "MATCH (i:Ingredient {name:$ingredient})<-[:CONTAINS]-(:MenuItem)"
        "<-[:INVOLVES]-(:ExposureEvent)-[:AT]->(f:Facility) "
        "WHERE f.facility_id IN $facility_ids "
        "WITH DISTINCT i, f "
        "MATCH (f)-[:PURCHASED]->(l:Lot)-[:SUPPLIED_BY]->(s:Supplier) "
        "OPTIONAL MATCH (l)-[:ORIGINATES_FROM]->(farm:Farm) "
        "RETURN i.name AS ingredient, f.name AS facility, "
        "       l.lot_id AS lot_id, l.product_name AS product, "
        "       l.harvest_date AS harvest_date, l.use_by AS use_by, "
        "       s.name AS supplier, s.supplier_id AS supplier_id, "
        "       farm.name AS farm "
        "ORDER BY supplier, lot_id"
    )
    return run_read(
        db,
        f"{ingredient_name} -> lots/suppliers",
        cypher,
        {"ingredient": ingredient_name, "facility_ids": facility_ids},
    )


def cluster_by_exposure(db: GraphDB, pathogen: str = "Salmonella") -> QueryOutcome:
    """Community detection (label propagation) over the epidemiological graph.

    FalkorDB's label-propagation algorithm has no relTypes filter, so it runs
    over the whole graph; we then scope the result to cases of one pathogen and
    attach each case's facilities. Cases sharing meals/suppliers fall into the
    same community without us telling the algorithm what a "cluster" is.
    """
    cypher = (
        "CALL algo.labelPropagation({}) YIELD node, communityId "
        "WITH node, communityId "
        "WHERE node.pathogen = $pathogen "
        "MATCH (node)<-[:HAS_CASE]-(p:Person)-[:PARTICIPATED]->(e:ExposureEvent)"
        "-[:AT]->(f:Facility) "
        "RETURN communityId AS community, "
        "       collect(DISTINCT node.case_id) AS cases, "
        "       collect(DISTINCT f.name) AS facilities, "
        "       count(DISTINCT node) AS case_count "
        "ORDER BY case_count DESC"
    )
    return run_read(
        db, "exposure communities", cypher, {"pathogen": pathogen}, algorithm="label-propagation"
    )


def temporal_fit(db: GraphDB, case_id: str, event_id: str, pathogen: str) -> QueryOutcome:
    """Does a meal fall inside the pathogen's incubation window for this case?

    The meal must be on or before the onset date and within the max incubation
    ceiling. This is what refutes the C-104 temporal trap (meal after onset).
    """
    min_date, max_date = onset_window(_case_onset(db, case_id)[0], pathogen)
    cypher = (
        "MATCH (c:Case {case_id:$case_id})<-[:HAS_CASE]-(:Person)"
        "-[:PARTICIPATED]->(e:ExposureEvent {event_id:$event_id}) "
        "RETURN c.case_id AS case_id, c.onset AS onset, e.event_id AS event_id, "
        "       e.date AS meal_date, e.date > c.onset AS meal_after_onset, "
        "       (e.date >= date($min_date) AND e.date <= c.onset) AS within_incubation_window "
    )
    return run_read(
        db,
        f"temporal fit {case_id}/{event_id}",
        cypher,
        {"case_id": case_id, "event_id": event_id, "min_date": min_date},
    )


def valid_exposures(db: GraphDB, case_id: str, pathogen: str) -> QueryOutcome:
    """Only the exposures that sit inside the incubation window (traps excluded)."""
    onset = _case_onset(db, case_id)[0]
    min_date, _ = onset_window(onset, pathogen)
    cypher = (
        "MATCH (c:Case {case_id:$case_id})<-[:HAS_CASE]-(:Person)"
        "-[:PARTICIPATED]->(e:ExposureEvent) "
        "WHERE e.date >= date($min_date) AND e.date <= c.onset "
        "OPTIONAL MATCH (e)-[:AT]->(f:Facility) "
        "RETURN e.event_id AS event_id, e.date AS meal_date, e.kind AS kind, "
        "       e.note AS note, f.name AS facility "
        "ORDER BY e.date"
    )
    return run_read(
        db, f"valid exposures for {case_id}", cypher,
        {"case_id": case_id, "min_date": min_date},
    )


def _case_onset(db: GraphDB, case_id: str) -> tuple[str, str]:
    row = db.ro_query(
        "MATCH (c:Case {case_id:$case_id}) RETURN c.onset AS onset, c.pathogen AS pathogen",
        {"case_id": case_id},
    ).first()
    if not row:
        raise ValueError(f"unknown case_id: {case_id}")
    return row["onset"], row["pathogen"]


# ------------------------------------------------------------------ laboratory
def lot_source_ranking(db: GraphDB, pathogen: str = "Salmonella") -> QueryOutcome:
    """Rank lots by how many patients their source isolate matches, with SNP distances.

    This is the genomic smoking gun: a food isolate within a couple of SNPs of
    many patient isolates is effectively the outbreak strain.
    """
    cypher = (
        "MATCH (source:Isolate)-[:SAMPLED_FROM]->(l:Lot) "
        "MATCH (source)<-[m:MATCHES]-(piso:Isolate)<-[:LINKED_ISOLATE]-(c:Case {pathogen:$pathogen}) "
        "RETURN l.lot_id AS lot_id, l.product_name AS product, "
        "       source.isolate_id AS source_isolate, "
        "       count(DISTINCT c) AS matched_cases, "
        "       min(m.snp_distance) AS min_snp, max(m.snp_distance) AS max_snp, "
        "       round(avg(m.snp_distance) * 100.0) / 100.0 AS avg_snp, "
        "       collect(DISTINCT c.case_id) AS case_ids "
        "ORDER BY matched_cases DESC, avg_snp ASC"
    )
    return run_read(db, "lot genomic ranking", cypher, {"pathogen": pathogen})


def match_isolates(db: GraphDB, isolate_id: str) -> QueryOutcome:
    """Direct genomic neighbours of an isolate, with SNP distances and linked cases."""
    cypher = (
        "MATCH (a:Isolate {isolate_id:$isolate_id})-[m:MATCHES]-(b:Isolate) "
        "OPTIONAL MATCH (b)<-[:LINKED_ISOLATE]-(c:Case) "
        "OPTIONAL MATCH (b)-[:SAMPLED_FROM]->(l:Lot) "
        "OPTIONAL MATCH (b)<-[:DETECTED]-(w:WastewaterSite) "
        "RETURN b.isolate_id AS matched_isolate, b.source_kind AS source_kind, "
        "       b.pathogen AS pathogen, b.strain AS strain, "
        "       m.snp_distance AS snp_distance, "
        "       collect(DISTINCT c.case_id) AS cases, "
        "       collect(DISTINCT l.lot_id) AS lots, "
        "       collect(DISTINCT w.name) AS wastewater_sites "
        "ORDER BY snp_distance"
    )
    return run_read(db, f"matches for {isolate_id}", cypher, {"isolate_id": isolate_id})


def wastewater_detections(db: GraphDB) -> QueryOutcome:
    """Wastewater detections of the outbreak strain — early environmental signal."""
    cypher = (
        "MATCH (w:WastewaterSite)-[d:DETECTED]->(iso:Isolate) "
        "RETURN w.name AS site, w.zone AS zone, iso.isolate_id AS isolate, "
        "       iso.pathogen AS pathogen, iso.strain AS strain, d.on AS detected_on "
        "ORDER BY detected_on"
    )
    return run_read(db, "wastewater detections", cypher)
