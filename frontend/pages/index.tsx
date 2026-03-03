import React, { useMemo, useState, useEffect } from "react";
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

const LEVEL_COLORS: Record<BloomLevel, string> = {
  remember: "#4e79a7",
  understand: "#59a14f",
  apply: "#f28e2b",
  analyze: "#af7aa1",
  evaluate: "#e15759",
  create: "#76b7b2",
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

export default function Home() {
  const [name, setName] = useState("");
  const [ds, setDs] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [lastJob, setLastJob] = useState<number | undefined>();
  const [activeTab, setActiveTab] = useState<"analysis" | "graph" | "labeling">("analysis");
  const [textInput, setTextInput] = useState("");
  const [nodes, setNodes] = useState<AnalyzeNode[]>([]);
  const [nodesStatus, setNodesStatus] = useState<string | null>(null);
  const [graphNodesData, setGraphNodesData] = useState<AnalyzeNode[]>([]);
  const [graphEdgesData, setGraphEdgesData] = useState<GraphEdge[]>([]);
  const [threshold, setThreshold] = useState(0.3);
  const [graphTopK, setGraphTopK] = useState(3);
  const [graphMinScore, setGraphMinScore] = useState(0.6);
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
    // If someone set NEXT_PUBLIC_API_BASE=http://backend:8000 in docker-compose,
    // the browser won't resolve "backend". Auto-fix for local usage.
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
    if(!ds || !file) return;
    const fd = new FormData(); fd.append("file", file);
    try {
      setError(null);
      const r = await fetch(`${apiBase}/datasets/${ds}/documents`, {method:"POST", body:fd});
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
  const exportJsonl = () => { if(!ds) return; window.open(`${apiBase}/export/datasets/${ds}?format=jsonl`, "_blank"); };

  const analyzeText = async () => {
    if (!textInput.trim() || !ds) return;
    setNodesStatus("Анализируем текст...");
    const json = await apiFetchJson(`/analyze/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textInput, dataset_id: ds }),
    });
    if (!json) {
      setNodesStatus("Ошибка анализа (см. сообщение сверху).");
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
      setNodesStatus("Ошибка загрузки узлов (см. сообщение сверху).");
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
    const params = new URLSearchParams({
      annotator,
      limit: "80",
    });
    const json = await apiFetchJson(`/datasets/${ds}/labeling/queue?${params.toString()}`);
    if (!json) {
      setLabelQueueStatus("Ошибка загрузки очереди (см. сообщение сверху).");
      return;
    }
    const items = (json.items || []) as AnalyzeNode[];
    setLabelQueue(items);
    setLabelProgress({ total: Number(json.total || 0), labeled: Number(json.labeled || 0) });
    setLabelQueueStatus(items.length ? `В очереди: ${items.length}` : "Очередь пуста");
    // reset current labels
    setCurrentLabels({
      remember: false,
      understand: false,
      apply: false,
      analyze: false,
      evaluate: false,
      create: false,
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
      remember: false,
      understand: false,
      apply: false,
      analyze: false,
      evaluate: false,
      create: false,
    });
    setLabelProgress((p) => (p ? { ...p, labeled: p.labeled + 1 } : p));
  };

  useEffect(() => {
    if (activeTab !== "labeling") return;
    const handler = (e: KeyboardEvent) => {
      const map: Record<string, BloomLevel> = {
        "1": "remember",
        "2": "understand",
        "3": "apply",
        "4": "analyze",
        "5": "evaluate",
        "6": "create",
      };
      const lvl = map[e.key];
      if (!lvl) return;
      setCurrentLabels((s) => ({ ...s, [lvl]: !s[lvl] }));
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTab]);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.brand}>
            <h1 className={styles.title}>Bloom RAG Studio</h1>
            <p className={styles.subtitle}>
              RAG-разметка узлов знаний с multi-label таксономией Блума, графом и ручной разметкой 100+
            </p>
          </div>
          <div className={styles.metaRow}>
            <div className={styles.pill} title="Доступность API">
              <span
                className={[
                  styles.dot,
                  apiStatus === "ok" ? styles.dotOk : "",
                  apiStatus === "down" ? styles.dotBad : "",
                ].join(" ")}
              />
              <span>API</span>
              <span className={styles.kbd}>{apiStatus}</span>
            </div>
            <div className={styles.pill} title="Текущий dataset_id">
              <span>dataset</span>
              <span className={styles.kbd}>{ds ?? "-"}</span>
            </div>
            {lastJob && (
              <div className={styles.pill} title="Последняя задача">
                <span>job</span>
                <span className={styles.kbd}>{lastJob}</span>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className={styles.shell}>
        <nav className={styles.nav}>
          <div className={styles.navCard}>
            <button
              className={[styles.navBtn, activeTab === "analysis" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("analysis")}
            >
              <span>Анализ</span>
              <span className={styles.navHint}>content</span>
            </button>
            <button
              className={[styles.navBtn, activeTab === "graph" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("graph")}
            >
              <span>Граф</span>
              <span className={styles.navHint}>cyto</span>
            </button>
            <button
              className={[styles.navBtn, activeTab === "labeling" ? styles.navBtnActive : ""].join(" ")}
              onClick={() => setActiveTab("labeling")}
            >
              <span>Разметка</span>
              <span className={styles.navHint}>100+</span>
            </button>
          </div>
        </nav>

        <main className={styles.main}>
          {error && <div className={styles.error}>{error}</div>}

          {activeTab === "analysis" && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Анализ контента</h2>
              <p className={styles.cardNote}>
                Вставь текст, получи узлы знаний, multi-label уровни Блума и объяснение. Сохраняется в БД как RAG-элементы.
              </p>

              <div className={styles.grid}>
                <label className={styles.fieldLabel}>
                  Текст для анализа
                  <textarea
                    className={styles.textarea}
                    placeholder="Вставьте текст для анализа (RU)"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                  />
                </label>

                <div className={styles.btnRow}>
                  <button className={[styles.btn, styles.btnPrimary].join(" ")} onClick={analyzeText} disabled={!ds || !textInput.trim()}>
                    Анализировать
                  </button>
                  <button className={styles.btn} onClick={loadNodesFromDb} disabled={!ds}>
                    Узлы из БД
                  </button>
                  <label className={styles.btn}>
                    <input
                      type="file"
                      accept=".txt"
                      style={{ display: "none" }}
                      onChange={(e) => loadTextFile(e.target.files?.[0] || null)}
                    />
                    Загрузить .txt в поле
                  </label>
                  <button className={styles.btn} onClick={exportNodesJson} disabled={!nodes.length}>
                    Export JSON
                  </button>
                  <button className={styles.btn} onClick={exportNodesCsv} disabled={!nodes.length}>
                    Export CSV
                  </button>
                </div>

                {nodesStatus && <div className={styles.muted}>{nodesStatus}</div>}

                {nodes.length > 0 && (
                  <div className={styles.tableWrap}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th>Узел</th>
                          <th>Контекст</th>
                          <th>Уровни</th>
                          <th>Вероятности</th>
                        </tr>
                      </thead>
                      <tbody>
                        {nodes.map((n) => {
                          const sorted = getSortedLevels(n.prob_vector);
                          const primary = sorted[0]?.lvl ?? "remember";
                          return (
                            <tr key={n.id}>
                              <td>
                                <div style={{ display: "grid", gap: 6 }}>
                                  <div style={{ fontWeight: 750 }}>{n.title}</div>
                                  <div className={styles.muted}>
                                    id: <span className={styles.kbd}>{n.id}</span>{" "}
                                    {typeof n.frequency === "number" ? (
                                      <>
                                        freq: <span className={styles.kbd}>{n.frequency}</span>
                                      </>
                                    ) : null}
                                  </div>
                                </div>
                              </td>
                              <td style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.35 }}>
                                {n.context_text}
                                {n.rationale ? (
                                  <div style={{ marginTop: 8 }}>
                                    <span className={styles.kbd}>rationale</span> {n.rationale}
                                  </div>
                                ) : null}
                              </td>
                              <td>
                                <div className={styles.row}>
                                  {n.top_levels.map((lvl) => (
                                    <span key={lvl} className={styles.badge} title={lvl}>
                                      <span
                                        className={styles.badgeSwatch}
                                        style={{ background: LEVEL_COLORS[lvl] }}
                                      />
                                      {LEVEL_LABELS[lvl]}
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td style={{ fontSize: 12, color: "var(--muted)" }}>
                                <div className={styles.grid}>
                                  <span className={styles.badge} title={`primary=${primary}`}>
                                    <span className={styles.badgeSwatch} style={{ background: LEVEL_COLORS[primary] }} />
                                    primary: {LEVEL_LABELS[primary]}
                                  </span>
                                  <div style={{ fontFamily: "var(--font-mono)" }}>
                                    {sorted
                                      .slice(0, 3)
                                      .map((p) => `${LEVEL_LABELS[p.lvl]}=${p.prob.toFixed(2)}`)
                                      .join("  ")}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "graph" && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Граф знаний</h2>
              <p className={styles.cardNote}>
                Узлы цветом/формой по уровню Блума. Второй уровень подсвечен обводкой. Рёбра из БД (после rebuild).
              </p>

              <div className={styles.grid}>
                <div className={styles.row}>
                  {BLOOM_LEVELS.map((lvl) => (
                    <label key={lvl} className={styles.badge}>
                      <input
                        type="checkbox"
                        checked={filters[lvl]}
                        onChange={(e) => setFilters({ ...filters, [lvl]: e.target.checked })}
                      />
                      <span className={styles.badgeSwatch} style={{ background: LEVEL_COLORS[lvl] }} />
                      {LEVEL_LABELS[lvl]}
                    </label>
                  ))}
                </div>

                <div className={styles.row}>
                  <label className={styles.fieldLabel} style={{ maxWidth: 160 }}>
                    Порог 2-го уровня
                    <input
                      className={styles.input}
                      type="number"
                      step="0.05"
                      min="0"
                      max="1"
                      value={threshold}
                      onChange={(e) => setThreshold(Number(e.target.value))}
                    />
                  </label>
                  <label className={styles.fieldLabel} style={{ maxWidth: 120 }}>
                    Top-K
                    <input className={styles.input} type="number" min="1" max="10" value={graphTopK} onChange={(e) => setGraphTopK(Number(e.target.value))} />
                  </label>
                  <label className={styles.fieldLabel} style={{ maxWidth: 140 }}>
                    Min score
                    <input className={styles.input} type="number" step="0.05" min="0" max="1" value={graphMinScore} onChange={(e) => setGraphMinScore(Number(e.target.value))} />
                  </label>
                  <label className={styles.badge} title="Добавлять co-occurrence рёбра">
                    <input type="checkbox" checked={graphIncludeCo} onChange={(e) => setGraphIncludeCo(e.target.checked)} />
                    Co-occurrence
                  </label>
                  <label className={styles.fieldLabel} style={{ maxWidth: 160 }}>
                    Limit nodes
                    <input className={styles.input} type="number" min="10" max="2000" value={graphLimitNodes} onChange={(e) => setGraphLimitNodes(Number(e.target.value))} />
                  </label>
                </div>

                <div className={styles.btnRow}>
                  <button className={[styles.btn, styles.btnPrimary].join(" ")} onClick={loadGraph} disabled={!ds}>
                    Загрузить граф
                  </button>
                  <button className={[styles.btn, styles.btnWarn].join(" ")} onClick={rebuildGraph} disabled={!ds}>
                    Rebuild edges (job)
                  </button>
                </div>

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

                {(selectedNode || hoveredNode) && (
                  <div className={styles.card} style={{ boxShadow: "none" }}>
                    <h3 className={styles.cardTitle} style={{ marginBottom: 8 }}>
                      {(hoveredNode || selectedNode)!.title}
                    </h3>
                    <div className={styles.muted} style={{ lineHeight: 1.45 }}>
                      {(hoveredNode || selectedNode)!.context_text}
                    </div>
                    {(hoveredNode || selectedNode)!.rationale ? (
                      <div className={styles.muted} style={{ marginTop: 10 }}>
                        <span className={styles.kbd}>rationale</span> {(hoveredNode || selectedNode)!.rationale}
                      </div>
                    ) : null}
                    <div className={styles.muted} style={{ marginTop: 10, fontFamily: "var(--font-mono)" }}>
                      {getSortedLevels((hoveredNode || selectedNode)!.prob_vector)
                        .map((p) => `${LEVEL_LABELS[p.lvl]}=${p.prob.toFixed(2)}`)
                        .join("  ")}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "labeling" && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Ручная разметка (100+)</h2>
              <p className={styles.cardNote}>
                Быстрый режим: выбери уровни чекбоксами или клавишами <span className={styles.kbd}>1..6</span>, затем “Сохранить и далее”.
              </p>

              <div className={styles.grid}>
                <div className={styles.row}>
                  <label className={styles.fieldLabel} style={{ maxWidth: 240 }}>
                    Annotator
                    <input className={styles.input} value={annotator} onChange={(e) => setAnnotator(e.target.value)} />
                  </label>
                  <button className={[styles.btn, styles.btnPrimary].join(" ")} onClick={loadLabelQueue} disabled={!ds}>
                    Загрузить очередь
                  </button>
                  <button
                    className={styles.btn}
                    onClick={() => {
                      if (!ds) return;
                      window.open(
                        `${apiBase}/datasets/${ds}/labeling/export?annotator=${encodeURIComponent(annotator)}`,
                        "_blank"
                      );
                    }}
                    disabled={!ds}
                  >
                    Export JSONL
                  </button>
                  {labelProgress && (
                    <span className={styles.pill} style={{ background: "rgba(255,255,255,0.5)" }}>
                      прогресс <span className={styles.kbd}>{labelProgress.labeled}</span> /{" "}
                      <span className={styles.kbd}>{labelProgress.total}</span>
                    </span>
                  )}
                </div>

                {labelQueueStatus && <div className={styles.muted}>{labelQueueStatus}</div>}

                {labelQueue[0] ? (
                  <div className={styles.card} style={{ boxShadow: "none" }}>
                    <h3 className={styles.cardTitle} style={{ marginBottom: 6 }}>
                      {labelQueue[0].title}
                    </h3>
                    <div className={styles.muted} style={{ lineHeight: 1.45 }}>
                      {labelQueue[0].context_text}
                    </div>
                    <div className={styles.muted} style={{ marginTop: 10 }}>
                      model top: <span className={styles.kbd}>{labelQueue[0].top_levels.join(", ")}</span>{" "}
                      {labelQueue[0].rationale ? (
                        <>
                          <span className={styles.kbd}>rationale</span> {labelQueue[0].rationale}
                        </>
                      ) : null}
                    </div>

                    <div className={styles.row} style={{ marginTop: 10 }}>
                      {BLOOM_LEVELS.map((lvl, i) => (
                        <label key={lvl} className={styles.badge}>
                          <input
                            type="checkbox"
                            checked={currentLabels[lvl]}
                            onChange={(e) => setCurrentLabels({ ...currentLabels, [lvl]: e.target.checked })}
                          />
                          <span className={styles.badgeSwatch} style={{ background: LEVEL_COLORS[lvl] }} />
                          {i + 1}. {LEVEL_LABELS[lvl]}
                        </label>
                      ))}
                    </div>

                    <div className={styles.btnRow} style={{ marginTop: 10 }}>
                      <button
                        className={[styles.btn, styles.btnPrimary].join(" ")}
                        onClick={saveLabels}
                        disabled={!BLOOM_LEVELS.some((lvl) => currentLabels[lvl])}
                      >
                        Сохранить и далее
                      </button>
                      <button className={styles.btn} onClick={() => setLabelQueue((q) => q.slice(1))}>
                        Пропустить
                      </button>
                      <span className={styles.muted}>
                        подсказка: <span className={styles.kbd}>1..6</span> переключают уровни
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className={styles.muted}>Нет элементов в очереди</div>
                )}
              </div>
            </div>
          )}
        </main>

        <aside className={styles.aside}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Подключение</h2>
            <p className={styles.cardNote}>
              Если видишь <span className={styles.kbd}>Failed to fetch</span>, проверь, что API доступен и CORS разрешен.
            </p>
            <div className={styles.grid}>
              <label className={styles.fieldLabel}>
                API base
                <input className={styles.input} value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
              </label>
              <div className={styles.btnRow}>
                <button className={styles.btn} onClick={() => window.open(`${apiBase}/docs`, "_blank")}>
                  Open /docs
                </button>
                <button className={styles.btn} onClick={() => window.open(`${apiBase}/health`, "_blank")}>
                  Open /health
                </button>
                <button className={styles.btn} onClick={() => setApiBase("http://localhost:8000")}>
                  localhost:8000
                </button>
              </div>
            </div>
          </div>

          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Dataset</h2>
            <div className={styles.grid}>
              <label className={styles.fieldLabel}>
                Имя (для создания)
                <input className={styles.input} placeholder="например: demo_2026_02_10" value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <div className={styles.btnRow}>
                <button className={[styles.btn, styles.btnPrimary].join(" ")} onClick={createDataset} disabled={!name.trim()}>
                  Create
                </button>
                <button
                  className={styles.btn}
                  onClick={() => {
                    const v = prompt("Укажи dataset id");
                    if (!v) return;
                    const id = Number(v);
                    if (!Number.isFinite(id)) return;
                    setDs(id);
                  }}
                >
                  Set id
                </button>
              </div>

              <label className={styles.fieldLabel}>
                dataset id
                <input
                  className={styles.input}
                  type="number"
                  value={ds ?? ""}
                  onChange={(e) => setDs(e.target.value ? Number(e.target.value) : undefined)}
                />
              </label>

              <label className={styles.fieldLabel}>
                Документ для индексации
                <input className={styles.input} type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </label>

              <div className={styles.btnRow}>
                <button className={styles.btn} onClick={upload} disabled={!ds || !file}>
                  Upload
                </button>
                <button className={styles.btn} onClick={indexDs} disabled={!ds}>
                  Index (job)
                </button>
                <button className={styles.btn} onClick={exportJsonl} disabled={!ds}>
                  Export JSONL
                </button>
              </div>

              <div className={styles.btnRow}>
                <button className={styles.btn} onClick={() => annotate("apply")} disabled={!ds}>
                  Annotate apply
                </button>
                <button className={styles.btn} onClick={() => annotate("analyze")} disabled={!ds}>
                  Annotate analyze
                </button>
              </div>

              {lastJob && (
                <div className={styles.card} style={{ boxShadow: "none" }}>
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
