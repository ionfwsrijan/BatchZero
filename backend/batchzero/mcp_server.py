"""BatchZero MCP server.

Speaks MCP over stdio, so the same server can be driven by the in-process
agent (via :mod:`batchzero.mcp_client`) or attached to Claude Desktop /
any other MCP host.

The tenant, session and working role are injected through environment
variables when the process is spawned, which is what makes the tool-set and
the provenance logging (``ToolCall`` nodes) session-scoped::

    BATCHZERO_TENANT=pmph_ops
    BATCHZERO_SESSION_ID=<uuid>
    BATCHZERO_ROLE=cluster            # intake | cluster | tracer | briefing
    BATCHZERO_INVESTIGATION_ID=INV-.. # optional
    BATCHZERO_LOG_CALLS=0             # optional, disable provenance writes
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase, FuncMetadata
from pydantic import create_model

from .config import get_settings
from .db import GraphDB
from .tools import ToolContext, execute, tools_for_role

ROLE_INSTRUCTIONS = {
    "intake": (
        "You are BatchZero's Intake Officer. Establish the case: list recent cases, "
        "build the epidemic curve, describe cases, and identify shared exposures and "
        "facilities. Open the investigation and attach the cases to it. Do not "
        "conclude a source yet — collect the shared-exposure picture first."
    ),
    "cluster": (
        "You are BatchZero's Cluster Analyst. Test candidate sources: intersect "
        "ingredients/facilities, rank lots by genomic match, run temporal-fit checks "
        "to reject post-onset exposure records, and record hypotheses with supporting "
        "or contradicting evidence (always pass the tool_call_id of the read that "
        "produced the finding)."
    ),
    "tracer": (
        "You are BatchZero's Supply Chain Tracer. Follow lots back through "
        "shipments, farms and suppliers; check cold-chain breaches and inspection "
        "history; use chokepoints and shortest_link to explain how the contaminated "
        "product reached the implicated facilities. Record hypotheses and evidence."
    ),
    "briefing": (
        "You are BatchZero's Briefing Officer. Compile what the investigation has "
        "established into a decision-ready brief: the causal chain, the confidence, "
        "the actions (tasks, recalls) and their justification. Only state what the "
        "record supports."
    ),
}


def build_server() -> tuple[MCPServer, ToolContext]:
    settings = get_settings()
    role = os.environ.get("BATCHZERO_ROLE", "cluster")
    tenant = os.environ.get("BATCHZERO_TENANT", settings.tenant_graph)
    session_id = os.environ.get("BATCHZERO_SESSION_ID") or None
    inv_id = os.environ.get("BATCHZERO_INVESTIGATION_ID") or None
    log_calls = os.environ.get("BATCHZERO_LOG_CALLS", "1") != "0"

    ctx = ToolContext(
        db=GraphDB(tenant),
        session_id=session_id,
        investigation_id=inv_id,
        role=role,
        log_calls=log_calls,
    )

    server = MCPServer(
        name="batchzero",
        title="BatchZero Outbreak Investigation Toolkit",
        instructions=ROLE_INSTRUCTIONS.get(role, ROLE_INSTRUCTIONS["cluster"]),
    )

    # ToolManager derives input_schema/arg validation from the Python signature;
    # BatchZero tools are dynamic, so both are rebuilt from tools.py's JSON schema.
    def _make_handler(tool_name: str):
        def handler(**kwargs):
            # absent == "use the Python default", so strip explicit nulls
            return execute(ctx, tool_name, {k: v for k, v in kwargs.items() if v is not None})

        handler.__name__ = tool_name
        handler.__doc__ = None
        return handler

    for spec in tools_for_role(role):
        registered = server._tool_manager.add_tool(
            _make_handler(spec.name),
            name=spec.name,
            description=spec.description,
            structured_output=False,
        )
        registered.parameters = spec.parameters
        registered.fn_metadata = FuncMetadata(arg_model=_arg_model(spec.name, spec.parameters))

    return server, ctx


_JSON_TYPES = {"string": str, "number": float, "integer": int, "boolean": bool, "array": list, "object": dict}


def _arg_model(name: str, schema: dict) -> type[ArgModelBase]:
    """Build the pydantic argument model the MCP server validates calls against."""
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}
    for prop, prop_schema in schema.get("properties", {}).items():
        py_type = _JSON_TYPES.get(prop_schema.get("type"), Any)
        if prop in required:
            fields[prop] = (py_type, ...)
        else:
            fields[prop] = (py_type | None, None)
    return create_model(f"{name}Arguments", __base__=ArgModelBase, **fields)

    return server, ctx


async def _run() -> None:
    server, _ctx = build_server()
    await server.run_stdio_async()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
