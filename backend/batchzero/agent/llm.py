"""Provider-agnostic LLM access for the agent loop.

``GroqLLM`` talks to the Groq OpenAI-compatible endpoint (live runs, demos with
a key). ``MockLLM`` replays a deterministic role plan (offline runs, tests,
demos that must never fail mid-presentation) — both return the same
:class:`LLMResponse` shape, so the tool loop is provider-agnostic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import get_settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""


class BaseLLM:
    """Minimal chat interface: messages + tools in, content/tool-calls out."""

    provider = "base"
    model = ""

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        raise NotImplementedError


# --------------------------------------------------------------------- groq
class GroqLLM(BaseLLM):
    provider = "groq"

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str | None = None):
        from openai import AsyncOpenAI

        settings = get_settings()
        self.model = model or settings.groq_model
        self._client = AsyncOpenAI(
            api_key=api_key or settings.groq_api_key,
            base_url=base_url or settings.openai_base_url,
            max_retries=1,  # free-tier 429s should surface fast; FallbackLLM takes over
        )

    async def complete(self, messages, tools):
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["inputSchema"],
                },
            }
            for t in tools
        ]
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0.15}
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"
        resp = await self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LLMResponse(content=msg.content, tool_calls=calls, model=self.model)


# ------------------------------------------------------------------- hybrid
class FallbackLLM(BaseLLM):
    """Live-then-deterministic: use the provider until it fails, then continue.

    Groq's free tier caps tokens-per-minute, so a long tool loop can hit a 429
    mid-run. Rather than break a live demo, this wrapper transparently switches
    to the deterministic role plan for the rest of the session — state carries
    over because the plan derives its progress from the tool results already in
    the conversation.
    """

    provider = "groq->mock"

    def __init__(self, primary: BaseLLM, fallback: BaseLLM):
        self._primary: BaseLLM | None = primary
        self._fallback = fallback
        self.model = primary.model

    async def complete(self, messages, tools):
        if self._primary is not None:
            try:
                return await self._primary.complete(messages, tools)
            except Exception as exc:  # noqa: BLE001 - any provider failure
                import sys

                print(f"[llm] live provider unavailable ({type(exc).__name__}); "
                      f"continuing on the deterministic plan", file=sys.stderr)
                self._primary = None
        return await self._fallback.complete(messages, tools)


# --------------------------------------------------------------------- mock
StepFn = Callable[[dict[str, Any]], dict[str, Any]]
FinalFn = Callable[[dict[str, Any]], str]


@dataclass
class ScriptStep:
    """One planned tool call. ``args`` may be a dict or a builder(history)."""

    tool: str
    args: dict[str, Any] | StepFn = field(default_factory=dict)
    note: str | None = None


def history_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Tool results keyed by tool name (last call wins) — the mock's memory."""
    history: dict[str, Any] = {}
    for message in messages:
        if message.get("role") != "tool":
            continue
        try:
            payload = json.loads(message.get("content") or "{}")
        except ValueError:
            continue
        name = payload.get("tool")
        if name:
            history[name] = payload
    return history


class MockLLM(BaseLLM):
    """Deterministic plan replayer: every tool round advances one script step.

    Progress is derived from the number of tool results already in the
    conversation, so it behaves like a real loop without any state of its own.
    """

    provider = "mock"

    def __init__(self, script: list[ScriptStep], final: str | FinalFn, model: str = "batchzero-plan-v1"):
        self.script = script
        self.final = final
        self.model = model

    async def complete(self, messages, tools):
        history = history_from_messages(messages)
        done = sum(1 for m in messages if m.get("role") == "tool")
        if done < len(self.script):
            step = self.script[done]
            available = {t["name"] for t in tools}
            if step.tool not in available:
                # Role scope changed mid-run: skip rather than fail the loop.
                skipped = ScriptStep(tool=step.tool, args=step.args, note=None)
                return LLMResponse(
                    content=None,
                    tool_calls=[ToolCall(id=f"call_{done}", name=skipped.tool, arguments=self._resolve(skipped, history))],
                    model=self.model,
                )
            args = self._resolve(step, history)
            return LLMResponse(
                content=step.note,
                tool_calls=[ToolCall(id=f"call_{done + 1}", name=step.tool, arguments=args)],
                model=self.model,
            )
        final = self.final(history) if callable(self.final) else self.final
        return LLMResponse(content=final, model=self.model)

    @staticmethod
    def _resolve(step: ScriptStep, history: dict[str, Any]) -> dict[str, Any]:
        return step.args(history) if callable(step.args) else dict(step.args)


# ------------------------------------------------------------------ factory
def make_llm(
    role: str = "intake",
    inv_id: str = "",
    briefs: dict[str, str] | None = None,
    provider: str | None = None,
) -> BaseLLM:
    """Groq when a key is configured (with a deterministic safety net), else the plan."""
    settings = get_settings()
    provider = (provider or settings.llm_provider).lower()
    from .scripts import role_plan

    plan = role_plan(role, inv_id, briefs or {})
    if provider == "groq" and settings.groq_api_key:
        return FallbackLLM(GroqLLM(), plan)

    return plan


__all__ = [
    "BaseLLM",
    "FallbackLLM",
    "GroqLLM",
    "LLMResponse",
    "MockLLM",
    "ScriptStep",
    "ToolCall",
    "history_from_messages",
    "make_llm",
    "StepFn",
    "FinalFn",
]
