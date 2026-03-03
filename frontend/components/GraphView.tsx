import React, { useEffect, useMemo, useRef } from "react";
import cytoscape, { Core, ElementDefinition } from "cytoscape";
import styles from "../styles/graph.module.css";

type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

const BLOOM_LEVELS: BloomLevel[] = ["remember", "understand", "apply", "analyze", "evaluate", "create"];

const LEVEL_LABELS: Record<BloomLevel, string> = {
  remember: "Знать",
  understand: "Понимать",
  apply: "Применять",
  analyze: "Анализировать",
  evaluate: "Оценивать",
  create: "Создавать",
};

const LEVEL_COLORS: Record<BloomLevel, string> = {
  remember: "#4e79a7",
  understand: "#59a14f",
  apply: "#f28e2b",
  analyze: "#af7aa1",
  evaluate: "#e15759",
  create: "#76b7b2",
};

const LEVEL_SHAPES: Record<BloomLevel, cytoscape.Css.NodeShape> = {
  remember: "ellipse",
  understand: "round-rectangle",
  apply: "rectangle",
  analyze: "diamond",
  evaluate: "hexagon",
  create: "triangle",
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
};

const getSortedLevels = (probs: number[]) =>
  BLOOM_LEVELS.map((lvl, idx) => ({ lvl, prob: Number(probs?.[idx] ?? 0) })).sort((a, b) => b.prob - a.prob);

function computeSize(freq: number | null | undefined) {
  const f = Math.max(1, Number(freq ?? 1));
  return 28 + 8 * Math.log(1 + f);
}

export default function GraphView({ nodes, edges, filters, threshold, onHover }: Props) {
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
              "font-size": 9,
              "text-wrap": "wrap",
              "text-max-width": 90,
              "text-valign": "bottom",
              "text-margin-y": 6,
              "background-color": (ele) => LEVEL_COLORS[ele.data("primary") as BloomLevel],
              shape: (ele) => LEVEL_SHAPES[ele.data("primary") as BloomLevel],
              width: "data(size)",
              height: "data(size)",
              "border-width": (ele) => (ele.data("secondary") ? 4 : 1),
              "border-color": (ele) =>
                ele.data("secondary")
                  ? LEVEL_COLORS[ele.data("secondary") as BloomLevel]
                  : "#ffffff",
            },
          },
          {
            selector: "edge",
            style: {
              width: 1,
              "line-color": "#bdbdbd",
              opacity: (ele) => Math.max(0.15, Math.min(0.9, Number(ele.data("weight") ?? 0.2))),
            },
          },
          { selector: ":selected", style: { "border-color": "#111", "border-width": 6 } },
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

  const exportPng = () => {
    const cy = cyRef.current;
    if (!cy) return;
    const png = cy.png({ bg: "#ffffff", full: true, scale: 2 });
    const a = document.createElement("a");
    a.href = png;
    a.download = "knowledge_graph.png";
    a.click();
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <button className={styles.btn} onClick={exportPng} disabled={!filteredNodes.length}>
          Export PNG
        </button>
        <div className={styles.summary}>
          Узлов: {filteredNodes.length}, Рёбер: {edges.length}
        </div>
      </div>
      <div
        ref={containerRef}
        className={styles.canvas}
      />
      <div className={styles.legend}>
        {BLOOM_LEVELS.map((lvl) => (
          <div key={lvl} className={styles.legendItem}>
            <span
              className={styles.swatch}
              style={{ background: LEVEL_COLORS[lvl] }}
            />
            <span>{LEVEL_LABELS[lvl]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
