import { useCallback, useEffect, useMemo, useState } from "react";
import { getJSON, streamSSE } from "./api.js";
import AgentStream from "./components/AgentStream.jsx";
import GraphCanvas from "./components/GraphCanvas.jsx";
import InvestigationPanel from "./components/InvestigationPanel.jsx";
import EpiCurve from "./components/EpiCurve.jsx";
import { Badge } from "./components/ui/badge.jsx";
import { Button } from "./components/ui/button.jsx";
import {
  Activity, ArrowRight, ArrowUpRight, Atom, BarChart3, Check,
  ChevronDown, CircleDot, FlaskConical, GitBranch, Moon, Network, Play,
  Send, ShieldCheck, Sparkles, Sun, Users, Waypoints, X,
} from "lucide-react";
import { MotionConfig, motion } from "motion/react";

const EMPTY_GRAPH = { nodes: [], edges: [] };

export default function App() {
  const [config, setConfig] = useState(null);
  const [tenant, setTenant] = useState("pmph_ops");
  const [investigations, setInvestigations] = useState([]);
  const [invId, setInvId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [graph, setGraph] = useState(EMPTY_GRAPH);
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [followup, setFollowup] = useState("");
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(() => window.localStorage.getItem("batchzero-theme-v3") || "light");
  const [vizTab, setVizTab] = useState("network");

  const roleLabels = useMemo(() => Object.fromEntries((config?.roles || []).map((role) => [role.key, role.label])), [config]);
  const incident = detail?.investigation || detail || {};
  const activeInvestigation = investigations.find((item) => item.inv_id === invId);
  const caseCount = incident.cases?.length || activeInvestigation?.cases || 0;
  const hypotheses = detail?.hypotheses || [];
  const leadingHypothesis = [...hypotheses].sort((a, b) => (b.confidence || 0) - (a.confidence || 0))[0];
  const providerLabel = config?.provider === "mock" ? "Demo environment" : "Live model";

  useEffect(() => { window.localStorage.setItem("batchzero-theme-v3", theme); }, [theme]);

  const loadDetail = useCallback(async (id, currentTenant = tenant) => {
    setDetail(await getJSON(`/investigations/${id}`, { tenant: currentTenant }));
  }, [tenant]);

  const loadGraph = useCallback(async (id, currentTenant = tenant) => {
    setGraph(await getJSON(`/investigations/${id}/graph`, { tenant: currentTenant }));
  }, [tenant]);

  const refreshWorkspace = useCallback(async (currentTenant, chooseLatest = true) => {
    const rows = await getJSON("/investigations", { tenant: currentTenant });
    const list = rows.rows || [];
    setInvestigations(list);
    const nextId = chooseLatest ? list[0]?.inv_id : null;
    setInvId(nextId || null);
    setSelected(null);
    if (!nextId) {
      setDetail(null);
      setGraph(EMPTY_GRAPH);
      return;
    }
    const [nextDetail, nextGraph] = await Promise.all([
      getJSON(`/investigations/${nextId}`, { tenant: currentTenant }),
      getJSON(`/investigations/${nextId}/graph`, { tenant: currentTenant }),
    ]);
    setDetail(nextDetail);
    setGraph(nextGraph);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const cfg = await getJSON("/config");
        setConfig(cfg);
        const initialTenant = cfg.tenant || "pmph_ops";
        setTenant(initialTenant);
        await refreshWorkspace(initialTenant);
      } catch (e) {
        setError(String(e.message || e));
      }
    })();
  }, [refreshWorkspace]);

  const changeTenant = async (nextTenant) => {
    setTenant(nextTenant);
    setError("");
    try {
      await refreshWorkspace(nextTenant);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const run = async () => {
    setError("");
    setEvents([]);
    setRunning(true);
    let currentId = invId;
    try {
      await streamSSE("/investigations/stream", { tenant }, (evt) => {
        setEvents((prev) => [...prev, evt]);
        if (evt.type === "investigation") {
          currentId = evt.inv_id;
          setInvId(evt.inv_id);
        }
      });
      if (currentId) {
        await Promise.all([loadDetail(currentId), loadGraph(currentId)]);
        const list = await getJSON("/investigations", { tenant });
        setInvestigations(list.rows || []);
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  };

  const sendFollowup = async () => {
    if (!followup.trim() || !invId) return;
    const message = followup.trim();
    setFollowup("");
    setRunning(true);
    try {
      await streamSSE(`/investigations/${invId}/chat/stream`, { message, tenant }, (evt) => setEvents((prev) => [...prev, evt]));
      await Promise.all([loadDetail(invId), loadGraph(invId)]);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  };

  const openExisting = async (id) => {
    setInvId(id || null);
    setSelected(null);
    setEvents([]);
    if (!id) {
      setDetail(null);
      setGraph(EMPTY_GRAPH);
      return;
    }
    try {
      const [nextDetail, nextGraph] = await Promise.all([
        getJSON(`/investigations/${id}`, { tenant }),
        getJSON(`/investigations/${id}/graph`, { tenant }),
      ]);
      setDetail(nextDetail);
      setGraph(nextGraph);
    } catch (e) {
      setError(String(e.message || e));
    }
  };

  const status = incident.status || activeInvestigation?.status || incident.stage || "Ready to investigate";
  const isHealthy = Boolean(invId && detail);

  return (
    <MotionConfig reducedMotion="user">
      <div className={`app theme-${theme}`}>
        <div className="ambient ambient-one" />
        <div className="ambient ambient-two" />

        <header className="topbar">
          <a className="brand" href="#home" aria-label="BatchZero home">
            <span className="logo-mark"><Activity size={19} strokeWidth={2.4} /></span>
            <span className="brand-copy"><strong>BatchZero</strong><small>OUTBREAK INTELLIGENCE</small></span>
          </a>
          <div className="topbar-context"><span className="context-divider" /><span className="live-indicator" /><span>Response center</span><span className="context-slash">/</span><strong>Investigation workspace</strong></div>
          <div className="top-actions">
            {config && <Badge variant={config.provider === "mock" ? "warning" : "success"} className="provider-tag"><span className="provider-dot" />{providerLabel}</Badge>}
            <label className="tenant-control"><span>WORKSPACE</span><span className="tenant-select-wrap"><select value={tenant} onChange={(e) => changeTenant(e.target.value)} aria-label="Select workspace"><option value="pmph_ops">Port Meridian PH</option><option value="training_academy">Training Academy</option></select><ChevronDown size={14} /></span></label>
            <Button variant="outline" size="icon" className="theme-toggle" onClick={() => setTheme((value) => value === "light" ? "dark" : "light")} aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`} title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}>
              {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
            </Button>
            <Button className="run-button" onClick={run} disabled={running}>
              {running ? <Activity className="spin-icon" size={15} /> : <Play size={14} fill="currentColor" />}
              <span>{running ? "Investigation running" : "Run investigation"}</span>
              {!running && <ArrowUpRight size={15} className="button-trailing" />}
            </Button>
          </div>
        </header>

        {error && <div className="error-banner"><span>!</span>{error}</div>}

        <div className="workspace">
          <motion.aside className="activity-rail" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: .38 }}>
            <div className="rail-overline"><span>COMMAND DESK</span><span className="rail-live"><i /> OPERATIONAL</span></div>
            <div className="rail-section-label"><span>CASEWORK</span><span className="rail-menu">···</span></div>
            <label className="field-label" htmlFor="investigation-select">Active investigation</label>
            <div className="active-select-shell"><span className="select-status-dot" /><select id="investigation-select" className="inv-select" value={invId || ""} onChange={(e) => openExisting(e.target.value)}><option value="">Select an investigation…</option>{investigations.map((item) => <option key={item.inv_id} value={item.inv_id}>{item.inv_id} · {item.stage} · {item.cases} cases</option>)}</select><ChevronDown size={15} /></div>
            <div className="sidebar-section-heading"><div><Users size={15} /><span>Response team</span></div><Badge variant="secondary">04 agents</Badge></div>
            <AgentStream events={events} roleLabels={roleLabels} />

            <div className="sidebar-lower">
              <div className="followup-card">
                <div className="followup-heading"><span className="sparkle"><Sparkles size={15} /></span><div><strong>Ask the investigation</strong><small>Query the agent team</small></div></div>
                <form className="followup-input-wrap" onSubmit={(e) => { e.preventDefault(); sendFollowup(); }}>
                  <input placeholder="Ask about a lot, supplier…" value={followup} onChange={(e) => setFollowup(e.target.value)} disabled={!invId || running} aria-label="Ask a follow-up question" />
                  <Button variant="secondary" size="icon" type="submit" aria-label="Send follow-up" disabled={!invId || running || !followup.trim()}><Send size={15} /></Button>
                </form>
                {!invId && <small className="chat-hint">Start an investigation to ask a question.</small>}
              </div>
              <div className="rail-footer"><ShieldCheck size={14} /><span>Evidence-backed by FalkorDB</span><span className="footer-check"><Check size={11} /></span></div>
            </div>
          </motion.aside>

          <motion.main className="main-content" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .42, delay: .04 }}>
            <section className="incident-overview">
              <div className="breadcrumb"><span>INTELLIGENCE</span><ArrowRight size={12} /><span>RESPONSE CENTER</span><ArrowRight size={12} /><span className="breadcrumb-current">{incident.inv_id || invId || "NEW INVESTIGATION"}</span></div>
              <div className="incident-title-row">
                <div className="incident-title-copy">
                  <div className="incident-title-line"><span className="incident-icon"><Atom size={19} /></span><div><h1>{incident.title || activeInvestigation?.title || "Outbreak intelligence"}</h1><p>{incident.summary || "Follow the signal from first case to source. Every conclusion stays connected to its evidence."}</p></div></div>
                </div>
                <div className="title-actions"><Badge variant={isHealthy ? "success" : "warning"} className="status-tag"><i />{isHealthy ? status : "Awaiting signal"}</Badge><div className="case-count"><strong>{caseCount || "—"}</strong><span>{caseCount ? "CONFIRMED CASES" : "CASE CLUSTER"}</span></div></div>
              </div>

              <div className="signal-banner">
                <div className="signal-orb"><Activity size={18} /></div>
                <div className="signal-copy"><span>INCIDENT RESPONSE DESK</span><strong>{invId ? "Investigation ready for review" : "A clear picture starts with a signal"}</strong><small>{invId ? "Evidence is connected. Review the strongest lead and coordinate next steps." : "Launch the response team to connect cases, compare sources, and trace evidence upstream."}</small></div>
                <div className="protocol-steps" aria-label="Investigation workflow"><span className="step-active"><i>01</i><b>Intake</b></span><i /><span className={events.some((event) => event.role === "cluster") ? "step-active" : ""}><i>02</i><b>Analyze</b></span><i /><span className={events.some((event) => event.role === "tracer") ? "step-active" : ""}><i>03</i><b>Trace</b></span><i /><span className={events.some((event) => event.role === "briefing") ? "step-active" : ""}><i>04</i><b>Respond</b></span></div>
                <span className="banner-glow" aria-hidden="true" />
              </div>

              <div className="overview-metrics">
                <article className="metric-item metric-pathogen"><span className="metric-icon"><FlaskConical size={17} /></span><div><small>PATHOGEN</small><strong>{incident.cases?.find((item) => item.pathogen)?.pathogen || "Awaiting case data"}</strong></div><span className="metric-index">01</span></article>
                <article className="metric-item metric-priority"><span className="metric-icon"><Activity size={17} /></span><div><small>PRIORITY</small><strong>{incident.priority || "Not assessed"}</strong></div><span className="metric-index">02</span></article>
                <article className="metric-item metric-hypotheses"><span className="metric-icon"><GitBranch size={17} /></span><div><small>HYPOTHESES</small><strong>{hypotheses.length ? `${hypotheses.length} under review` : "No hypotheses yet"}</strong></div><span className="metric-index">03</span></article>
                <article className="metric-item metric-leading"><span className="metric-icon"><Waypoints size={17} /></span><div><small>LEADING HYPOTHESIS</small><strong>{leadingHypothesis ? `${Math.round((leadingHypothesis.confidence || 0) * 100)}% confidence` : "Awaiting evidence"}</strong></div><span className="metric-index">04</span></article>
              </div>
            </section>

            <div className="investigation-grid">
              <motion.section className="graph-card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .4, delay: .08 }}>
                <div className="card-heading graph-heading">
                  <div className="graph-title-group"><div className="section-kicker"><span className="kicker-mark"><Network size={13} /></span> INVESTIGATION SIGNALS</div><h2>{vizTab === "network" ? "Evidence network" : "Epidemic curve"}</h2><p>{vizTab === "network" ? "The relationships behind this outbreak" : "Cases grouped by symptom onset date"}</p></div>
                  <div className="graph-count"><span className="graph-live-dot" /> <strong>{graph.nodes?.length || 0}</strong> entities <span className="count-divider" /> <strong>{graph.edges?.length || 0}</strong> connections</div>
                </div>
                <div className="viz-toolbar"><div className="viz-tabs" role="tablist" aria-label="Investigation visualizations"><button className={vizTab === "network" ? "active" : ""} onClick={() => setVizTab("network")} role="tab" aria-selected={vizTab === "network"}><Waypoints size={15} /> Evidence network</button><button className={vizTab === "curve" ? "active" : ""} onClick={() => setVizTab("curve")} role="tab" aria-selected={vizTab === "curve"}><BarChart3 size={15} /> Epidemic curve</button></div><span className="viz-helper">{vizTab === "network" ? "SELECT A NODE TO INSPECT" : "CASES BY SYMPTOM ONSET"}</span></div>
                <div className={`graph-viewport ${vizTab === "curve" ? "curve-viewport" : ""}`}>
                    {vizTab === "network" ? <>
                    <GraphCanvas graph={graph} onSelect={setSelected} theme={theme} />
                    {(!graph.nodes || graph.nodes.length === 0) && <div className="graph-empty">
                      <div className="empty-network" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /><svg viewBox="0 0 280 160"><path d="M38 84 91 42 141 79 199 31 243 72M38 84l57 46 46-51 58 43 44-50M91 42l4 88M199 31l-5 86M38 84l109-5 96-7" /></svg><span className="network-core"><Activity size={21} /></span></div>
                      <Badge variant="violet" className="empty-kicker"><span className="kicker-pulse" /> RESPONSE PROTOCOL · 4 SPECIALISTS READY</Badge>
                      <strong>{invId ? "Building your evidence network" : "One signal can reveal the whole picture."}</strong>
                      <p>{invId ? "The agent team is connecting cases, hypotheses, and source evidence." : "Start an investigation to connect cases, test competing sources, and trace evidence upstream."}</p>
                      <Button className="empty-start" onClick={run} disabled={running}>{running ? <Activity className="spin-icon" size={15} /> : <Play size={13} fill="currentColor" />}{running ? "Starting response" : "Start investigation"}<ArrowUpRight size={15} /></Button>
                      <div className="empty-trust"><span><i /> Epidemiology</span><span><i /> Genomics</span><span><i /> Traceability</span></div>
                    </div>}
                  </> : <EpiCurve cases={incident.cases || []} />}
                </div>
                {selected && <div className="selected-bar"><Badge variant="secondary" className="selected-kind">{selected.labels?.[0] || "Entity"}</Badge><strong>{selected.props?.statement || selected.props?.summary || selected.props?.name || selected.props?.tool || selected.props?.lot_id || selected.props?.case_id || selected.id}</strong><Button variant="ghost" size="icon" onClick={() => setSelected(null)} aria-label="Clear selected entity"><X size={15} /></Button></div>}
                {!selected && graph.nodes?.length > 0 && <div className="graph-footnote"><ShieldCheck size={13} /> Relationships are drawn from the investigation graph. Select an entity to inspect its provenance.</div>}
              </motion.section>

              <motion.aside className="findings-column" initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: .4, delay: .12 }}>
                {detail ? <InvestigationPanel state={detail} selected={selected} /> : <div className="empty-brief">
                  <div className="brief-heading"><div><div className="section-kicker"><span className="kicker-mark"><CircleDot size={13} /></span> RESPONSE BRIEF</div><h2>Standing by for a signal</h2><p>Your command view is ready. No case data has been processed yet.</p></div><span className="brief-ready"><i /> READY</span></div>
                  <div className="brief-hero">
                    <div className="brief-orbit" aria-hidden="true"><span className="orbit-ring orbit-ring-one" /><span className="orbit-ring orbit-ring-two" /><span className="orbit-node orbit-node-one"><FlaskConical size={13} /></span><span className="orbit-node orbit-node-two"><GitBranch size={13} /></span><span className="orbit-node orbit-node-three"><Waypoints size={13} /></span><span className="orbit-node orbit-node-four"><ShieldCheck size={13} /></span><span className="orbit-center"><Activity size={18} /></span></div>
                    <div className="brief-hero-copy"><span>THE RESPONSE PROTOCOL</span><strong>Four specialists.<br />One evidence trail.</strong><small>Each finding stays connected to its source, from the first case through response planning.</small></div>
                  </div>
                  <div className="brief-sequence-heading"><span>HOW THE SIGNAL MOVES</span><span>4 STEPS</span></div>
                  <ol className="brief-sequence">
                    <li><span className="sequence-icon sequence-intake"><FlaskConical size={14} /></span><div><strong>Intake</strong><small>Normalize case reports</small></div><span className="sequence-number">01</span></li>
                    <li><span className="sequence-icon sequence-cluster"><GitBranch size={14} /></span><div><strong>Analyze</strong><small>Connect cases & test hypotheses</small></div><span className="sequence-number">02</span></li>
                    <li><span className="sequence-icon sequence-trace"><Waypoints size={14} /></span><div><strong>Trace</strong><small>Follow evidence to its source</small></div><span className="sequence-number">03</span></li>
                    <li><span className="sequence-icon sequence-brief"><ShieldCheck size={14} /></span><div><strong>Respond</strong><small>Prepare evidence-backed actions</small></div><span className="sequence-number">04</span></li>
                  </ol>
                  <div className="brief-footnote"><span className="footnote-shield"><ShieldCheck size={14} /></span><div><strong>Built for decisions you can defend</strong><small>Evidence and provenance remain linked throughout.</small></div><ArrowUpRight size={14} /></div>
                </div>}
              </motion.aside>
            </div>
          </motion.main>
        </div>
      </div>
    </MotionConfig>
  );
}
