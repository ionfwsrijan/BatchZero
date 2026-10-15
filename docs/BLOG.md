# Building BatchZero: an outbreak investigator that thinks in graph

*Graph Hacks 2026 — FalkorDB track.*

We didn't want to build "an LLM that talks to a database." We wanted to build
the thing that only exists *because* of the database. So we picked a domain
where the data is irreducibly a graph and the stakes are real: **foodborne
outbreak source investigation**.

## The question is a traversal

When people start getting sick from the same food, an investigator's job is a
chain: *which cases → where did they eat → what did they eat → what ingredients
→ which lots → which supplier → which shipment → which farm*. In SQL that's a
pile of self-joins. In Cypher it's:

```cypher
MATCH (c:Case)-[:INVOLVES|CONTAINS*..]->(ing:Ingredient)
WHERE c.case_id IN $case_ids
WITH ing, count(DISTINCT c) AS cases
WHERE cases = size($case_ids)
RETURN ing.name, cases
```

That's the shared-exposure intersection. It's the first real finding, and it's
one pattern.

## The trap that makes it interesting

The intersection returned **two** ingredients, each present in all eleven cases.
Two suppliers tied too. This is the actual problem with outbreak
investigations: counts can't break ties. You need independent evidence.

We designed the synthetic dataset (Port Meridian, September–October 2026) so the
tie is real and only **genomics** breaks it. An environmental isolate from lot
`MG-4417` matches patient isolates across all cases at ≤2 SNPs; the competing
lettuce lot's isolate matches nothing. In the graph that's a small sub-graph
(`Isolate-[:MATCHES {snp_distance}]->Isolate`) and two traversals — and it flips
one hypothesis to `confirmed` and the other to `refuted`.

We also planted a **temporal trap**: one case has an exposure record logged
*after* symptom onset. A careless agent cites it; ours runs `temporal_fit`
against the incubation window (which lives in the graph as protocol data) and
rejects it. This is the difference between "retrieval" and "investigation."

## Making the graph load-bearing, not decorative

The rule we set ourselves: if you delete FalkorDB, the project shouldn't get
slower — it should be impossible. Four things enforce that:

1. **The intersection, the trace, and the cold chain are traversals.** The
   cold-chain peak uses `reduce` because FalkorDB has no scalar `max` over a
   collected list — a detail that forced the query to be *about the graph*.
2. **Graph algorithms do real work.** `algo.betweenness` finds the structural
   chokepoint in the supply network (shipment SH-2291, lot MG-4417);
   `labelPropagation` finds exposure communities. These aren't garnish; they're
   findings.
3. **The agent's memory is the same graph.** Hypotheses, evidence, tasks,
   recalls, and a distilled `Fact` for institutional memory all live as nodes
   next to the outbreak data.
4. **Provenance is a first-class chain.** Every tool call becomes a `ToolCall`
   node logged to its `Session`; every piece of evidence links to the tool call
   that produced it. The UI draws that chain. Any claim is reconstructible.

## Four agents, one protocol, one tool surface

We modeled a real incident command: **Intake Officer → Cluster Analyst → Supply
Chain Tracer → Briefing Officer**. Each role is a genuine MCP server subprocess
exposing only its tools. The protocol is enforced by the capability surface:
the Cluster Analyst *cannot* draft a recall, because `draft_recall` isn't in its
tool-set or its MCP server. Handoffs are edges in the graph
(`Session-[:HANDOFF]->Session`).

This is where MCP earned its keep: the agent discovers its tools from the
server, so "what a role can do" is a deployment decision, not a prompt.

## Determinism as a feature

Demos die. Keys run out, Wi-Fi drops, models get rate-limited. So we made the
LLM swappable behind one interface. With a key, Groq drives the tool loop.
Without one, a deterministic plan drives the **same loop** — still 50 real MCP
tool calls against FalkorDB, same answer. `python -m batchzero.demo.replay
--benchmark 3` prints `correct source identification: 3/3`. The tests, the
benchmark, and the offline demo all run against a live graph.

## What we'd take away

- **Pick a domain where graph is the only honest representation.** The
  tie-break-with-genomics moment only exists because the data has that shape.
- **Store your reasoning.** Writing evidence → tool call → session back into the
  graph turned "trust me" into "replay it."
- **Let the schema enforce the process.** Role-scoped tools did more for
  correctness than any amount of prompt engineering.

The source was lot `MG-4417`. The graph is why we know.
