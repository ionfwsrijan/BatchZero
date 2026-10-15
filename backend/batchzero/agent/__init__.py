"""BatchZero agent: MCP-driven tool loop, role orchestration, memory writes."""

from .llm import BaseLLM, GroqLLM, LLMResponse, MockLLM, ToolCall, make_llm
from .loop import RoleResult, run_role_session
from .orchestrator import (
    InvestigationRun,
    ROLES,
    ROLE_LABEL,
    route_role,
    run_followup,
    run_investigation,
)

__all__ = [
    "BaseLLM",
    "GroqLLM",
    "LLMResponse",
    "MockLLM",
    "ToolCall",
    "make_llm",
    "RoleResult",
    "run_role_session",
    "InvestigationRun",
    "ROLES",
    "ROLE_LABEL",
    "route_role",
    "run_followup",
    "run_investigation",
]
