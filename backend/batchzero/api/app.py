"""BatchZero's FastAPI layer: read endpoints + Server-Sent-Events agent streams.

The API is thin on purpose — it serves the graph (cases, investigations, the
provenance sub-graph the canvas draws) and it *streams the agent*, turning the
orchestrator's event callbacks into SSE frames so the UI can show each role's
tool calls as they happen rather than after the fact.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .. import tools
from ..agent import ROLES, ROLE_LABEL, run_followup, run_investigation
from ..config import get_settings
from ..db import GraphDB
from ..queries import epidemiology, memory
from ..seed import seed_ops_tenant

settings = get_settings()


class InvestigationRequest(BaseModel):
    message: str | None = None
    title: str | None = None
    tenant: str | None = None
    roles: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    tenant: str | None = None


class SearchRequest(BaseModel):
    query: str
    tenant: str | None = None


def _graph(tenant: str | None = None) -> GraphDB:
    return GraphDB(tenant or settings.tenant_graph)


def _sse(events: AsyncIterator[dict[str, Any]]) -> EventSourceResponse:
    async def generator():
        async for event in events:
            yield {"event": event.get("type", "message"), "data": json.dumps(event, default=str)}

    return EventSourceResponse(generator())


async def _run_stream(coro_factory) -> AsyncIterator[dict[str, Any]]:
    """Bridge an orchestrator ``emit`` callback into an async generator of events."""
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = {"type": "_done"}

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def runner() -> None:
        try:
            await coro_factory(emit)
        except Exception as exc:  # surface, never hang the stream
            await queue.put({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            await queue.put(sentinel)

    task = asyncio.create_task(runner())
    try:
        while True:
            event = await queue.get()
            if event is sentinel:
                break
            yield event
    finally:
        await task


app = FastAPI(title="BatchZero API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    db = _graph()
    return {
        "ok": True,
        "falkordb": db.ping(),
        "graph": db.graph_name,
        "provider": settings.resolved_llm_provider,
        "model": settings.groq_model,
    }


@app.get("/api/config")
def config() -> dict[str, Any]:
    db = _graph()
    return {
        "tenant": db.graph_name,
        "provider": settings.resolved_llm_provider,
        "model": settings.groq_model,
        "roles": [{"key": r, "label": ROLE_LABEL[r]} for r in ROLES],
        "graph": db.stats(),
    }


@app.get("/api/cases")
def cases(pathogen: str = Query("Salmonella")) -> dict[str, Any]:
    res = epidemiology.list_recent_cases(_graph(), pathogen=pathogen)
    return {"pathogen": pathogen, "count": len(res.rows), "rows": res.rows, "ms": res.ms}


@app.get("/api/investigations")
def investigations(tenant: str | None = Query(None)) -> dict[str, Any]:
    res = memory.list_investigations(_graph(tenant))
    return {"count": len(res.rows), "rows": res.rows}


@app.get("/api/investigations/{inv_id}")
def investigation_detail(inv_id: str, tenant: str | None = Query(None)) -> dict[str, Any]:
    db = _graph(tenant)
    if not db.ro_query(
        "MATCH (i:Investigation {inv_id:$inv_id}) RETURN i.inv_id AS inv_id", {"inv_id": inv_id}
    ).rows:
        raise HTTPException(status_code=404, detail=f"investigation {inv_id} not found")
    return memory.investigation_state(db, inv_id)


@app.get("/api/investigations/{inv_id}/graph")
def investigation_graph(
    inv_id: str, tenant: str | None = Query(None), hops: int = 3, limit: int = 400
) -> dict[str, Any]:
    return memory.evidence_subgraph(_graph(tenant), inv_id, hops=hops, limit=limit)


@app.get("/api/graph/summary")
def graph_summary(tenant: str | None = Query(None)) -> dict[str, Any]:
    return memory.graph_stats(_graph(tenant))


@app.get("/api/agents/roles")
def agent_roles() -> dict[str, Any]:
    return {
        "roles": [
            {"key": role, "label": ROLE_LABEL[role], "tools": [t.name for t in tools.tools_for_role(role)]}
            for role in ROLES
        ]
    }


@app.post("/api/search")
def search(req: SearchRequest) -> dict[str, Any]:
    res = memory.search_entities(_graph(req.tenant), req.query)
    return {"query": req.query, "count": len(res.rows), "rows": res.rows}


@app.post("/api/seed")
def seed(tenant: str | None = None) -> dict[str, Any]:
    db = _graph(tenant)
    db.delete_graph()
    seed_ops_tenant(db)
    return {"ok": True, "graph": db.graph_name, **db.stats()}


@app.post("/api/investigations/stream")
def start_investigation(req: InvestigationRequest) -> EventSourceResponse:
    tenant = req.tenant or settings.tenant_graph
    db = _graph(tenant)
    roles = req.roles or ROLES

    async def factory(emit):
        await run_investigation(
            db, tenant=tenant, user_message=req.message, title=req.title, emit=emit, roles=roles
        )

    return _sse(_run_stream(factory))


@app.post("/api/investigations/{inv_id}/chat/stream")
def chat(inv_id: str, req: ChatRequest) -> EventSourceResponse:
    tenant = req.tenant or settings.tenant_graph
    db = _graph(tenant)

    async def factory(emit):
        await run_followup(db, tenant=tenant, inv_id=inv_id, message=req.message, emit=emit)

    return _sse(_run_stream(factory))


def main() -> None:
    import uvicorn

    uvicorn.run("batchzero.api.app:app", host=settings.api_host, port=settings.api_port)


def _mount_ui() -> None:
    """Serve the built React frontend at / when it has been compiled."""
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")


_mount_ui()


if __name__ == "__main__":
    main()

