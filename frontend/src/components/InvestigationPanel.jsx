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

export default function InvestigationPanel({ state, selected }) {
  if (!state || !state.hypotheses) return <p className="muted">No investigation selected.</p>;
  const investigation = state.investigation || state;
  const hyps = [...(state.hypotheses || [])].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
  const confirmed = hyps.filter((h) => h.status === "confirmed").length;
  const recalls = state.recalls || [];
  const tasks = state.tasks || [];

  return <div className="panel">
    <div className="findings-header"><div><div className="section-kicker"><span className="kicker-mark">✳</span> CASE ASSESSMENT</div><h2>Findings & response</h2></div><span className="findings-count">{hyps.length} <small>HYPOTHESES</small></span></div>
    {hyps.length === 0 && <div className="panel-empty"><span>◎</span><strong>Evidence collection in progress</strong><p>Candidate sources will appear here as the agents examine the case.</p></div>}

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
