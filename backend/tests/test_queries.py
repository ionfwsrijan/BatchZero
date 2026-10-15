"""Correctness tests for the BatchZero query layer.

These assert the *investigative* answers, not just that queries run — a query
that returns the wrong source is worse than one that fails. They run against the
seeded FalkorDB instance, so run ``python -m batchzero.seed --reset`` first.
"""

import pytest

from batchzero.db import GraphDB
from batchzero.config import get_settings
from batchzero.queries import actions, epidemiology, memory, protocol, supply


@pytest.fixture(scope="module")
def db():
    return GraphDB(get_settings().tenant_graph)


def test_recent_cases_lists_salmonella_cluster(db):
    res = epidemiology.list_recent_cases(db, pathogen="Salmonella")
    assert len(res.rows) == 11
    assert all(r["pathogen"] == "Salmonella" for r in res.rows)


def test_epi_curve_monotonic_onsets(db):
    res = epidemiology.epi_curve(db, "Salmonella")
    onsets = res.scalars("onset")
    assert onsets == sorted(onsets)
    assert sum(res.scalars("cases")) == 11


def test_common_ingredients_surfaces_microgreens_first(db):
    case_ids = [f"C-{n}" for n in range(101, 112)]
    res = epidemiology.find_common_ingredients(db, case_ids)
    top = res.rows[0]
    # Microgreens AND romaine both appear in every case's meals — the point is
    # they're co-common, so genomics must break the tie.
    assert top["cases"] == 11
    names = {r["ingredient"] for r in res.rows if r["cases"] == 11}
    assert names == {"Microgreens Mix", "Romaine Lettuce"}


def test_common_suppliers_ties_greenleaf_and_valley(db):
    case_ids = [f"C-{n}" for n in range(101, 112)]
    res = epidemiology.find_common_suppliers(db, case_ids)
    top2 = {r["supplier"] for r in res.rows[:2]}
    # Decoy confirmed: two suppliers both reach all three facilities.
    assert top2 == {"GreenLeaf Distributors", "Valley Field Farms"}


def test_genomic_ranking_is_decisive(db):
    """The food-isolate match is what separates the real source from the decoy."""
    res = epidemiology.lot_source_ranking(db, "Salmonella")
    top = res.rows[0]
    assert top["lot_id"] == "MG-4417"
    assert top["matched_cases"] == 11
    assert top["max_snp"] <= 2  # all patients within 2 SNPs of the food isolate


def test_supply_chain_reaches_source(db):
    res = supply.trace_supply_chain(db, "MG-4417")
    row = res.rows[0]
    assert row["supplier"] == "GreenLeaf Distributors"
    assert row["farm"] == "Sunrise Hydroponics"
    assert "SH-2291" in row["shipments"]
    assert set(row["delivered_to"]) == {"Harbor Grill", "Noodle Atlas", "Green Fork Cafe"}


def test_cold_chain_detects_breach(db):
    res = supply.cold_chain(db, "SH-2291")
    row = res.rows[0]
    assert row["peak_c"] == 12.8
    assert row["declared_breach"] is True
    assert len(row["excursions"]) >= 2


def test_chokepoints_rank_implicated_lot_and_shipment(db):
    res = supply.find_chokepoints(db, top=5)
    idents = [r["ident"] for r in res.rows[:3]]
    # Betweenness puts the implicated lot/shipment at the structural centre.
    assert "MG-4417" in idents
    assert "SH-2291" in idents


def test_temporal_fit_refutes_traps(db):
    # C-104's E-104b meal is AFTER onset -> must be flagged as outside the window.
    res = epidemiology.temporal_fit(db, "C-104", "E-104b", "Salmonella")
    row = res.rows[0]
    assert row["meal_after_onset"] is True
    assert row["within_incubation_window"] is False
    # Its earlier meal E-104a IS within the window.
    ok = epidemiology.temporal_fit(db, "C-104", "E-104a", "Salmonella").rows[0]
    assert ok["within_incubation_window"] is True


def test_valid_exposures_drop_post_onset_meal(db):
    res = epidemiology.valid_exposures(db, "C-104", "Salmonella")
    ids = res.scalars("event_id")
    assert "E-104b" not in ids
    assert "E-104a" in ids


def test_clusters_group_by_facility(db):
    res = epidemiology.cluster_by_exposure(db, "Salmonella")
    facility_sets = [set(r["facilities"]) for r in res.rows]
    # Harbor Grill diners form their own community.
    assert {"Harbor Grill"} in facility_sets
    total_cases = sum(r["case_count"] for r in res.rows)
    assert total_cases == 11


def test_shortest_link_between_two_cases(db):
    a = supply.resolve_entity(db, "Case", "case_id", "C-101").first()["node_id"]
    b = supply.resolve_entity(db, "Case", "case_id", "C-105").first()["node_id"]
    res = supply.shortest_link(db, a, b)
    path = res.rows[0]
    assert path["hops"] >= 1
    assert "C-101" in path["path_nodes"] and "C-105" in path["path_nodes"]


def test_supplier_profile_surfaces_history(db):
    res = supply.supplier_profile(db, "S-GLD")
    row = res.rows[0]
    assert row["name"] == "GreenLeaf Distributors"
    assert any("cilantro" in (pi["summary"] or "").lower() for pi in row["prior_incidents"])
    assert "Miriam Okafor" in row["investigators"]
    assert any("cold-chain" in f.lower() for f in row["known_facts"])


def test_protocol_is_a_linked_chain(db):
    res = protocol.get_protocol(db)
    assert len(res.rows) == 7
    assert res.rows[0]["step_id"] == "PS-1"
    assert res.rows[0]["next_step"] == "PS-2"
    assert res.rows[6]["next_step"] is None


def test_actions_evidence_provenance_chain(db):
    inv = actions.open_investigation(db, "test-chain")
    hyp = actions.add_hypothesis(db, inv["inv_id"], "test hypothesis")
    tc = actions.record_tool_call(db, "S-TEST", "test_tool", {"a": 1}, "ok", 1.5)
    ev = actions.attach_evidence(
        db, hyp["hyp_id"], "genomic", "unit-test evidence", supports=True,
        about_label="Lot", about_value="MG-4417", tool_call_id=tc,
    )
    # verify the chain Hypothesis->Evidence->ToolCall and ABOUT->Lot
    chain = db.ro_query(
        "MATCH (h:Hypothesis {hyp_id:$h})-[:SUPPORTED_BY]->(e:Evidence {evidence_id:$e})"
        "-[:DERIVED_FROM]->(tc:ToolCall {tool_call_id:$t}) "
        "MATCH (e)-[:ABOUT]->(l:Lot {lot_id:'MG-4417'}) RETURN h.hyp_id, e.evidence_id",
        {"h": hyp["hyp_id"], "e": ev["evidence_id"], "t": tc},
    )
    assert len(chain.rows) == 1
    # cleanup
    db.query(
        "MATCH (h:Hypothesis {hyp_id:$h}) DETACH DELETE h "
        "WITH 1 AS x MATCH (e:Evidence {evidence_id:$e}) DETACH DELETE e "
        "WITH 1 AS x MATCH (t:ToolCall {tool_call_id:$t}) DETACH DELETE t "
        "WITH 1 AS x MATCH (i:Investigation {inv_id:$i}) DETACH DELETE i",
        {"h": hyp["hyp_id"], "e": ev["evidence_id"], "t": tc, "i": inv["inv_id"]},
    )


def test_tenant_isolation():
    ops = GraphDB(get_settings().tenant_graph)
    train = GraphDB(get_settings().training_tenant_graph)
    ops_ids = set(ops.ro_query("MATCH (n) RETURN coalesce(n.case_id, n.facility_id, n.name) AS k").scalars("k"))
    train_ids = set(train.ro_query("MATCH (n) RETURN coalesce(n.case_id, n.facility_id, n.name) AS k").scalars("k"))
    # The two tenants share no entities: per-tenant graph isolation.
    assert not (ops_ids & train_ids)
    train_facility = train.ro_query("MATCH (f:Facility) RETURN f.name AS n").scalars("n")
    assert "Riverside Bistro" in train_facility
    assert "Harbor Grill" not in train_facility
