function ConfidenceBar({ value, status }) {
  const pct = Math.round((Number(value) || 0) * 100);
  return (
    <div className="conf-bar-wrap">
      <div className={`conf-bar ${status}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function InvestigationPanel({ state, selected }) {
  if (!state || !state.hypotheses) {
    return <p className="muted">No investigation selected.</p>;
  }
  const hyps = [...(state.hypotheses || [])].sort(
    (a, b) => (b.confidence || 0) - (a.confidence || 0)
  );

  return (
    <div className="panel">
      <h3>{state.inv_id}</h3>
      {state.title && <p className="muted">{state.title}</p>}

      <h4>Hypotheses</h4>
      {hyps.map((h) => (
        <div className={`hyp ${h.status}`} key={h.hyp_id}>
          <div className="hyp-top">
            <span className={`pill ${h.status}`}>{h.status}</span>
            <span className="conf-num">{Math.round((h.confidence || 0) * 100)}%</span>
          </div>
          <p className="hyp-stmt">{h.statement}</p>
          <ConfidenceBar value={h.confidence} status={h.status} />
          <ul className="ev-list">
            {(h.supporting || [])
              .filter((e) => e && e.evidence_id)
              .map((e) => (
                <li key={e.evidence_id}>
                  <span className="ev-kind">{e.kind}</span> {e.summary}
                  {e.tool && <span className="tool-chip">{e.tool}</span>}
                </li>
              ))}
            {(h.contradicting || [])
              .filter((e) => e && e.evidence_id)
              .map((e) => (
                <li className="contradiction" key={e.evidence_id}>
                  <span className="ev-neg">contradicts · {e.kind}</span> {e.summary}
                  {e.tool && <span className="tool-chip">{e.tool}</span>}
                </li>
              ))}
          </ul>
        </div>
      ))}

      {state.recalls?.length > 0 && (
        <>
          <h4>Recall</h4>
          {state.recalls.map((r) => (
            <div className="recall" key={r.recall_id}>
              <span className="pill active">{r.status || "draft"}</span>
              <strong> lots: {(r.lots || []).join(", ")}</strong>
              {r.rationale && <p className="muted small">{r.rationale}</p>}
            </div>
          ))}
        </>
      )}

      <h4>Action tasks</h4>
      <ul className="task-list">
        {(state.tasks || []).map((t) => (
          <li className="task" key={t.task_id}>
            <span className="pill">{t.type}</span> {t.instructions}
            {t.assigned_to && <span className="muted small"> — {t.assigned_to}</span>}
          </li>
        ))}
      </ul>

      {selected && (
        <>
          <h4>Selected node</h4>
          <pre className="node-inspect">
            {JSON.stringify({ id: selected.id, labels: selected.labels, ...selected.props }, null, 2)}
          </pre>
        </>
      )}
    </div>
  );
}
