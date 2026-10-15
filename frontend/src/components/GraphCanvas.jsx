import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";

const TYPE_COLORS = {
  Investigation: "#7c5cff",
  Hypothesis: "#3b82f6",
  Evidence: "#22c55e",
  ToolCall: "#64748b",
  Session: "#f59e0b",
  Case: "#ef4444",
  Person: "#94a3b8",
  Lot: "#06b6d4",
  Supplier: "#a855f7",
  Facility: "#ec4899",
  Shipment: "#eab308",
  Farm: "#84cc16",
  Ingredient: "#14b8a6",
  Isolate: "#f97316",
  Task: "#0ea5e9",
  Recall: "#dc2626",
  Fact: "#8b5cf6",
  ProtocolStep: "#475569",
};

function nodeLabel(props, labels) {
  const p = props || {};
  return (
    p.name ||
    p.statement ||
    p.summary ||
    p.case_id ||
    p.lot_id ||
    p.evidence_id ||
    p.tool ||
    p.role ||
    (labels && labels[0]) ||
    "?"
  );
}

function labelFor(n) {
  const text = String(nodeLabel(n.props, n.labels));
  const clipped = text.length > 46 ? text.slice(0, 44) + "…" : text;
  return clipped;
}

export default function GraphCanvas({ graph, onSelect }) {
  const ref = useRef(null);
  const cyRef = useRef(null);

  useEffect(() => {
    if (!ref.current) return;
    const nodes = (graph?.nodes || []).map((n) => {
      const type = (n.labels && n.labels[0]) || "Node";
      return {
        data: {
          id: String(n.id),
          type,
          label: labelFor({ ...n, id: n.id }, n.labels),
          status: n.props?.status,
          color: TYPE_COLORS[type] || "#64748b",
        },
      };
    });
    const edges = (graph?.edges || []).map((e) => ({
      data: { id: "e" + e.id, source: String(e.source), target: String(e.target), label: e.type },
    }));

    if (cyRef.current) cyRef.current.destroy();
    const cy = cytoscape({
      container: ref.current,
      elements: [...nodes, ...edges],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#e2e8f0",
            "font-size": 9,
            "text-wrap": "wrap",
            "text-max-width": 90,
            "text-valign": "bottom",
            "text-margin-y": 5,
            width: 22,
            height: 22,
            "border-width": 2,
            "border-color": "#0f172a",
          },
        },
        {
          selector: 'node[status = "confirmed"]',
          style: { "border-color": "#22c55e", "border-width": 4, width: 30, height: 30 },
        },
        {
          selector: 'node[status = "refuted"]',
          style: { "border-color": "#ef4444", "border-width": 4, opacity: 0.7 },
        },
        {
          selector: 'node[status = "likely"]',
          style: { "border-color": "#f59e0b", "border-width": 3 },
        },
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            "line-color": "#334155",
            "target-arrow-color": "#334155",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.7,
            width: 1.2,
            label: "data(label)",
            "font-size": 7,
            color: "#64748b",
            "text-rotation": "autorotate",
            "text-opacity": 0.7,
          },
        },
        { selector: ":selected", style: { "border-color": "#fff", "line-color": "#fff" } },
      ],
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 500,
        nodeRepulsion: 9000,
        idealEdgeLength: 90,
        padding: 20,
      },
      wheelSensitivity: 0.2,
    });

    cy.on("tap", "node", (evt) => {
      const d = evt.target.data();
      const raw = (graph.nodes || []).find((n) => String(n.id) === d.id);
      onSelect && onSelect(raw);
    });
    cyRef.current = cy;
    return () => cy.destroy();
  }, [graph, onSelect]);

  return <div className="graph-canvas" ref={ref} />;
}
