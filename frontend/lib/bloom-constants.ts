import type { Css } from "cytoscape";

export type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

export const BLOOM_LEVELS: BloomLevel[] = [
  "remember",
  "understand",
  "apply",
  "analyze",
  "evaluate",
  "create",
];

export const LEVEL_LABELS: Record<BloomLevel, string> = {
  remember:   "Знать",
  understand: "Понимать",
  apply:      "Применять",
  analyze:    "Анализировать",
  evaluate:   "Оценивать",
  create:     "Создавать",
};

export const LEVEL_COLORS: Record<BloomLevel, string> = {
  remember:   "#60a5fa",
  understand: "#34d399",
  apply:      "#fb923c",
  analyze:    "#c084fc",
  evaluate:   "#f87171",
  create:     "#2dd4bf",
};

export const LEVEL_BG: Record<BloomLevel, string> = {
  remember:   "rgba(96,165,250,0.14)",
  understand: "rgba(52,211,153,0.14)",
  apply:      "rgba(251,146,60,0.14)",
  analyze:    "rgba(192,132,252,0.14)",
  evaluate:   "rgba(248,113,113,0.14)",
  create:     "rgba(45,212,191,0.14)",
};

export const LEVEL_BORDER: Record<BloomLevel, string> = {
  remember:   "rgba(96,165,250,0.28)",
  understand: "rgba(52,211,153,0.28)",
  apply:      "rgba(251,146,60,0.28)",
  analyze:    "rgba(192,132,252,0.28)",
  evaluate:   "rgba(248,113,113,0.28)",
  create:     "rgba(45,212,191,0.28)",
};

export const LEVEL_SHAPES: Record<BloomLevel, Css.NodeShape> = {
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
