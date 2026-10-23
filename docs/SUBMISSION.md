# BatchZero — Submission Guide & Rubric Map

**Graph Hacks 2026 · FalkorDB track · team ApexCoders**
<!-- Last updated: 23 October 2026 -->

This document is the judge-facing index. It says what BatchZero is, how to run
it in one minute, where every requirement is satisfied, and how to verify each
claim yourself.

---

## 1 — TL;DR

**Live:** <https://batchzero.onrender.com/> — the whole stack in one container
(free tier; ~60s cold start if it has gone to sleep).

BatchZero is an **outbreak source-investigation agent** that runs a real
foodborne-illness case end to end over **FalkorDB**. Four role-scoped agents
(Intake Officer → Cluster Analyst → Supply Chain Tracer → Briefing Officer) work
in protocol order over real **MCP** subprocesses. Every answer is a live Cypher
traversal; every conclusion is written back as a node with a provenance chain
down to the tool call that produced it.

**The demo moment:** the shared-exposure intersection returns *two* ingredients
and two suppliers, each present in **11/11 cases**. Counting cannot break the
tie. Genomics does: the isolate from lot `MG-4417` matches all 11 cases at ≤2
SNPs, the competing lettuce lot matches nothing. One hypothesis goes
**confirmed 0.96**, the other **refuted 0.05**, and a recall is scoped to a
single lot.

**Run it in one line each** (FalkorDB must be up — see Quickstart):

```bash
python -m batchzero.demo.replay            # watch the whole investigation
python -m batchzero.demo.replay --benchmark 3   # correctness + latency
```

**Or run the whole stack as one container** (FalkorDB included, no external DB):
`docker build -f deploy/Dockerfile -t batchzero . && docker run -p 8000:8000 batchzero`
— the same image `render.yaml` deploys as a free Render web service.

---

## Track fit — scored requirements, mapped

| Requirement | Where it is satisfied | Evidence |
|-------------|----------------------|----------|
| **Document the graph data model** | `README.md` → *Graph data model*; `docs/GRAPH_MODEL.md` (26 labels, 40 rel types) | `backend/batchzero/schema.py` is authoritative |
| **Show key Cypher / queries** | `README.md` → *Key Cypher*; `backend/batchzero/queries/` (pure functions) | 5 highlighted patterns incl. intersection, `reduce` cold chain, provenance replay |
| **Architecture diagram** | `README.md` → *Architecture*; `docs/ARCHITECTURE.md` (Mermaid + prose) | 5 layers: db → queries → tools → MCP → agent/API |
| **Use graph algorithms** | `algo.betweenness`, `algo.labelPropagation`, `algo.SPpaths`, `algo.WCC` | `queries/supply.py:121`, `queries/epidemiology.py:175` |
| **Graph is load-bearing** | Removing FalkorDB makes 4 core capabilities *impossible*, not slow | `README.md` → *Why this is a graph problem* |
| **Multi-tenant** | One FalkorDB graph per agency (`pmph_ops`, `training_academy`) | `config.py`, `BATCHZERO_TENANT` injected per MCP subprocess |
| **Reproducible demo** | Deterministic plan drives the same loop; no key required | `agent/scripts.py`, `tests/conftest.py` pins `LLM_PROVIDER=mock` |
| **Demo video** | `docs/demo.mp4` — 90s, 4K @ 60fps: architecture, data model, live UI investigation, benchmark + test output | Recorded end-to-end against the running stack |
| **Live LLM path** | Groq (OpenAI-compatible) with automatic deterministic fallback | `agent/llm.py` → `GroqLLM`, `FallbackLLM`, `make_llm` |
| **Tests** | 36 tests offline against a live FalkorDB | `backend/tests/` |
| **Live deployment** | Running at <https://batchzero.onrender.com/> — one container (FalkorDB + API + built UI), free Render web service from `render.yaml` | `deploy/Dockerfile`, `deploy/start.sh`, `render.yaml` |
| **Agentic / tool use** | Real MCP stdio subprocesses, role-scoped tool-sets | `mcp_server.py`, `mcp_client.py`, `tools.py` |
| **Explainable output** | Provenance chain on every claim | `Hypothesis→Evidence→ToolCall→Session` |

---

## The graph is load-bearing (the central claim)

BatchZero is not "an app with a database." Delete FalkorDB and four
capabilities do not degrade — they vanish:

1. **Epidemiology is a set intersection over a path.**
   `Person→Case→ExposureEvent→MenuItem→Ingredient→Lot→Supplier` — "which
   ingredient is common to *all* 11 cases" is one Cypher pattern
   (`README.md` Key Cypher #1). In a relational model it is a nested self-join
   per hop, and the count-tie problem it exposes is invisible in the SQL result
   *shape*.
2. **Traceability is a variable-length traversal.** Walking a lot upstream to
   farm and downstream to every plate (`queries/supply.py`) is the natural unit
   of a recall.
3. **The algorithms are findings, not garnish.** `algo.betweenness` names the
   structural chokepoint to inspect first; `algo.labelPropagation` finds the
   exposure communities; `algo.SPpaths` finds the shortest causal link between
   any two entities.
4. **Reasoning is stored in the same graph.** Hypothesis/Evidence/ToolCall/Session
   form a first-class provenance graph, so *any* claim is replayable. A
   traditional RAG stack discards exactly this.

---

## Feature inventory (code pointers)

| Feature | Implementation |
|---------|----------------|
| FalkorDB access layer (query, ro_query, JSON serialization) | `backend/batchzero/db.py` |
| Schema, indexes, incubation windows as data | `backend/batchzero/schema.py` |
| Synthetic Port Meridian fixture (134 nodes, 197 edges) | `backend/batchzero/seed.py` |
| Epi / exposure / genomic queries | `backend/batchzero/queries/epidemiology.py` |
| Supply trace, cold chain, betweenness, components, shortest link | `backend/batchzero/queries/supply.py` |
| Recall, dossiers, subgraph, digest, stats | `backend/batchzero/queries/memory.py` |
| Protocol steps + handoffs | `backend/batchzero/queries/protocol.py` |
| Every write (hypothesis, evidence, task, recall, fact, tool call) | `backend/batchzero/queries/actions.py` |
| 40-tool registry + role-scoped tool-sets | `backend/batchzero/tools.py` |
| Real stdio MCP server (per-role) | `backend/batchzero/mcp_server.py` |
| Agent-side MCP session/host | `backend/batchzero/mcp_client.py` |
| LLM interface (Groq, Mock, Fallback) | `backend/batchzero/agent/llm.py` |
| Deterministic 4-role plans | `backend/batchzero/agent/scripts.py` |
| Shared tool loop | `backend/batchzero/agent/loop.py` |
| 4-role orchestrator + chat routing | `backend/batchzero/agent/orchestrator.py:89` |
| FastAPI read endpoints + SSE streams | `backend/batchzero/api/app.py` |
| React + cytoscape investigation console | `frontend/src/` |
| Reproducible live transcript + benchmark | `backend/batchzero/demo/replay.py` |

---

## 5-minute judge walkthrough

**Fastest path:** open <https://batchzero.onrender.com/> and click **Run
investigation** — no install, no key. Everything below reproduces it locally.

```bash
# 1. Graph up
docker compose up -d falkordb

# 2. Backend
cd backend
python -m venv .venv && .\.venv\Scripts\Activate.ps1   # Windows
pip install -e ".[dev]"
python -m batchzero.seed --reset

# 3. Watch the investigation (no key needed)
python -m batchzero.demo.replay

# 4. Prove it: correctness + latency over N clean runs
python -m batchzero.demo.replay --benchmark 3

# 5. Serve API + UI
python -m batchzero.api.app        # http://localhost:8000
```

Then in the UI: **Run investigation** → watch the four role cards fill with live
tool calls → click the **confirmed hypothesis** → see evidence cite the exact
`ToolCall` → note the recall scoped to `MG-4417`.

Or open the FalkorDB Browser at `http://localhost:3000` and run the queries from
`README.md` → *Key Cypher* directly.

---

## Reproducibility & determinism

- **Same answer, every time.** `demo/replay.py` defaults to the deterministic
  plan; `--benchmark N` re-seeds a clean graph between runs and reports
  correctness + latency.
- **Tests are offline and hermetic.** `tests/conftest.py` pins `LLM_PROVIDER=mock`
  before importing the package and forks each suite onto its own seeded tenant
  (`batchzero_query_test`, `batchzero_mcp_test`), so results never depend on a
  network or on other tests.
- **The live path is a swap, not a rewrite.** `make_llm` returns `GroqLLM` when a
  key exists and the deterministic plan otherwise; both drive the *same* loop
  (`agent/loop.py`). A `FallbackLLM` catches provider errors (e.g. free-tier
  `429`) and finishes the session deterministically, so a live demo is never
  interrupted.

---

## Limitations & honest framing

BatchZero is a working prototype benchmarked on a synthetic fixture. We would
rather state its limits plainly than let a reviewer discover them:

- **The outbreak is synthetic.** *Port Meridian* is a hand-built, internally
  consistent fixture (134 nodes / 197 edges). The 3/3 benchmark measures
  **determinism and correctness on that fixture** — the same input always
  produces the same traceable answer — not epidemiological validity on real
  public-health data. The graph engineering under test (traversal, tie-breaking
  by genomic distance, temporal rejection, provenance) is fixture-independent.
- **The default deployment uses the deterministic provider.** `LLM_PROVIDER=mock`
  on the live instance gives every visitor the same reproducible run with no API
  key; a key swaps in `GroqLLM` over the same tool loop.
- **The live instance is a free tier.** It sleeps after ~15 minutes idle, so the
  first request can take ~60s; it reseeds on boot and is never left broken.
- **The UI is intentionally dense.** It is an operations console, not a consumer
  app; some labels are small at 100% browser zoom.

What would make it production-grade: real (or de-identified public) outbreak
data, an epidemiological review of the protocol, and human sign-off before any
recall is filed.

---

## Metrics (from `--benchmark`)

| Metric | Value |
|--------|-------|
| Correct source identified | **3/3** clean runs |
| Tool calls per full investigation | ~50 (real MCP calls) |
| Roles / sessions per run | 4 |
| Main hypothesis | `confirmed`, confidence **0.96** (lot `MG-4417`) |
| Decoy hypothesis | `refuted`, confidence **0.05** (lot `LET-2210`) |
| Recall scope | `['MG-4417']` |
| Tasks created | 3 (inspection + follow-up) |
| Fixture size | 134 nodes / 197 edges |
| Tests | 36 passing |
| Per-run latency (deterministic, full 4 roles) | 4.9 – 5.5 s |

---

## Repository map

```
batchzero/
├─ README.md                 # overview, graph model, key Cypher, quickstart
├─ docs/
│  ├─ GRAPH_MODEL.md         # full node/relationship catalogue + ER diagram
│  ├─ ARCHITECTURE.md        # layered design + sequence diagrams
│  ├─ demo.mp4               # 90s, 4K @ 60fps demo of the working project
│  └─ SUBMISSION.md          # this file — judge guide + rubric map
├─ backend/                  # FastAPI + FalkorDB + MCP + agent runtime
│  └─ batchzero/  tests/  pyproject.toml
├─ frontend/                 # React + cytoscape console (Vite)
├─ deploy/                   # single container: FalkorDB + API + built UI
├─ render.yaml               # free Render blueprint for the hosted demo
├─ docker-compose.yml        # FalkorDB (dev)
└─ Makefile                  # one-word targets for common tasks
```

---

## How we used FalkorDB specifically

- **Native graph traversals** for the intersection, the supply trace, the cold
  chain, and the provenance chain.
- **Built-in graph algorithms** (`betweenness`, `labelPropagation`, `SPpaths`,
  `WCC`) surfaced as investigative findings.
- **Graph-per-tenant isolation** using FalkorDB's multi-graph keyspace.
- **Range + fulltext indexes** created idempotently by `schema.ensure_schema`
  for the frequent lookups and the semantic-recall tool.
- **The agent's own memory is a graph** — the same instance holds the outbreak
  and the reasoning, which is what makes every answer auditable.
