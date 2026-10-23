# BatchZero — Submission Form Answers

<!-- Last updated: 23 October 2026 -->

Copy-paste-ready answers for the **Graph Hacks 2026 · FalkorDB track** submission
form (WeMakeDevs). Repo: <https://github.com/ionfwsrijan/BatchZero>.

---

## Part 1 — Project details

**Project title**
```
BatchZero — Outbreak source investigation as a four-role agent graph
```

**Description** *(what problem it solves, and who it is for)*
```
When a foodborne-illness cluster lands on a public-health desk, investigators have 48 hours to answer one question: what do we recall? BatchZero answers it. Eleven lab-confirmed Salmonella Enteritidis cases across three restaurants tie two ingredients and two suppliers at 11/11 each — counts alone cannot decide. BatchZero runs four specialist agents (intake, cluster, tracer, briefing) in protocol order over a FalkorDB graph of the cases, exposures, supply chain and lab isolates, breaks the tie with genomics (0–2 SNPs), rejects a post-onset exposure trap, and returns a confirmed source at 96% confidence plus a lot-scoped recall — where every sentence traces back to the exact Cypher call that produced it.

It is for epidemiologists and outbreak-response teams who need audit-grade reasoning, and for anyone building agents that must act on connected data rather than summarize documents.
```

**Track** *(select all that apply)*
```
☑ Track 01 — Agents That Act on Connected Data
☑ Track 02 — Agent Memory and Coordination
```

**Repository**
```
https://github.com/ionfwsrijan/BatchZero
```

**Demo video** *(YouTube link, public or unlisted)*
```
https://youtu.be/XXXXXXXXXXX
```
> Upload `docs/demo.mp4` (90s, 4K @ 60fps) to YouTube first, then paste the link.

**Live demo or deployment**
```
https://batchzero.onrender.com/
```
> Free Render instance; ~60s cold start after 15 min idle. It reseeds itself on
> boot, so the demo is always in a known state.

**How did you use FalkorDB? What technical problems did you solve with it?**
```
FalkorDB is the product, not the storage layer. Remove it and five core capabilities become impossible, not slow:

1. Set intersection as a pattern. "Which ingredient is common to all 11 cases?" is one Cypher traversal (Person→Case→ExposureEvent→MenuItem→Ingredient→Lot→Supplier). In SQL it is a pile of self-joins per hop, and the count-tie (2 ingredients × 2 suppliers at 11/11) is invisible in the result shape.
2. Recall scope is a traversal. Walking lot MG-4417 upstream to its farm and downstream to every plate is a variable-length path — the natural unit of a food recall.
3. Graph algorithms are findings, not garnish. algo.labelPropagation (exposure communities), algo.betweenness (structural chokepoint to inspect first), algo.SPpaths (shortest causal link) and algo.WCC all run directly in Cypher.
4. Reasoning lives in the same graph. Hypothesis→Evidence→ToolCall→Session is a first-class provenance subgraph, so any claim can be replayed to the exact query behind it.
5. Multi-tenancy is free: one graph per agency (pmph_ops, training_academy), so scoping is a connection parameter rather than row-level security. Each role-scoped MCP subprocess gets the tenant's FalkorDB connection explicitly.

26 node labels, 40 relationship types; 4 agents × ~50 real MCP tool calls per run; 36 tests and a 3/3 correctness benchmark run against a live FalkorDB in CI.
```

**Blog link** *(optional — best blog post wins AirPods 5)*
```
https://___________
```
> Optional; leave empty if there is no published post.

---

## Part 2 — Feedback

**What did you like about FalkorDB?**
```
Three things. First, algorithms inline: label propagation and betweenness run as part of the query, so "the graph is the analysis" — no separate analytics store or library round-trip. Second, the Redis wire protocol made operations trivial — redis-cli works for healthchecks, CI spins up a FalkorDB service container in seconds, and existing Redis tooling just works. Third, graph-per-database gave us multi-tenancy almost for free: each tenant gets a named graph, and scoping is a connection parameter rather than a WHERE clause on every query. It also starts fast enough that the whole 36-test suite runs against a real graph offline in ~30 seconds — no mocks of the database layer anywhere in the project.
```

**What improvements would you like to see in FalkorDB?**
```
1. Persistence and backup ergonomics — clearer docs on RDB/AOF trade-offs for graph workloads and a documented snapshot/restore workflow, since agent provenance data is now primary data, not cache.
2. Per-graph resource controls — memory/usage limits per database (like Redis maxmemory policy, but per graph) so a noisy tenant or a runaway variable-length traversal cannot affect others.
3. Query profiling for openCypher — a friendlier EXPLAIN/PROFILE output (row counts and timing per step) to show where variable-length paths blow up, the number-one performance cliff on any graph DB.
4. Broader Cypher coverage docs — an explicit compatibility matrix of clauses and aggregations versus Neo4j, so teams porting queries know what to expect up front.
```

---

## Remaining step

Only the YouTube upload (and the optional blog post) are user-side. Everything
else above is final and verified against the live deployment.
