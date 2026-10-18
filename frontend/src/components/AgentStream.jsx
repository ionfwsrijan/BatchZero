import { Activity, Check, Circle, FlaskConical, GitFork, Search, Truck } from "lucide-react";

const ROLE_ORDER = ["intake", "cluster", "tracer", "briefing"];
const ROLE_ICONS = { intake: FlaskConical, cluster: Search, tracer: Truck, briefing: GitFork };

function statusDot(ok) {
  return ok === false ? "dot err" : "dot ok";
}

export default function AgentStream({ events = [], roleLabels = {} }) {
  const byRole = {};
  for (const event of events) {
    const role = event.role || "system";
    byRole[role] ||= { tools: [], content: "", started: false, ended: false };
    if (event.type === "role_start") byRole[role].started = true;
    if (event.type === "role_end") {
      byRole[role].ended = true;
      byRole[role].content = event.content || byRole[role].content;
    }
    if (event.type === "assistant" && event.content) byRole[role].content = event.content;
    if (event.type === "tool") byRole[role].tools.push(event);
  }

  const totalCalls = ROLE_ORDER.reduce((total, role) => total + (byRole[role]?.tools.length || 0), 0);
  const completed = ROLE_ORDER.filter((role) => byRole[role]?.ended).length;
  const started = ROLE_ORDER.some((role) => byRole[role]?.started);

  return <div className={`agent-stream ${started ? "has-activity" : "is-idle"}`}>
    <div className="team-progress">
      <div className="progress-track"><span style={{ width: `${started ? Math.max(9, (completed / ROLE_ORDER.length) * 100) : 0}%` }} /></div>
      <div className="team-progress-caption"><small>{started ? completed === ROLE_ORDER.length ? "Protocol complete" : `${completed} of 4 specialists complete` : "Four specialists ready"}</small><small>{totalCalls} queries</small></div>
    </div>
    <div className="agent-list">
      {ROLE_ORDER.map((role, index) => {
        const activity = byRole[role] || { tools: [], content: "", started: false, ended: false };
        const state = activity.ended ? "done" : activity.started ? "live" : "queued";
        const Icon = ROLE_ICONS[role];
        return <article className={`role-card ${state}`} key={role}>
          <div className="role-marker"><span>{activity.ended ? <Check size={13} /> : <Icon size={14} />}</span></div>
          <div className="role-card-main">
            <div className="role-head"><span className="role-name">{roleLabels[role] || ({ intake: "Intake officer", cluster: "Cluster analyst", tracer: "Supply chain tracer", briefing: "Briefing officer" })[role]}</span><span className={`role-state state-${state}`}>{activity.ended ? "Complete" : activity.started ? "Working" : "Ready"}</span></div>
            <span className="role-call-count">{activity.tools.length ? `${activity.tools.length} graph ${activity.tools.length === 1 ? "query" : "queries"}` : ({ intake: "Case intake", cluster: "Epidemiology", tracer: "Source tracing", briefing: "Response brief" })[role]}</span>
            {activity.content && <p className="role-summary">{activity.content}</p>}
            {activity.tools.length > 0 && <ul className="tool-list">{activity.tools.slice(-2).map((tool, index) => <li key={`${tool.tool}-${index}`}><span className={statusDot(tool.ok)} /><span className="tool-name">{tool.tool}</span><span className="tool-meta">{tool.ok === false ? "error" : tool.ms ? `${Math.round(tool.ms)}ms` : "done"}</span></li>)}</ul>}
          </div>
          <span className="role-step-index">0{index + 1}</span>
        </article>;
      })}
    </div>
    <div className="activity-total"><span className="team-status-icon">{started ? <Activity size={13} /> : <Circle size={8} />}</span><span>{started ? `${totalCalls} graph operations recorded` : "Agents activate when a signal is submitted"}</span></div>
  </div>;
}
