"""Investigation orchestration: the four roles, in protocol order.

Intake -> Cluster Analyst -> Supply Chain Tracer -> Briefing Officer, each a
separate MCP session with its own tool-set, handing off through the graph
(``Session -[:HANDOFF]-> Session``) and through the brief each role produces.
The orchestrator is also what the API drives for a chat turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

from ..config import get_settings
from ..db import GraphDB
from ..queries import actions, memory
from .llm import BaseLLM, make_llm
from .loop import RoleResult, run_role_session
from .prompts import followup_task, handoff_note

Emit = Callable[[dict[str, Any]], Awaitable[None]]

ROLES = ["intake", "cluster", "tracer", "briefing"]

ROLE_LABEL = {
    "intake": "Intake Officer",
    "cluster": "Cluster Analyst",
    "tracer": "Supply Chain Tracer",
    "briefing": "Briefing Officer",
}

STAGE_BY_ROLE = {
    "intake": "hypotheses",
    "cluster": "hypotheses",
    "tracer": "testing",
    "briefing": "control",
}

PREVIOUS_ROLE = {"cluster": "intake", "tracer": "cluster", "briefing": "tracer"}

DEFAULT_CASE_IDS = [f"C-1{n:02d}" for n in range(1, 12)]

DEFAULT_TITLE = "Salmonellosis cluster — Port Meridian, October 2026"


@dataclass
class InvestigationRun:
    inv_id: str
    title: str
    roles: list[RoleResult] = field(default_factory=list)
    brief: str = ""
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_calls(self) -> int:
        return sum(r.tool_calls for r in self.roles)


def _session_id(role: str) -> str:
    return f"ses-{role}-{uuid4().hex[:10]}"


def build_task(role: str, inv_id: str, user_message: str | None, briefs: dict[str, str]) -> str:
    if role == "intake":
        opening = user_message or (
            "A cluster of gastrointestinal illness has been reported in Port Meridian. "
            "Eleven laboratory-confirmed Salmonella cases since late September."
        )
        return (
            f"{opening}\n\n"
            f"Investigation id: {inv_id}. Case ids in scope: {', '.join(DEFAULT_CASE_IDS)}.\n"
            "Establish the case and the shared-exposure picture; do not conclude a source."
        )
    previous = PREVIOUS_ROLE.get(role)
    context = handoff_note(previous, briefs.get(previous, "no brief produced")) if previous else ""
    objective = {
        "cluster": "Test candidate sources against the shared-exposure picture and record "
                   "hypotheses with evidence. Break any exposure ties with genomics, and run "
                   "temporal checks so stale exposure records cannot mislead you.",
        "tracer": "Trace the leading source lot upstream through shipments, farms and the "
                  "distributor; verify the cold chain and history; file the action tasks.",
        "briefing": "Compile the decision brief: causal chain, confidence, evidence integrity, "
                    "actions and the recall. Persist the summary and the institutional fact.",
    }[role]
    return f"Investigation id: {inv_id}.\n\n{context}\n\nTASK: {objective}"


async def run_investigation(
    db: GraphDB,
    *,
    tenant: str,
    user_message: str | None = None,
    title: str | None = None,
    emit: Emit | None = None,
    llm_factory: Callable[[str, str, dict[str, str]], BaseLLM] | None = None,
    roles: list[str] | None = None,
    inv_id: str | None = None,
) -> InvestigationRun:
    roles = roles or ROLES
    llm_factory = llm_factory or (lambda role, iid, briefs: make_llm(role, iid, briefs))
    if inv_id:
        inv = {"inv_id": inv_id, "title": title or DEFAULT_TITLE}
    else:
        inv = actions.open_investigation(db, title or DEFAULT_TITLE, priority="high")
    run = InvestigationRun(inv_id=inv["inv_id"], title=inv.get("title", title or DEFAULT_TITLE))

    briefs: dict[str, str] = {}
    previous_session: str | None = None
    if emit:
        await emit({"type": "investigation", "inv_id": run.inv_id, "title": run.title})

    for role in roles:
        session_id = _session_id(role)
        actions.set_investigation_stage(db, run.inv_id, STAGE_BY_ROLE.get(role, "intake"))
        result = await run_role_session(
            db=db,
            tenant=tenant,
            inv_id=run.inv_id,
            role=role,
            task=build_task(role, run.inv_id, user_message if role == "intake" else None, briefs),
            llm=llm_factory(role, run.inv_id, briefs),
            session_id=session_id,
            emit=emit,
            handoff_from=previous_session,
        )
        briefs[role] = result.content
        previous_session = session_id
        run.roles.append(result)

    run.brief = briefs.get(roles[-1], "")
    run.state = memory.investigation_state(db, run.inv_id)
    if emit:
        await emit({
            "type": "done",
            "inv_id": run.inv_id,
            "brief": run.brief,
            "tool_calls": run.tool_calls,
        })
    return run


def route_role(message: str) -> str:
    """Cheap intent router for chat follow-ups on an existing investigation."""
    text = message.lower()
    if any(k in text for k in ("trace", "supply", "farm", "shipment", "cold", "distributor", "recall")):
        return "tracer"
    if any(k in text for k in ("case", "exposure", "cluster", "genomic", "isolate", "hypothesis", "strain")):
        return "cluster"
    if any(k in text for k in ("intake", "new cluster", "new cases")):
        return "intake"
    return "briefing"


def route_roles(message: str) -> list[str]:
    """Which role(s) to run for a chat follow-up."""
    return [route_role(message)]


async def run_followup(
    db: GraphDB,
    *,
    tenant: str,
    inv_id: str,
    message: str,
    emit: Emit | None = None,
    llm_factory: Callable[[str, str, dict[str, str]], BaseLLM] | None = None,
) -> RoleResult:
    """Route one chat follow-up to the right role, against the existing case file."""
    llm_factory = llm_factory or (lambda role, iid, briefs: make_llm(role, iid, briefs))
    role = route_role(message)
    session_id = _session_id(role)
    if emit:
        await emit({"type": "routing", "role": role, "session_id": session_id})
    result = await run_role_session(
        db=db,
        tenant=tenant,
        inv_id=inv_id,
        role=role,
        task=followup_task(message, inv_id, {}),
        llm=llm_factory(role, inv_id, {}),
        session_id=session_id,
        emit=emit,
    )
    return result


def load_state(db: GraphDB, inv_id: str) -> dict[str, Any]:
    return memory.investigation_state(db, inv_id)


def default_tenant() -> str:
    return get_settings().tenant_graph
