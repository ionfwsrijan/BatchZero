# BatchZero — Demo Script (≈3 minutes)

A tight script for the submission video. Times are targets, not rules.

---

### 0:00 — The hook (15s)

> "Salmonella is spreading in Port Meridian. Eleven confirmed cases, three
> restaurants, 48 hours on the clock. The question is one lot, one supplier,
> and one decision: **what do we recall?**"

Show the running UI with an empty case file.

## 0:15 — It's a graph problem

> "Every case is a trail: person → exposure → dish → ingredient → lot →
> supplier → shipment → farm. BatchZero runs that investigation as four agents
> in protocol order, and every answer is a live FalkorDB traversal."

Click **Run investigation**. The left pane fills with role cards and tool calls
streaming in over SSE; the graph pane populates as hypotheses and evidence land.

## 0:40 — The tie that a count can't break

> "Intake finds the shared exposure. But watch: *Microgreens Mix* and *Romaine
> Lettuce* are each in **11 of 11** cases. Two suppliers tie too. Counting
> can't decide this."

Point at the two hypotheses (both `open`).

## 1:00 — Genomics breaks it

> "The Cluster Analyst calls `lot_source_ranking` and `match_isolates`. The
> environmental isolate from lot **MG-4417** matches patient isolates across all
> 11 cases at ≤2 SNPs. The lettuce isolate matches **nothing**."

The Microgreens hypothesis jumps to `likely`; the lettuce hypothesis drops to
`refuted`.

## 1:20 — Temporal hygiene

> "One exposure record is logged *after* symptom onset. `temporal_fit` rejects
> it inside the incubation window — a stale row can't mislead the agent."

## 1:35 — Trace it upstream

> "The Tracer walks `MG-4417` back through its shipment to the farm, and audits
> the cold chain — a 12.8 °C breach on shipment SH-2291. Then it checks the
> supplier's history: a 2025 incident with the same distributor."

The hypothesis upgrades to **confirmed**. A recall node appears, scoped to
`MG-4417`; inspection tasks are assigned to named inspectors.

## 2:00 — Provenance (the anti-hallucination move)

Click the confirmed hypothesis node. The right pane shows each piece of
evidence; hover one and note it cites the **exact tool call** that produced it.

> "Nothing is asserted without a traversal behind it. Every claim is a chain:
> hypothesis → evidence → tool call → session. You can replay it."

Click through the graph: Investigation → Hypothesis → Evidence → ToolCall.

## 2:20 — It never fails live

> "No key? The agent replays a deterministic plan — still **50 real MCP tool
> calls** against FalkorDB. Same graph, same answer, every time."

Run `python -m batchzero.demo.replay --benchmark 3` in a terminal; show
`correct source identification: 3/3`.

## 2:40 — Wrap

> "BatchZero: four agents, one protocol, a load-bearing graph, and a decision
> you can defend line by line. The source was lot **MG-4417**."

---

### Backup talking points (Q&A)

- **Why FalkorDB?** The shared-exposure intersection, the supply trace, the
  genomic match graph, and the provenance chain are all natural traversals; the
  graph algorithms (betweenness, label propagation) find chokepoints and
  communities that no table query surfaces cleanly.
- **Why four roles?** Mirrors a real incident command, and role-scoped MCP
  tool-sets make the protocol enforceable: only the Briefing role can file a
  recall.
- **Is it live or scripted?** Both share one loop. Set `GROQ_API_KEY` and a
  model drives the same tool calls; without it the deterministic plan runs.
- **Multi-tenant?** One FalkorDB graph per agency; tenant injected into each MCP
  subprocess so sessions can't read across tenants.
