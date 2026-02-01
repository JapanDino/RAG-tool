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

type ExtractedNode = {
  title: string;
  context_snippet: string;
  frequency: number;
};

type ClassifiedNode = {
  title: string;
  prob_vector: number[];
  top_levels: BloomLevel[];
};

type NodeView = ExtractedNode & ClassifiedNode & { id: number };

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
  const [nodes, setNodes] = useState<NodeView[]>([]);
  const [threshold, setThreshold] = useState(0.3);
  const [filters, setFilters] = useState<Record<BloomLevel, boolean>>({
    remember: true,
    understand: true,
    apply: true,
    analyze: true,
    evaluate: true,
    create: true,
  });
  const [hoveredNode, setHoveredNode] = useState<NodeView | null>(null);
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
    if (!textInput.trim()) return;
    const extractResp = await fetch(`${api}/analyze/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textInput }),
    });
    const extractJson = await extractResp.json();
    const extracted: ExtractedNode[] = extractJson.nodes || [];

    const classifyResp = await fetch(`${api}/analyze/classify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nodes: extracted.map((n) => ({
          title: n.title,
          context_snippet: n.context_snippet,
        })),
      }),
    });
    const classifyJson = await classifyResp.json();
    const classified: ClassifiedNode[] = classifyJson.nodes || [];

    const combined = extracted.map((node, idx) => ({
      ...node,
      ...classified[idx],
      id: idx + 1,
    }));
    setNodes(combined);
  };

  const filteredNodes = useMemo(
    () =>
      nodes.filter((n) => n.top_levels.some((lvl) => filters[lvl])),
    [nodes, filters]
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
    const edges: { from: number; to: number }[] = [];
    for (let i = 0; i < graphNodes.length - 1; i += 1) {
      edges.push({ from: graphNodes[i].id, to: graphNodes[i + 1].id });
    }
    return edges;
  }, [graphNodes]);

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
          <button onClick={analyzeText}>Анализировать</button>

          {nodes.length > 0 && (
            <div style={{ border: "1px solid #ddd", padding: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Узлы знаний</div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Узел</th>
                    <th style={{ textAlign: "left" }}>Top уровни</th>
                    <th style={{ textAlign: "left" }}>Вероятности</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.map((n) => (
                    <tr key={n.id}>
                      <td style={{ padding: "6px 4px" }}>{n.title}</td>
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
                <div style={{ marginBottom: 6 }}>{hoveredNode.context_snippet}</div>
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
