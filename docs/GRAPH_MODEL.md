# BatchZero — Graph Data Model

Everything BatchZero knows lives in one FalkorDB graph per tenant. The model has
two halves that share the same instance: the **domain graph** (the outbreak) and
the **agent graph** (the investigation's own memory, provenance and protocol).

The authoritative source is [`backend/batchzero/schema.py`](../backend/batchzero/schema.py).

---

## Node labels

| Label | Meaning |
|-------|---------|
| `Person` | case, contact, food worker, inspector or lab technician |
| `Case` | a reported illness episode (`case_id`, `onset`, `pathogen`, `severity`) |
| `ExposureEvent` | a meal / catered event (`event_id`, `meal_date`, `kind`) |
| `Facility` | restaurant, caterer, kitchen or processor (`facility_id`, `name`) |
| `MenuItem` | a dish (`menu_id`, `name`) |
| `Ingredient` | a food ingredient (`ingredient_id`, `name`) |
| `Lot` | a traceable lot of an ingredient (`lot_id`, `product_name`, `harvest_date`, `use_by`) |
| `Supplier` | distributor / grower / processor (`supplier_id`, `name`, `risk_tier`) |
| `Farm` | origin farm (`farm_id`, `name`) |
| `Shipment` | a physical movement (`shipment_id`, `carrier`, `depart`, `arrive`, `breached`) |
| `TemperatureReading` | cold-chain sensor reading (`at`, `celsius`) |
| `Lab` | laboratory (`lab_id`, `name`) |
| `Isolate` | pathogen isolate (`isolate_id`, `pathogen`, `source`, `sequence_type`) |
| `Inspection` | regulatory inspection (`insp_id`, `date`, `score`, `violations`) |
| `WastewaterSite` | environmental surveillance site (`site_id`, `name`) |
| `PriorIncident` | historical incident (`incident_id`, `year`, `summary`, `outcome`) |
| `Investigation` | the case file (`inv_id`, `title`, `stage`, `status`, `priority`, `summary`) |
| `Hypothesis` | a candidate source (`hyp_id`, `statement`, `status`, `confidence`) |
| `Evidence` | a reason for/against (`evidence_id`, `kind`, `summary`, `weight`) |
| `Task` | an action item (`task_id`, `type`, `instructions`, `status`, `due`) |
| `Recall` | a recall (`recall_id`, `scope`, `rationale`, `status`) |
| `Session` | one agent role-session (`session_id`, `role`, `started`, `summary`) |
| `Message` | a conversation turn (`role`, `content`, `at`) |
| `ToolCall` | a logged MCP call (`tool_call_id`, `tool`, `args`, `result`, `ms`) |
| `Fact` | distilled institutional memory (`fact_id`, `statement`, `kind`, `confidence`) |
| `ProtocolStep` | a step in the outbreak-investigation protocol (`step_id`, `name`, `order`) |

---

## Relationship types

### Domain graph — the outbreak

```
(Person)-[:HAS_CASE]->(Case)
(Person)-[:PARTICIPATED]->(ExposureEvent)
(ExposureEvent)-[:AT]->(Facility)
(ExposureEvent)-[:INVOLVES]->(MenuItem)
(MenuItem)-[:CONTAINS]->(Ingredient)
(ExposureEvent)-[:CONSUMED]->(Lot)
(Facility)-[:PURCHASED]->(Lot)
(Lot)-[:SUPPLIED_BY]->(Supplier)
(Lot)-[:ORIGINATES_FROM]->(Farm)
(Lot)-[:SHIPPED_IN]->(Shipment)
(Shipment)-[:DELIVERED_TO]->(Facility)
(Shipment)-[:HAS_READING]->(TemperatureReading)
(Facility)-[:EMPLOYS]->(Person)
(Facility|Supplier)-[:SUBJECT_OF]->(Inspection)
(Supplier|Facility)-[:IMPLICATED_IN]->(PriorIncident)
(Case)-[:LINKED_ISOLATE]->(Isolate)
(Lab)-[:PROCESSED]->(Isolate)
(Isolate)-[:SAMPLED_FROM]->(Lot)
(Isolate)-[:MATCHES {snp_distance}]->(Isolate)
(WastewaterSite)-[:DETECTED {on}]->(Isolate)
```

### Agent graph — the investigation's memory

```
(Investigation)-[:INCLUDES]->(Case)
(Investigation)-[:HAS_HYPOTHESIS]->(Hypothesis)
(Hypothesis)-[:SUPPORTED_BY]->(Evidence)
(Hypothesis)-[:CONTRADICTED_BY]->(Evidence)
(Evidence|Task|Fact)-[:ABOUT]->(entity)          # Lot, Supplier, Facility, ...
(Evidence)-[:DERIVED_FROM]->(ToolCall)            # <-- the provenance link
(Investigation)-[:HAS_TASK]->(Task)
(Task)-[:ASSIGNED_TO]->(Person)
(Investigation)-[:HAS_RECALL]->(Recall)
(Recall)-[:COVERS]->(Lot)
(Session)-[:BELONGS_TO]->(Investigation)
(Session)-[:HANDOFF]->(Session)                   # role-to-role protocol handoff
(Session)-[:HAS_MESSAGE]->(Message)
(Session)-[:LOGGED]->(ToolCall)
(Fact)-[:FACT_ABOUT]->(entity)
(Fact)-[:FACT_SUPPORTED_BY]->(Evidence)
(Fact)-[:RECALLED_IN]->(Session)
(ProtocolStep)-[:NEXT]->(ProtocolStep)
(Session)-[:AT_STEP]->(ProtocolStep)
```

---

## The provenance chain

This is the spine of the whole project. Any statement the agent commits is
reconstructible:

```
Hypothesis-[:SUPPORTED_BY]->Evidence-[:DERIVED_FROM]->ToolCall-[:LOGGED]->Session
```

Because the `ToolCall` stores the tool name, arguments and latency, and the
`Session` stores the role, a reviewer can see *which role asked what, with which
tool, and when* for every piece of evidence. The UI renders exactly this chain
with cytoscape.

---

## Indexes

Range indexes on all frequent lookup keys (`Case.case_id`, `Case.onset`,
`Lot.lot_id`, `Investigation.inv_id`, `Hypothesis.hyp_id`, `Session.session_id`,
`ProtocolStep.step_id`, …) and fulltext indexes on names/summaries used by the
semantic-recall tool. Created idempotently by `schema.ensure_schema` via
`python -m batchzero.seed`.

---

## Procedural memory (the protocol in the graph)

Seven `ProtocolStep` nodes chained with `NEXT` describe the investigation
protocol: *verify case definition → build exposure picture → form hypotheses →
test with lab/genomics → trace supply chain → act (recall/inspection) → brief*.
Incubation windows per pathogen live alongside the steps as data, so the agent
**queries the protocol** instead of hard-coding rules in a prompt. Each session
is anchored to its current step with `AT_STEP`.
