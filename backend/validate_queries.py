"""Live validation of BatchZero's core investigative queries."""
import sys
sys.path.insert(0, ".")
from batchzero.db import GraphDB

db = GraphDB("pmph_ops")

def show(title, cypher, params=None):
    print(f"\n=== {title} ===")
    try:
        r = db.ro_query(cypher, params or {})
        for row in r.rows[:12]:
            print("  ", row)
        print(f"  ({len(r.rows)} rows, {r.ms:.1f}ms)")
    except Exception as e:
        print("  ERR:", str(e)[:200])

# 1. Common ingredients among salmonellosis cases
show("Common ingredients (salmonella cases)", """
MATCH (c:Case {pathogen:'Salmonella'})<-[:HAS_CASE]-(p:Person)-[:PARTICIPATED]->(e:ExposureEvent)-[:INVOLVES]->(m:MenuItem)-[:CONTAINS]->(i:Ingredient)
RETURN i.name AS ingredient, count(DISTINCT c) AS cases
ORDER BY cases DESC
""")

# 2. Common suppliers across the 3 implicated facilities
show("Common suppliers across 3 facilities", """
MATCH (f:Facility)<-[:PURCHASED]-(l:Lot)-[:SUPPLIED_BY]->(s:Supplier)
WHERE f.facility_id IN ['F-HG','F-NA','F-GF']
RETURN s.name AS supplier, count(DISTINCT f) AS facilities, collect(DISTINCT l.lot_id) AS lots
ORDER BY facilities DESC
""")

# 3. Lot-level: which lot's food isolate matches the most salmonella patients
show("Food isolate -> lot, matched patients + SNP", """
MATCH (source:Isolate)-[:SAMPLED_FROM]->(l:Lot)
MATCH (source)<-[m:MATCHES]-(piso:Isolate)<-[:LINKED_ISOLATE]-(c:Case {pathogen:'Salmonella'})
RETURN l.lot_id AS lot, count(DISTINCT c) AS matched_cases, min(m.snp_distance) AS min_snp, max(m.snp_distance) AS max_snp
ORDER BY matched_cases DESC
""")

# 4. Cold chain for the implicated lot
show("Cold chain of MG-4417", """
MATCH (l:Lot {lot_id:'MG-4417'})-[:SHIPPED_IN]->(s:Shipment)
MATCH (s)-[:HAS_READING]->(r:TemperatureReading)
RETURN s.shipment_id, s.breached AS breached, s.temp_max_c AS tmax, max(r.celsius) AS peak_reading, count(r) AS readings
""")

# 5. Full multi-hop supply chain from implicated lot
show("MG-4417 -> supplier -> farm", """
MATCH (l:Lot {lot_id:'MG-4417'})-[:SUPPLIED_BY]->(s:Supplier)-[:IMPLICATED_IN]->(pi:PriorIncident)
MATCH (l)-[:ORIGINATES_FROM]->(f:Farm)
MATCH (l)-[:SHIPPED_IN]->(sh:Shipment)
RETURN s.name AS supplier, f.name AS farm, sh.shipment_id, sh.breached, pi.summary
""")

# 6. Temporal trap: cases whose recorded meal is after onset
show("Temporal traps (meal after onset)", """
MATCH (c:Case)<-[:HAS_CASE]-(p:Person)-[part:PARTICIPATED]->(e:ExposureEvent)
WHERE e.date > c.onset
RETURN c.case_id, c.onset, e.event_id, e.date AS meal_date, part.role
""")

# 7. Incubation-window-fit exposures (meal within 6-72h before onset) per case
show("Valid exposures (meal 6-72h before onset)", """
MATCH (c:Case {pathogen:'Salmonella'})<-[:HAS_CASE]-(p:Person)-[:PARTICIPATED]->(e:ExposureEvent)
WHERE e.date >= c.onset AND duration.between(e.date, c.onset).hours >= 6 AND duration.between(e.date, c.onset).hours <= 72
RETURN c.case_id, e.event_id, e.date, c.onset, duration.between(e.date, c.onset).hours AS incubation_h
ORDER BY c.case_id
""")

# 8. Algorithms
show("WCC components", "CALL algo.WCC({}) YIELD node, componentId RETURN node.name AS name, labels(node)[0] AS label, componentId ORDER BY componentId")
show("labelPropagation", "CALL algo.labelPropagation({}) YIELD node, communityId RETURN node.name AS name, labels(node)[0] AS label, communityId")
show("pageRank on Lot/SUPPLIED_BY", "CALL algo.pageRank('Lot','SUPPLIED_BY') YIELD node, score WHERE node.lot_id IS NOT NULL RETURN node.lot_id AS lot, score ORDER BY score DESC")
show("betweenness (top)", "CALL algo.betweenness({}) YIELD node, score RETURN node.name AS name, labels(node)[0] AS label, score ORDER BY score DESC LIMIT 8")

# 9. Shortest path between two cases through exposure graph
show("Shortest path C-101 <-> C-105", """
MATCH (a:Case {case_id:'C-101'}), (b:Case {case_id:'C-105'})
MATCH path = shortestPath((a)-[*1..8]-(b))
RETURN [n IN nodes(path) | coalesce(n.name, n.case_id, n.lot_id, labels(n)[0])] AS path_nodes, length(path) AS hops
""")

# 10. Prior incident memory
show("Supplier prior incidents + worked_on", """
MATCH (s:Supplier {name:'GreenLeaf Distributors'})-[r:IMPLICATED_IN]->(pi:PriorIncident)
OPTIONAL MATCH (p:Person)-[:WORKED_ON]->(pi)
RETURN s.name, pi.year, pi.summary, collect(p.name) AS investigators
""")
print("\nDONE")
