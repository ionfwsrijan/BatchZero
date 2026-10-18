import { Badge } from "./ui/badge.jsx";

function ConfidenceBar({ value, status }) {
  const pct = Math.max(0, Math.min(100, Math.round((Number(value) || 0) * 100)));
  return <div className="conf-bar-wrap" aria-label={`${pct}% confidence`}><div className={`conf-bar ${status}`} style={{ width: `${pct}%` }} /></div>;
}

function EvidenceList({ items, contradiction = false }) {
  const valid = (items || []).filter((e) => e && e.evidence_id);
  if (!valid.length) return null;
  return <ul className={`ev-list ${contradiction ? "contradiction-list" : ""}`}>
    {valid.map((e) => <li key={e.evidence_id} className={contradiction ? "contradiction" : ""}>
      <span className="evidence-marker">{contradiction ? "−" : "＋"}</span>
      <div className="evidence-copy"><div className="evidence-meta"><span className="ev-kind">{e.kind || (contradiction ? "Contradicting evidence" : "Supporting evidence")}</span>{e.tool && <span className="tool-chip">{e.tool}</span>}</div><p>{e.summary}</p></div>
    </li>)}
  </ul>;
}

export default function InvestigationPanel({ state, selected, graph = { nodes: [], edges: [] } }) {
  if (!state || !state.hypotheses) return <p className="muted">No investigation selected.</p>;
  const investigation = state.investigation || state;
  const hyps = [...(state.hypotheses || [])].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
  const confirmed = hyps.filter((h) => h.status === "confirmed").length;
  const recalls = state.recalls || [];
  const tasks = state.tasks || [];
  const sessions = state.sessions || [];
  const attachedCases = (investigation.cases || []).filter(Boolean).length;
  const graphNodes = graph.nodes || [];
  const evidenceRecords = graphNodes.filter((node) => node.labels?.includes("Evidence")).length;
  const roleSteps = [
    ["intake", "Intake officer", "Case normalization"],
    ["cluster", "Cluster analyst", "Exposure & hypotheses"],
    ["tracer", "Supply chain tracer", "Source provenance"],
    ["briefing", "Briefing officer", "Response planning"],
  ];

  return <div className="panel">
    <div className="findings-header"><div><div className="section-kicker"><span className="kicker-mark">✳</span> CASE ASSESSMENT</div><h2>Findings & response</h2></div><span className="findings-count">{hyps.length} <small>HYPOTHESES</small></span></div>
    {hyps.length === 0 && <div className="assessment-empty">
      <div className="assessment-signal-art" aria-hidden="true"><span className="assessment-orbit assessment-orbit-a" /><span className="assessment-orbit assessment-orbit-b" /><i /><i /><i /><i /><b>↗</b></div>
      <Badge variant={attachedCases ? "success" : graphNodes.length ? "warning" : "outline"}><span className="provider-dot" />{attachedCases ? "CASE FILE CONNECTED" : graphNodes.length ? "ACTIVITY LOGGED · NO CASES" : "AWAITING CASE DATA"}</Badge>
      <strong>{attachedCases ? "Case file connected; hypotheses are pending" : graphNodes.length ? "Investigation activity is logged, but no cases are attached" : "Evidence collection is standing by"}</strong>
      <p>{attachedCases ? `${attachedCases} case${attachedCases === 1 ? " is" : "s are"} attached. The team has not recorded a source hypothesis yet.` : graphNodes.length ? "The graph contains agent activity, but no case records. Run an investigation against the Port Meridian sample or attach a case file to begin evidence assessment." : "Run an investigation to attach case records, connect exposures, and build evidence-backed source hypotheses."}</p>
      <div className="assessment-stats"><div><strong>{attachedCases}</strong><span>cases attached</span></div><i /><div><strong>{evidenceRecords}</strong><span>evidence records</span></div><i /><div><strong>{sessions.length}</strong><span>agent sessions</span></div></div>
    </div>}

    {hyps.length === 0 && <section className="trail-section"><div className="subsection-heading"><span className="trail-heading-mark">↗</span><div><h3>Investigation trail</h3><small>Four roles coordinate the response</small></div><span className="trail-count">{sessions.length || 0}/4</span></div><ol className="trail-list">{roleSteps.map(([role, label, task], index) => { const recorded = sessions.some((session) => session.role === role); return <li key={role} className={recorded ? "recorded" : ""}><span className="trail-step">{recorded ? "✓" : `0${index + 1}`}</span><div><strong>{label}</strong><small>{task}</small></div><span className="trail-status">{recorded ? "SESSION LOGGED" : "READY"}</span></li>; })}</ol></section>}

    {hyps.map((h, index) => <article className={`hyp ${h.status} ${index === 0 ? "hyp-leading" : ""}`} key={h.hyp_id}>
      <div className="hyp-top"><span className={`pill ${h.status}`}><i />{h.status || "open"}</span><span className="conf-num">{Math.round((h.confidence || 0) * 100)}<small>%</small></span></div>
      <p className="hyp-stmt">{h.statement}</p>
      <div className="confidence-label"><span>Confidence</span><span>{h.status === "confirmed" ? "Strongly supported" : h.status === "refuted" ? "Evidence against" : "Under review"}</span></div>
      <ConfidenceBar value={h.confidence} status={h.status} />
      <EvidenceList items={h.supporting} />
      <EvidenceList items={h.contradicting} contradiction />
    </article>)}

    {recalls.length > 0 && <section className="response-section"><div className="subsection-heading"><span className="response-icon recall-icon">!</span><div><h3>Recall scope</h3><small>{recalls.length} response {recalls.length === 1 ? "action" : "actions"}</small></div></div>
      {recalls.map((r) => <div className="recall" key={r.recall_id}><div className="recall-top"><span className="recall-lot">{(r.lots || []).length ? (r.lots || []).join(", ") : r.scope || "Recall scope pending"}</span><span className={`pill ${r.status || "open"}`}>{r.status || "draft"}</span></div>{r.rationale && <p>{r.rationale}</p>}</div>)}
    </section>}

    <section className="response-section tasks-section"><div className="subsection-heading"><span className="response-icon task-icon">✓</span><div><h3>Action tasks</h3><small>{tasks.length} assigned</small></div></div>
      {tasks.length > 0 ? <ul className="task-list">{tasks.map((t) => <li className="task" key={t.task_id}><span className="task-check">✓</span><div className="task-copy"><div className="task-meta"><span className="pill">{t.type}</span>{t.status && <span className="task-status">{t.status}</span>}</div><p>{t.instructions}</p>{(t.assigned_to || t.about) && <small>{t.assigned_to && <>Assigned to <strong>{t.assigned_to}</strong></>}{t.assigned_to && t.about && " · "}{t.about && <>Regarding <strong>{t.about}</strong></>}</small>}</div></li>)}</ul> : <p className="no-tasks">Response tasks will appear when actions are assigned.</p>}
    </section>

    {selected && <details className="selected-inspector" open><summary><span>Selected graph entity</span><span>{selected.labels?.[0] || "Entity"}</span></summary><pre>{JSON.stringify({ id: selected.id, labels: selected.labels, ...selected.props }, null, 2)}</pre></details>}
    {confirmed > 0 && <div className="provenance-note"><span>◈</span><p>Findings retain their evidence trail to the underlying graph query and agent session.</p></div>}
    {investigation.summary && <details className="case-summary"><summary>Investigation summary</summary><p>{investigation.summary}</p></details>}
  </div>;
}
