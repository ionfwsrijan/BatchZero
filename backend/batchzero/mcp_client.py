"""A real MCP client that spawns the BatchZero MCP server over stdio.

The agent never touches FalkorDB directly — it discovers and invokes tools
through MCP (:func:`list_tools` / :func:`call_tool`), exactly as an external
MCP host would. Each role gets its own server process with its own tool-set
and its own provenance scope (``BATCHZERO_SESSION_ID``).
"""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import get_default_environment, stdio_client

from .config import get_settings

BACKEND_DIR = str(Path(__file__).resolve().parents[1])


def server_params(
    *,
    tenant: str,
    role: str,
    session_id: str | None = None,
    investigation_id: str | None = None,
    log_calls: bool = True,
    python: str | None = None,
) -> StdioServerParameters:
    env = dict(get_default_environment())
    env.update(
        {
            "BATCHZERO_TENANT": tenant,
            "BATCHZERO_ROLE": role,
            "BATCHZERO_LOG_CALLS": "1" if log_calls else "0",
        }
    )
    # MCP's safe inherited-environment allowlist omits app-specific settings.
    # Pass the active graph connection explicitly so tool writes land in the
    # same tenant database queried by the API and shown in the UI.
    settings = get_settings()
    env["FALKORDB_HOST"] = settings.falkordb_host
    env["FALKORDB_PORT"] = str(settings.falkordb_port)
    if settings.falkordb_password:
        env["FALKORDB_PASSWORD"] = settings.falkordb_password
    else:
        env.pop("FALKORDB_PASSWORD", None)
    if session_id:
        env["BATCHZERO_SESSION_ID"] = session_id
    if investigation_id:
        env["BATCHZERO_INVESTIGATION_ID"] = investigation_id
    return StdioServerParameters(
        command=python or sys.executable,
        args=["-m", "batchzero.mcp_server"],
        env=env,
        cwd=BACKEND_DIR,
    )


class MCPToolSession:
    """Async context manager wrapping one stdio MCP connection."""

    def __init__(self, params: StdioServerParameters | None = None, **kwargs: Any):
        self._params = params or server_params(**kwargs)
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self.tools: list[dict[str, Any]] = []
        self.server_info: Any = None
        self.instructions: str | None = None

    async def __aenter__(self) -> "MCPToolSession":
        # One stack per session: enter and exit happen in the same task.
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(self._params))
            session = await stack.enter_async_context(ClientSession(read, write))
            init = await session.initialize()
            listed = await session.list_tools()
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        self._session = session
        self.server_info = init
        self.instructions = getattr(init, "instructions", None)
        self.tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.input_schema,
            }
            for t in listed.tools
        ]
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            stack, self._stack = self._stack, None
            self._session = None
            await stack.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        return self.tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke a tool and return its JSON payload (plus a transport guard)."""
        if self._session is None:
            raise RuntimeError("MCPToolSession is not connected")
        result = await self._session.call_tool(name, arguments or {})
        raw = ""
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text:
                raw = text
                break
        if getattr(result, "isError", False):
            return {"ok": False, "tool": name, "error": raw or "tool error"}
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            payload = {"ok": True, "tool": name, "text": raw}
        if isinstance(payload, dict):
            payload.setdefault("tool", name)
        return payload
