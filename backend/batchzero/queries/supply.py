"""Supply-chain read queries: traces, cold chain, chokepoints, supplier profiles.

These are the Tracer role's traversals — where the investigation crosses from
epidemiology into logistics, and where graph algorithms earn their keep.
"""

from __future__ import annotations

from ..db import GraphDB
from .base import QueryOutcome, run_read


def trace_supply_chain(db: GraphDB, lot_id: str) -> QueryOutcome:
    """Full provenance of a lot: supplier, farm, shipment(s), delivery sites."""
    cypher = (
        "MATCH (l:Lot {lot_id:$lot_id}) "
        "OPTIONAL MATCH (l)-[:SUPPLIED_BY]->(s:Supplier) "
        "OPTIONAL MATCH (l)-[:ORIGINATES_FROM]->(farm:Farm) "
        "OPTIONAL MATCH (l)-[:SHIPPED_IN]->(sh:Shipment) "
        "OPTIONAL MATCH (sh)-[:DELIVERED_TO]->(f:Facility) "
        "OPTIONAL MATCH (l)<-[:PURCHASED]-(pf:Facility) "
        "RETURN l.lot_id AS lot_id, l.product_name AS product, "
        "       l.harvest_date AS harvest_date, l.use_by AS use_by, "
        "       s.name AS supplier, s.supplier_id AS supplier_id, "
        "       farm.name AS farm, farm.practice AS farm_practice, "
        "       collect(DISTINCT sh.shipment_id) AS shipments, "
        "       collect(DISTINCT f.name) AS delivered_to, "
        "       collect(DISTINCT pf.name) AS purchased_by"
    )
    return run_read(db, f"supply chain of {lot_id}", cypher, {"lot_id": lot_id})


def facility_sources(db: GraphDB, facility_id: str) -> QueryOutcome:
    """Every lot a facility purchased, with suppliers and farms behind them."""
    cypher = (
        "MATCH (f:Facility {facility_id:$facility_id})-[:PURCHASED]->(l:Lot)"
        "-[:SUPPLIED_BY]->(s:Supplier) "
        "OPTIONAL MATCH (l)-[:ORIGINATES_FROM]->(farm:Farm) "
        "OPTIONAL MATCH (l)-[:SHIPPED_IN]->(sh:Shipment) "
        "RETURN l.lot_id AS lot_id, l.product_name AS product, l.use_by AS use_by, "
        "       s.name AS supplier, s.supplier_id AS supplier_id, "
        "       farm.name AS farm, collect(DISTINCT sh.shipment_id) AS shipments "
        "ORDER BY s.name, l.lot_id"
    )
    return run_read(db, f"sources of {facility_id}", cypher, {"facility_id": facility_id})


def cold_chain(db: GraphDB, shipment_id: str) -> QueryOutcome:
    """Temperature trace of a shipment with a breach flag computed in-graph.

    Peak/min are computed with ``reduce`` (FalkorDB has no scalar max over a
    collected list), and excursions are the readings above the 4C cold-chain limit.
    """
    cypher = (
        "MATCH (sh:Shipment {shipment_id:$shipment_id})-[:HAS_READING]->(r:TemperatureReading) "
        "WITH sh, collect(r) AS readings "
        "RETURN sh.shipment_id AS shipment_id, sh.carrier AS carrier, "
        "       sh.depart AS depart, sh.arrive AS arrive, "
        "       sh.breached AS declared_breach, sh.temp_max_c AS declared_max, "
        "       reduce(m = 0.0, x IN readings | CASE WHEN x.celsius > m THEN x.celsius ELSE m END) AS peak_c, "
        "       reduce(m = 999.0, x IN readings | CASE WHEN x.celsius < m THEN x.celsius ELSE m END) AS min_c, "
        "       size(readings) AS readings, "
        "       [x IN readings WHERE x.celsius > 4.0 | toString(x.at) + ' @ ' + toString(x.celsius) + 'C'] AS excursions "
    )
    return run_read(db, f"cold chain {shipment_id}", cypher, {"shipment_id": shipment_id})


def lot_cold_chain(db: GraphDB, lot_id: str) -> QueryOutcome:
    """Cold-chain status of every shipment that carried a given lot."""
    cypher = (
        "MATCH (l:Lot {lot_id:$lot_id})-[:SHIPPED_IN]->(sh:Shipment) "
        "OPTIONAL MATCH (sh)-[:HAS_READING]->(r:TemperatureReading) "
        "WITH sh, l, collect(r) AS readings "
        "RETURN l.lot_id AS lot_id, sh.shipment_id AS shipment_id, "
        "       sh.carrier AS carrier, sh.depart AS depart, sh.arrive AS arrive, "
        "       sh.breached AS breached, "
        "       reduce(m = 0.0, x IN readings | CASE WHEN x.celsius > m THEN x.celsius ELSE m END) AS peak_c, "
        "       size(readings) AS readings "
        "ORDER BY sh.depart"
    )
    return run_read(db, f"cold chain for lot {lot_id}", cypher, {"lot_id": lot_id})


def find_chokepoints(db: GraphDB, top: int = 10) -> QueryOutcome:
    """Betweenness centrality over the whole graph — structural chokepoints.

    The entity with the highest betweenness is the bridge everything routes
    through: in a supply network that is the lot/shipment to inspect first.
    """
    cypher = (
        "CALL algo.betweenness({}) YIELD node, score "
        "WHERE score > 0 "
        "RETURN labels(node)[0] AS label, "
        "       coalesce(node.name, node.case_id, node.lot_id, node.shipment_id, "
        "                node.supplier_id, node.facility_id, node.farm_id, "
        "                node.isolate_id, node.event_id, node.menu_id, node.ingredient_id) AS ident, "
        "       round(score * 100.0) / 100.0 AS betweenness "
        "ORDER BY score DESC LIMIT $top"
    )
    return run_read(
        db, "supply chokepoints", cypher, {"top": top}, algorithm="betweenness-centrality"
    )


def connected_components(db: GraphDB) -> QueryOutcome:
    """Weakly connected components — the epidemiologically-linked core."""
    cypher = (
        "CALL algo.WCC({}) YIELD node, componentId "
        "WITH node, componentId "
        "WHERE NOT node:ProtocolStep AND NOT node:Fact "
        "RETURN componentId AS component, "
        "       labels(node)[0] AS label, "
        "       coalesce(node.name, node.case_id, node.lot_id, node.shipment_id, "
        "                node.supplier_id, node.facility_id, node.farm_id, "
        "                node.isolate_id, node.event_id, node.menu_id) AS ident "
        "ORDER BY component"
    )
    return run_read(db, "connected components", cypher, algorithm="weakly-connected-components")


def shortest_link(db: GraphDB, a_id: str, b_id: str, max_len: int = 8) -> QueryOutcome:
    """Shortest traversal path between any two entities (algo.SPpaths).

    Works on internal node ids, so the caller resolves labels first via
    ``resolve_entity``.
    """
    cypher = (
        "MATCH (a) WHERE id(a) = $a_id "
        "MATCH (b) WHERE id(b) = $b_id "
        "CALL algo.SPpaths({sourceNode:a, targetNode:b, maxLen:$maxLen, relDirection:'both'}) "
        "YIELD path, pathCost "
        "RETURN [n IN nodes(path) | coalesce(n.name, n.case_id, n.lot_id, n.event_id, "
        "         n.shipment_id, n.supplier_id, n.facility_id, n.farm_id, n.isolate_id, "
        "         n.menu_id, n.ingredient_id, labels(n)[0])] AS path_nodes, "
        "       [r IN relationships(path) | type(r)] AS path_rels, "
        "       pathCost AS hops "
    )
    return run_read(
        db,
        f"link {a_id}->{b_id}",
        cypher,
        {"a_id": a_id, "b_id": b_id, "maxLen": max_len},
        algorithm="shortest-path",
    )


def resolve_entity(db: GraphDB, label: str, key: str, value: str) -> QueryOutcome:
    """Look up one entity by label + identifying property, returning its internal id."""
    cypher = (
        f"MATCH (n:{label}) WHERE n.{key} = $value "
        f"RETURN id(n) AS node_id, labels(n)[0] AS label, "
        f"       coalesce(n.name, n.{key}) AS ident, n AS props LIMIT 1"
    )
    return run_read(db, f"resolve {label}.{key}", cypher, {"value": value})


def supplier_profile(db: GraphDB, supplier_id: str) -> QueryOutcome:
    """Full supplier dossier: lots, deliveries, inspections, prior incidents, facts."""
    cypher = (
        "MATCH (s:Supplier {supplier_id:$supplier_id}) "
        "OPTIONAL MATCH (s)<-[:SUPPLIED_BY]-(l:Lot) "
        "OPTIONAL MATCH (s)-[:SUBJECT_OF]->(insp:Inspection) "
        "OPTIONAL MATCH (s)-[:IMPLICATED_IN]->(pi:PriorIncident) "
        "OPTIONAL MATCH (pi)<-[:WORKED_ON]-(inv:Person) "
        "OPTIONAL MATCH (s)<-[:FACT_ABOUT]-(fact:Fact) "
        "RETURN s.supplier_id AS supplier_id, s.name AS name, s.type AS type, "
        "       s.risk_tier AS risk_tier, "
        "       collect(DISTINCT l.lot_id) AS lots, "
        "       collect(DISTINCT {date: insp.date, score: insp.score, "
        "                          violations: insp.violations}) AS inspections, "
        "       collect(DISTINCT {year: pi.year, summary: pi.summary, "
        "                          outcome: pi.outcome}) AS prior_incidents, "
        "       collect(DISTINCT inv.name) AS investigators, "
        "       collect(DISTINCT fact.statement) AS known_facts"
    )
    return run_read(db, f"supplier {supplier_id}", cypher, {"supplier_id": supplier_id})


def facility_profile(db: GraphDB, facility_id: str) -> QueryOutcome:
    """Facility dossier: inspections, employees, suppliers."""
    cypher = (
        "MATCH (f:Facility {facility_id:$facility_id}) "
        "OPTIONAL MATCH (f)-[:SUBJECT_OF]->(insp:Inspection) "
        "OPTIONAL MATCH (f)-[:EMPLOYS]->(w:Person) "
        "OPTIONAL MATCH (f)-[:PURCHASED]->(l:Lot)-[:SUPPLIED_BY]->(s:Supplier) "
        "RETURN f.facility_id AS facility_id, f.name AS name, f.type AS type, "
        "       f.neighborhood AS neighborhood, f.permit_id AS permit_id, "
        "       collect(DISTINCT {date: insp.date, score: insp.score, "
        "                          violations: insp.violations}) AS inspections, "
        "       collect(DISTINCT w.name) AS staff, "
        "       collect(DISTINCT s.name) AS suppliers"
    )
    return run_read(db, f"facility {facility_id}", cypher, {"facility_id": facility_id})
