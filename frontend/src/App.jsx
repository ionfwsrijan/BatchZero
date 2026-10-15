import { useCallback, useEffect, useRef, useState } from "react";
import { getJSON, streamSSE } from "./api.js";
import AgentStream from "./components/AgentStream.jsx";
import GraphCanvas from "./components/GraphCanvas.jsx";
import InvestigationPanel from "./components/InvestigationPanel.jsx";

export default function App() {
  const [config, setConfig] = useState(null);
  const [tenant, setTenant] = useState("pmph_ops");
  const [investigations, setInvestigations] = useState([]);
  const [invId, setInvId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [followup, setFollowup] = useState("");
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const abortRef = useRef(null);

  const roleLabels = Object.fromEntries((config?.roles || []).map((r) => [r.key, r.label]));

  const loadDetail = useCallback(
    async (id, t = tenant) => {
      const d = await getJSON(`/investigations/${id}`, { tenant: t });
      setDetail(d);
    },
    [tenant]
  );

  const loadGraph = useCallback(
    async (id, t = tenant) => {
      const g = await getJSON(`/investigations/${id}/graph`, { tenant: t });
      setGraph(g);
    },
    [tenant]
  );

  const refreshInvestigations = useCallback(
    async (t = tenant) => {
      const res = await getJSON("/investigations", { tenant: t });
      setInvestigations(res.rows || []);
      return res.rows || [];
    },
    [tenant]
  );

  const openInvestigation = useCallback(
    async (id, t = tenant) => {
      setInvId(id);
      setSelected(null);
      await Promise.all([loadDetail(id, t), loadGraph(id, t)]);
    },
    [tenant, loadDetail, loadGraph]
  );
  void openInvestigation;

  useEffect(() => {
    (async () => {
      try {
        const cfg = await getJSON("/config");
        setConfig(cfg);
        setTenant(cfg.tenant);
        const rows = await getJSON("/investigations", { tenant: cfg.tenant });
        setInvestigations(rows.rows || []);
        if (rows.rows?.length) {
          const latest = rows.rows[0].inv_id;
          setInvId(latest);
          setDetail(await getJSON(`/investigations/${latest}`, { tenant: cfg.tenant }));
          setGraph(await getJSON(`/investigations/${latest}/graph`, { tenant: cfg.tenant }));
        }
      } catch (e) {
        setError(String(e.message || e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async () => {
    setError("");
    setEvents([]);
    setRunning(true);
    const controller = new AbortController();
    abortRef.current = controller;
    let currentId = invId;
    try {
      await streamSSE(
        "/investigations/stream",
        { tenant },
        (evt) => {
          setEvents((prev) => [...prev, evt]);
          if (evt.type === "investigation") {
            currentId = evt.inv_id;
            setInvId(evt.inv_id);
          }
        },
        controller.signal
      );
      if (currentId) {
        await loadDetail(currentId);
        await loadGraph(currentId);
        const list = await getJSON("/investigations", { tenant });
        setInvestigations(list.rows || []);
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(String(e.message || e));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  const sendFollowup = async () => {
    if (!followup.trim() || !invId) return;
    const message = followup.trim();
    setFollowup("");
    setRunning(true);
    try {
      await streamSSE(`/investigations/${invId}/chat/stream`, { message, tenant }, (evt) =>
        setEvents((prev) => [...prev, evt])
      );
      await loadDetail(invId);
      await loadGraph(invId);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  };

  const openExisting = async (id) => {
    setInvId(id);
    setSelected(null);
    setEvents([]);
    await loadDetail(id);
    await loadGraph(id);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">B0</span>
          <div>
            <strong>BatchZero</strong>
            <span className="muted"> outbreak source-investigation agent</span>
          </div>
        </div>
        <div className="top-actions">
          {config && (
            <span className={`badge ${config.provider === "mock" ? "muted-badge" : "live"}`}>
              LLM: {config.provider}
            </span>
          )}
          <select value={tenant} onChange={(e) => setTenant(e.target.value)}>
            <option value="pmph_ops">pmph_ops</option>
            <option value="training_academy">training_academy</option>
          </select>
          <button className="primary" onClick={run} disabled={running}>
            {running ? "Investigating…" : "Run investigation"}
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="layout">
        <aside className="col left">
          <h3>Case file</h3>
          <select
            className="inv-select"
            value={invId || ""}
            onChange={(e) => openExisting(e.target.value)}
          >
            <option value="">select an investigation…</option>
            {investigations.map((i) => (
              <option key={i.inv_id} value={i.inv_id}>
                {i.inv_id} · {i.stage} · {i.cases} cases
              </option>
            ))}
          </select>

          <h3>Agent activity</h3>
          <AgentStream events={events} roleLabels={roleLabels} />

          <div className="followup">
            <input
              placeholder="Ask a follow-up (e.g. trace the cold chain)…"
              value={followup}
              onChange={(e) => setFollowup(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendFollowup()}
              disabled={!invId || running}
            />
            <button onClick={sendFollowup} disabled={!invId || running}>
              Send
            </button>
          </div>
        </aside>

        <main className="col center">
          <div className="canvas-head">
            <h3>Evidence graph</h3>
            <span className="muted small">
              {graph.nodes?.length || 0} nodes · {graph.edges?.length || 0} edges
              {graph.ms ? ` · {Math.round(graph.ms)}ms` : ""}
            </span>
          </div>
          <GraphCanvas graph={graph} onSelect={setSelected} />
          {selected && (
            <div className="selected-bar">
              <strong>{selected.labels?.[0]}</strong>
              <span className="muted">
                {selected.props?.statement ||
                  selected.props?.summary ||
                  selected.props?.name ||
                  selected.props?.tool ||
                  selected.props?.lot_id}
              </span>
            </div>
          )}
        </main>

        <aside className="col right">
          {detail ? (
            <InvestigationPanel state={detail} selected={selected} />
          ) : (
            <p className="muted">No investigation loaded.</p>
          )}
        </aside>
      </div>
    </div>
  );
}

function res(list) {
  return list.rows || [];
}
