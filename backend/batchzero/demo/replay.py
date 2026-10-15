"""BatchZero demo + benchmark.

``python -m batchzero.demo.replay`` re-runs the full four-role investigation
against FalkorDB and prints a live transcript — every role, every MCP tool call,
every hypothesis upgrade — so the result is reproducible from a clean clone.

``python -m batchzero.demo.replay --benchmark 3`` runs it several times and
prints correctness/latency metrics (handy for the submission notes).
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

from ..agent import ROLE_LABEL, run_investigation
from ..agent.llm import BaseLLM, make_llm
from ..db import GraphDB
from ..seed import seed_ops_tenant


def _llm_factory(live: bool):
    """Deterministic by default; the live provider only when explicitly asked."""

    def factory(role: str, inv_id: str, briefs: dict[str, str]) -> BaseLLM:
        return make_llm(role, inv_id, briefs, provider="groq" if live else "mock")

    return factory


def _banner() -> None:
    print("=" * 64)
    print("  BatchZero — outbreak source investigation")
    print("=" * 64)


async def _emit(event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "investigation":
        print(f"\n[{event['inv_id']}] {event['title']}")
    elif kind == "role_start":
        print(f"\n▶ {ROLE_LABEL.get(event['role'], event['role'])}  ({len(event['tools'])} tools)")
    elif kind == "tool":
        status = "✓" if event.get("ok", True) else "✗"
        ms = f"{round(event['ms'])}ms" if event.get("ms") else ""
        rows = f" [{event['row_count']} rows]" if event.get("row_count") is not None else ""
        print(f"   {status} {event['tool']}{rows} {ms}")
    elif kind == "role_end":
        print(f"   ↳ brief ready ({event['tool_calls']} tool calls)")


async def replay(tenant: str, fresh: bool = True, live: bool = False) -> dict[str, Any]:
    db = GraphDB(tenant)
    if fresh:
        db.delete_graph()
    seed_ops_tenant(db)
    _banner()
    run = await run_investigation(db, tenant=tenant, emit=_emit, llm_factory=_llm_factory(live))
    print("\n" + "=" * 64)
    print("  BRIEF — Briefing Officer")
    print("=" * 64)
    print(run.brief.strip())
    return run.state


async def run_once(tenant: str, fresh: bool = True) -> tuple[Any, float]:
    db = GraphDB(tenant)
    if fresh:
        db.delete_graph()
    seed_ops_tenant(db)
    start = time.perf_counter()
    run = await run_investigation(db, tenant=tenant, llm_factory=_llm_factory(False))
    return run, (time.perf_counter() - start) * 1000.0


async def benchmark(tenant: str, runs: int) -> None:
    print(f"Running {runs} investigation(s) against '{tenant}'…\n")
    header = f"{'run':>3}  {'tools':>5}  {'ms':>7}  {'main':>10}  {'decoy':>10}  {'recall':>6}  {'tasks':>5}  ok"
    print(header)
    print("-" * len(header))
    confirmed = 0
    for i in range(1, runs + 1):
        run, ms = await run_once(tenant)
        hyps = run.state["hypotheses"]
        main = next((h for h in hyps if "MG-4417" in (h.get("statement") or "")), {})
        decoy = next((h for h in hyps if "LET-2210" in (h.get("statement") or "")), {})
        lots = {lot for r in run.state["recalls"] for lot in r["lots"]}
        ok = main.get("status") == "confirmed" and decoy.get("status") == "refuted"
        confirmed += int(ok)
        print(
            f"{i:>3}  {run.tool_calls:>5}  {round(ms):>7}  "
            f"{main.get('status', '?'):>10}  {decoy.get('status', '?'):>10}  "
            f"{('MG-4417' in lots):>6}  {len(run.state['tasks']):>5}  {'✓' if ok else '✗'}"
        )
    print("-" * len(header))
    print(f"correct source identification: {confirmed}/{runs}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BatchZero demo / benchmark")
    parser.add_argument("--tenant", default="pmph_ops")
    parser.add_argument("--benchmark", type=int, default=0, help="run N times and report metrics")
    parser.add_argument("--keep", action="store_true", help="do not reset the graph first")
    parser.add_argument("--live", action="store_true", help="use the live LLM instead of the plan")
    args = parser.parse_args()

    if args.benchmark:
        asyncio.run(benchmark(args.tenant, args.benchmark))
    else:
        asyncio.run(replay(args.tenant, fresh=not args.keep, live=args.live))


if __name__ == "__main__":
    main()
