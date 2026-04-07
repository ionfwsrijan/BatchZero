"""API tests: read endpoints + the SSE agent stream.

The stream test runs a two-role investigation (intake -> cluster, enough to
produce hypotheses) against a dedicated tenant and asserts the SSE life-cycle.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from batchzero.api.app import InvestigationRequest, app
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
    ready = client.get("/api/ready")
    assert ready.status_code == 200 and ready.json()["ready"] is True
    cfg = client.get("/api/config").json()
    assert [r["key"] for r in cfg["roles"]] == ["intake", "cluster", "tracer", "briefing"]


def test_invalid_tenant_and_traversal_params_are_rejected():
    # Tenant names become FalkorDB graph keys: reject separators/spaces.
    assert client.get("/api/investigations", params={"tenant": "bad tenant"}).status_code == 422
    assert client.post("/api/search", json={"query": "MG-4417", "tenant": "../etc"}).status_code == 422
    # Traversal depth/limit are bounded so one request cannot walk the graph.
    graph = client.get("/api/investigations/INV-X/graph", params={"tenant": TENANT, "hops": 99})
    assert graph.status_code == 422
    graph = client.get("/api/investigations/INV-X/graph", params={"tenant": TENANT, "limit": 5000})
    assert graph.status_code == 422
    # The pathogen label is interpolated into the case query: bound it too.
    assert client.get("/api/cases", params={"pathogen": ""}).status_code == 422


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


def test_investigation_roles_are_validated_and_deduplicated():
    resp = client.post(
        "/api/investigations/stream", json={"tenant": TENANT, "roles": ["intake", "intkae"]}
    )
    assert resp.status_code == 422
    assert "unknown role" in resp.text
    assert InvestigationRequest(roles=["intake", "intake", "cluster"]).roles == ["intake", "cluster"]


def test_request_bodies_are_bounded():
    too_long = "x" * 4_001
    assert (
        client.post(
            "/api/investigations/stream", json={"tenant": TENANT, "message": too_long}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/investigations/stream", json={"tenant": TENANT, "title": "x" * 201}
        ).status_code
        == 422
    )
    assert client.post("/api/search", json={"query": "", "tenant": TENANT}).status_code == 422
    assert (
        client.post("/api/search", json={"query": "x" * 201, "tenant": TENANT}).status_code == 422
    )
    assert (
        client.post(
            "/api/investigations/INV-X/chat/stream", json={"tenant": TENANT, "message": ""}
        ).status_code
        == 422
    )


def test_health_is_liveness_and_ready_is_readiness(monkeypatch):
    # Simulate FalkorDB being unreachable: liveness stays 200, readiness fails.
    monkeypatch.setattr("batchzero.api.app._probe", lambda tenant=None: (False, "pmph_ops"))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is False and health.json()["falkordb"] is False

    ready = client.get("/api/ready")
    assert ready.status_code == 503
    assert ready.headers["Retry-After"] == "5"
    assert ready.json() == {"ready": False, "falkordb": False, "graph": "pmph_ops"}


def test_graph_outage_returns_503_not_500(monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    def boom(tenant=None):
        raise RedisConnectionError("connection refused")

    monkeypatch.setattr("batchzero.api.app._graph", boom)
    resp = client.get("/api/config")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"
    body = resp.json()
    assert body["detail"] == "graph database unavailable"
    assert body["error"] == "ConnectionError"
