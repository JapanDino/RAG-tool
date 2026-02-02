import React, { useMemo, useState } from "react";
import JobStatus from "../components/JobStatus";

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
};

type GraphEdge = {
  from_id: number;
  to_id: number;
  weight: number;
};

const getSortedLevels = (probs: number[]) =>
  BLOOM_LEVELS.map((lvl, idx) => ({ lvl, prob: probs[idx] }))
    .sort((a, b) => b.prob - a.prob);

export default function Home() {
  const [name, setName] = useState("");
  const [ds, setDs] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [lastJob, setLastJob] = useState<number | undefined>();
  const [activeTab, setActiveTab] = useState<"analysis" | "graph">("analysis");
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
  const api = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  const createDataset = async () => {
    const r = await fetch(`${api}/datasets`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name})});
    const j = await r.json(); setDs(j.id);
  };
  const upload = async () => {
    if(!ds || !file) return;
    const fd = new FormData(); fd.append("file", file);
    await fetch(`${api}/datasets/${ds}/documents`, {method:"POST", body:fd});
  };
  const indexDs = async () => {
    if (!ds) return;
    const r = await fetch(`${api}/datasets/${ds}/index`, { method: "POST" });
    const j = await r.json();
    setLastJob(j.job_id);
  };
  const annotate = async (level: string) => {
    if (!ds) return;
    const r = await fetch(`${api}/annotate/datasets/${ds}?level=${level}`, {
      method: "POST",
    });
    const j = await r.json();
    setLastJob(j.job_id);
  };
  const exportJsonl = () => { if(!ds) return; window.open(`${api}/export/datasets/${ds}?format=jsonl`, "_blank"); };

  const analyzeText = async () => {
    if (!textInput.trim() || !ds) return;
    setNodesStatus("Анализируем текст...");
    const resp = await fetch(`${api}/analyze/content`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textInput, dataset_id: ds }),
    });
    const json = await resp.json();
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
    const resp = await fetch(`${api}/nodes?${params.toString()}`);
    const json = await resp.json();
    const items: AnalyzeNode[] = json.items || [];
    setNodes(items);
    setNodesStatus(items.length ? `Загружено узлов: ${items.length}` : "В БД нет узлов");
  };

  const loadGraph = async () => {
    if (!ds) return;
    const params = new URLSearchParams({
      dataset_id: String(ds),
      top_k: String(graphTopK),
      min_score: String(graphMinScore),
      include_cooccurrence: graphIncludeCo ? "true" : "false",
      limit_nodes: String(graphLimitNodes),
    });
    const resp = await fetch(`${api}/graph?${params.toString()}`);
    const json = await resp.json();
    setGraphNodesData(json.nodes || []);
    setGraphEdgesData(json.edges || []);
  };

  const filteredNodes = useMemo(
    () =>
      graphNodesData.filter((n) => n.top_levels.some((lvl) => filters[lvl])),
    [graphNodesData, filters]
  );

  const graphNodes = useMemo(() => {
    const r = 220;
    const center = { x: 300, y: 260 };
    return filteredNodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(filteredNodes.length, 1);
      return {
        ...n,
        x: center.x + r * Math.cos(angle),
        y: center.y + r * Math.sin(angle),
      };
    });
  }, [filteredNodes]);

  const graphEdges = useMemo(() => {
    const nodeIds = new Set(graphNodes.map((n) => n.id));
    return graphEdgesData
      .filter((e) => nodeIds.has(e.from_id) && nodeIds.has(e.to_id))
      .map((e) => ({ from: e.from_id, to: e.to_id, weight: e.weight }));
  }, [graphEdgesData, graphNodes]);

  return (
    <div style={{maxWidth:720, margin:"40px auto", fontFamily:"sans-serif"}}>
      <h1>RAG Bloom MVP</h1>
      <div style={{display:"flex", gap:12, marginBottom: 16}}>
        <button onClick={() => setActiveTab("analysis")} disabled={activeTab === "analysis"}>
          Анализ контента
        </button>
        <button onClick={() => setActiveTab("graph")} disabled={activeTab === "graph"}>
          Граф знаний
        </button>
      </div>

      {activeTab === "analysis" && (
        <div style={{display:"grid", gap:12}}>
          <textarea
            rows={6}
            placeholder="Вставьте текст для анализа"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
          />
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button onClick={analyzeText} disabled={!ds || !textInput.trim()}>
              Анализировать
            </button>
            <button onClick={loadNodesFromDb} disabled={!ds}>
              Загрузить из БД
            </button>
            <input
              type="file"
              accept=".txt"
              onChange={(e) => loadTextFile(e.target.files?.[0] || null)}
            />
            <button onClick={exportNodesJson} disabled={!nodes.length}>
              Export JSON
            </button>
            <button onClick={exportNodesCsv} disabled={!nodes.length}>
              Export CSV
            </button>
          </div>
          {nodesStatus && <div style={{ fontSize: 12, color: "#666" }}>{nodesStatus}</div>}

          {nodes.length > 0 && (
            <div style={{ border: "1px solid #ddd", padding: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Узлы знаний</div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Узел</th>
                    <th style={{ textAlign: "left" }}>Контекст</th>
                    <th style={{ textAlign: "left" }}>Top уровни</th>
                    <th style={{ textAlign: "left" }}>Вероятности</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((n) => (
                    <tr key={n.id}>
                      <td style={{ padding: "6px 4px" }}>{n.title}</td>
                      <td style={{ padding: "6px 4px", fontSize: 12 }}>
                        {n.context_text}
                      </td>
                      <td style={{ padding: "6px 4px" }}>
                        {n.top_levels.map((lvl) => LEVEL_LABELS[lvl]).join(", ")}
                      </td>
                      <td style={{ padding: "6px 4px", fontSize: 12 }}>
                        {getSortedLevels(n.prob_vector)
                          .map((p) => `${LEVEL_LABELS[p.lvl]}: ${p.prob}`)
                          .join(" | ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ borderTop: "1px solid #eee", paddingTop: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Служебные операции (dataset)</div>
            <div style={{display:"grid", gap:12}}>
              <input placeholder="dataset name" value={name} onChange={e=>setName(e.target.value)} />
              <button onClick={createDataset}>Create dataset</button>
              <div>dataset id: {ds ?? "-"}</div>
              <input
                type="number"
                placeholder="dataset id"
                value={ds ?? ""}
                onChange={(e) => setDs(e.target.value ? Number(e.target.value) : undefined)}
              />
              <input type="file" onChange={e=>setFile(e.target.files?.[0] || null)} />
              <button onClick={upload} disabled={!ds || !file}>Upload document</button>
              <button onClick={indexDs} disabled={!ds}>Index</button>
              <div>
                <button onClick={() => annotate("apply")} disabled={!ds}>
                  Annotate: apply
                </button>
                <button
                  onClick={() => annotate("analyze")}
                  disabled={!ds}
                  style={{ marginLeft: 8 }}
                >
                  Annotate: analyze
                </button>
              </div>
              <button onClick={exportJsonl} disabled={!ds}>Export JSONL</button>
            </div>
            {lastJob && (
              <div style={{ marginTop: 16, padding: 8, border: "1px solid #ddd" }}>
                <JobStatus jobId={lastJob} apiBase={api} />
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === "graph" && (
        <div style={{ display: "grid", gap: 12 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            {BLOOM_LEVELS.map((lvl) => (
              <label key={lvl} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={filters[lvl]}
                  onChange={(e) =>
                    setFilters({ ...filters, [lvl]: e.target.checked })
                  }
                />
                <span style={{ color: LEVEL_COLORS[lvl] }}>{LEVEL_LABELS[lvl]}</span>
              </label>
            ))}
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              Порог градиента
              <input
                type="number"
                step="0.1"
                min="0"
                max="1"
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                style={{ width: 60 }}
              />
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              Top‑K
              <input
                type="number"
                min="1"
                max="10"
                value={graphTopK}
                onChange={(e) => setGraphTopK(Number(e.target.value))}
                style={{ width: 60 }}
              />
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              Min score
              <input
                type="number"
                step="0.1"
                min="0"
                max="1"
                value={graphMinScore}
                onChange={(e) => setGraphMinScore(Number(e.target.value))}
                style={{ width: 60 }}
              />
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={graphIncludeCo}
                onChange={(e) => setGraphIncludeCo(e.target.checked)}
              />
              Co‑occurrence
            </label>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              Limit nodes
              <input
                type="number"
                min="10"
                max="2000"
                value={graphLimitNodes}
                onChange={(e) => setGraphLimitNodes(Number(e.target.value))}
                style={{ width: 80 }}
              />
            </label>
            <button onClick={loadGraph} disabled={!ds}>
              Загрузить граф
            </button>
          </div>

          <div style={{ border: "1px solid #ddd", padding: 8, position: "relative" }}>
            <svg width={640} height={520}>
              <defs>
                {graphNodes.map((n) => {
                  const sorted = getSortedLevels(n.prob_vector);
                  const primary = sorted[0];
                  const secondary = sorted[1];
                  if (!secondary || secondary.prob < threshold) return null;
                  const gradientId = `grad-${n.id}`;
                  return (
                    <linearGradient key={gradientId} id={gradientId} x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor={LEVEL_COLORS[primary.lvl]} />
                      <stop offset="100%" stopColor={LEVEL_COLORS[secondary.lvl]} />
                    </linearGradient>
                  );
                })}
              </defs>

              {graphEdges.map((e, idx) => {
                const from = graphNodes.find((n) => n.id === e.from);
                const to = graphNodes.find((n) => n.id === e.to);
                if (!from || !to) return null;
                return (
                  <line
                    key={`edge-${idx}`}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke="#bbb"
                  />
                );
              })}

              {graphNodes.map((n) => {
                const sorted = getSortedLevels(n.prob_vector);
                const primary = sorted[0];
                const secondary = sorted[1];
                const gradientId =
                  secondary && secondary.prob >= threshold ? `url(#grad-${n.id})` : LEVEL_COLORS[primary.lvl];
                return (
                  <g
                    key={n.id}
                    onMouseEnter={() => setHoveredNode(n)}
                    onMouseLeave={() => setHoveredNode(null)}
                  >
                    <circle cx={n.x} cy={n.y} r={18} fill={gradientId} />
                    <text x={n.x} y={n.y + 32} textAnchor="middle" fontSize="10">
                      {n.title}
                    </text>
                  </g>
                );
              })}
            </svg>
            {hoveredNode && (
              <div
                style={{
                  position: "absolute",
                  top: 12,
                  right: 12,
                  width: 220,
                  border: "1px solid #ddd",
                  background: "#fff",
                  padding: 8,
                  fontSize: 12,
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 6 }}>{hoveredNode.title}</div>
                <div style={{ marginBottom: 6 }}>{hoveredNode.context_text}</div>
                <div>
                  {getSortedLevels(hoveredNode.prob_vector)
                    .map((p) => `${LEVEL_LABELS[p.lvl]}: ${p.prob}`)
                    .join(" | ")}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
