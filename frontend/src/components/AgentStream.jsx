const ROLE_ORDER = ["intake", "cluster", "tracer", "briefing"];

function statusDot(ok) {
  return ok === false ? "dot err" : "dot ok";
}

export default function AgentStream({ events, roleLabels }) {
  const byRole = {};
  for (const e of events) {
    const role = e.role || "system";
    byRole[role] = byRole[role] || { tools: [], content: "", started: false, ended: false };
    if (e.type === "role_start") byRole[role].started = true;
    if (e.type === "role_end") {
      byRole[role].ended = true;
      byRole[role].content = e.content || byRole[role].content;
    }
    if (e.type === "assistant" && e.content) byRole[role].content = e.content;
    if (e.type === "tool") byRole[role].tools.push(e);
  }

  const order = ROLE_ORDER.filter((r) => byRole[r]);

  return (
    <div className="agent-stream">
      {order.length === 0 && <p className="muted">No agent activity yet. Run an investigation.</p>}
      {order.map((role) => {
        const b = byRole[role];
        return (
          <div className={`role-card ${b.ended ? "done" : "live"}`} key={role}>
            <div className="role-head">
              <span className="role-name">{roleLabels?.[role] || role}</span>
              <span className={b.ended ? "badge done" : "badge live"}>
                {b.ended ? "done" : "running"}
              </span>
            </div>
            <ul className="tool-list">
              {b.tools.map((t, i) => (
                <li key={i}>
                  <span className={statusDot(t.ok)} />
                  <span className="tool-name">{t.tool}</span>
                  <span className="tool-meta">
                    {t.ok === false ? "error" : `${t.ms ? Math.round(t.ms) + "ms" : ""}`}
                  </span>
                </li>
              ))}
              {b.tools.length === 0 && <li className="muted small">thinking…</li>}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
