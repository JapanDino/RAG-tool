import React, { useMemo, useState, useEffect, useRef, useCallback } from "react";
import dynamic from "next/dynamic";
import JobStatus from "../components/JobStatus";
import ErrorBoundary from "../components/ErrorBoundary";
import styles from "../styles/home.module.css";

const GraphView = dynamic(() => import("../components/GraphView"), { ssr: false });
import {
  BloomLevel,
  BLOOM_LEVELS,
  LEVEL_LABELS,
  LEVEL_COLORS,
  LEVEL_BG,
  LEVEL_BORDER,
  AnalyzeNode,
} from "../lib/bloom-constants";

type SearchResult = {
  chunk_id: number;
  text: string;
  document_id: number;
  document_title: string;
  score: number;
};

type Toast = { id: number; msg: string; type: "success" | "error" | "info" };
type CanvasAlert = { title: string; message: string };

type GraphEdge = {
  from_id: number;
  to_id: number;
  weight: number;
};

const getSortedLevels = (probs: number[]) =>
  BLOOM_LEVELS.map((lvl, idx) => ({ lvl, prob: Number(probs?.[idx] ?? 0) }))
    .sort((a, b) => b.prob - a.prob);

type ConfidenceBand = "high" | "medium" | "low";

function getConfidenceMeta(node: Pick<AnalyzeNode, "prob_vector" | "top_levels">) {
  const sorted = getSortedLevels(node.prob_vector || []);
  const primary = sorted[0] || { lvl: node.top_levels?.[0] || "remember", prob: 0 };
  const runnerUp = sorted[1] || null;
  const gap = runnerUp ? primary.prob - runnerUp.prob : primary.prob;

  let band: ConfidenceBand = "low";
  if (primary.prob >= 0.72 && gap >= 0.18) {
    band = "high";
  } else if (primary.prob >= 0.52 && gap >= 0.08) {
    band = "medium";
  }

  const label =
    band === "high"
      ? "Высокая уверенность"
      : band === "medium"
        ? "Средняя уверенность"
        : "Низкая уверенность";

  const shortLabel =
    band === "high" ? "Высокая" : band === "medium" ? "Средняя" : "Низкая";

  const guidance =
    band === "high"
      ? "Распределение устойчивое, ручная проверка обычно не требуется."
      : band === "medium"
        ? "Решение выглядит правдоподобно, но есть близкие альтернативы."
        : "Уровни расположены близко друг к другу — лучше проверить вручную.";

  return {
    band,
    label,
    shortLabel,
    guidance,
    primary,
    runnerUp,
    gap,
  };
}

function getExplainabilityLines(node: AnalyzeNode) {
  const meta = getConfidenceMeta(node);
  const lines = [
    `Основной уровень: ${LEVEL_LABELS[meta.primary.lvl]} (${(meta.primary.prob * 100).toFixed(0)}%)`,
  ];
  if (meta.runnerUp) {
    lines.push(
      `Ближайшая альтернатива: ${LEVEL_LABELS[meta.runnerUp.lvl]} (${(meta.runnerUp.prob * 100).toFixed(0)}%)`
    );
  }
  lines.push(`Разрыв между 1-м и 2-м уровнем: ${(meta.gap * 100).toFixed(0)} п.п.`);
  return lines;
}

// ── SVG Icons (inline, no deps) ───────────────────────────────

function IconBrain() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.5 2a2.5 2.5 0 0 1 5 0"/>
      <path d="M9.5 2C7 2 5 4 5 6.5a5.5 5.5 0 0 0 1.5 3.8"/>
      <path d="M14.5 2C17 2 19 4 19 6.5a5.5 5.5 0 0 1-1.5 3.8"/>
      <path d="M6.5 10.3C4.5 11.2 3 13 3 15.5a5.5 5.5 0 0 0 5.5 5.5c1.5 0 2.8-.6 3.8-1.5"/>
      <path d="M17.5 10.3c2 .9 3.5 2.7 3.5 5.2a5.5 5.5 0 0 1-5.5 5.5c-1.5 0-2.8-.6-3.8-1.5"/>
      <path d="M12 12a3 3 0 0 0-3 3v3a3 3 0 0 0 6 0v-3a3 3 0 0 0-3-3z"/>
    </svg>
  );
}

function IconGraph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="12" r="2"/>
      <circle cx="19" cy="5" r="2"/>
      <circle cx="19" cy="19" r="2"/>
      <path d="M7 12h7"/>
      <path d="M17.2 7.4L14 10"/>
      <path d="M17.2 16.6L14 14"/>
    </svg>
  );
}

function IconTag() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2H2v10l10 10L22 12z"/>
      <circle cx="7" cy="7" r="1" fill="currentColor"/>
    </svg>
  );
}

function IconUpload() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  );
}

function IconDownload() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  );
}

function IconRefresh() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/>
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg>
  );
}

function IconPlus() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <line x1="12" y1="5" x2="12" y2="19"/>
      <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );
}

function IconAlert() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="8" x2="12" y2="12"/>
      <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  );
}

function IconFile() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
    </svg>
  );
}

function IconChevron() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  );
}

function IconNodes() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="5" r="2"/>
      <circle cx="5" cy="19" r="2"/>
      <circle cx="19" cy="19" r="2"/>
      <line x1="12" y1="7" x2="12" y2="14"/>
      <line x1="12" y1="14" x2="5" y2="17"/>
      <line x1="12" y1="14" x2="19" y2="17"/>
    </svg>
  );
}

function IconSparkle() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2l2.09 6.26L20 10l-5.91 1.74L12 18l-2.09-6.26L4 10l5.91-1.74z"/>
    </svg>
  );
}

function IconCanvas() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 10v6M2 10l10-5 10 5-10 5z"/>
      <path d="M6 12v5c3 3 9 3 12 0v-5"/>
    </svg>
  );
}

// ── BloomBadge component ──────────────────────────────────────

function BloomBadge({ level }: { level: BloomLevel }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "3px 9px",
        borderRadius: 999,
        fontSize: 11.5,
        fontWeight: 500,
        whiteSpace: "nowrap",
        background: LEVEL_BG[level],
        color: LEVEL_COLORS[level],
        border: `1px solid ${LEVEL_BORDER[level]}`,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: LEVEL_COLORS[level],
          flexShrink: 0,
        }}
      />
      {LEVEL_LABELS[level]}
    </span>
  );
}

// ── Main component ────────────────────────────────────────────


type HeroStatTone = "neutral" | "accent" | "success" | "warning" | "info";

function SectionHero({
  eyebrow,
  title,
  description,
  stats = [],
  actions,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  stats?: { label: string; value: React.ReactNode; tone?: HeroStatTone }[];
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const toneClass: Record<HeroStatTone, string> = {
    neutral: styles.heroStat,
    accent: [styles.heroStat, styles.heroStatAccent].join(" "),
    success: [styles.heroStat, styles.heroStatSuccess].join(" "),
    warning: [styles.heroStat, styles.heroStatWarning].join(" "),
    info: [styles.heroStat, styles.heroStatInfo].join(" "),
  };

  return (
    <div className={styles.sectionHero}>
      <div className={styles.sectionHeroTop}>
        <div className={styles.sectionHeroMain}>
          <div className={styles.sectionEyebrow}>{eyebrow}</div>
          <div className={styles.sectionHeroTitle}>{title}</div>
          <div className={styles.sectionHeroText}>{description}</div>
        </div>
        {actions ? <div className={styles.sectionHeroActions}>{actions}</div> : null}
      </div>
      {stats.length > 0 && (
        <div className={styles.sectionHeroStats}>
          {stats.map((stat) => (
            <div
              key={`${stat.label}-${String(stat.value)}`}
              className={toneClass[stat.tone || "neutral"]}
            >
              <span className={styles.heroStatLabel}>{stat.label}</span>
              <span className={styles.heroStatValue}>{stat.value}</span>
            </div>
          ))}
        </div>
      )}
      {children ? <div className={styles.sectionHeroExtra}>{children}</div> : null}
    </div>
  );
}

function FlowStep({
  step,
  title,
  text,
  state,
}: {
  step: string;
  title: string;
  text: string;
  state: "pending" | "current" | "done";
}) {
  const stateClass =
    state === "done"
      ? styles.flowStepDone
      : state === "current"
        ? styles.flowStepCurrent
        : styles.flowStepPending;

  return (
    <div className={[styles.flowStep, stateClass].join(" ")}>
      <div className={styles.flowStepIndex}>{step}</div>
      <div className={styles.flowStepBody}>
        <div className={styles.flowStepTitle}>{title}</div>
        <div className={styles.flowStepText}>{text}</div>
      </div>
    </div>
  );
}

export default function Home() {

  const [name, setName] = useState("");
  const [ds, setDs] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [lastJob, setLastJob] = useState<number | undefined>();
  const [activeTab, setActiveTab] = useState<"analysis" | "graph" | "labeling" | "search" | "dashboard" | "canvas">("analysis");
  const [textInput, setTextInput] = useState("");
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [analyzeFileName, setAnalyzeFileName] = useState<string | null>(null);
  const [nodes, setNodes] = useState<AnalyzeNode[]>([]);
  const [nodesStatus, setNodesStatus] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeStatusMsg, setAnalyzeStatusMsg] = useState("");
  const analyzeProgressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const analyzeAbortRef = useRef<AbortController | null>(null);
  const loadGraphAbortRef = useRef<AbortController | null>(null);
  const [showGuide, setShowGuide] = useState(false);
  const [maxNodes, setMaxNodes] = useState(30);
  const [maxNodesAuto, setMaxNodesAuto] = useState(false);

  const suggestMaxNodes = (text: string): number => {
    const chars = text.replace(/\s/g, "").length;
    return Math.min(500, Math.max(10, Math.round(chars / 3000) * 10));
  };
  const [graphNodesData, setGraphNodesData] = useState<AnalyzeNode[]>([]);
  const [graphEdgesData, setGraphEdgesData] = useState<GraphEdge[]>([]);
  const [threshold, setThreshold] = useState(0.3);
  const [graphTopK, setGraphTopK] = useState(3);
  const [graphMinScore, setGraphMinScore] = useState(0.2);
  const [graphIncludeCo, setGraphIncludeCo] = useState(true);
  const [graphLimitNodes, setGraphLimitNodes] = useState(300);
  const [filters, setFilters] = useState<Record<BloomLevel, boolean>>({
    remember: true,
    understand: true,
    apply: true,
    analyze: true,
    evaluate: true,
    create: true,
  });
  const [hoveredNode, setHoveredNode] = useState<AnalyzeNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<AnalyzeNode | null>(null);

  const [annotator, setAnnotator] = useState("default");
  const [labelQueue, setLabelQueue] = useState<AnalyzeNode[]>([]);
  const [labelQueueStatus, setLabelQueueStatus] = useState<string | null>(null);
  const [labelProgress, setLabelProgress] = useState<{ total: number; labeled: number } | null>(null);
  const [currentLabels, setCurrentLabels] = useState<Record<BloomLevel, boolean>>({
    remember: false,
    understand: false,
    apply: false,
    analyze: false,
    evaluate: false,
    create: false,
  });

  const DEFAULT_API = process.env.NEXT_PUBLIC_API_BASE || "/api-proxy";
  const [apiBase, setApiBase] = useState(DEFAULT_API);
  const [apiStatus, setApiStatus] = useState<"unknown" | "ok" | "down">("unknown");
  const [error, setError] = useState<string | null>(null);

  // ── Dashboard ────────────────────────────────────────────────
  const [dashDatasets, setDashDatasets] = useState<any[]>([]);
  const [dashNodeCount, setDashNodeCount] = useState<number | null>(null);
  const [isDashLoading, setIsDashLoading] = useState(false);

  // ── Settings ─────────────────────────────────────────────────
  const [showSettings, setShowSettings] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [minProb, setMinProb] = useState(0.2);
  const [maxLevels, setMaxLevels] = useState(6);
  const [embeddingModel, setEmbeddingModel] = useState("");

  // ── Node detail modal ─────────────────────────────────────────
  const [detailNode, setDetailNode] = useState<AnalyzeNode | null>(null);

  // ── Inline editing ────────────────────────────────────────────
  const [editingNodeId, setEditingNodeId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContext, setEditContext] = useState("");

  // ── Graph search ──────────────────────────────────────────────
  const [graphSearch, setGraphSearch] = useState("");

  // ── Search mode: chunks vs knowledge nodes ────────────────────
  const [searchMode, setSearchMode] = useState<"chunks" | "nodes">("chunks");
  const [nodeSearchResults, setNodeSearchResults] = useState<AnalyzeNode[]>([]);
  const [nodeSearchQuery, setNodeSearchQuery] = useState("");

  // ── Onboarding ────────────────────────────────────────────────
  const [showOnboarding, setShowOnboarding] = useState(false);

  // ── Export dropdown ───────────────────────────────────────────
  const [showExportMenu, setShowExportMenu] = useState(false);

  // ── Batch upload ──────────────────────────────────────────────
  const [batchFiles, setBatchFiles] = useState<{ name: string; file: File; status: "pending"|"uploading"|"done"|"error" }[]>([]);

  // ── Undo labeling ─────────────────────────────────────────────
  const [undoStack, setUndoStack] = useState<{ node: AnalyzeNode; labels: Record<BloomLevel, boolean> }[]>([]);

  // ── Toast system ────────────────────────────────────────────
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastCounter = useRef(0);
  const addToast = (msg: string, type: Toast["type"] = "info") => {
    const id = ++toastCounter.current;
    setToasts(p => [...p, { id, msg, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3800);
  };

  // ── Search tab ───────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchTopK, setSearchTopK] = useState(5);
  const [searchDone, setSearchDone] = useState(false);

  // ── Node filter/sort ─────────────────────────────────────────
  const [nodeSearch, setNodeSearch] = useState("");
  const [nodeSort, setNodeSort] = useState<"default" | "confidence" | "alpha" | "level">("default");

  // ── Text history ─────────────────────────────────────────────
  const [textHistory, setTextHistory] = useState<string[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // ── Canvas LMS ───────────────────────────────────────────────
  type CanvasCourse = { id: number; name: string; course_code: string | null; workflow_state: string };
  const [canvasCourses, setCanvasCourses] = useState<CanvasCourse[]>([]);
  const [canvasCoursesLoading, setCanvasCoursesLoading] = useState(false);
  const [canvasSelectedCourse, setCanvasSelectedCourse] = useState<number | null>(null);
  const [canvasContentTypes, setCanvasContentTypes] = useState<string[]>(["syllabus", "pages", "assignments", "quizzes", "discussions", "files"]);
  const [canvasMaxNodes, setCanvasMaxNodes] = useState(30);
  const [canvasMaxFiles, setCanvasMaxFiles] = useState(20);
  const [canvasIngesting, setCanvasIngesting] = useState(false);
const [canvasIngestResult, setCanvasIngestResult] = useState<{ documents_ingested: number; nodes_created: number; nodes_updated: number; skipped: string[] } | null>(null);
const [canvasProgress, setCanvasProgress] = useState<{ label: string; stage: string; nodes_created: number; nodes_updated: number; elapsedSec?: number } | null>(null);
const [canvasAlert, setCanvasAlert] = useState<CanvasAlert | null>(null);
const [canvasCourseSearch, setCanvasCourseSearch] = useState("");
const canvasProgressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);


  // Restore persisted values on mount
  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedApi = localStorage.getItem("bloom_api");
    const shouldUseProxy =
      !savedApi ||
      savedApi === "http://localhost:8000" ||
      savedApi === "http://127.0.0.1:8000" ||
      savedApi.includes("://backend:");
    const resolvedApi = shouldUseProxy ? DEFAULT_API : savedApi;
    setApiBase(resolvedApi);

    const savedDs = localStorage.getItem("bloom_ds");
    if (savedDs) setDs(Number(savedDs));

    const savedHistory = localStorage.getItem("bloom_history");
    if (savedHistory) { try { setTextHistory(JSON.parse(savedHistory)); } catch {} }

    // Settings
    const savedMinProb = localStorage.getItem("bloom_min_prob");
    if (savedMinProb) setMinProb(Number(savedMinProb));
    const savedMaxLevels = localStorage.getItem("bloom_max_levels");
    if (savedMaxLevels) setMaxLevels(Number(savedMaxLevels));
    const savedModel = localStorage.getItem("bloom_embedding_model");
    if (savedModel) setEmbeddingModel(savedModel);
    const savedAnnotator = localStorage.getItem("bloom_annotator");
    if (savedAnnotator) setAnnotator(savedAnnotator);

    const savedTheme = localStorage.getItem("bloom_theme");
    if (savedTheme === "dark" || savedTheme === "light") {
      setTheme(savedTheme);
      document.documentElement.setAttribute("data-theme", savedTheme);
    } else {
      document.documentElement.setAttribute("data-theme", "light");
    }

    // Onboarding
    if (!localStorage.getItem("bloom_visited")) {
      setShowOnboarding(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist ds and apiBase
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (ds) localStorage.setItem("bloom_ds", String(ds));
    else localStorage.removeItem("bloom_ds");
  }, [ds]);

  useEffect(() => { localStorage.setItem("bloom_min_prob", String(minProb)); }, [minProb]);
  useEffect(() => { localStorage.setItem("bloom_max_levels", String(maxLevels)); }, [maxLevels]);
  useEffect(() => { localStorage.setItem("bloom_embedding_model", embeddingModel); }, [embeddingModel]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem("bloom_theme", theme);
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);
  useEffect(() => { localStorage.setItem("bloom_annotator", annotator); }, [annotator]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem("bloom_api", apiBase);
  }, [apiBase]);

  const checkApiStatus = useCallback(async () => {
    try {
      const controller = new AbortController();
      // 8 s — Docker Desktop + WSL2 relay can be slow on first request
      const t = setTimeout(() => controller.abort(), 8000);
      const r = await fetch(`${apiBase}/health`, { signal: controller.signal });
      clearTimeout(t);
      setApiStatus(r.ok ? "ok" : "down");
    } catch {
      setApiStatus("down");
    }
  }, [apiBase]);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      if (cancelled) return;
      await checkApiStatus();
    };
    setApiStatus("unknown");
    check();
    const it = setInterval(check, 8000);
    return () => { cancelled = true; clearInterval(it); };
  }, [checkApiStatus]);

  const apiFetchJson = useCallback(async (path: string, init?: RequestInit): Promise<any | null> => {
    try {
      setError(null);
      const r = await fetch(`${apiBase}${path}`, init);
      const text = await r.text();
      let data: any = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = text;
      }
      if (!r.ok) {
        const details = typeof data === "string" ? data : JSON.stringify(data);
        setError(`${r.status} ${r.statusText}${details ? `: ${details}` : ""}`);
        return null;
      }
      return data ?? null;
    } catch (e: any) {
      const raw = String(e?.message || e);
      const msg =
        e?.name === "AbortError"
          ? "API не отвечает (таймаут). Проверь, что backend запущен и порт 8000 доступен."
          : raw.includes("Failed to fetch")
            ? `Не удалось подключиться к API (${apiBase}). Проверь:\n- backend запущен и слушает 0.0.0.0:8000\n- в браузере открывается ${apiBase}/docs\n- Docker Desktop/WSL не блокирует localhost\n- CORS включен (в backend сейчас CORS_ALLOW_ORIGINS=*)`
            : `Ошибка запроса к API: ${raw}`;
      setError(msg);
      return null;
    }
  }, [apiBase]);

  const createDataset = async () => {
    if (!name.trim()) {
      setError("Укажи имя датасета перед созданием.");
      return;
    }
    const j = await apiFetchJson(`/datasets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!j) return;
    setDs(j.id);
    addToast(`✓ Dataset #${j.id} создан`, "success");
  };

  const upload = async () => {
    if (!ds || !file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      setError(null);
      const r = await fetch(`${apiBase}/datasets/${ds}/documents`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const j = await r.json();
      if (j.job_id) setLastJob(j.job_id);
    } catch (e: any) {
      setError(`Не удалось загрузить документ: ${String(e?.message || e)}`);
    }
  };

  const indexDs = async () => {
    if (!ds) return;
    const j = await apiFetchJson(`/datasets/${ds}/index`, { method: "POST" });
    if (!j) return;
    setLastJob(j.job_id);
  };

  const annotate = async (level: string) => {
    if (!ds) return;
    const j = await apiFetchJson(`/annotate/datasets/${ds}?level=${encodeURIComponent(level)}`, { method: "POST" });
    if (!j) return;
    setLastJob(j.job_id);
  };

  const exportJsonl = () => {
    if (!ds) return;
    window.open(`${apiBase}/export/datasets/${ds}?format=jsonl`, "_blank");
  };

  const ANALYZE_MSGS = [
    "Извлекаем ключевые понятия…",
    "Классифицируем по уровням Блума…",
    "Генерируем векторные эмбеддинги…",
    "Сохраняем узлы знаний в БД…",
  ];

  const analyzeText = async () => {
    if (!textInput.trim()) return;

    analyzeAbortRef.current?.abort();
    analyzeAbortRef.current = new AbortController();
    const signal = analyzeAbortRef.current.signal;

    // Auto-create dataset if none is selected yet
    let datasetId = ds;
    if (!datasetId) {
      const dsName = name.trim() || "dataset";
      const j = await apiFetchJson(`/datasets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: dsName }),
      });
      if (!j) return;
      setDs(j.id);
      setName(dsName);
      datasetId = j.id;
    }

    setIsAnalyzing(true);
    setNodes([]);
    setNodesStatus(null);
    setAnalyzeProgress(4);
    setAnalyzeStatusMsg(ANALYZE_MSGS[0]);
    let msgIdx = 0;
    analyzeProgressRef.current = setInterval(() => {
      setAnalyzeProgress((p) => (p >= 84 ? 84 : p + Math.random() * 7 + 2));
      msgIdx = (msgIdx + 1) % ANALYZE_MSGS.length;
      setAnalyzeStatusMsg(ANALYZE_MSGS[msgIdx]);
    }, 900);

    const body: Record<string, unknown> = {
      text: textInput,
      dataset_id: datasetId,
      max_nodes: maxNodes,
      min_prob: minProb,
      max_levels: maxLevels,
    };
    if (embeddingModel) {
      body.embedding_model = embeddingModel;
    }

    const json = await apiFetchJson(`/analyze/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });

    if (analyzeProgressRef.current) { clearInterval(analyzeProgressRef.current); analyzeProgressRef.current = null; }
    setAnalyzeProgress(100);
    setAnalyzeStatusMsg("Готово!");
    setTimeout(() => { setAnalyzeProgress(0); setAnalyzeStatusMsg(""); }, 700);

    setIsAnalyzing(false);
    if (!json) {
      setNodesStatus("Ошибка анализа (см. сообщение выше).");
      return;
    }
    const items: AnalyzeNode[] = json.nodes || [];
    setNodes(items);
    setNodesStatus(items.length ? `Найдено узлов: ${items.length}` : "Узлы не найдены");
    if (items.length) {
      addToast(`✓ Найдено ${items.length} узлов`, "success");
      // Save to history
      if (textInput.trim().length > 20) {
        setTextHistory(h => {
          const next = [textInput.trim(), ...h.filter(x => x !== textInput.trim())].slice(0, 5);
          localStorage.setItem("bloom_history", JSON.stringify(next));
          return next;
        });
      }
    } else {
      addToast("Узлы не найдены — попробуй другой текст", "info");
    }
  };

  const loadTextFile = async (f: File | null) => {
    if (!f) return;
    setIsTranscribing(true);
    setAnalyzeFileName(f.name);
    setName(f.name.replace(/\.[^.]+$/, ""));
    try {
      if (f.name.toLowerCase().endsWith(".pdf")) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch(`${apiBase}/datasets/extract-text`, { method: "POST", body: fd });
        if (!r.ok) { setError("Не удалось извлечь текст из PDF"); setAnalyzeFileName(null); return; }
        const { text } = await r.json();
        setTextInput(text);
        setMaxNodes(suggestMaxNodes(text));
        setMaxNodesAuto(true);
      } else {
        const text = await f.text();
        setTextInput(text);
        setMaxNodes(suggestMaxNodes(text));
        setMaxNodesAuto(true);
      }
    } finally {
      setIsTranscribing(false);
    }
  };

  const exportNodesJson = () => {
    if (!nodes.length) return;
    const blob = new Blob([JSON.stringify(nodes, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "knowledge_nodes.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportNodesCsv = () => {
    if (!nodes.length) return;
    const header = ["id", "title", "context_text", "top_levels", "prob_vector"].join(",");
    const rows = nodes.map((n) =>
      [
        n.id,
        `"${n.title.replace(/"/g, '""')}"`,
        `"${n.context_text.replace(/"/g, '""')}"`,
        `"${n.top_levels.join("|")}"`,
        `"${n.prob_vector.join("|")}"`,
      ].join(",")
    );
    const csv = [header, ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "knowledge_nodes.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const loadNodesFromDb = async () => {
    if (!ds) return;
    setNodesStatus("Загружаем узлы из БД...");
    const params = new URLSearchParams({
      dataset_id: String(ds),
      limit: "1000",
      offset: "0",
    });
    const json = await apiFetchJson(`/nodes?${params.toString()}`);
    if (!json) {
      setNodesStatus("Ошибка загрузки узлов.");
      return;
    }
    const items: AnalyzeNode[] = json.items || [];
    setNodes(items);
    setNodesStatus(items.length ? `Загружено узлов: ${items.length}` : "В БД нет узлов");
  };

  const loadDashboard = async () => {
    setIsDashLoading(true);
    const datasets = await apiFetchJson("/datasets");
    if (datasets) setDashDatasets(Array.isArray(datasets) ? datasets : datasets.items || []);
    if (ds) {
      const params = new URLSearchParams({ dataset_id: String(ds), limit: "1", offset: "0" });
      const res = await apiFetchJson(`/nodes?${params.toString()}`);
      if (res) setDashNodeCount(res.total ?? null);
    }
    setIsDashLoading(false);
  };

  const saveInlineEdit = async (nodeId: number) => {
    const ok = await apiFetchJson(`/nodes/${nodeId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: editTitle, context_text: editContext }),
    });
    if (ok !== null) {
      setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, title: editTitle, context_text: editContext } : n));
      addToast("✓ Узел обновлён", "success");
    }
    setEditingNodeId(null);
  };

  const searchByNodes = async () => {
    if (!nodeSearchQuery.trim()) return;
    setIsSearching(true);
    setNodeSearchResults([]);
    setSearchDone(false);
    const params = new URLSearchParams({ limit: "200", offset: "0" });
    if (ds) params.set("dataset_id", String(ds));
    const json = await apiFetchJson(`/nodes?${params.toString()}`);
    setIsSearching(false);
    setSearchDone(true);
    if (!json) return;
    const all: AnalyzeNode[] = json.items || [];
    const q = nodeSearchQuery.toLowerCase();
    setNodeSearchResults(all.filter(n =>
      n.title.toLowerCase().includes(q) || (n.context_text || "").toLowerCase().includes(q)
    ));
  };

  const batchUploadAll = async () => {
    if (!ds) { addToast("Выбери dataset перед загрузкой", "error"); return; }
    const pending = batchFiles.map((item, i) => ({ item, i })).filter(({ item }) => item.status !== "done");
    pending.forEach(({ i }) =>
      setBatchFiles(prev => prev.map((x, idx) => idx === i ? { ...x, status: "uploading" } : x))
    );
    const uploadOne = async ({ item, i }: { item: typeof batchFiles[0]; i: number }) => {
      const fd = new FormData();
      fd.append("file", item.file);
      try {
        const r = await fetch(`${apiBase}/datasets/${ds}/documents`, { method: "POST", body: fd });
        setBatchFiles(prev => prev.map((x, idx) => idx === i ? { ...x, status: r.ok ? "done" : "error" } : x));
        if (r.ok) {
          const j = await r.json();
          if (j.job_id) setLastJob(j.job_id);
          return true;
        }
      } catch {
        setBatchFiles(prev => prev.map((x, idx) => idx === i ? { ...x, status: "error" } : x));
      }
      return false;
    };
    const maxConcurrent = 3;
    let successCount = 0;
    let errorCount = 0;
    for (let i = 0; i < pending.length; i += maxConcurrent) {
      const slice = pending.slice(i, i + maxConcurrent);
      const results = await Promise.all(slice.map(uploadOne));
      successCount += results.filter(Boolean).length;
      errorCount += results.length - results.filter(Boolean).length;
    }
    if (errorCount === 0) addToast(`✓ Batch загрузка завершена: ${successCount}`, "success");
    else if (successCount === 0) addToast(`Batch загрузка завершилась с ошибками: ${errorCount}`, "error");
    else addToast(`Batch загрузка: ${successCount} успешно, ${errorCount} с ошибкой`, "info");
  };

  const undoLabel = useCallback(() => {
    const last = undoStack[undoStack.length - 1];
    if (!last) return;
    setUndoStack(s => s.slice(0, -1));
    setLabelQueue(q => [last.node, ...q]);
    setCurrentLabels(last.labels);
    addToast("↩ Отменено", "info");
  }, [undoStack]);

  const searchNodes = async () => {
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setSearchResults([]);
    setSearchDone(false);
    const params = new URLSearchParams({ q: searchQuery, top_k: String(searchTopK) });
    if (ds) params.set("dataset_id", String(ds));
    const json = await apiFetchJson(`/search?${params.toString()}`);
    setIsSearching(false);
    setSearchDone(true);
    if (!json) return;
    setSearchResults(Array.isArray(json) ? json : []);
  };

  const copyNode = (n: AnalyzeNode) => {
    const text = `## ${n.title}\n\n${n.context_text}\n\nBloom: ${n.top_levels.join(", ")}`;
    navigator.clipboard.writeText(text).then(() => addToast("Скопировано в буфер", "success"));
  };

  const loadCanvasCourses = useCallback(async () => {
    setCanvasCoursesLoading(true);
    setCanvasCourses([]);
    setCanvasAlert(null);
    const json = await apiFetchJson("/canvas/courses");
    setCanvasCoursesLoading(false);
    if (!json) {
      setCanvasAlert({
        title: "Не удалось загрузить курсы",
        message: apiStatus === "down"
          ? "Backend недоступен — проверь, что Docker запущен и backend-контейнер поднят."
          : "Ошибка запроса к Canvas. Возможно, CANVAS_TOKEN неверный, URL недоступен или нет курсов. Детали — во вкладке «Анализ» (красная строка ошибки).",
      });
      return;
    }
    setCanvasCourses(Array.isArray(json) ? json : []);
  }, [apiFetchJson, apiStatus]);

  const ingestCanvasCourse = useCallback(async () => {
    if (!canvasSelectedCourse || !ds) return;
    setCanvasIngesting(true);
    setCanvasIngestResult(null);
    setCanvasAlert(null);
    setCanvasProgress({ label: "Подключение к Canvas…", stage: "start", nodes_created: 0, nodes_updated: 0, elapsedSec: 0 });
    if (canvasProgressTimerRef.current) clearInterval(canvasProgressTimerRef.current);
    const startedAt = Date.now();
    canvasProgressTimerRef.current = setInterval(() => {
      const elapsedSec = Math.floor((Date.now() - startedAt) / 1000);
      setCanvasProgress((prev) => {
        if (!prev) return prev;
        let label = prev.label;
        if (prev.stage === "start") {
          if (elapsedSec >= 15) {
            label = "Canvas отвечает медленно, но анализ продолжается…";
          } else if (elapsedSec >= 8) {
            label = "Запрашиваем структуру курса и список материалов…";
          } else if (elapsedSec >= 4) {
            label = "Открываем поток событий и готовим импорт…";
          }
        }
        return { ...prev, label, elapsedSec };
      });
    }, 1000);

    try {
      const response = await fetch(`${apiBase}/canvas/ingest-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          course_id: canvasSelectedCourse,
          dataset_id: ds,
          content_types: canvasContentTypes,
          max_nodes_per_doc: canvasMaxNodes,
          max_files: canvasMaxFiles,
        }),
      });

      if (!response.ok || !response.body) {
        // HTTP error ≠ backend down — read actual message from server
        let errDetail = `HTTP ${response.status}`;
        try {
          const body = await response.text();
          const j = JSON.parse(body);
          errDetail = j.detail || j.message || errDetail;
        } catch { /* ignore parse errors */ }
        setCanvasAlert({
          title: "Анализ не запущен",
          message: `Ошибка: ${errDetail}. Проверь, что датасет выбран и Canvas настроен.`,
        });
        addToast(`Canvas: ${errDetail}`, "error");
        setCanvasIngesting(false);
        setCanvasProgress(null);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE lines end with \n\n
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          for (const line of part.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            try {
              const ev = JSON.parse(line.slice(6));
              if (ev.type === "start" || ev.type === "stage") {
                setCanvasProgress(p => ({ ...p!, label: ev.label, stage: ev.stage ?? ev.type }));
              } else if (ev.type === "progress") {
                setCanvasProgress(p => ({ ...(p || { elapsedSec: 0 }), label: ev.label, stage: "processing", nodes_created: ev.nodes_created ?? 0, nodes_updated: ev.nodes_updated ?? 0 }));
              } else if (ev.type === "done") {
                setCanvasIngestResult(ev.result);
                setCanvasAlert(null);
                addToast(`Canvas: создано ${ev.result.nodes_created} узлов, обновлено ${ev.result.nodes_updated}`, "success");
              } else if (ev.type === "error") {
                setCanvasAlert({
                  title: "Анализ курса остановлен",
                  message: String(ev.message || "Во время обработки Canvas-курса произошла ошибка. Проверь backend и повтори запуск."),
                });
                addToast(`Ошибка Canvas: ${ev.message}`, "error");
              }
            } catch { /* skip malformed SSE line */ }
          }
        }
      }
    } catch (err: unknown) {
      // Only a true network error (connection refused, timeout) means backend is down
      const isNetwork = err instanceof TypeError && String(err.message).toLowerCase().includes("fetch");
      if (isNetwork) setApiStatus("down");
      setCanvasAlert({
        title: isNetwork ? "Анализ курса прерван" : "Ошибка выполнения",
        message: isNetwork
          ? "Backend недоступен — проверь, что Docker запущен и backend-контейнер поднят, затем нажми «Проверить backend» или запусти анализ еще раз."
          : `Ошибка: ${String(err instanceof Error ? err.message : err)}`,
      });
      addToast(isNetwork ? "Нет связи с backend" : `Canvas: ${String(err instanceof Error ? err.message : err)}`, "error");
    } finally {
      if (canvasProgressTimerRef.current) {
        clearInterval(canvasProgressTimerRef.current);
        canvasProgressTimerRef.current = null;
      }
      setCanvasIngesting(false);
      setCanvasProgress(null);
    }
  }, [apiBase, canvasSelectedCourse, ds, canvasContentTypes, canvasMaxNodes, canvasMaxFiles]);

  const filteredNodes = useMemo(() => {
    let result = [...nodes];
    result = result.filter((n) => {
      const levels = (n.top_levels || []) as BloomLevel[];
      return levels.length ? levels.some((lvl) => filters[lvl]) : true;
    });
    if (nodeSearch.trim()) {
      const q = nodeSearch.toLowerCase();
      result = result.filter(n =>
        n.title.toLowerCase().includes(q) || (n.context_text || "").toLowerCase().includes(q)
      );
    }
    if (nodeSort === "confidence") {
      result.sort((a, b) => Math.max(...b.prob_vector) - Math.max(...a.prob_vector));
    } else if (nodeSort === "alpha") {
      result.sort((a, b) => a.title.localeCompare(b.title, "ru"));
    } else if (nodeSort === "level") {
      result.sort((a, b) => BLOOM_LEVELS.indexOf(a.top_levels[0]) - BLOOM_LEVELS.indexOf(b.top_levels[0]));
    }
    return result;
  }, [nodes, nodeSearch, nodeSort, filters]);

  useEffect(() => {
    setHoveredNode(null);
    setSelectedNode(null);
  }, [ds, filters, graphNodesData, graphEdgesData]);

  useEffect(() => {
    if (activeTab !== "canvas") return;
    if (apiStatus === "down") {
      setCanvasAlert((prev) => prev ?? {
        title: "Canvas сейчас недоступен",
        message: "Backend недоступен — проверь, что Docker запущен и backend-контейнер поднят. После восстановления backend можно снова загрузить курсы или запустить анализ курса.",
      });
      return;
    }
    if (apiStatus === "ok") {
      setCanvasAlert((prev) => {
        if (!prev) return prev;
        if (!prev.message.includes("Backend недоступен")) return prev;
        return null;
      });
    }
  }, [activeTab, apiStatus]);

  const loadGraph = async () => {
    if (!ds) return;
    loadGraphAbortRef.current?.abort();
    loadGraphAbortRef.current = new AbortController();
    const params = new URLSearchParams({
      dataset_id: String(ds),
      source: "db",
      top_k: String(graphTopK),
      min_score: String(graphMinScore),
      include_cooccurrence: graphIncludeCo ? "true" : "false",
      limit_nodes: String(graphLimitNodes),
    });
    const json = await apiFetchJson(`/graph?${params.toString()}`, { signal: loadGraphAbortRef.current.signal });
    if (!json) return;
    setGraphNodesData(json.nodes || []);
    setGraphEdgesData(json.edges || []);
  };

  const rebuildGraph = async () => {
    if (!ds) return;
    const json = await apiFetchJson(`/graph/rebuild`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: ds,
        top_k: graphTopK,
        min_score: graphMinScore,
        max_edges: 800,
        include_cooccurrence: graphIncludeCo,
        limit_nodes: graphLimitNodes,
        co_window: 2,
      }),
    });
    if (!json) return;
    setLastJob(json.job_id);
  };

  const loadLabelQueue = async () => {
    if (!ds) return;
    setLabelQueueStatus("Загружаем очередь разметки...");
    const params = new URLSearchParams({ annotator, limit: "80" });
    const json = await apiFetchJson(`/datasets/${ds}/labeling/queue?${params.toString()}`);
    if (!json) {
      setLabelQueueStatus("Ошибка загрузки очереди.");
      return;
    }
    const items = (json.items || []) as AnalyzeNode[];
    setLabelQueue(items);
    setLabelProgress({ total: Number(json.total || 0), labeled: Number(json.labeled || 0) });
    setLabelQueueStatus(items.length ? `В очереди: ${items.length}` : "Очередь пуста");
    setCurrentLabels({
      remember: false, understand: false, apply: false,
      analyze: false, evaluate: false, create: false,
    });
  };

  const saveLabels = async () => {
    const node = labelQueue[0];
    if (!ds || !node) return;
    const labels = BLOOM_LEVELS.filter((lvl) => currentLabels[lvl]);
    if (!labels.length) return;
    const ok = await apiFetchJson(`/nodes/${node.id}/labels`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ labels, annotator }),
    });
    if (!ok) return;
    addToast("✓ Разметка сохранена", "success");
    setUndoStack(s => [...s.slice(-9), { node, labels: { ...currentLabels } }]);
    setLabelQueue((q) => q.slice(1));
    setCurrentLabels({
      remember: false, understand: false, apply: false,
      analyze: false, evaluate: false, create: false,
    });
    setLabelProgress((p) => (p ? { ...p, labeled: p.labeled + 1 } : p));
  };

  // Ref to the save button — clicking the real button guarantees React has the latest state.
  const saveBtnRef = useRef<HTMLButtonElement>(null);
  // Refs for hidden file inputs
  const analyzeFileRef = useRef<HTMLInputElement>(null);
  const sidebarFileRef = useRef<HTMLInputElement>(null);

  // Global hotkeys: Alt+1-4 for tabs, Ctrl+Z for undo labeling
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return;
      if (e.altKey) {
        if (e.key === "1") { e.preventDefault(); setActiveTab("analysis"); }
        if (e.key === "2") { e.preventDefault(); setActiveTab("graph"); }
        if (e.key === "3") { e.preventDefault(); setActiveTab("labeling"); }
        if (e.key === "4") { e.preventDefault(); setActiveTab("search"); }
        if (e.key === "5") { e.preventDefault(); setActiveTab("dashboard"); }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && activeTab === "labeling") {
        e.preventDefault();
        undoLabel();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTab, undoLabel]);

  useEffect(() => {
    if (activeTab !== "labeling") return;
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return;
      const map: Record<string, BloomLevel> = {
        "1": "remember", "2": "understand", "3": "apply",
        "4": "analyze", "5": "evaluate", "6": "create",
      };
      const lvl = map[e.key];
      if (lvl) {
        setCurrentLabels((s) => ({ ...s, [lvl]: !s[lvl] }));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        saveBtnRef.current?.click();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTab]);

  // ── Render helpers ──────────────────────────────────────────

  const apiStatusDotClass =
    apiStatus === "ok" ? styles.dotOk :
    apiStatus === "down" ? styles.dotBad : "";

const progressPct = labelProgress && labelProgress.total > 0
  ? Math.round((labelProgress.labeled / labelProgress.total) * 100)
  : 0;
const hasDataset = Boolean(ds);
const hasAnalysisSource = Boolean(textInput.trim() || analyzeFileName);
const hasNodes = nodes.length > 0;
const hasGraph = graphNodesData.length > 0 || graphEdgesData.length > 0;
const lowConfidenceCount = nodes.filter((n) => getConfidenceMeta(n).band === "low").length;
const contextLead = !hasDataset
  ? "Сначала выбери или создай активный датасет."
  : !hasAnalysisSource
    ? "Теперь добавь текст или файл, чтобы запустить анализ."
    : !hasNodes
      ? "Запусти анализ и получи первые узлы и уровни Блума."
      : "Узлы уже получены: можно идти к графу, поиску или разметке.";
const contextActionLabel = hasNodes ? "Перейти к разметке" : "Открыть анализ";
const contextActionTab = hasNodes ? "labeling" : "analysis";
const analysisFlowSteps = [
  {
    step: "01",
    title: "Датасет",
    text: hasDataset ? `Активен dataset #${ds}` : "Выбери или создай рабочий датасет",
    state: (hasDataset ? "done" : "current") as "pending" | "current" | "done",
  },
  {
    step: "02",
    title: "Источник",
    text: hasAnalysisSource ? "Текст или файл уже готов к анализу" : "Добавь текст или загрузи файл",
    state: (!hasDataset ? "pending" : hasAnalysisSource ? "done" : "current") as "pending" | "current" | "done",
  },
  {
    step: "03",
    title: "Анализ",
    text: hasNodes
      ? `Получено ${nodes.length} узлов`
      : isAnalyzing
        ? "Извлекаем понятия и уровни Блума"
        : "Запусти анализ, чтобы получить узлы",
    state: !hasAnalysisSource ? "pending" : hasNodes ? "done" : "current",
  },
  {
    step: "04",
    title: "Следующий шаг",
    text: hasNodes ? "Открой граф, поиск, очередь разметки или экспорт" : "Подготовь данные и переходи к следующему шагу",
    state: hasNodes ? "done" : "pending",
  },
];

  return (
    <div className={styles.page}>

      {/* ── Header ─────────────────────────────────────── */}
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}>
            <div className={styles.brandIcon}>
              <span className={styles.brandIconSvg}>
                <IconSparkle />
              </span>
            </div>
            <div className={styles.brandText}>
              <span className={styles.title}>Bloom RAG Studio</span>
              <span className={styles.subtitle}>multi-label knowledge taxonomy</span>
            </div>
          </div>

          <div className={styles.metaRow}>
            {/* API status */}
            <div className={styles.pill}>
              <span className={[styles.dot, apiStatusDotClass].join(" ")} />
              <span>API</span>
              <span className={styles.kbd}>{apiStatus}</span>
            </div>

            {/* Dataset badge */}
            <div className={styles.pill}>
              <span style={{ color: "var(--text-muted)" }}>dataset</span>
              <span className={styles.kbd} style={{ color: ds ? "var(--text-accent)" : undefined }}>
                {ds ?? "—"}
              </span>
            </div>

            {/* Job badge */}
            {lastJob && (
              <div className={styles.pill}>
                <span style={{ color: "var(--text-muted)" }}>job</span>
                <span className={styles.kbd}>{lastJob}</span>
              </div>
            )}

            <button
              className={styles.themeToggle}
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              title="Переключить тему"
              type="button"
            >
              {theme === "light" ? "Тёмная" : "Светлая"}
            </button>

            {/* Settings gear */}
            <button
              className={styles.gearBtn}
              onClick={() => setShowSettings(true)}
              title="Настройки (Settings)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>

            {/* Help button */}
            <button
              className={styles.helpBtn}
              onClick={() => setShowGuide(true)}
              title="Инструкция по использованию"
            >
              ?
            </button>
          </div>
        </div>
      </header>

      {/* ── Shell ──────────────────────────────────────── */}
      <div className={styles.shell}>

        {/* ── Sidebar nav ──────────────────────────────── */}
        <nav className={styles.nav}>
          <div className={styles.navCard}>
            <div className={styles.navSectionTitle}>Инструменты</div>

            <button
              className={[styles.navBtn, activeTab === "analysis" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("analysis")}
            >
              <span className={styles.navIcon}><IconBrain /></span>
              <span className={styles.navLabel}>Анализ</span>
              {nodes.length > 0
                ? <span className={styles.navCount}>{nodes.length}</span>
                : <span className={styles.navHint}>content</span>
              }
            </button>

            <button
              className={[styles.navBtn, activeTab === "graph" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("graph")}
            >
              <span className={styles.navIcon}><IconGraph /></span>
              <span className={styles.navLabel}>Граф</span>
              <span className={styles.navHint}>cyto</span>
            </button>

            <button
              className={[styles.navBtn, activeTab === "labeling" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("labeling")}
            >
              <span className={styles.navIcon}><IconTag /></span>
              <span className={styles.navLabel}>Разметка</span>
              {labelProgress && labelProgress.total > 0 ? (
                <div className={styles.navProgressChip}>
                  <span className={styles.navProgressText}>{labelProgress.labeled}/{labelProgress.total}</span>
                  <div className={styles.navProgressMini}>
                    <div className={styles.navProgressMiniFill} style={{ width: `${progressPct}%` }} />
                  </div>
                </div>
              ) : (
                <span className={styles.navHint}>queue</span>
              )}
            </button>

            <button
              className={[styles.navBtn, activeTab === "dashboard" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => { setActiveTab("dashboard"); loadDashboard(); }}
            >
              <span className={styles.navIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                </svg>
              </span>
              <span className={styles.navLabel}>Дашборд</span>
              <span className={styles.navHint}>stats</span>
            </button>

            <button
              className={[styles.navBtn, activeTab === "search" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("search")}
            >
              <span className={styles.navIcon}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
              </span>
              <span className={styles.navLabel}>Поиск</span>
              <span className={styles.navHint}>RAG</span>
            </button>

            <button
              className={[styles.navBtn, activeTab === "canvas" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => { setActiveTab("canvas"); if (!canvasCourses.length) loadCanvasCourses(); }}
            >
              <span className={styles.navIcon}><IconCanvas /></span>
              <span className={styles.navLabel}>Canvas</span>
              <span className={styles.navHint}>LMS</span>
            </button>
          </div>
        </nav>

        {/* ── Main area ────────────────────────────────── */}
        <main className={styles.main}>

          {/* Error banner */}
          {error && (
            <div className={styles.error}>
              <span className={styles.errorIcon}><IconAlert /></span>
              <span style={{ flex: 1 }}>{error}</span>
              <button
                onClick={() => setError(null)}
                style={{
                  flexShrink: 0, background: "none", border: "none", cursor: "pointer",
                  color: "#fca5a5", fontSize: 18, lineHeight: 1, padding: "0 2px",
                  opacity: 0.7, marginLeft: 4,
                }}
                title="Закрыть"
              >×</button>
            </div>
          )}

          {/* ── Analysis Tab ─────────────────────────── */}
          {activeTab === "analysis" && (
            <div className={styles.card}>

<SectionHero
  eyebrow="Главный сценарий"
  title="От текста к карте знаний"
  description="Загрузи материал и запусти анализ, чтобы получить узлы знаний с уровнями Блума. Когда основа готова, переходи к графу, поиску и ручной проверке."
  stats={[
    { label: "API", value: apiStatus === "ok" ? "online" : "offline", tone: apiStatus === "ok" ? "success" : "warning" },
    { label: "Датасет", value: hasDataset ? `#${ds}` : "Не выбран", tone: hasDataset ? "accent" : "warning" },
    { label: "Узлы", value: nodes.length, tone: hasNodes ? "info" : "neutral" },
    { label: "Нужна проверка", value: lowConfidenceCount, tone: lowConfidenceCount ? "warning" : "success" },
  ]}
  actions={nodes.length > 0 ? (
    <div className={styles.exportMenuWrap}>
      <button
        className={[styles.btn, styles.btnGhost].join(" ")}
        onClick={() => setShowExportMenu(v => !v)}
        type="button"
      >
        <IconDownload /> Экспорт ▾
      </button>
      {showExportMenu && (
        <div className={styles.exportDropdown}>
          <div className={styles.exportItem} onClick={() => { exportNodesJson(); setShowExportMenu(false); }}>
            <IconDownload /> JSON
          </div>
          <div className={styles.exportItem} onClick={() => { exportNodesCsv(); setShowExportMenu(false); }}>
            <IconDownload /> CSV
          </div>
          {ds && (
            <div className={styles.exportItem} onClick={() => { exportJsonl(); setShowExportMenu(false); }}>
              <IconDownload /> JSONL (датасет)
            </div>
          )}
        </div>
      )}
    </div>
  ) : (
    <button className={[styles.btn, styles.btnGhost].join(" ")} onClick={() => setShowGuide(true)} type="button">
      Показать подсказки
    </button>
  )}
>
  <div className={styles.flowSteps}>
    {analysisFlowSteps.map((item) => (
      <FlowStep key={item.step} step={item.step} title={item.title} text={item.text} state={item.state as "pending" | "current" | "done"} />
    ))}
  </div>
</SectionHero>

              <div className={styles.grid}>
                {/* File drop zone */}
                <div
                  style={{
                    padding: "13px 16px", borderRadius: 8,
                    border: `1.5px dashed ${isTranscribing ? "var(--text-accent)" : analyzeFileName ? "var(--success)" : "var(--border-2)"}`,
                    background: analyzeFileName && !isTranscribing ? "rgba(16,185,129,0.04)" : "var(--bg-card)",
                    transition: "border-color 0.15s, background 0.15s",
                    cursor: isTranscribing ? "default" : "pointer",
                  }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) loadTextFile(f); }}
                  onClick={() => !isTranscribing && analyzeFileRef.current?.click()}
                >
                  {/* Hidden native file input */}
                  <input
                    ref={analyzeFileRef}
                    type="file"
                    accept=".txt,.pdf,.md"
                    style={{ display: "none" }}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) loadTextFile(f); e.target.value = ""; }}
                  />
                  {isTranscribing ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className={styles.spinner} />
                      <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Извлекаем текст из PDF…</span>
                    </div>
                  ) : analyzeFileName ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--success)", fontWeight: 500 }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--success)", flexShrink: 0, boxShadow: "0 0 6px rgba(16,185,129,0.5)" }} />
                      {analyzeFileName}
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-muted)", fontWeight: 400 }}>нажми, чтобы заменить</span>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500 }}>Выбрать файл</span>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>или перетащи сюда (.txt, .pdf, .md)</span>
                    </div>
                  )}
                </div>

                {/* Textarea */}
                <label className={styles.fieldLabel}>
                  Текст для анализа
                  <div style={{ position: "relative" }}>
                    <textarea
                      className={styles.textarea}
                      placeholder="Вставьте текст вручную или загрузите файл выше…"
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      onKeyDown={(e) => {
                        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                          e.preventDefault();
                          if (textInput.trim() && !isAnalyzing && !isTranscribing) analyzeText();
                        }
                      }}
                      onPaste={(e) => {
                        const pasted = e.clipboardData.getData("text");
                        if (pasted.length > 200) {
                          setMaxNodes(suggestMaxNodes(pasted));
                          setMaxNodesAuto(true);
                        }
                      }}
                      onFocus={() => setShowHistory(false)}
                    />
                    {/* History dropdown */}
                    {showHistory && textHistory.length > 0 && (
                      <div className={styles.historyDropdown}>
                        {textHistory.map((h, i) => (
                          <div
                            key={i}
                            className={styles.historyItem}
                            onClick={() => { setTextInput(h); setShowHistory(false); setMaxNodes(suggestMaxNodes(h)); setMaxNodesAuto(true); }}
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, opacity: 0.5 }}>
                              <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-5.09"/>
                            </svg>
                            <span className={styles.historyItemText}>{h.slice(0, 100)}{h.length > 100 ? "…" : ""}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </label>
                {/* Char counter + history button */}
                {(textInput.length > 0 || textHistory.length > 0) && (
                  <div className={styles.textMeta}>
                    <span className={styles.charCount}>
                      {textInput.length > 0 ? `${textInput.length.toLocaleString("ru")} симв · ${textInput.trim().split(/\s+/).filter(Boolean).length.toLocaleString("ru")} слов · ~${suggestMaxNodes(textInput)} узлов` : ""}
                    </span>
                    {textHistory.length > 0 && (
                      <button
                        className={styles.historyBtn}
                        onClick={() => setShowHistory(v => !v)}
                        title="История запросов"
                      >
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-5.09"/>
                        </svg>
                        История ({textHistory.length})
                      </button>
                    )}
                  </div>
                )}

                {/* Actions row */}
                <div className={styles.btnRow}>
                  <button
                    className={[styles.btn, styles.btnPrimaryLg].join(" ")}
                    onClick={analyzeText}
                    disabled={!textInput.trim() || isAnalyzing || isTranscribing}
                    title="Анализировать (Ctrl+Enter)"
                  >
                    {isAnalyzing ? <span className={styles.spinner} /> : <IconSparkle />}
                    {isAnalyzing ? "Анализируем..." : "Анализировать"}
                    {!isAnalyzing && textInput.trim() && (
                      <span style={{ fontSize: 10, opacity: 0.6, marginLeft: 4, fontFamily: "var(--font-mono)" }}>⌘↵</span>
                    )}
                  </button>

                  <div className={styles.paramField} style={{ margin: 0, minWidth: 180 }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      Макс. узлов
                      {maxNodesAuto && (
                        <span style={{
                          fontSize: 10, padding: "1px 5px", borderRadius: 4,
                          background: "rgba(99,102,241,0.15)", color: "var(--text-accent)",
                          fontWeight: 600, letterSpacing: "0.03em",
                        }}>авто</span>
                      )}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <input
                        className={styles.paramSlider}
                        type="range"
                        min="10"
                        max="500"
                        step="10"
                        value={maxNodes}
                        onChange={(e) => { setMaxNodes(Number(e.target.value)); setMaxNodesAuto(false); }}
                        style={{ flex: 1 }}
                      />
                      <input
                        className={styles.paramInput}
                        type="number"
                        min="10"
                        max="500"
                        step="10"
                        value={maxNodes}
                        onChange={(e) => { setMaxNodes(Math.min(500, Math.max(10, Number(e.target.value) || 10))); setMaxNodesAuto(false); }}
                        style={{ width: 56, flexShrink: 0 }}
                      />
                    </div>
                  </div>

                  <button
                    className={[styles.btn].join(" ")}
                    onClick={loadNodesFromDb}
                    disabled={!ds}
                  >
                    <IconNodes />
                    Узлы из БД
                  </button>
                </div>

                {/* Progress bar */}
                {analyzeProgress > 0 && (
                  <div className={styles.analyzeProgressWrap}>
                    <div className={styles.analyzeProgressHeader}>
                      <span className={styles.analyzeProgressMsg}>{analyzeStatusMsg}</span>
                      <span className={styles.analyzeProgressPct}>
                        {analyzeProgress < 100 ? `${Math.round(analyzeProgress)}%` : "✓"}
                      </span>
                    </div>
                    <div className={styles.analyzeProgressTrack}>
                      <div
                        className={[styles.analyzeProgressFill, analyzeProgress < 100 ? styles.analyzeProgressFillAnim : ""].join(" ")}
                        style={{ width: `${analyzeProgress}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Status */}
                {nodesStatus && !isAnalyzing && (
                  <div className={styles.statusLine}>
                    <span
                      style={{
                        width: 7, height: 7, borderRadius: "50%",
                        background: "var(--success)", flexShrink: 0,
                        boxShadow: "0 0 5px rgba(16,185,129,0.5)"
                      }}
                    />
                    {nodesStatus}
                  </div>
                )}

                {/* Stats chips */}
                {nodes.length > 0 && !isAnalyzing && (() => {
                  const activeLevels = BLOOM_LEVELS.filter(lvl => nodes.some(n => n.top_levels.includes(lvl)));
                  const topLvl = BLOOM_LEVELS
                    .map(lvl => ({ lvl, count: nodes.filter(n => n.top_levels.includes(lvl)).length }))
                    .sort((a, b) => b.count - a.count)[0];
                  const avgProb = nodes.reduce((acc, n) => acc + (n.prob_vector[BLOOM_LEVELS.indexOf(n.top_levels[0])] ?? 0), 0) / nodes.length;
                  return (
                    <div className={styles.statChips}>
                      <div className={styles.statChip}>
                        <span className={styles.statChipVal}>{nodes.length}</span>
                        <span className={styles.statChipLabel}>узлов</span>
                      </div>
                      <div className={styles.statChip}>
                        <span className={styles.statChipVal}>{activeLevels.length}</span>
                        <span className={styles.statChipLabel}>уровней Блума</span>
                      </div>
                      {topLvl && (
                        <div className={styles.statChip}>
                          <span className={styles.statChipVal} style={{ fontSize: 14, color: LEVEL_COLORS[topLvl.lvl] }}>
                            {LEVEL_LABELS[topLvl.lvl]}
                          </span>
                          <span className={styles.statChipLabel}>топ-уровень</span>
                        </div>
                      )}
                      <div className={styles.statChip}>
                        <span className={styles.statChipVal} style={{ fontSize: 18 }}>
                          {(avgProb * 100).toFixed(0)}%
                        </span>
                        <span className={styles.statChipLabel}>ср. уверенность</span>
                      </div>
                    </div>
                  );
                })()}

                {/* Bloom distribution widget */}
                {nodes.length > 0 && (() => {
                  const dist = BLOOM_LEVELS
                    .map(lvl => ({ lvl, count: nodes.filter(n => n.top_levels.includes(lvl)).length }))
                    .filter(d => d.count > 0);
                  const maxCount = Math.max(...dist.map(d => d.count));
                  const topLevel = dist.sort((a, b) => b.count - a.count)[0]?.lvl;
                  return (
                    <div className={styles.bloomDistWidget}>
                      <div className={styles.bloomDistMeta}>
                        <span className={styles.bloomDistTitle}>Распределение по таксономии Блума</span>
                        <div className={styles.bloomDistStats}>
                          <span className={styles.bloomDistStat}>
                            <span className={styles.bloomDistStatVal}>{nodes.length}</span> узлов
                          </span>
                          <span className={styles.bloomDistStat}>
                            <span className={styles.bloomDistStatVal}>{dist.length}</span> уровней
                          </span>
                          {topLevel && (
                            <span className={styles.bloomDistStat}>
                              доминирует{" "}
                              <span style={{ color: LEVEL_COLORS[topLevel], fontWeight: 600 }}>
                                {LEVEL_LABELS[topLevel]}
                              </span>
                            </span>
                          )}
                        </div>
                      </div>
                      <div className={styles.bloomDistBars}>
                        {BLOOM_LEVELS.map(lvl => {
                          const count = nodes.filter(n => n.top_levels.includes(lvl)).length;
                          if (!count) return null;
                          return (
                            <div key={lvl} className={styles.bloomDistRow}>
                              <span className={styles.bloomDistLabel} style={{ color: LEVEL_COLORS[lvl] }}>
                                {LEVEL_LABELS[lvl]}
                              </span>
                              <div className={styles.bloomDistTrack}>
                                <div
                                  className={styles.bloomDistFill}
                                  style={{ width: `${(count / maxCount) * 100}%`, background: LEVEL_COLORS[lvl] }}
                                />
                              </div>
                              <span className={styles.bloomDistCount}>{count}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

                {/* Node controls: search + sort */}
                {nodes.length > 0 && !isAnalyzing && (
                  <div className={styles.nodeControls}>
                    <input
                      className={styles.nodeSearchInput}
                      placeholder="Поиск по узлам…"
                      value={nodeSearch}
                      onChange={e => setNodeSearch(e.target.value)}
                    />
                    <select
                      className={styles.nodeSortSelect}
                      value={nodeSort}
                      onChange={e => setNodeSort(e.target.value as typeof nodeSort)}
                    >
                      <option value="default">Порядок по умолчанию</option>
                      <option value="confidence">По уверенности ↓</option>
                      <option value="alpha">По алфавиту</option>
                      <option value="level">По уровню Блума</option>
                    </select>
                    <span className={styles.nodeControlsCount}>
                      {filteredNodes.length !== nodes.length
                        ? `${filteredNodes.length} / ${nodes.length}`
                        : nodes.length}
                    </span>
                  </div>
                )}

                {/* Skeleton while analyzing */}
                {isAnalyzing && (
                  <div className={styles.nodesGrid}>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <div key={i} className={styles.skeletonCard}>
                        <div className={styles.skeletonLine} style={{ width: "60%", height: 14 }} />
                        <div className={styles.skeletonLine} style={{ width: "90%" }} />
                        <div className={styles.skeletonLine} style={{ width: "75%" }} />
                        <div className={styles.skeletonLine} style={{ width: "40%", height: 8 }} />
                      </div>
                    ))}
                  </div>
                )}

                {/* Node cards grid */}
                {filteredNodes.length > 0 && !isAnalyzing && (
                  <div className={styles.nodesGrid}>
                    {filteredNodes.map((n) => {
                      const sorted = getSortedLevels(n.prob_vector);
                      const confidence = getConfidenceMeta(n);
                      const explanationLines = getExplainabilityLines(n);
                      const accentColor = n.top_levels[0] ? LEVEL_COLORS[n.top_levels[0]] : "var(--border)";
                      return (
                        <div
                          key={n.id}
                          className={styles.nodeCard}
                          style={{ borderLeft: `3px solid ${accentColor}`, cursor: "pointer" }}
                          onClick={() => setDetailNode(n)}
                        >
                          {/* Copy button */}
                          <button
                            className={styles.copyBtn}
                            onClick={e => { e.stopPropagation(); copyNode(n); }}
                            title="Копировать в буфер"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                            </svg>
                          </button>

                          {/* Head */}
                          <div className={styles.nodeCardHead}>
                            <div className={styles.nodeTitle}>{n.title}</div>
                            <span className={styles.nodeId}>#{n.id}</span>
                          </div>

                          {/* Context */}
                          <div className={styles.nodeContext}>{n.context_text}</div>

                          {/* Bloom level badges */}
                          <div className={styles.nodeLevels}>
                            {n.top_levels.map((lvl) => (
                              <BloomBadge key={lvl} level={lvl} />
                            ))}
                            {typeof n.frequency === "number" && (
                              <span className={styles.kbd}>freq: {n.frequency}</span>
                            )}
                          </div>

                          <div className={styles.confidenceRow}>
                            <span
                              className={[
                                styles.confidenceBadge,
                                confidence.band === "high"
                                  ? styles.confidenceHigh
                                  : confidence.band === "medium"
                                    ? styles.confidenceMedium
                                    : styles.confidenceLow,
                              ].join(" ")}
                            >
                              {confidence.label}
                            </span>
                            <span className={styles.confidenceMeta}>
                              {LEVEL_LABELS[confidence.primary.lvl]} {(confidence.primary.prob * 100).toFixed(0)}%
                              {confidence.runnerUp ? ` · разрыв ${(confidence.gap * 100).toFixed(0)} п.п.` : ""}
                            </span>
                          </div>

                          {/* Mini prob chart (all 6 levels) */}
                          <div className={styles.probMiniChart} title="Вектор вероятностей по 6 уровням Блума">
                            {BLOOM_LEVELS.map((lvl, i) => {
                              const p = n.prob_vector[i] ?? 0;
                              return (
                                <div
                                  key={lvl}
                                  className={styles.probMiniSeg}
                                  style={{ width: `${Math.max(4, Math.round(p * 100))}%`, background: LEVEL_COLORS[lvl], opacity: p > 0.05 ? 1 : 0.2 }}
                                  title={`${LEVEL_LABELS[lvl]}: ${(p * 100).toFixed(0)}%`}
                                />
                              );
                            })}
                          </div>

                          {/* Probability bars (top 3) */}
                          <div className={styles.nodeProbs}>
                            {sorted.slice(0, 3).map(({ lvl, prob }) => (
                              <div key={lvl} className={styles.probRow}>
                                <span className={styles.probLabel}>{LEVEL_LABELS[lvl]}</span>
                                <div className={styles.probBar}>
                                  <div
                                    className={styles.probFill}
                                    style={{
                                      width: `${Math.round(prob * 100)}%`,
                                      background: LEVEL_COLORS[lvl],
                                    }}
                                  />
                                </div>
                                <span className={styles.probValue}>{prob.toFixed(2)}</span>
                              </div>
                            ))}
                          </div>

                          {/* Rationale */}
                          {n.rationale && (
                            <div className={styles.nodeRationale}>
                              {n.rationale}
                            </div>
                          )}
                          <div className={styles.explainList}>
                            {explanationLines.map((line) => (
                              <div key={line} className={styles.explainItem}>
                                <span className={styles.explainDot} />
                                <span>{line}</span>
                              </div>
                            ))}
                          </div>
                          {confidence.band === "low" && (
                            <div className={styles.reviewHint}>
                              Лучше проверить вручную: модель видит близкие альтернативы между уровнями.
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Empty state */}
                {!nodes.length && !nodesStatus && (
                  <div className={styles.emptyState}>
                    <span className={styles.emptyIcon}><IconBrain /></span>
                    <div className={styles.emptyTitle}>Нет результатов</div>
                    <div className={styles.emptyText}>
                      Вставь текст выше и нажми &quot;Анализировать&quot; (нужен активный dataset).
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Search Tab ───────────────────────────── */}
          {activeTab === "search" && (
            <div className={styles.card}>

<SectionHero
  eyebrow="Навигация по материалам"
  title="Семантический поиск"
  description="Ищи фрагменты по содержанию или находи конкретные узлы знаний, чтобы быстро возвращаться к нужному контексту."
  stats={[
    { label: "Датасет", value: hasDataset ? `#${ds}` : "Не выбран", tone: hasDataset ? "accent" : "warning" },
    { label: "Режим", value: searchMode === "chunks" ? "чанки" : "узлы", tone: "info" },
    { label: "Результаты", value: searchMode === "chunks" ? searchResults.length : nodeSearchResults.length, tone: "neutral" },
  ]}
/>
<div className={styles.grid}>
                {/* Search mode toggle */}
                <div className={[styles.searchModeToggle, styles.sectionBlock].join(" ")}>
                  <button
                    className={[styles.searchModeBtn, searchMode === "chunks" ? styles.searchModeBtnActive : ""].join(" ")}
                    onClick={() => setSearchMode("chunks")}
                  >
                    Чанки документов
                  </button>
                  <button
                    className={[styles.searchModeBtn, searchMode === "nodes" ? styles.searchModeBtnActive : ""].join(" ")}
                    onClick={() => setSearchMode("nodes")}
                  >
                    Узлы знаний
                  </button>
                </div>

                {/* Chunk search mode */}
                {searchMode === "chunks" && (
                <div style={{ display: "contents" }}>
                  <div className={styles.searchBox}>
                    <input
                      className={styles.searchInput}
                      placeholder="Введи поисковый запрос…"
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") searchNodes(); }}
                    />
                    <div className={styles.paramField} style={{ margin: 0, flexShrink: 0 }}>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Top-K</span>
                      <input
                        className={styles.paramInput}
                        type="number"
                        min="1"
                        max="20"
                        value={searchTopK}
                        onChange={e => setSearchTopK(Number(e.target.value))}
                        style={{ width: 52 }}
                      />
                    </div>
                    <button
                      className={[styles.btn, styles.btnPrimary].join(" ")}
                      onClick={searchNodes}
                      disabled={!searchQuery.trim() || isSearching}
                      style={{ flexShrink: 0 }}
                    >
                      {isSearching ? <span className={styles.spinner} /> : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        </svg>
                      )}
                      {isSearching ? "Ищем…" : "Найти"}
                    </button>
                  </div>

                  {/* Skeleton while searching */}
                  {isSearching && (
                    <div className={styles.searchResults}>
                      {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className={styles.skeletonCard}>
                          <div className={styles.skeletonLine} style={{ width: "40%", height: 10 }} />
                          <div className={styles.skeletonLine} style={{ width: "90%" }} />
                          <div className={styles.skeletonLine} style={{ width: "70%" }} />
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Results */}
                  {!isSearching && searchResults.length > 0 && (
                    <div className={styles.searchResults}>
                      {searchResults.map((r, i) => (
                        <div key={r.chunk_id} className={styles.searchResultCard}>
                          <div className={styles.searchResultHead}>
                            <span className={styles.searchScoreBadge}>{(Math.max(0, r.score) * 100).toFixed(1)}%</span>
                            <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>#{i + 1}</span>
                            <span className={styles.searchDocBadge}>📄 {r.document_title || `doc #${r.document_id}`}</span>
                          </div>
                          <div className={styles.searchChunkText}>{r.text}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Empty state */}
                  {!isSearching && searchDone && searchResults.length === 0 && (
                    <div className={styles.emptyState}>
                      <span className={styles.emptyIcon}>
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        </svg>
                      </span>
                      <div className={styles.emptyTitle}>Ничего не найдено</div>
                      <div className={styles.emptyText}>Попробуй другой запрос или проверь, что документы проиндексированы.</div>
                    </div>
                  )}

                  {/* Hint when empty */}
                  {!isSearching && !searchDone && (
                    <div className={styles.emptyState}>
                      <span className={styles.emptyIcon}>
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        </svg>
                      </span>
                      <div className={styles.emptyTitle}>Семантический RAG-поиск</div>
                      <div className={styles.emptyText}>Введи запрос на естественном языке — система найдёт смыслово похожие фрагменты документов. Не забудь сначала загрузить и проиндексировать документ.</div>
                    </div>
                  )}
                </div>
                )}

                {/* Nodes search mode */}
                {searchMode === "nodes" && (
                <div>
                  <div className={styles.searchBox}>
                    <input
                      className={styles.searchInput}
                      placeholder="Поиск по узлам знаний…"
                      value={nodeSearchQuery}
                      onChange={e => setNodeSearchQuery(e.target.value)}
                      onKeyDown={e => { if (e.key === "Enter") searchByNodes(); }}
                    />
                    <button
                      className={[styles.btn, styles.btnPrimary].join(" ")}
                      onClick={searchByNodes}
                      disabled={!nodeSearchQuery.trim() || isSearching}
                      style={{ flexShrink: 0 }}
                    >
                      {isSearching ? <span className={styles.spinner} /> : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        </svg>
                      )}
                      {isSearching ? "Ищем…" : "Найти"}
                    </button>
                  </div>
                  {nodeSearchResults.length > 0 && (
                    <div className={styles.searchResults} style={{ marginTop: 12 }}>
                      {nodeSearchResults.map(n => (
                        <div key={n.id} className={styles.searchResultCard} style={{ cursor: "pointer" }} onClick={() => setDetailNode(n)}>
                          <div className={styles.searchResultHead}>
                            {n.top_levels.map(lvl => <BloomBadge key={lvl} level={lvl} />)}
                            <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginLeft: "auto" }}>#{n.id}</span>
                          </div>
                          <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)", marginBottom: 4 }}>{n.title}</div>
                          <div className={styles.searchChunkText}>{n.context_text}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {!isSearching && searchDone && nodeSearchResults.length === 0 && (
                    <div className={styles.emptyState}>
                      <div className={styles.emptyTitle}>Ничего не найдено</div>
                      <div className={styles.emptyText}>Попробуй другой запрос.</div>
                    </div>
                  )}
                  {!searchDone && !isSearching && (
                    <div className={styles.emptyState}>
                      <div className={styles.emptyTitle}>Поиск по узлам знаний</div>
                      <div className={styles.emptyText}>Ищет по названию и контексту узлов в текущем датасете. Узлы должны быть загружены в БД.</div>
                    </div>
                  )}
                </div>
                )}
              </div>
            </div>
          )}

          {/* ── Graph Tab ────────────────────────────── */}
          {activeTab === "graph" && (
            <div className={styles.card}>

<SectionHero
  eyebrow="Связи и структура"
  title="Граф знаний"
  description="Смотри, как понятия связаны между собой. Здесь удобно проверять структуру материала, переходить между уровнями и замечать пробелы."
  stats={[
    { label: "Датасет", value: hasDataset ? `#${ds}` : "Не выбран", tone: hasDataset ? "accent" : "warning" },
    { label: "Узлы", value: graphNodesData.length, tone: hasGraph ? "info" : "neutral" },
    { label: "Связи", value: graphEdgesData.length, tone: hasGraph ? "success" : "neutral" },
  ]}
/>

<div className={[styles.sectionBlock, styles.graphControls].join(" ")}>
                {/* Level filters */}
                <div className={styles.graphFilters}>
                  {BLOOM_LEVELS.map((lvl) => (
                    <label
                      key={lvl}
                      className={[styles.filterChip, filters[lvl] ? styles.filterChipActive : ""].join(" ")}
                      style={filters[lvl] ? {
                        background: LEVEL_BG[lvl],
                        borderColor: LEVEL_BORDER[lvl],
                        color: LEVEL_COLORS[lvl],
                      } : undefined}
                    >
                      <input
                        type="checkbox"
                        checked={filters[lvl]}
                        onChange={(e) => setFilters({ ...filters, [lvl]: e.target.checked })}
                        style={{ display: "none" }}
                      />
                      <span
                        className={styles.filterDot}
                        style={{ background: LEVEL_COLORS[lvl] }}
                      />
                      {LEVEL_LABELS[lvl]}
                    </label>
                  ))}
                </div>

                {/* Params */}
                <div className={styles.graphParams}>
                  <label className={styles.paramField}>
                    Порог 2-го уровня
                    <input
                      className={styles.paramInput}
                      type="number"
                      step="0.05"
                      min="0"
                      max="1"
                      value={threshold}
                      onChange={(e) => setThreshold(Number(e.target.value))}
                    />
                  </label>
                  <label className={styles.paramField}>
                    Top-K
                    <input
                      className={styles.paramInput}
                      type="number"
                      min="1"
                      max="10"
                      value={graphTopK}
                      onChange={(e) => setGraphTopK(Number(e.target.value))}
                    />
                  </label>
                  <label className={styles.paramField}>
                    Min score
                    <input
                      className={styles.paramInput}
                      type="number"
                      step="0.05"
                      min="0"
                      max="1"
                      value={graphMinScore}
                      onChange={(e) => setGraphMinScore(Number(e.target.value))}
                    />
                  </label>
                  <label className={styles.paramField}>
                    Лимит узлов
                    <input
                      className={styles.paramInput}
                      type="number"
                      min="10"
                      max="2000"
                      value={graphLimitNodes}
                      onChange={(e) => setGraphLimitNodes(Number(e.target.value))}
                    />
                  </label>
                  <label className={styles.paramCheckbox}>
                    <input
                      type="checkbox"
                      checked={graphIncludeCo}
                      onChange={(e) => setGraphIncludeCo(e.target.checked)}
                    />
                    Co-occurrence
                  </label>
                </div>

                {/* Graph action buttons */}
                <div className={styles.btnRow}>
                  <button
                    className={[styles.btn, styles.btnPrimary].join(" ")}
                    onClick={loadGraph}
                    disabled={!ds}
                  >
                    <IconGraph />
                    Загрузить граф
                  </button>
                  <button
                    className={[styles.btn, styles.btnWarn].join(" ")}
                    onClick={rebuildGraph}
                    disabled={!ds}
                  >
                    <IconRefresh />
                    Rebuild edges (job)
                  </button>
                  <input
                    className={styles.graphSearchInput}
                    placeholder="Поиск по графу…"
                    value={graphSearch}
                    onChange={e => setGraphSearch(e.target.value)}
                    title="Подсветить узлы по тексту"
                  />
                  {graphSearch && (
                    <button className={[styles.btn, styles.btnGhost].join(" ")} onClick={() => setGraphSearch("")}>✕</button>
                  )}
                </div>
              </div>

              {/* Graph canvas */}
              <ErrorBoundary>
                <GraphView
                  nodes={graphNodesData}
                  edges={graphEdgesData}
                  filters={filters}
                  threshold={threshold}
                  searchQuery={graphSearch}
                  onHover={(n: AnalyzeNode | null) => setHoveredNode(n)}
                  onSelect={(n: AnalyzeNode | null) => setSelectedNode(n)}
                />
              </ErrorBoundary>

              {/* Node detail card — fixed overlay, sticky on click */}
              {(selectedNode || hoveredNode) && (() => {
                const n = (selectedNode || hoveredNode)!;
                const sorted = getSortedLevels(n.prob_vector);
                const confidence = getConfidenceMeta(n);
                return (
                  <div
                    className={styles.cardSm}
                    style={{
                      position: "fixed",
                      bottom: 24,
                      right: 24,
                      width: 340,
                      maxWidth: "calc(100vw - 48px)",
                      zIndex: 200,
                      boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
                    }}
                  >
                    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 10 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className={styles.cardTitle}>{n.title}</div>
                        {n.rationale && (
                          <div className={styles.muted} style={{ marginTop: 4 }}>{n.rationale}</div>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", flexShrink: 0, alignItems: "center" }}>
                        {n.top_levels.map((lvl) => <BloomBadge key={lvl} level={lvl} />)}
                        <button
                          onClick={() => { setSelectedNode(null); setHoveredNode(null); }}
                          style={{
                            marginLeft: 4, background: "none", border: "none", cursor: "pointer",
                            color: "var(--text-muted)", fontSize: 16, lineHeight: 1, padding: "0 2px",
                          }}
                          title="Закрыть"
                        >×</button>
                      </div>
                    </div>
                    <div className={styles.muted}>{n.context_text}</div>
                    <div className={styles.graphInsightRow}>
                      <span
                        className={[
                          styles.confidenceBadge,
                          confidence.band === "high"
                            ? styles.confidenceHigh
                            : confidence.band === "medium"
                              ? styles.confidenceMedium
                              : styles.confidenceLow,
                        ].join(" ")}
                      >
                        {confidence.shortLabel}
                      </span>
                      <span className={styles.confidenceMeta}>
                        {confidence.guidance}
                      </span>
                    </div>
                    <div style={{ marginTop: 10, display: "flex", gap: 12, flexWrap: "wrap" }}>
                      {sorted.slice(0, 4).map(({ lvl, prob }) => (
                        <span
                          key={lvl}
                          style={{ fontSize: 11.5, fontFamily: "var(--font-mono)", color: LEVEL_COLORS[lvl] }}
                        >
                          {LEVEL_LABELS[lvl]}: {prob.toFixed(2)}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          {/* ── Labeling Tab ─────────────────────────── */}
          {activeTab === "labeling" && (
            <div className={styles.card}>

<SectionHero
  eyebrow="Подтверждение качества"
  title="Ручная разметка"
  description="Проверяй автоматические уровни, подтверждай выводы модели и улучшай качество данных. Быстрые клавиши 1–6 тоже работают."
  stats={[
    { label: "В очереди", value: labelQueue.length, tone: labelQueue.length ? "info" : "neutral" },
    { label: "Прогресс", value: labelProgress ? `${progressPct}%` : "Не начат", tone: labelProgress ? "success" : "neutral" },
    { label: "Аннотатор", value: annotator || "default", tone: "accent" },
  ]}
/>

{/* Labeling controls */}
<div className={[styles.sectionBlock, styles.labelingHeader].join(" ")}>
                <label className={styles.fieldLabel} style={{ maxWidth: 200 }}>
                  Annotator
                  <input
                    className={styles.input}
                    value={annotator}
                    onChange={(e) => setAnnotator(e.target.value)}
                  />
                </label>
                <button
                  className={[styles.btn, styles.btnPrimary].join(" ")}
                  onClick={loadLabelQueue}
                  disabled={!ds}
                >
                  Загрузить очередь
                </button>
                <button
                  className={[styles.btn, styles.btnGhost].join(" ")}
                  onClick={() => {
                    if (!ds) return;
                    window.open(
                      `${apiBase}/datasets/${ds}/labeling/export?annotator=${encodeURIComponent(annotator)}`,
                      "_blank"
                    );
                  }}
                  disabled={!ds}
                >
                  <IconDownload />
                  Export JSONL
                </button>
              </div>

              {/* Progress */}
              {labelProgress && (
                <div style={{ marginBottom: 16 }}>
                  <div className={styles.progressLabel}>
                    <span>Прогресс разметки</span>
                    <span>
                      <span style={{ color: "var(--text-accent)", fontWeight: 600 }}>{labelProgress.labeled}</span>
                      {" "}/{" "}
                      <span>{labelProgress.total}</span>
                      {" "}
                      <span style={{ color: "var(--text-muted)" }}>({progressPct}%)</span>
                    </span>
                  </div>
                  <div className={styles.progressBar}>
                    <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
                  </div>
                </div>
              )}

              {labelQueueStatus && (
                <div className={styles.statusLine} style={{ marginBottom: 16 }}>
                  <span style={{
                    width: 7, height: 7, borderRadius: "50%",
                    background: labelQueue.length ? "var(--info)" : "var(--text-muted)",
                    flexShrink: 0,
                  }} />
                  {labelQueueStatus}
                </div>
              )}

              {/* Label card */}
              {labelQueue[0] ? (
                <div className={styles.labelNodeCard}>
                  <div className={styles.labelNodeTitle}>{labelQueue[0].title}</div>
                  <div className={styles.labelNodeContext}>{labelQueue[0].context_text}</div>

                  {/* Model prediction meta */}
                  <div className={styles.labelNodeMeta}>
                    <span className={styles.mutedSm}>Предсказание модели:</span>
                    {labelQueue[0].top_levels.map((lvl) => (
                      <BloomBadge key={lvl} level={lvl} />
                    ))}
                    {labelQueue[0].rationale && (
                      <span className={styles.mutedSm} style={{ marginLeft: 4 }}>
                        — {labelQueue[0].rationale}
                      </span>
                    )}
                  </div>

                  {/* Level toggles */}
                  <div className={styles.labelLevelToggles}>
                    {BLOOM_LEVELS.map((lvl, i) => {
                      const isActive = currentLabels[lvl];
                      return (
                        <label
                          key={lvl}
                          className={[
                            styles.levelToggle,
                            isActive ? styles.levelToggleActive : "",
                          ].join(" ")}
                          style={isActive ? {
                            background: LEVEL_BG[lvl],
                            borderColor: LEVEL_COLORS[lvl],
                            color: LEVEL_COLORS[lvl],
                          } : undefined}
                        >
                          <input
                            type="checkbox"
                            checked={isActive}
                            onChange={(e) => setCurrentLabels({ ...currentLabels, [lvl]: e.target.checked })}
                            style={{ display: "none" }}
                          />
                          <span
                            className={styles.levelToggleDot}
                            style={{
                              background: isActive ? LEVEL_COLORS[lvl] : "var(--text-muted)",
                              boxShadow: isActive ? `0 0 6px ${LEVEL_COLORS[lvl]}70` : "none",
                            }}
                          />
                          {LEVEL_LABELS[lvl]}
                          <span className={styles.levelToggleKey}>{i + 1}</span>
                        </label>
                      );
                    })}
                  </div>

                  {/* Actions */}
                  <div className={styles.labelActions}>
                    <button
                      ref={saveBtnRef}
                      className={[styles.btn, styles.btnPrimaryLg, styles.btnSuccess].join(" ")}
                      onClick={saveLabels}
                      disabled={!BLOOM_LEVELS.some((lvl) => currentLabels[lvl])}
                      style={{ flex: "none" }}
                    >
                      Сохранить и далее
                      <IconChevron />
                    </button>
                    <button
                      className={styles.btnSkip}
                      onClick={() => setLabelQueue((q) => q.slice(1))}
                    >
                      Пропустить
                    </button>
                    {undoStack.length > 0 && (
                      <button
                        className={[styles.btn, styles.btnGhost].join(" ")}
                        onClick={undoLabel}
                        title="Отменить последнее действие (Ctrl+Z)"
                      >
                        ↩ Отмена
                      </button>
                    )}
                    <span className={styles.labelHint}>
                      Осталось в очереди: <span className={styles.kbd}>{labelQueue.length}</span>
                    </span>
                  </div>
                </div>
              ) : (
                labelQueueStatus && (
                  <div className={styles.emptyState}>
                    <span className={styles.emptyIcon}><IconTag /></span>
                    <div className={styles.emptyTitle}>Очередь пуста</div>
                    <div className={styles.emptyText}>
                      Загрузи очередь или все узлы уже размечены.
                    </div>
                  </div>
                )
              )}
            </div>
          )}
          {/* ── Dashboard Tab ──────────────────────────── */}
          {activeTab === "dashboard" && (
            <div className={styles.card}>

<SectionHero
  eyebrow="Статус по платформе"
  title="Дашборд"
  description="Краткая сводка по датасетам, текущему объёму знаний и операционному состоянию платформы."
  stats={[
    { label: "Датасеты", value: dashDatasets.length, tone: "accent" },
    { label: "Узлы в DS", value: dashNodeCount ?? "?", tone: dashNodeCount ? "info" : "neutral" },
    { label: "API", value: apiStatus === "ok" ? "online" : "offline", tone: apiStatus === "ok" ? "success" : "warning" },
  ]}
  actions={
    <button
      className={[styles.btn, styles.btnPrimary].join(" ")}
      onClick={loadDashboard}
      disabled={isDashLoading}
      type="button"
    >
      {isDashLoading ? <span className={styles.spinner} /> : <IconRefresh />}
      Обновить
    </button>
  }
/>

{isDashLoading ? (
                <div className={styles.dashGrid}>
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i} className={styles.skeletonCard} style={{ height: 80 }} />
                  ))}
                </div>
              ) : (
                <>
                  {/* KPI chips */}
                  <div className={styles.dashGrid}>
                    <div className={styles.dashCard}>
                      <div className={styles.dashCardVal}>{dashDatasets.length}</div>
                      <div className={styles.dashCardLabel}>Датасетов</div>
                    </div>
                    <div className={styles.dashCard}>
                      <div className={styles.dashCardVal}>{dashNodeCount ?? "—"}</div>
                      <div className={styles.dashCardLabel}>Узлов (текущий DS)</div>
                    </div>
                    <div className={styles.dashCard}>
                      <div className={styles.dashCardVal}>{labelProgress?.labeled ?? 0}</div>
                      <div className={styles.dashCardLabel}>Размечено</div>
                    </div>
                    <div className={styles.dashCard}>
                      <div className={styles.dashCardVal} style={{ color: "var(--success)" }}>
                        {apiStatus === "ok" ? "Online" : "Offline"}
                      </div>
                      <div className={styles.dashCardLabel}>API статус</div>
                    </div>
                  </div>

                  {/* Datasets table */}
                  {dashDatasets.length > 0 && (
                    <div className={styles.dashSection}>
                      <div className={styles.cardTitle} style={{ fontSize: 13, marginBottom: 10 }}>
                        Все датасеты
                      </div>
                      {dashDatasets.map((d: any) => (
                        <div key={d.id} className={styles.dashDatasetRow}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-muted)" }}>
                            #{d.id}
                          </span>
                          <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                            {d.name}
                          </span>
                          <button
                            className={[styles.btnCompact].join(" ")}
                            onClick={() => { setDs(d.id); setActiveTab("analysis"); addToast(`Переключён на dataset #${d.id}`, "info"); }}
                          >
                            Выбрать
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Bloom distribution (from current nodes) */}
                  {nodes.length > 0 && (
                    <div className={styles.dashSection}>
                      <div className={styles.cardTitle} style={{ fontSize: 13, marginBottom: 10 }}>
                        Bloom-распределение (текущий анализ)
                      </div>
                      {BLOOM_LEVELS.map(lvl => {
                        const count = nodes.filter(n => n.top_levels.includes(lvl)).length;
                        if (!count) return null;
                        const pct = (count / nodes.length) * 100;
                        return (
                          <div key={lvl} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                            <span style={{ width: 90, fontSize: 12, color: LEVEL_COLORS[lvl] }}>{LEVEL_LABELS[lvl]}</span>
                            <div style={{ flex: 1, height: 6, background: "var(--bg-hover)", borderRadius: 3, overflow: "hidden" }}>
                              <div style={{ height: "100%", width: `${pct}%`, background: LEVEL_COLORS[lvl], borderRadius: 3 }} />
                            </div>
                            <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-muted)", width: 28, textAlign: "right" }}>{count}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {!dashDatasets.length && !isDashLoading && (
                    <div className={styles.emptyState}>
                      <span className={styles.emptyIcon}>
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                          <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
                        </svg>
                      </span>
                      <div className={styles.emptyTitle}>Нет данных</div>
                      <div className={styles.emptyText}>Нажми «Обновить» или создай датасет в боковой панели.</div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── Canvas LMS tab ──────────────────────── */}
          {activeTab === "canvas" && (
            <div className={styles.card}>

              <SectionHero
                eyebrow="Интеграция"
                title="Canvas LMS"
                description="Загрузи содержимое курса Canvas в датасет Bloom RAG Studio. Страницы, задания, тесты и обсуждения будут автоматически размечены по уровням Блума."
                stats={[
                  { label: "Курсов", value: canvasCourses.length || "—", tone: canvasCourses.length ? "accent" : "neutral" },
                  { label: "Датасет", value: ds ? `#${ds}` : "Не выбран", tone: ds ? "success" : "warning" },
                  { label: "Выбран курс", value: canvasSelectedCourse
                      ? (canvasCourses.find(c => c.id === canvasSelectedCourse)?.name?.slice(0, 22) ?? `#${canvasSelectedCourse}`)
                      : "—", tone: canvasSelectedCourse ? "info" : "neutral" },
                ]}
                actions={
                  <button
                    className={[styles.btn, styles.btnGhost].join(" ")}
                    onClick={loadCanvasCourses}
                    disabled={canvasCoursesLoading}
                    type="button"
                  >
                    {canvasCoursesLoading ? <span className={styles.spinner} /> : <IconRefresh />}
                    Обновить список
                  </button>
                }
              />

              <div className={styles.grid}>
                {/* Course search + list */}
                <div>
                  <label className={styles.fieldLabel}>
                    Поиск курса
                    <input
                      className={styles.input}
                      placeholder="Введи название курса..."
                      value={canvasCourseSearch}
                      onChange={e => setCanvasCourseSearch(e.target.value)}
                    />
                  </label>

                  {canvasCoursesLoading && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 0", color: "var(--text-muted)", fontSize: 13 }}>
                      <span className={styles.spinner} /> Загружаем курсы из Canvas...
                    </div>
                  )}

                  {!canvasCoursesLoading && canvasCourses.length === 0 && (
                    <div className={styles.emptyState} style={{ padding: "24px 0" }}>
                      <span className={styles.emptyIcon}><IconCanvas /></span>
                      <div className={styles.emptyTitle}>Курсы не загружены</div>
                      <div className={styles.emptyText}>Нажми «Обновить список» или проверь CANVAS_TOKEN в backend/.env</div>
                    </div>
                  )}

                  {canvasCourses.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 340, overflowY: "auto", marginTop: 8 }}>
                      {canvasCourses
                        .filter(c => !canvasCourseSearch || c.name.toLowerCase().includes(canvasCourseSearch.toLowerCase()) || (c.course_code || "").toLowerCase().includes(canvasCourseSearch.toLowerCase()))
                        .map(course => (
                          <div
                            key={course.id}
                            onClick={() => setCanvasSelectedCourse(course.id)}
                            style={{
                              display: "flex", alignItems: "center", gap: 10,
                              padding: "9px 12px", borderRadius: 8, cursor: "pointer",
                              border: `1.5px solid ${canvasSelectedCourse === course.id ? "var(--text-accent)" : "var(--border-1)"}`,
                              background: canvasSelectedCourse === course.id ? "rgba(99,102,241,0.08)" : "var(--bg-card)",
                              transition: "all 0.12s",
                            }}
                          >
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {course.name}
                              </div>
                              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                                {course.course_code || ""} · id: {course.id}
                              </div>
                            </div>
                            {canvasSelectedCourse === course.id && (
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                              </svg>
                            )}
                          </div>
                        ))
                      }
                    </div>
                  )}
                </div>

                {/* Ingest settings */}
                <div>
                  {canvasAlert && (
                    <div className={styles.canvasAlert} role="alert" aria-live="assertive">
                      <div className={styles.canvasAlertTitle}>
                        <IconAlert />
                        {canvasAlert.title}
                      </div>
                      <div className={styles.canvasAlertText}>{canvasAlert.message}</div>
                      <div className={styles.canvasAlertActions}>
                        <button
                          className={[styles.btn, styles.btnWarn].join(" ")}
                          onClick={() => { setApiStatus("unknown"); checkApiStatus(); }}
                          type="button"
                        >
                          <IconRefresh />
                          Проверить backend
                        </button>
                        <button
                          className={[styles.btn, styles.btnGhost].join(" ")}
                          onClick={() => setCanvasAlert(null)}
                          type="button"
                        >
                          Скрыть
                        </button>
                      </div>
                    </div>
                  )}

                  <label className={styles.fieldLabel}>
                    Типы контента
                  </label>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
                    {[
                      { id: "syllabus",     label: "Силлабус" },
                      { id: "pages",        label: "Страницы" },
                      { id: "assignments",  label: "Задания" },
                      { id: "quizzes",      label: "Тесты" },
                      { id: "discussions",  label: "Обсуждения" },
                      { id: "files",        label: "📎 Файлы" },
                    ].map(({ id: ct, label }) => (
                      <label key={ct} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer", padding: "5px 10px", borderRadius: 6, border: `1px solid ${canvasContentTypes.includes(ct) ? "var(--text-accent)" : "var(--border-1)"}`, background: canvasContentTypes.includes(ct) ? "rgba(99,102,241,0.08)" : "var(--bg-card)", transition: "all 0.12s" }}>
                        <input
                          type="checkbox"
                          checked={canvasContentTypes.includes(ct)}
                          onChange={e => setCanvasContentTypes(prev => e.target.checked ? [...prev, ct] : prev.filter(x => x !== ct))}
                          style={{ accentColor: "var(--text-accent)" }}
                        />
                        {label}
                      </label>
                    ))}
                  </div>

                  <div className={styles.paramField} style={{ marginBottom: 10 }}>
                    <span>Макс. узлов на документ</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <input className={styles.paramSlider} type="range" min={5} max={100} step={5} value={canvasMaxNodes} onChange={e => setCanvasMaxNodes(Number(e.target.value))} style={{ flex: 1 }} />
                      <input className={styles.paramInput} type="number" min={5} max={100} step={5} value={canvasMaxNodes} onChange={e => setCanvasMaxNodes(Number(e.target.value))} style={{ width: 56 }} />
                    </div>
                  </div>

                  {canvasContentTypes.includes("files") && (
                    <div className={styles.paramField} style={{ marginBottom: 16 }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        Макс. файлов
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>PDF, TXT, MD, DOCX (до 20 МБ)</span>
                      </span>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <input className={styles.paramSlider} type="range" min={1} max={100} step={1} value={canvasMaxFiles} onChange={e => setCanvasMaxFiles(Number(e.target.value))} style={{ flex: 1 }} />
                        <input className={styles.paramInput} type="number" min={1} max={100} step={1} value={canvasMaxFiles} onChange={e => setCanvasMaxFiles(Number(e.target.value))} style={{ width: 56 }} />
                      </div>
                    </div>
                  )}

                  {!ds && (
                    <div style={{ padding: "10px 12px", borderRadius: 8, background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.3)", fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
                      ⚠️ Выбери датасет в боковой панели, прежде чем запускать ингест
                    </div>
                  )}

                  <button
                    className={[styles.btn, styles.btnPrimaryLg].join(" ")}
                    onClick={ingestCanvasCourse}
                    disabled={!canvasSelectedCourse || !ds || canvasIngesting || canvasContentTypes.length === 0}
                    style={{ width: "100%" }}
                    type="button"
                  >
                    {canvasIngesting
                      ? <><span className={styles.spinner} /> Анализируем...</>
                      : <><IconCanvas /> Запустить анализ курса</>
                    }
                  </button>

                  {/* Streaming progress block */}
                  {canvasIngesting && canvasProgress && (
                    <div style={{ marginTop: 12, padding: "12px 14px", borderRadius: 10, background: "rgba(99,102,241,0.06)", border: "1px solid rgba(99,102,241,0.2)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <span className={styles.spinner} style={{ flexShrink: 0 }} />
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500, lineHeight: 1.4 }}>
                            {canvasProgress.label}
                          </div>
                          <div style={{ marginTop: 3, fontSize: 11, color: "var(--text-muted)" }}>
                            Шаг: {canvasProgress.stage} · прошло {canvasProgress.elapsedSec ?? 0} c
                          </div>
                        </div>
                      </div>
                      {/* Indeterminate progress bar */}
                      <div style={{ height: 4, borderRadius: 4, background: "rgba(99,102,241,0.15)", overflow: "hidden" }}>
                        <div style={{ height: "100%", width: "40%", borderRadius: 4, background: "var(--accent)", animation: "canvasSlide 1.4s ease-in-out infinite" }} />
                      </div>
                      {(canvasProgress.nodes_created > 0 || canvasProgress.nodes_updated > 0) && (
                        <div style={{ marginTop: 8, display: "flex", gap: 12, fontSize: 11, color: "var(--text-muted)" }}>
                          <span>✦ создано: <strong style={{ color: "var(--success)" }}>{canvasProgress.nodes_created}</strong></span>
                          <span>↺ обновлено: <strong style={{ color: "var(--accent)" }}>{canvasProgress.nodes_updated}</strong></span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Result */}
                  {canvasIngestResult && (
                    <div style={{ marginTop: 16, padding: "14px 16px", borderRadius: 10, background: "rgba(16,185,129,0.06)", border: "1px solid rgba(16,185,129,0.25)" }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--success)", marginBottom: 8 }}>Готово!</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
                        {[
                          { label: "Документов", value: canvasIngestResult.documents_ingested },
                          { label: "Узлов создано", value: canvasIngestResult.nodes_created },
                          { label: "Обновлено", value: canvasIngestResult.nodes_updated },
                        ].map(s => (
                          <div key={s.label} style={{ textAlign: "center", padding: "8px", borderRadius: 8, background: "var(--bg-card)" }}>
                            <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{s.value}</div>
                            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{s.label}</div>
                          </div>
                        ))}
                      </div>
                      {canvasIngestResult.skipped.length > 0 && (
                        <details style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                          <summary style={{ cursor: "pointer" }}>Пропущено: {canvasIngestResult.skipped.length}</summary>
                          <ul style={{ margin: "6px 0 0 16px", lineHeight: 1.6 }}>
                            {canvasIngestResult.skipped.map((s, i) => <li key={i}>{s}</li>)}
                          </ul>
                        </details>
                      )}
                      <button
                        className={[styles.btn, styles.btnPrimary].join(" ")}
                        onClick={() => setActiveTab("graph")}
                        style={{ marginTop: 10, width: "100%" }}
                        type="button"
                      >
                        <IconGraph /> Открыть граф знаний
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

        </main>

        {/* ── Aside (right sidebar) ────────────────────── */}
        <aside className={styles.aside}>

          {/* Connection card */}
          <div className={styles.asideCard}>
            <div className={styles.asideCardHeader}>
              <span className={styles.asideCardTitle}>Подключение</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div className={[styles.dot, apiStatusDotClass].join(" ")} />
                <span style={{ fontSize: 11, color: apiStatus === "ok" ? "var(--success)" : apiStatus === "down" ? "var(--error, #f87171)" : "var(--text-muted)" }}>
                  {apiStatus === "ok" ? "online" : apiStatus === "down" ? "offline" : "…"}
                </span>
              </div>
            </div>
            <div className={styles.asideCardBody}>
              <label className={styles.fieldLabel}>
                API Base URL
                <input
                  className={styles.input}
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  placeholder="/api-proxy"
                />
              </label>
              {apiStatus === "down" && (
                <div style={{ padding: "8px 10px", borderRadius: 7, background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)", fontSize: 12, color: "#f87171", marginBottom: 6 }}>
                  Backend недоступен — проверь что Docker запущен и backend-контейнер поднят
                </div>
              )}
              <div className={styles.row}>
                <button
                  className={styles.btnCompact}
                  onClick={() => setApiBase("/api-proxy")}
                >
                  proxy
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={() => window.open(`${apiBase}/docs`, "_blank")}
                >
                  /docs
                </button>
                <button
                  className={[styles.btnCompact, apiStatus === "down" ? styles.btnCompactPrimary : ""].join(" ")}
                  onClick={() => { setApiStatus("unknown"); checkApiStatus(); }}
                  title="Проверить соединение с бэкендом"
                >
                  ↺ Проверить
                </button>
              </div>
            </div>
          </div>

          {/* Dataset card */}
          <div className={styles.asideCard}>
            <div className={styles.asideCardHeader}>
              <span className={styles.asideCardTitle}>Датасет</span>
              {ds && (
                <div className={styles.dsIdBadge}>
                  <span style={{ color: "var(--text-muted)", fontSize: 11 }}>id</span>
                  <span className={styles.dsIdBadgeValue}>{ds}</span>
                </div>
              )}
            </div>
            <div className={styles.asideCardBody}>
              {/* Create new */}
              <label className={styles.fieldLabel}>
                Имя нового датасета
                <div className={styles.dsRow}>
                  <input
                    className={styles.dsInput}
                    placeholder="demo_2026_03"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                  <button
                    className={[styles.btnCompact, styles.btnCompactPrimary].join(" ")}
                    onClick={createDataset}
                    disabled={!name.trim()}
                  >
                    <IconPlus /> Создать
                  </button>
                </div>
              </label>

              {/* Set ID */}
              <label className={styles.fieldLabel}>
                Dataset ID (ввести вручную)
                <input
                  className={styles.dsInput}
                  type="number"
                  placeholder="1"
                  value={ds ?? ""}
                  onChange={(e) => setDs(e.target.value ? Number(e.target.value) : undefined)}
                />
              </label>

              <div className={styles.divider} />

              {/* File upload drag zone */}
              <div className={styles.fieldLabel}>
                Документ для индексации
                {/* Hidden native file input */}
                <input
                  ref={sidebarFileRef}
                  type="file"
                  accept=".txt,.pdf,.md"
                  style={{ display: "none" }}
                  onChange={(e) => {
                    const f = e.target.files?.[0] || null;
                    setFile(f);
                    setFileName(f?.name ?? "");
                    if (f) setName(f.name.replace(/\.[^.]+$/, ""));
                    e.target.value = "";
                  }}
                />
                <div
                  className={styles.dropZone}
                  style={{ cursor: "pointer" }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const f = e.dataTransfer.files?.[0] || null;
                    setFile(f);
                    setFileName(f?.name ?? "");
                    if (f) setName(f.name.replace(/\.[^.]+$/, ""));
                  }}
                  onClick={() => sidebarFileRef.current?.click()}
                >
                  <span className={styles.dropZoneIcon}><IconFile /></span>
                  {fileName ? (
                    <span className={styles.dropZoneText} style={{ color: "var(--text-accent)" }}>
                      {fileName}
                    </span>
                  ) : (
                    <>
                      <span className={styles.dropZoneText}>Перетащи файл сюда</span>
                      <span className={styles.dropZoneHint}>.txt, .pdf, .md — любой текст</span>
                    </>
                  )}
                </div>
              </div>

              {/* Upload / Index */}
              <div className={styles.row}>
                <button
                  className={[styles.btnCompact, styles.btnCompactPrimary].join(" ")}
                  onClick={upload}
                  disabled={!ds || !file}
                >
                  <IconUpload /> Загрузить
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={indexDs}
                  disabled={!ds}
                >
                  Индексировать
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={exportJsonl}
                  disabled={!ds}
                >
                  <IconDownload /> JSONL
                </button>
              </div>

              <div className={styles.divider} />

              {/* Batch upload */}
              <div className={styles.fieldLabel} style={{ color: "var(--text-muted)", fontSize: 11 }}>
                Пакетная загрузка
              </div>
              <label style={{
                display: "block", padding: "7px 10px",
                borderRadius: 7, border: "1px dashed var(--border-2)",
                cursor: "pointer", fontSize: 12, color: "var(--text-secondary)",
                textAlign: "center",
              }}>
                <input
                  type="file"
                  multiple
                  accept=".txt,.pdf,.md"
                  style={{ display: "none" }}
                  onChange={e => {
                    const files = Array.from(e.target.files || []);
                    setBatchFiles(files.map(f => ({ name: f.name, file: f, status: "pending" as const })));
                    e.target.value = "";
                  }}
                />
                + Выбрать файлы
              </label>
              {batchFiles.length > 0 && (
                <>
                  <div className={styles.batchList}>
                    {batchFiles.map((item, i) => (
                      <div key={i} className={styles.batchItem}>
                        <span className={styles.batchItemName}>{item.name}</span>
                        <span className={[
                          styles.batchItemStatus,
                          item.status === "done" ? styles.batchDone :
                          item.status === "error" ? styles.batchError :
                          item.status === "uploading" ? styles.batchRunning :
                          styles.batchPending,
                        ].join(" ")}>
                          {item.status === "done" ? "✓" : item.status === "error" ? "✕" : item.status === "uploading" ? "…" : "·"}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className={styles.row}>
                    <button
                      className={[styles.btnCompact, styles.btnCompactPrimary].join(" ")}
                      onClick={batchUploadAll}
                      disabled={!ds}
                    >
                      <IconUpload /> Загрузить все
                    </button>
                    <button
                      className={styles.btnCompact}
                      onClick={() => setBatchFiles([])}
                    >
                      Очистить
                    </button>
                  </div>
                </>
              )}

              <div className={styles.divider} />

              {/* Annotate shortcuts */}
              <div className={styles.fieldLabel} style={{ color: "var(--text-muted)", fontSize: 11 }}>
                Автоаннотация
              </div>
              <div className={styles.row}>
                <button
                  className={styles.btnCompact}
                  onClick={() => annotate("apply")}
                  disabled={!ds}
                >
                  Annotate apply
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={() => annotate("analyze")}
                  disabled={!ds}
                >
                  Annotate analyze
                </button>
              </div>

              {/* Job status */}
              {lastJob && (
                <div style={{ marginTop: 4 }}>
                  <JobStatus jobId={lastJob} apiBase={apiBase} />
                </div>
              )}
            </div>
          </div>

        </aside>
      </div>

      {/* ── Node detail modal ──────────────────────────── */}
      {detailNode && (
        <div className={styles.detailOverlay} onClick={() => setDetailNode(null)}>
          <div className={styles.detailModal} onClick={e => e.stopPropagation()}>
            <div className={styles.detailHeader}>
              <div className={styles.detailTitle}>{detailNode.title}</div>
              <button className={styles.detailClose} onClick={() => setDetailNode(null)}>×</button>
            </div>
            <div className={styles.detailBody}>
              <div className={styles.detailSection}>
                <div className={styles.detailSectionLabel}>Уровни Блума</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {detailNode.top_levels.map(lvl => <BloomBadge key={lvl} level={lvl} />)}
                </div>
              </div>
              <div className={styles.detailSection}>
                <div className={styles.detailSectionLabel}>Уверенность модели</div>
                <div className={styles.detailInsightCard}>
                  <div className={styles.confidenceRow}>
                    <span
                      className={[
                        styles.confidenceBadge,
                        getConfidenceMeta(detailNode).band === "high"
                          ? styles.confidenceHigh
                          : getConfidenceMeta(detailNode).band === "medium"
                            ? styles.confidenceMedium
                            : styles.confidenceLow,
                      ].join(" ")}
                    >
                      {getConfidenceMeta(detailNode).label}
                    </span>
                    <span className={styles.confidenceMeta}>{getConfidenceMeta(detailNode).guidance}</span>
                  </div>
                  <div className={styles.explainList}>
                    {getExplainabilityLines(detailNode).map((line) => (
                      <div key={line} className={styles.explainItem}>
                        <span className={styles.explainDot} />
                        <span>{line}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <div className={styles.detailSection}>
                <div className={styles.detailSectionLabel}>Контекст</div>
                <div className={styles.detailText}>{detailNode.context_text}</div>
              </div>
              {detailNode.rationale && (
                <div className={styles.detailSection}>
                  <div className={styles.detailSectionLabel}>Обоснование</div>
                  <div className={styles.detailText} style={{ fontStyle: "italic", color: "var(--text-muted)" }}>{detailNode.rationale}</div>
                </div>
              )}
              <div className={styles.detailSection}>
                <div className={styles.detailSectionLabel}>Вектор вероятностей</div>
                <div className={styles.detailProbFull}>
                  {getSortedLevels(detailNode.prob_vector).map(({ lvl, prob }) => (
                    <div key={lvl} className={styles.detailProbRow}>
                      <span className={styles.detailProbLabel} style={{ color: LEVEL_COLORS[lvl] }}>{LEVEL_LABELS[lvl]}</span>
                      <div className={styles.detailProbBar}>
                        <div className={styles.detailProbFill} style={{ width: `${Math.round(prob * 100)}%`, background: LEVEL_COLORS[lvl] }} />
                      </div>
                      <span className={styles.detailProbVal}>{(prob * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button className={[styles.btn, styles.btnPrimary].join(" ")} onClick={() => copyNode(detailNode)}>
                  Копировать
                </button>
                <button className={[styles.btn, styles.btnGhost].join(" ")} onClick={() => setDetailNode(null)}>
                  Закрыть
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Settings drawer ─────────────────────────────── */}
      {showSettings && (
        <div className={styles.settingsOverlay} onClick={() => setShowSettings(false)}>
          <div className={styles.settingsPanel} onClick={e => e.stopPropagation()}>
            <div className={styles.settingsHeader}>
              <div className={styles.settingsTitle}>Настройки</div>
              <button className={styles.settingsClose} onClick={() => setShowSettings(false)}>×</button>
            </div>
            <div className={styles.settingsBody}>
              <div className={styles.settingsSectionTitle}>Анализ</div>

              <div className={styles.settingsRow}>
                <label className={styles.settingsLabel}>
                  Min prob (порог уверенности)
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{minProb.toFixed(2)}</span>
                </label>
                <input
                  type="range" min="0.05" max="0.5" step="0.05"
                  value={minProb}
                  onChange={e => setMinProb(Number(e.target.value))}
                  className={styles.settingsInput}
                />
              </div>

              <div className={styles.settingsRow}>
                <label className={styles.settingsLabel}>
                  Макс. уровней на узел
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{maxLevels}</span>
                </label>
                <input
                  type="range" min="1" max="6" step="1"
                  value={maxLevels}
                  onChange={e => setMaxLevels(Number(e.target.value))}
                  className={styles.settingsInput}
                />
              </div>

              <div className={styles.settingsSectionTitle} style={{ marginTop: 16 }}>Тема</div>
              <div className={styles.themeSwitchRow}>
                <button
                  className={[styles.themeOption, theme === "light" ? styles.themeOptionActive : ""].join(" ")}
                  onClick={() => setTheme("light")}
                  type="button"
                >
                  Светлая
                </button>
                <button
                  className={[styles.themeOption, theme === "dark" ? styles.themeOptionActive : ""].join(" ")}
                  onClick={() => setTheme("dark")}
                  type="button"
                >
                  Тёмная
                </button>
              </div>

              <div className={styles.settingsSectionTitle} style={{ marginTop: 16 }}>Эмбеддинги</div>

              <div className={styles.settingsRow}>
                <label className={styles.settingsLabel}>Модель</label>
                <select
                  className={styles.nodeSortSelect}
                  value={embeddingModel}
                  onChange={e => setEmbeddingModel(e.target.value)}
                  style={{ width: "100%" }}
                >
                  <option value="">Использовать backend provider (рекомендуется)</option>
                  <option value="text-embedding-3-small">text-embedding-3-small</option>
                  <option value="text-embedding-3-large">text-embedding-3-large</option>
                  <option value="text-embedding-ada-002">text-embedding-ada-002</option>
                </select>
              </div>

              <div className={styles.settingsSectionTitle} style={{ marginTop: 16 }}>Разметка</div>
              <div className={styles.settingsRow}>
                <label className={styles.settingsLabel}>Аннотатор по умолчанию</label>
                <input
                  className={styles.dsInput}
                  value={annotator}
                  onChange={e => setAnnotator(e.target.value)}
                  placeholder="default"
                />
              </div>

              <button
                className={[styles.btn, styles.btnPrimary].join(" ")}
                onClick={() => { setShowSettings(false); addToast("✓ Настройки сохранены", "success"); }}
                style={{ marginTop: 20, width: "100%" }}
              >
                Сохранить и закрыть
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Onboarding overlay ──────────────────────────── */}
      {showOnboarding && (
        <div className={styles.onboardOverlay}>
          <div className={styles.onboardCard}>
            <div className={styles.onboardIcon}>🌸</div>
            <div className={styles.onboardTitle}>Добро пожаловать в Bloom RAG Studio</div>
            <div className={styles.onboardSubtitle}>
              Инструмент для автоматической классификации знаний по таксономии Блума с RAG-индексацией.
            </div>
            <div className={styles.onboardSteps}>
              {[
                { n: "1", text: "Создай датасет в правой панели или введи ID существующего" },
                { n: "2", text: "Вставь текст на вкладке «Анализ» и нажми Анализировать" },
                { n: "3", text: "Загрузи документ и проиндексируй для семантического поиска" },
                { n: "4", text: "Перейди на вкладку «Разметка» для ручной аннотации (1–6 + Enter)" },
              ].map(({ n, text }) => (
                <div key={n} className={styles.onboardStep}>
                  <div className={styles.onboardStepNum}>{n}</div>
                  <div className={styles.onboardStepText}>{text}</div>
                </div>
              ))}
            </div>
            <button
              className={[styles.btn, styles.btnPrimaryLg].join(" ")}
              onClick={() => {
                setShowOnboarding(false);
                localStorage.setItem("bloom_visited", "1");
              }}
              style={{ marginTop: 8 }}
            >
              Начать работу →
            </button>
          </div>
        </div>
      )}

      {/* ── Guide modal ────────────────────────────────── */}
      {showGuide && (
        <div className={styles.guideOverlay} onClick={() => setShowGuide(false)}>
          <div className={styles.guidePanel} onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className={styles.guideHeader}>
              <div className={styles.guideHeaderIcon}>📖</div>
              <div style={{ flex: 1 }}>
                <div className={styles.guideTitle}>Как пользоваться</div>
                <div className={styles.guideSubtitle}>Bloom RAG Studio — краткое руководство</div>
              </div>
              <button className={styles.guideClose} onClick={() => setShowGuide(false)}>×</button>
            </div>

            <div className={styles.guideBody}>
              {/* Steps */}
              <div className={styles.guideSectionTitle}>Быстрый старт</div>

              <div className={styles.guideStep}>
                <div className={styles.guideStepNum}>1</div>
                <div className={styles.guideStepContent}>
                  <div className={styles.guideStepTitle}>
                    Подключение и датасет
                    <span className={styles.guideStepTag}>правая панель</span>
                  </div>
                  <div className={styles.guideStepText}>
                    Убедись, что API работает (зелёная точка в хедере). Создай датасет через поле «Имя» + кнопку <strong>Create</strong>, или введи ID существующего вручную.
                  </div>
                </div>
              </div>

              <div className={styles.guideStep}>
                <div className={styles.guideStepNum}>2</div>
                <div className={styles.guideStepContent}>
                  <div className={styles.guideStepTitle}>
                    Анализ контента
                    <span className={styles.guideStepTag}>вкладка Анализ</span>
                  </div>
                  <div className={styles.guideStepText}>
                    Вставь текст в поле или загрузи файл <span className={styles.guideStepKbd}>.txt .pdf .md</span>.
                    Нажми <strong>Анализировать</strong> — получишь узлы знаний с multi-label классификацией по Блуму.
                    Экспортируй результат через <span className={styles.guideStepKbd}>JSON</span> или <span className={styles.guideStepKbd}>CSV</span>.
                  </div>
                </div>
              </div>

              <div className={styles.guideStep}>
                <div className={styles.guideStepNum}>3</div>
                <div className={styles.guideStepContent}>
                  <div className={styles.guideStepTitle}>
                    Граф знаний
                    <span className={styles.guideStepTag}>вкладка Граф</span>
                  </div>
                  <div className={styles.guideStepText}>
                    Нажми <strong>Загрузить граф</strong> для визуализации узлов из БД.
                    Фильтруй по уровням Блума через чипсы. Hover на узел — увидишь детали.
                    Для перестройки рёбер используй <strong>Rebuild edges</strong>.
                  </div>
                </div>
              </div>

              <div className={styles.guideStep}>
                <div className={styles.guideStepNum}>4</div>
                <div className={styles.guideStepContent}>
                  <div className={styles.guideStepTitle}>
                    Ручная разметка
                    <span className={styles.guideStepTag}>вкладка Разметка</span>
                  </div>
                  <div className={styles.guideStepText}>
                    Нажми <strong>Загрузить очередь</strong>. Выбирай уровни кнопками или клавишами{" "}
                    <span className={styles.guideStepKbd}>1</span>–<span className={styles.guideStepKbd}>6</span>.
                    Нажми <span className={styles.guideStepKbd}>Enter</span> — сохранить и перейти к следующему.
                    Экспорт разметки через <strong>Export JSONL</strong>.
                  </div>
                </div>
              </div>

              <div className={styles.guideTip}>
                <span style={{ fontSize: 14, flexShrink: 0 }}>💡</span>
                <span>Анализ автоматически создаёт датасет, если он не выбран. Достаточно просто нажать «Анализировать».</span>
              </div>

              {/* Bloom taxonomy reference */}
              <div className={styles.guideSectionTitle} style={{ marginTop: 4 }}>Таксономия Блума</div>

              <div className={styles.bloomRef}>
                {([
                  ["remember",   "🔵", "Знать",         "Вспомнить и воспроизвести факты"],
                  ["understand", "🟢", "Понимать",       "Объяснить концепцию своими словами"],
                  ["apply",      "🟠", "Применять",      "Использовать знания в новой ситуации"],
                  ["analyze",    "🟣", "Анализировать",  "Разобрать структуру и связи"],
                  ["evaluate",   "🔴", "Оценивать",      "Критически оценить и обосновать"],
                  ["create",     "🩵", "Создавать",      "Синтезировать новое из имеющегося"],
                ] as const).map(([lvl, emoji, name, desc], i) => (
                  <div key={lvl} className={styles.bloomRefRow}>
                    <span className={styles.bloomRefDot} style={{ background: LEVEL_COLORS[lvl as BloomLevel] }} />
                    <span className={styles.bloomRefNum}>{i + 1}</span>
                    <span className={styles.bloomRefName} style={{ color: LEVEL_COLORS[lvl as BloomLevel] }}>{name}</span>
                    <span className={styles.bloomRefDesc}>{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast container ──────────────────────────────── */}
      {toasts.length > 0 && (
        <div className={styles.toastContainer}>
          {toasts.map(t => (
            <div
              key={t.id}
              className={[styles.toast, t.type === "success" ? styles.toastSuccess : t.type === "error" ? styles.toastError : styles.toastInfo].join(" ")}
              onClick={() => setToasts(p => p.filter(x => x.id !== t.id))}
            >
              <span style={{ fontSize: 14, flexShrink: 0 }}>
                {t.type === "success" ? "✓" : t.type === "error" ? "✕" : "ℹ"}
              </span>
              {t.msg}
            </div>
          ))}
        </div>
      )}

      {/* ── Footer ─────────────────────────────────────── */}
      <footer style={{
        position: "relative",
        padding: "32px 32px 28px",
        marginTop: 8,
      }}>
        {/* gradient divider */}
        <div style={{
          position: "absolute",
          top: 0, left: "5%", right: "5%",
          height: 1,
          background: "linear-gradient(90deg, transparent, var(--border-2) 25%, var(--border-2) 75%, transparent)",
        }} />

        <div style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 32,
          flexWrap: "wrap",
        }}>

          {/* ── Brand column ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 200 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: "linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, boxShadow: "0 0 12px rgba(99,102,241,0.3)",
              }}>🌸</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)", letterSpacing: "-0.2px" }}>
                  Bloom RAG Studio
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>
                  Knowledge Taxonomy Engine
                </div>
              </div>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6, maxWidth: 260 }}>
              Инструмент для автоматической классификации учебных материалов по таксономии Блума с RAG-индексацией и визуализацией графа знаний.
            </p>
            {/* tech badges */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 2 }}>
              {[["Next.js", "#fff"], ["FastAPI", "#009688"], ["PostgreSQL", "#336791"], ["pgvector", "#c084fc"], ["OpenAI", "#10a37f"]].map(([label, color]) => (
                <span key={label} style={{
                  fontSize: 10, fontWeight: 600, letterSpacing: "0.3px",
                  padding: "2px 7px", borderRadius: 4,
                  border: `1px solid ${color}33`,
                  background: `${color}11`,
                  color: color === "#fff" ? "var(--text-secondary)" : color,
                }}>{label}</span>
              ))}
            </div>
          </div>

          {/* ── Center: quick links ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.6px", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 4 }}>
              Ресурсы
            </div>
            {[
              { label: "API Docs", href: `${apiBase}/docs`, icon: "📄" },
              { label: "Health Check", href: `${apiBase}/health`, icon: "🟢" },
              { label: "OpenAPI JSON", href: `${apiBase}/openapi.json`, icon: "⚙️" },
            ].map(({ label, href, icon }) => (
              <a key={label} href={href} target="_blank" rel="noopener noreferrer" style={{
                display: "flex", alignItems: "center", gap: 7,
                fontSize: 12, color: "var(--text-muted)", textDecoration: "none",
                transition: "color 0.15s",
              }}
                onMouseEnter={e => { e.currentTarget.style.color = "var(--text-accent)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "var(--text-muted)"; }}
              >
                <span style={{ fontSize: 11 }}>{icon}</span>
                {label}
              </a>
            ))}
          </div>

          {/* ── Developer column ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "flex-end" }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.6px", color: "var(--text-muted)", textTransform: "uppercase" }}>
              Разработчик
            </div>
            <a
              href="https://t.me/JapanDino"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "inline-flex", alignItems: "center", gap: 9,
                padding: "9px 16px", borderRadius: 12,
                border: "1px solid var(--border-2)",
                background: "var(--bg-card)",
                textDecoration: "none", color: "var(--text-secondary)",
                fontSize: 13, fontWeight: 500,
                transition: "all 0.18s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "rgba(99,102,241,0.45)";
                e.currentTarget.style.background = "rgba(99,102,241,0.08)";
                e.currentTarget.style.color = "var(--text-accent)";
                e.currentTarget.style.boxShadow = "0 0 20px rgba(99,102,241,0.18)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--border-2)";
                e.currentTarget.style.background = "var(--bg-card)";
                e.currentTarget.style.color = "var(--text-secondary)";
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0, opacity: 0.85 }}>
                <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12L7.19 13.67l-2.96-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.958.889z"/>
              </svg>
              <span>JapanDino</span>
            </a>
            <div style={{ fontSize: 11, color: "var(--text-muted)", textAlign: "right", lineHeight: 1.5 }}>
              Bloom RAG Studio © {new Date().getFullYear()}<br/>
              <span style={{ opacity: 0.6 }}>MIT License</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
