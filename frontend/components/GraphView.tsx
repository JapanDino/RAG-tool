import React, { useEffect, useMemo, useRef } from "react";
import cytoscape, { Core, ElementDefinition } from "cytoscape";
import styles from "../styles/graph.module.css";

type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

const BLOOM_LEVELS: BloomLevel[] = ["remember", "understand", "apply", "analyze", "evaluate", "create"];

const LEVEL_LABELS: Record<BloomLevel, string> = {
  remember:   "Знать",
  understand: "Понимать",
  apply:      "Применять",
  analyze:    "Анализировать",
  evaluate:   "Оценивать",
  create:     "Создавать",
};

// Vivid palette matching the dark design system
const LEVEL_COLORS: Record<BloomLevel, string> = {
  remember:   "#60a5fa",
  understand: "#34d399",
  apply:      "#fb923c",
  analyze:    "#c084fc",
  evaluate:   "#f87171",
  create:     "#2dd4bf",
};

const LEVEL_SHAPES: Record<BloomLevel, cytoscape.Css.NodeShape> = {
  remember:   "ellipse",
  understand: "round-rectangle",
  apply:      "rectangle",
  analyze:    "diamond",
  evaluate:   "hexagon",
  create:     "triangle",
};

export type AnalyzeNode = {
  id: number;
  title: string;
  context_text: string;
  prob_vector: number[];
  top_levels: BloomLevel[];
  frequency?: number | null;
  rationale?: string | null;
};

export type GraphEdge = { from_id: number; to_id: number; weight: number };

type Props = {
  nodes: AnalyzeNode[];
  edges: GraphEdge[];
  filters: Record<BloomLevel, boolean>;
  threshold: number;
  onHover?: (node: AnalyzeNode | null) => void;
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

export default function GraphView({ nodes, edges, filters, threshold, onHover, searchQuery }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  const filteredNodes = useMemo(
    () => nodes.filter((n) => (n.top_levels || []).some((lvl) => filters[lvl])),
    [nodes, filters]
  );

  const elements: ElementDefinition[] = useMemo(() => {
    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const els: ElementDefinition[] = [];

    for (const n of filteredNodes) {
      const sorted = getSortedLevels(n.prob_vector || []);
      const primary = sorted[0]?.lvl ?? "remember";
      const secondary = sorted[1];
      const hasSecondary = Boolean(secondary && secondary.prob >= threshold);
      els.push({
        data: {
          id: String(n.id),
          label: n.title,
          primary,
          secondary: hasSecondary ? secondary!.lvl : "",
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
              "font-family": "Inter, -apple-system, sans-serif",
              "text-wrap": "wrap",
              "text-max-width": 80,
              "text-valign": "bottom",
              "text-margin-y": 7,
              "text-outline-width": 2,
              "text-outline-color": "#161b27",
              "background-color": (ele) => LEVEL_COLORS[ele.data("primary") as BloomLevel],
              shape: (ele) => LEVEL_SHAPES[ele.data("primary") as BloomLevel],
              width: "data(size)",
              height: "data(size)",
              "border-width": (ele) => (ele.data("secondary") ? 3 : 0),
              "border-color": (ele) =>
                ele.data("secondary")
                  ? LEVEL_COLORS[ele.data("secondary") as BloomLevel]
                  : "transparent",
              "border-opacity": 0.9,
            },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "rgba(139, 146, 168, 0.25)",
              "curve-style": "bezier",
              opacity: (ele) => Math.max(0.12, Math.min(0.75, Number(ele.data("weight") ?? 0.2))),
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

      cyRef.current.on("mouseover", "node", (evt) => {
        const id = Number(evt.target.data("id"));
        const node = filteredNodes.find((n) => n.id === id) || null;
        onHover?.(node);
      });
      cyRef.current.on("mouseout", "node", () => onHover?.(null));
      cyRef.current.on("tap", "node", (evt) => {
        const id = Number(evt.target.data("id"));
        const node = filteredNodes.find((n) => n.id === id) || null;
        onHover?.(node);
      });
    } else {
      const cy = cyRef.current;
      cy.elements().remove();
      cy.add(elements);
      cy.layout({ name: "cose", animate: true, fit: true }).run();
    }
  }, [elements, filteredNodes, onHover]);

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
  }, [searchQuery]);

  const exportPng = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const png = cy.png({ bg: "#161b27", full: true, scale: 2 });
    const a = document.createElement("a");
    a.href = png;
    a.download = "knowledge_graph.png";
    a.click();
  };

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
          {filteredNodes.length} узлов · {edges.length} рёбер
        </span>
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
