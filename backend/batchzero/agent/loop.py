"""The agent tool-loop: one role-session, MCP-driven, provenance-logged.

Flow per step:
  LLM(messages, tools-discovered-via-MCP) -> tool calls -> MCP call_tool ->
  JSON result -> back into the conversation (and into the graph as a ToolCall).

The loop is transport-honest: tools are discovered from the MCP server, not
hard-coded, so the role's capability surface is whatever its MCP server exposes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..db import GraphDB
from ..mcp_client import MCPToolSession
from ..queries import actions
from .llm import BaseLLM, LLMResponse
from .prompts import system_prompt

Emit = Callable[[dict[str, Any]], Awaitable[None]]
MAX_TOOL_CHARS = 20000  # keep big tool payloads out of the context window


@dataclass
class RoleResult:
    role: str
    session_id: str
    content: str
    tool_calls: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)


async def _noop(_event: dict[str, Any]) -> None:
    return None


async def run_role_session(
    *,
    db: GraphDB,
    tenant: str,
    inv_id: str,
    role: str,
    task: str,
    llm: BaseLLM,
    session_id: str,
    emit: Emit | None = None,
    handoff_from: str | None = None,
    max_steps: int = 40,
) -> RoleResult:
    emit = emit or _noop
    events: list[dict[str, Any]] = []
    actions.record_session(db, inv_id, session_id, role)
    if handoff_from:
        actions.handoff(db, handoff_from, session_id, reason=f"protocol handoff to {role}")
    actions.record_message(db, session_id, "user", task)

    result = RoleResult(role=role, session_id=session_id, content="")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(role, db, inv_id)},
        {"role": "user", "content": task},
    ]

    async with MCPToolSession(
        tenant=tenant, role=role, session_id=session_id, investigation_id=inv_id
    ) as mcp:
        await _publish(emit, events, {
            "type": "role_start",
            "role": role,
            "session_id": session_id,
            "tools": [t["name"] for t in mcp.tools],
            "provider": llm.provider,
        })

        for step in range(max_steps):
            response: LLMResponse = await llm.complete(messages, mcp.tools)
            if response.content:
                await _publish(emit, events, {
                    "type": "assistant",
                    "role": role,
                    "step": step,
                    "content": response.content,
                })
            if not response.tool_calls:
                result.content = response.content or ""
                break

            messages.append(_assistant_message(response))
            for call in response.tool_calls:
                payload = await mcp.call_tool(call.name, call.arguments)
                result.tool_calls += 1
                await _publish(emit, events, {
                    "type": "tool",
                    "role": role,
                    "tool": call.name,
                    "args": call.arguments,
                    "ok": payload.get("ok", True),
                    "ms": payload.get("ms"),
                    "title": payload.get("title"),
                    "row_count": payload.get("row_count"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "error": payload.get("error"),
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _clip(json.dumps(payload, default=str)),
                })
        else:
            result.content = "Reached step limit without a final message."

    if result.content:
        actions.record_message(db, session_id, "assistant", result.content)
    await _publish(emit, events, {
        "type": "role_end",
        "role": role,
        "session_id": session_id,
        "content": result.content,
        "tool_calls": result.tool_calls,
    })
    result.events = events
    return result


def _assistant_message(response: LLMResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in response.tool_calls
        ]
    return message


def _clip(text: str) -> str:
    if len(text) <= MAX_TOOL_CHARS:
        return text
    return '{"ok": true, "truncated": true, "note": "payload exceeded context cap"}'


async def _publish(emit: Emit, events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    events.append(event)
    await emit(event)
