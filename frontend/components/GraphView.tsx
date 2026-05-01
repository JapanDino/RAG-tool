import React, { useEffect, useMemo, useRef } from "react";
import cytoscape, { Core, ElementDefinition } from "cytoscape";
import styles from "../styles/graph.module.css";
import {
  BloomLevel,
  BLOOM_LEVELS,
  LEVEL_LABELS,
  LEVEL_COLORS,
  LEVEL_SHAPES,
  AnalyzeNode,
} from "../lib/bloom-constants";

export type { AnalyzeNode };
export type GraphEdge = { from_id: number; to_id: number; weight: number };

type Props = {
  nodes: AnalyzeNode[];
  edges: GraphEdge[];
  filters: Record<BloomLevel, boolean>;
  threshold: number;
  onHover?: (node: AnalyzeNode | null) => void;
  onSelect?: (node: AnalyzeNode | null) => void;
  searchQuery?: string;
};

const getSortedLevels = (probs: number[]) =>
  BLOOM_LEVELS.map((lvl, idx) => ({ lvl, prob: Number(probs?.[idx] ?? 0) })).sort(
    (a, b) => b.prob - a.prob
  );

function computeSize(freq: number | null | undefined) {
  const f = Math.max(1, Number(freq ?? 1));
  return 24 + 8 * Math.log(1 + f);
}

export default function GraphView({ nodes, edges, filters, threshold, onHover, onSelect, searchQuery }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const filteredNodesRef = useRef<AnalyzeNode[]>([]);
  const onHoverRef = useRef(onHover);
  const onSelectRef = useRef(onSelect);

  const filteredNodes = useMemo(
    () => nodes.filter((n) => (n.top_levels || []).some((lvl) => filters[lvl])),
    [nodes, filters]
  );
  filteredNodesRef.current = filteredNodes;
  onHoverRef.current = onHover;
  onSelectRef.current = onSelect;

  const elements: ElementDefinition[] = useMemo(() => {
    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const els: ElementDefinition[] = [];

    for (const n of filteredNodes) {
      const sorted = getSortedLevels(n.prob_vector || []);
      const primary = sorted[0]?.lvl ?? "remember";
      const secondary = sorted[1];
      const hasSecondary = Boolean(secondary && secondary.prob >= threshold);
      const primaryPct = hasSecondary
        ? Math.round((sorted[0].prob / (sorted[0].prob + secondary!.prob)) * 100)
        : 100;
      els.push({
        data: {
          id: String(n.id),
          label: n.title,
          primary,
          secondary: hasSecondary ? secondary!.lvl : "",
          primaryPct,
          secondaryPct: 100 - primaryPct,
          size: computeSize(n.frequency),
        },
      });
    }

    let i = 0;
    for (const e of edges) {
      if (!nodeIds.has(e.from_id) || !nodeIds.has(e.to_id)) continue;
      els.push({
        data: {
          id: `e-${i++}`,
          source: String(e.from_id),
          target: String(e.to_id),
          weight: e.weight,
        },
      });
    }
    return els;
  }, [filteredNodes, edges, threshold]);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!cyRef.current) {
      cyRef.current = cytoscape({
        container: containerRef.current,
        elements,
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              color: "#c9d1e8",
              "font-size": 9,
              "font-family": "IBM Plex Sans, Segoe UI, sans-serif",
              "text-wrap": "wrap",
              "text-max-width": "80px",
              "text-valign": "bottom",
              "text-margin-y": 7,
              "text-outline-width": 2,
              "text-outline-color": "#161b27",
              // background-color shows through when pie sections don't fill 100%
              "background-color": (ele: cytoscape.NodeSingular) =>
                LEVEL_COLORS[ele.data("primary") as BloomLevel],
              shape: (ele: cytoscape.NodeSingular) => LEVEL_SHAPES[ele.data("primary") as BloomLevel],
              width: "data(size)",
              height: "data(size)",
              // Pie-chart fill: primary sector + optional secondary sector
              "pie-size": "100%",
              "pie-1-background-color": (ele: cytoscape.NodeSingular) =>
                LEVEL_COLORS[ele.data("primary") as BloomLevel] || "#60a5fa",
              "pie-1-background-size": (ele: cytoscape.NodeSingular) =>
                Number(ele.data("primaryPct") ?? 100),
              "pie-1-background-opacity": 1,
              "pie-2-background-color": (ele: cytoscape.NodeSingular) =>
                ele.data("secondary")
                  ? LEVEL_COLORS[ele.data("secondary") as BloomLevel]
                  : "transparent",
              "pie-2-background-size": (ele: cytoscape.NodeSingular) =>
                Number(ele.data("secondaryPct") ?? 0),
              "pie-2-background-opacity": (ele: cytoscape.NodeSingular) =>
                ele.data("secondary") ? 1 : 0,
              "border-width": 0,
            },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "rgba(139, 146, 168, 0.25)",
              "curve-style": "bezier",
              opacity: (ele: cytoscape.EdgeSingular) =>
                Math.max(0.12, Math.min(0.75, Number(ele.data("weight") ?? 0.2))),
            },
          },
          {
            selector: ".dim",
            style: { opacity: 0.1 },
          },
          {
            selector: ".hl",
            style: { "border-width": 4, "border-color": "#6366f1", "border-opacity": 1, opacity: 1 },
          },
          {
            selector: ":selected",
            style: {
              "border-color": "#818cf8",
              "border-width": 4,
              "border-opacity": 1,
            },
          },
          {
            selector: "node:active",
            style: {
              "overlay-color": "#6366f1",
              "overlay-padding": 8,
              "overlay-opacity": 0.2,
            },
          },
        ],
        layout: { name: "cose", animate: true, fit: true },
      });

      cyRef.current.on("mouseover", "node", (evt: cytoscape.EventObject) => {
        const id = Number(evt.target.data("id"));
        const node = filteredNodesRef.current.find((n) => n.id === id) || null;
        onHoverRef.current?.(node);
      });
      cyRef.current.on("mouseout", "node", () => onHoverRef.current?.(null));
      cyRef.current.on("tap", "node", (evt: cytoscape.EventObject) => {
        const id = Number(evt.target.data("id"));
        const node = filteredNodesRef.current.find((n) => n.id === id) || null;
        onSelectRef.current?.(node);
      });
    } else {
      const cy = cyRef.current;
      cy.elements().remove();
      cy.add(elements);
      cy.layout({ name: "cose", animate: true, fit: true }).run();
    }
  }, [elements]);

  // Highlight nodes matching searchQuery
  useEffect(() => {
    if (!cyRef.current) return;
    cyRef.current.elements().removeClass("dim hl");
    if (!searchQuery?.trim()) return;
    const q = searchQuery.toLowerCase();
    cyRef.current.nodes().forEach((node) => {
      const label = (node.data("label") || "").toLowerCase();
      if (label.includes(q)) node.addClass("hl");
      else node.addClass("dim");
    });
  }, [searchQuery, elements]);

  const exportPng = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const png = cy.png({ bg: "#161b27", full: true, scale: 2 });
    const a = document.createElement("a");
    a.href = png;
    a.download = "knowledge_graph.png";
    a.click();
  };

  const zoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.25);
  const zoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() * 0.8);
  const zoomFit = () => cyRef.current?.fit(undefined, 20);
  const visibleEdgeCount = Math.max(0, elements.length - filteredNodes.length);

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <button
          className={styles.btn}
          onClick={exportPng}
          disabled={!filteredNodes.length}
        >
          Export PNG
        </button>
        <span className={styles.summary}>
          {filteredNodes.length} узлов · {visibleEdgeCount} рёбер
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <button className={styles.btn} onClick={zoomIn} title="Увеличить">+</button>
          <button className={styles.btn} onClick={zoomOut} title="Уменьшить">−</button>
          <button className={styles.btn} onClick={zoomFit} title="По размеру">⊡</button>
        </div>
      </div>

      <div ref={containerRef} className={styles.canvas} />

      <div className={styles.legend}>
        <div className={styles.legendTitle}>Уровни Блума</div>
        {BLOOM_LEVELS.map((lvl) => (
          <div key={lvl} className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: LEVEL_COLORS[lvl] }} />
            <span>{LEVEL_LABELS[lvl]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
