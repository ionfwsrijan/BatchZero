"""API tests: read endpoints + the SSE agent stream.

The stream test runs a two-role investigation (intake -> cluster, enough to
produce hypotheses) against a dedicated tenant and asserts the SSE life-cycle.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from batchzero.api.app import app
from batchzero.db import GraphDB
from batchzero.seed import seed_ops_tenant

TENANT = "batchzero_api_test"
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def seeded():
    db = GraphDB(TENANT)
    db.delete_graph()
    seed_ops_tenant(db)


def test_health_and_config():
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["falkordb"] is True
    cfg = client.get("/api/config").json()
    assert [r["key"] for r in cfg["roles"]] == ["intake", "cluster", "tracer", "briefing"]


def test_cases_and_search():
    assert client.get("/api/cases").json()["count"] == 11
    hits = client.post("/api/search", json={"query": "MG-4417", "tenant": TENANT}).json()
    assert hits["count"] >= 1


def test_role_toolsets_are_scoped():
    roles = {r["key"]: r["tools"] for r in client.get("/api/agents/roles").json()["roles"]}
    assert "draft_recall" in roles["briefing"]
    assert "draft_recall" not in roles["cluster"]


def test_investigation_stream_and_detail():
    events = []
    with client.stream(
        "POST", "/api/investigations/stream", json={"tenant": TENANT, "roles": ["intake", "cluster"]}
    ) as resp:
        assert resp.status_code == 200
        current = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((current, json.loads(line.split("data:", 1)[1].strip())))

    kinds = [k for k, _ in events]
    assert "investigation" in kinds and "done" in kinds
    assert events.count(("role_start", events[0][1])) == 0 or {"intake", "cluster"} <= {
        e["role"] for k, e in events if k == "role_start"
    }
    inv_id = next(e["inv_id"] for k, e in events if k == "investigation")

    detail = client.get(f"/api/investigations/{inv_id}", params={"tenant": TENANT}).json()
    assert any(h["status"] in ("open", "likely", "confirmed") for h in detail["hypotheses"])

    graph = client.get(f"/api/investigations/{inv_id}/graph", params={"tenant": TENANT}).json()
    assert len(graph["nodes"]) >= 1


def test_missing_investigation_404():
    resp = client.get("/api/investigations/INV-DOES-NOT-EXIST", params={"tenant": TENANT})
    assert resp.status_code == 404
