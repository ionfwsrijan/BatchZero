import { useCallback, useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { LocateFixed, Minus, Plus, RotateCcw, Waypoints } from "lucide-react";

const TYPE_COLORS = {
  Investigation: "#78aaff",
  Hypothesis: "#a88bff",
  Evidence: "#4fd4c0",
  ToolCall: "#8a9fca",
  Session: "#82b8ff",
  Case: "#ff7cac",
  Person: "#c28cff",
  Lot: "#79c9ff",
  Supplier: "#f2b86b",
  Facility: "#75b6ff",
  Shipment: "#63d3cc",
  Farm: "#9da5ff",
  Ingredient: "#8b9dff",
  Isolate: "#ff91b7",
  Task: "#a88bff",
  Recall: "#ff7c9b",
  Fact: "#9c9dff",
  ProtocolStep: "#8295b8",
  ExposureEvent: "#6fd6df",
  MenuItem: "#cf91ff",
  WastewaterSite: "#52d4c3",
  TemperatureReading: "#61c9ef",
  Inspection: "#8abaff",
};

function nodeLabel(props, labels) {
  const p = props || {};
  return p.name || p.statement || p.summary || p.case_id || p.lot_id || p.evidence_id || p.tool || p.role || labels?.[0] || "Entity";
}

function relationColor(type = "") {
  const label = type.toLowerCase();
  if (label.includes("supply") || label.includes("origin") || label.includes("deliver")) return "#f2b86b";
  if (label.includes("case") || label.includes("person") || label.includes("participat")) return "#ff7cac";
  if (label.includes("evidence") || label.includes("support") || label.includes("implicat")) return "#a88bff";
  return "#6e9de8";
}

export default function GraphCanvas({ graph, onSelect, theme = "dark" }) {
  const ref = useRef(null);
  const cyRef = useRef(null);
  const [layout, setLayout] = useState("concentric");

  const fit = useCallback((padding = 54) => {
    cyRef.current?.fit(undefined, padding);
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const degrees = new Map();
    for (const edge of graph?.edges || []) {
      const source = String(edge.source);
      const target = String(edge.target);
      degrees.set(source, (degrees.get(source) || 0) + 1);
      degrees.set(target, (degrees.get(target) || 0) + 1);
    }

    const nodes = (graph?.nodes || []).map((n) => {
      const id = String(n.id);
      const type = n.labels?.[0] || "Node";
      const color = TYPE_COLORS[type] || "#82aaff";
      const name = String(nodeLabel(n.props, n.labels));
      return { data: {
        id,
        type,
        label: name.length > 28 ? `${name.slice(0, 26)}…` : name,
        status: n.props?.status,
        color,
        size: 16 + Math.min((degrees.get(id) || 0) * 3.2, 28),
      } };
    });
    const edges = (graph?.edges || []).map((e) => ({
      data: {
        id: `e${e.id}`,
        source: String(e.source),
        target: String(e.target),
        label: e.type,
        color: relationColor(e.type),
      },
    }));

    cyRef.current?.destroy();
    const cy = cytoscape({
      container: ref.current,
      elements: [...nodes, ...edges],
      style: [
        {
          selector: "node",
          style: {
            width: "data(size)",
            height: "data(size)",
            "background-color": "data(color)",
            "background-opacity": 0.96,
            "border-width": 1,
            "border-color": theme === "light" ? "#ffffff" : "#dbe8ff",
            "border-opacity": 0.78,
            "shadow-blur": 20,
            "shadow-color": "data(color)",
            "shadow-opacity": 0.74,
            label: "data(label)",
            color: theme === "light" ? "#26354c" : "#e5eeff",
            "font-family": "DM Sans, Segoe UI, sans-serif",
            "font-size": 9,
            "font-weight": 600,
            "text-wrap": "wrap",
            "text-max-width": 112,
            "text-valign": "bottom",
            "text-margin-y": 7,
            "text-outline-color": theme === "light" ? "#ffffff" : "#080d17",
            "text-outline-width": 2.4,
            "text-background-color": theme === "light" ? "#ffffff" : "#111b2d",
            "text-background-opacity": theme === "light" ? 0.94 : 0.88,
            "text-background-padding": 5,
            "text-background-shape": "roundrectangle",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.15,
            "curve-style": "bezier",
            "control-point-step-size": 38,
            "line-color": "data(color)",
            "line-opacity": 0.72,
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.58,
            "shadow-blur": 10,
            "shadow-color": "data(color)",
            "shadow-opacity": 0.42,
            label: "data(label)",
            color: theme === "light" ? "#586983" : "#b5c6e4",
            "font-family": "DM Sans, Segoe UI, sans-serif",
            "font-size": 6,
            "font-weight": 500,
            "text-rotation": "autorotate",
            "text-opacity": 0.68,
            "text-background-color": theme === "light" ? "#f8faff" : "#080d17",
            "text-background-opacity": theme === "light" ? 0.94 : 0.86,
            "text-background-padding": 2,
            "text-outline-color": theme === "light" ? "#f8faff" : "#080d17",
            "text-outline-width": 1,
          },
        },
        { selector: 'node[status = "confirmed"]', style: { "border-color": theme === "light" ? "#7de2c2" : "#c4fff1", "border-width": 3, "shadow-blur": 30, "shadow-opacity": 0.94 } },
        { selector: 'node[status = "refuted"]', style: { opacity: 0.48, "shadow-opacity": 0.2 } },
        { selector: 'node[status = "likely"]', style: { "border-color": "#e2d6ff", "border-width": 2.5 } },
        { selector: "node:selected", style: { "border-color": theme === "light" ? "#ffffff" : "#f3f7ff", "border-width": 3, "shadow-blur": 34, "shadow-opacity": 1, "overlay-color": "#72aaff", "overlay-opacity": 0.15, "overlay-padding": 10 } },
        { selector: "edge:selected", style: { width: 2.7, "line-opacity": 1, "shadow-blur": 20, "shadow-opacity": 0.92 } },
      ],
      layout: {
        name: layout,
        animate: false,
        padding: 60,
        minNodeSpacing: 42,
        avoidOverlap: true,
        spacingFactor: 1.12,
        concentric: (node) => node.degree(),
        levelWidth: (nodes) => Math.max(nodes.maxDegree() / 3, 1),
        nodeRepulsion: () => 9000,
        idealEdgeLength: () => 104,
      },
      wheelSensitivity: 0.18,
      minZoom: 0.18,
      maxZoom: 2.4,
    });

    cy.on("tap", "node", (evt) => {
      const d = evt.target.data();
      const raw = (graph.nodes || []).find((n) => String(n.id) === d.id);
      onSelect?.(raw);
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [graph, onSelect, layout, theme]);

  const changeLayout = (value) => setLayout(value);

  return (
    <div className={`graph-stage ${theme === "light" ? "graph-stage-light" : ""}`}>
      <div className="graph-atmosphere" aria-hidden="true" />
      <div className="graph-stage-toolbar">
        <div className="map-brand"><span className="map-brand-mark"><Waypoints size={15} /></span><span><strong>OUTBREAK NETWORK</strong><small>LIVE EVIDENCE MAP</small></span></div>
        <div className="map-controls">
          <label className="layout-control"><span>LAYOUT</span><select value={layout} onChange={(event) => changeLayout(event.target.value)} aria-label="Graph layout"><option value="concentric">Source radial</option><option value="cose">Force graph</option><option value="circle">Orbit</option><option value="breadthfirst">Hierarchy</option></select></label>
          <div className="zoom-controls" aria-label="Graph zoom controls">
            <button onClick={() => cyRef.current?.zoom({ level: (cyRef.current?.zoom() || 1) * 1.2, renderedPosition: { x: (ref.current?.clientWidth || 0) / 2, y: (ref.current?.clientHeight || 0) / 2 } })} aria-label="Zoom in"><Plus size={14} /></button>
            <button onClick={() => cyRef.current?.zoom({ level: (cyRef.current?.zoom() || 1) / 1.2, renderedPosition: { x: (ref.current?.clientWidth || 0) / 2, y: (ref.current?.clientHeight || 0) / 2 } })} aria-label="Zoom out"><Minus size={14} /></button>
            <button onClick={() => fit()} aria-label="Fit graph"><LocateFixed size={14} /></button>
            <button onClick={() => cyRef.current?.reset()} aria-label="Reset graph"><RotateCcw size={13} /></button>
          </div>
        </div>
      </div>
      <div className="graph-canvas" ref={ref} />
      <div className="map-legend">
        <div className="map-legend-heading"><span>LEGEND</span><i className="legend-pulse" /></div>
        <small>NETWORK ENTITIES</small>
        <div className="map-legend-types"><span><i className="legend-case" /> Cases</span><span><i className="legend-hypothesis" /> Hypotheses</span><span><i className="legend-evidence" /> Evidence</span><span><i className="legend-supply" /> Supply chain</span></div>
        <div className="map-legend-divider" />
        <div className="map-counts"><span><strong>{graph?.nodes?.length || 0}</strong> nodes</span><span><strong>{graph?.edges?.length || 0}</strong> links</span></div>
      </div>
    </div>
  );
}
