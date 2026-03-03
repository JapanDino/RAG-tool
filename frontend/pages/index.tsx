import React, { useMemo, useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import JobStatus from "../components/JobStatus";
import styles from "../styles/home.module.css";

type BloomLevel = "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create";

const BLOOM_LEVELS: BloomLevel[] = [
  "remember",
  "understand",
  "apply",
  "analyze",
  "evaluate",
  "create",
];

const LEVEL_LABELS: Record<BloomLevel, string> = {
  remember: "Знать",
  understand: "Понимать",
  apply: "Применять",
  analyze: "Анализировать",
  evaluate: "Оценивать",
  create: "Создавать",
};

// Vivid colors for dark theme
const LEVEL_COLORS: Record<BloomLevel, string> = {
  remember:   "#60a5fa",
  understand: "#34d399",
  apply:      "#fb923c",
  analyze:    "#c084fc",
  evaluate:   "#f87171",
  create:     "#2dd4bf",
};

const LEVEL_BG: Record<BloomLevel, string> = {
  remember:   "rgba(96,165,250,0.14)",
  understand: "rgba(52,211,153,0.14)",
  apply:      "rgba(251,146,60,0.14)",
  analyze:    "rgba(192,132,252,0.14)",
  evaluate:   "rgba(248,113,113,0.14)",
  create:     "rgba(45,212,191,0.14)",
};

const LEVEL_BORDER: Record<BloomLevel, string> = {
  remember:   "rgba(96,165,250,0.28)",
  understand: "rgba(52,211,153,0.28)",
  apply:      "rgba(251,146,60,0.28)",
  analyze:    "rgba(192,132,252,0.28)",
  evaluate:   "rgba(248,113,113,0.28)",
  create:     "rgba(45,212,191,0.28)",
};

type AnalyzeNode = {
  id: number;
  title: string;
  context_text: string;
  prob_vector: number[];
  top_levels: BloomLevel[];
  frequency?: number | null;
  rationale?: string | null;
};

type GraphEdge = {
  from_id: number;
  to_id: number;
  weight: number;
};

const getSortedLevels = (probs: number[]) =>
  BLOOM_LEVELS.map((lvl, idx) => ({ lvl, prob: Number(probs?.[idx] ?? 0) }))
    .sort((a, b) => b.prob - a.prob);

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

export default function Home() {
  const [name, setName] = useState("");
  const [ds, setDs] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [lastJob, setLastJob] = useState<number | undefined>();
  const [activeTab, setActiveTab] = useState<"analysis" | "graph" | "labeling">("analysis");
  const [textInput, setTextInput] = useState("");
  const [nodes, setNodes] = useState<AnalyzeNode[]>([]);
  const [nodesStatus, setNodesStatus] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
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

  const DEFAULT_API = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
  const [apiBase, setApiBase] = useState(DEFAULT_API);
  const [apiStatus, setApiStatus] = useState<"unknown" | "ok" | "down">("unknown");
  const [error, setError] = useState<string | null>(null);

  const GraphView = useMemo(
    () => dynamic(() => import("../components/GraphView"), { ssr: false }),
    []
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (apiBase.includes("://backend:") && window.location.hostname === "localhost") {
      setApiBase("http://localhost:8000");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 2000);
        const r = await fetch(`${apiBase}/health`, { signal: controller.signal });
        clearTimeout(t);
        if (!cancelled) setApiStatus(r.ok ? "ok" : "down");
      } catch {
        if (!cancelled) setApiStatus("down");
      }
    };
    setApiStatus("unknown");
    check();
    const it = setInterval(check, 6000);
    return () => {
      cancelled = true;
      clearInterval(it);
    };
  }, [apiBase]);

  const apiFetchJson = async (path: string, init?: RequestInit): Promise<any | null> => {
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
  };

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
  };

  const upload = async () => {
    if (!ds || !file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      setError(null);
      const r = await fetch(`${apiBase}/datasets/${ds}/documents`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
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

  const analyzeText = async () => {
    if (!textInput.trim() || !ds) return;
    setIsAnalyzing(true);
    setNodesStatus("Анализируем текст...");
    const json = await apiFetchJson(`/analyze/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textInput, dataset_id: ds }),
    });
    setIsAnalyzing(false);
    if (!json) {
      setNodesStatus("Ошибка анализа (см. сообщение выше).");
      return;
    }
    const items: AnalyzeNode[] = json.nodes || [];
    setNodes(items);
    setNodesStatus(items.length ? `Найдено узлов: ${items.length}` : "Узлы не найдены");
  };

  const loadTextFile = async (f: File | null) => {
    if (!f) return;
    const text = await f.text();
    setTextInput(text);
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

  const loadGraph = async () => {
    if (!ds) return;
    const params = new URLSearchParams({
      dataset_id: String(ds),
      source: "db",
      top_k: String(graphTopK),
      min_score: String(graphMinScore),
      include_cooccurrence: graphIncludeCo ? "true" : "false",
      limit_nodes: String(graphLimitNodes),
    });
    const json = await apiFetchJson(`/graph?${params.toString()}`);
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
    setLabelQueue((q) => q.slice(1));
    setCurrentLabels({
      remember: false, understand: false, apply: false,
      analyze: false, evaluate: false, create: false,
    });
    setLabelProgress((p) => (p ? { ...p, labeled: p.labeled + 1 } : p));
  };

  // Ref to the save button — clicking the real button guarantees React has the latest state.
  const saveBtnRef = useRef<HTMLButtonElement>(null);

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
              <span className={styles.navHint}>content</span>
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
              <span className={styles.navHint}>100+</span>
            </button>
          </div>
        </nav>

        {/* ── Main area ────────────────────────────────── */}
        <main className={styles.main}>

          {/* Error banner */}
          {error && (
            <div className={styles.error}>
              <span className={styles.errorIcon}><IconAlert /></span>
              <span>{error}</span>
            </div>
          )}

          {/* ── Analysis Tab ─────────────────────────── */}
          {activeTab === "analysis" && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <div>
                  <div className={styles.cardTitle}>Анализ контента</div>
                  <div className={styles.cardNote}>
                    Вставь текст — получи узлы знаний с multi-label уровнями Блума. Сохраняется в БД как RAG-элементы.
                  </div>
                </div>
                {nodes.length > 0 && (
                  <div className={styles.cardActions}>
                    <button
                      className={[styles.btn, styles.btnGhost].join(" ")}
                      onClick={exportNodesJson}
                      title="Экспорт JSON"
                    >
                      <IconDownload /> JSON
                    </button>
                    <button
                      className={[styles.btn, styles.btnGhost].join(" ")}
                      onClick={exportNodesCsv}
                      title="Экспорт CSV"
                    >
                      <IconDownload /> CSV
                    </button>
                  </div>
                )}
              </div>

              <div className={styles.grid}>
                {/* Textarea */}
                <label className={styles.fieldLabel}>
                  Текст для анализа
                  <textarea
                    className={styles.textarea}
                    placeholder="Вставьте текст на русском языке — например: «Нейронные сети — это вычислительные модели, вдохновлённые строением мозга...»"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                  />
                </label>

                {/* Actions row */}
                <div className={styles.btnRow}>
                  <button
                    className={[styles.btn, styles.btnPrimaryLg].join(" ")}
                    onClick={analyzeText}
                    disabled={!ds || !textInput.trim() || isAnalyzing}
                  >
                    {isAnalyzing ? <span className={styles.spinner} /> : <IconSparkle />}
                    {isAnalyzing ? "Анализируем..." : "Анализировать"}
                  </button>

                  <button
                    className={[styles.btn].join(" ")}
                    onClick={loadNodesFromDb}
                    disabled={!ds}
                  >
                    <IconNodes />
                    Узлы из БД
                  </button>

                  <label className={styles.btn} style={{ cursor: "pointer" }}>
                    <input
                      type="file"
                      accept=".txt"
                      style={{ display: "none" }}
                      onChange={(e) => loadTextFile(e.target.files?.[0] || null)}
                    />
                    <IconUpload />
                    .txt в поле
                  </label>
                </div>

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
                {isAnalyzing && (
                  <div className={styles.statusLine}>
                    <span className={styles.statusLineIcon} />
                    Анализируем текст, извлекаем узлы знаний...
                  </div>
                )}

                {/* Node cards grid */}
                {nodes.length > 0 && (
                  <div className={styles.nodesGrid}>
                    {nodes.map((n) => {
                      const sorted = getSortedLevels(n.prob_vector);
                      return (
                        <div key={n.id} className={styles.nodeCard}>
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

                          {/* Probability bars */}
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
                      Вставь текст выше и нажми "Анализировать" (нужен активный dataset).
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Graph Tab ────────────────────────────── */}
          {activeTab === "graph" && (
            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <div>
                  <div className={styles.cardTitle}>Граф знаний</div>
                  <div className={styles.cardNote}>
                    Узлы окрашены по уровню Блума. Обводка — второй уровень. Рёбра из БД (после rebuild).
                  </div>
                </div>
              </div>

              <div className={styles.graphControls}>
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
                    Limit nodes
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
                </div>
              </div>

              {/* Graph canvas */}
              <GraphView
                nodes={graphNodesData}
                edges={graphEdgesData}
                filters={filters}
                threshold={threshold}
                onHover={(n: AnalyzeNode | null) => {
                  setHoveredNode(n);
                  if (n) setSelectedNode(n);
                }}
              />

              {/* Node detail card */}
              {(selectedNode || hoveredNode) && (() => {
                const n = (hoveredNode || selectedNode)!;
                const sorted = getSortedLevels(n.prob_vector);
                return (
                  <div className={styles.cardSm} style={{ marginTop: 12 }}>
                    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 10 }}>
                      <div>
                        <div className={styles.cardTitle}>{n.title}</div>
                        {n.rationale && (
                          <div className={styles.muted} style={{ marginTop: 4 }}>{n.rationale}</div>
                        )}
                      </div>
                      <div style={{ marginLeft: "auto", display: "flex", gap: 5, flexWrap: "wrap", flexShrink: 0 }}>
                        {n.top_levels.map((lvl) => <BloomBadge key={lvl} level={lvl} />)}
                      </div>
                    </div>
                    <div className={styles.muted}>{n.context_text}</div>
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
              <div className={styles.cardHeader}>
                <div>
                  <div className={styles.cardTitle}>Ручная разметка</div>
                  <div className={styles.cardNote}>
                    Выбирай уровни Блума кнопками или клавишами{" "}
                    <span className={styles.kbd}>1–6</span>, затем "Сохранить и далее".
                  </div>
                </div>
              </div>

              {/* Labeling controls */}
              <div className={styles.labelingHeader}>
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
        </main>

        {/* ── Aside (right sidebar) ────────────────────── */}
        <aside className={styles.aside}>

          {/* Connection card */}
          <div className={styles.asideCard}>
            <div className={styles.asideCardHeader}>
              <span className={styles.asideCardTitle}>Подключение</span>
              <div className={[styles.dot, apiStatusDotClass].join(" ")} />
            </div>
            <div className={styles.asideCardBody}>
              <label className={styles.fieldLabel}>
                API Base URL
                <input
                  className={styles.input}
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  placeholder="http://localhost:8000"
                />
              </label>
              <div className={styles.row}>
                <button
                  className={styles.btnCompact}
                  onClick={() => setApiBase("http://localhost:8000")}
                >
                  localhost
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={() => window.open(`${apiBase}/docs`, "_blank")}
                >
                  /docs
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={() => window.open(`${apiBase}/health`, "_blank")}
                >
                  /health
                </button>
              </div>
            </div>
          </div>

          {/* Dataset card */}
          <div className={styles.asideCard}>
            <div className={styles.asideCardHeader}>
              <span className={styles.asideCardTitle}>Dataset</span>
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
                    <IconPlus /> Create
                  </button>
                </div>
              </label>

              {/* Set ID */}
              <label className={styles.fieldLabel}>
                Dataset ID (ввести вручную)
                <div className={styles.dsRow}>
                  <input
                    className={styles.dsInput}
                    type="number"
                    placeholder="1"
                    value={ds ?? ""}
                    onChange={(e) => setDs(e.target.value ? Number(e.target.value) : undefined)}
                  />
                  <button
                    className={styles.btnCompact}
                    onClick={() => {
                      const v = prompt("Укажи dataset id");
                      if (!v) return;
                      const id = Number(v);
                      if (!Number.isFinite(id)) return;
                      setDs(id);
                    }}
                  >
                    Set
                  </button>
                </div>
              </label>

              <div className={styles.divider} />

              {/* File upload drag zone */}
              <label className={styles.fieldLabel}>
                Документ для индексации
                <div className={styles.dropZone}>
                  <input
                    type="file"
                    onChange={(e) => {
                      const f = e.target.files?.[0] || null;
                      setFile(f);
                      setFileName(f?.name ?? "");
                    }}
                  />
                  <span className={styles.dropZoneIcon}><IconFile /></span>
                  {fileName ? (
                    <span className={styles.dropZoneText} style={{ color: "var(--text-accent)" }}>
                      {fileName}
                    </span>
                  ) : (
                    <>
                      <span className={styles.dropZoneText}>Кликни или перетащи файл</span>
                      <span className={styles.dropZoneHint}>.txt, .pdf, .md — любой текст</span>
                    </>
                  )}
                </div>
              </label>

              {/* Upload / Index */}
              <div className={styles.row}>
                <button
                  className={[styles.btnCompact, styles.btnCompactPrimary].join(" ")}
                  onClick={upload}
                  disabled={!ds || !file}
                >
                  <IconUpload /> Upload
                </button>
                <button
                  className={styles.btnCompact}
                  onClick={indexDs}
                  disabled={!ds}
                >
                  Index (job)
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
    </div>
  );
}
