import React, { useEffect, useState } from "react";
import JobStatus from "../components/JobStatus";

export default function Home() {
  const [activeTab, setActiveTab] = useState<"analyze" | "graph">("analyze");
  const [name, setName] = useState("");
  const [ds, setDs] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [lastJob, setLastJob] = useState<number | undefined>();
  const [analysisText, setAnalysisText] = useState("");
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [edgeThreshold, setEdgeThreshold] = useState(0.2);
  const [maxEdges, setMaxEdges] = useState(50);
  const [taxonomyLevels, setTaxonomyLevels] = useState<any[]>([]);
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null);
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
  const runAnalyze = async () => {
    if (!analysisText.trim()) return;
    setAnalysisError(null);
    setAnalysisResult(null);
    try {
      const r = await fetch(`${api}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: analysisText,
          edge_threshold: edgeThreshold,
          max_edges: maxEdges,
        }),
      });
      const j = await r.json();
      setAnalysisResult(j);
    } catch (e) {
      setAnalysisError("Ошибка анализа текста.");
    }
  };

  useEffect(() => {
    const loadTaxonomy = async () => {
      try {
        const r = await fetch(`${api}/taxonomy`);
        const j = await r.json();
        setTaxonomyLevels(j.levels || []);
      } catch (e) {
        setTaxonomyError("Не удалось загрузить таксономию.");
      }
    };
    loadTaxonomy();
  }, [api]);

  return (
    <div style={{maxWidth:720, margin:"40px auto", fontFamily:"sans-serif"}}>
      <h1>RAG Bloom MVP</h1>
      <section style={{ marginBottom: 24, padding: 12, border: "1px solid #eee" }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            onClick={() => setActiveTab("analyze")}
            style={{
              fontWeight: activeTab === "analyze" ? "bold" : "normal",
            }}
          >
            Анализ контента
          </button>
          <button
            onClick={() => setActiveTab("graph")}
            style={{
              fontWeight: activeTab === "graph" ? "bold" : "normal",
            }}
          >
            Граф знаний
          </button>
        </div>
        {activeTab === "analyze" && (
          <>
            <h2 style={{ marginTop: 0 }}>Анализ контента</h2>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                Порог схожести
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={edgeThreshold}
                  onChange={(e) => setEdgeThreshold(Number(e.target.value))}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                Макс. связей
                <input
                  type="number"
                  min="0"
                  max="200"
                  value={maxEdges}
                  onChange={(e) => setMaxEdges(Number(e.target.value))}
                />
              </label>
            </div>
            <textarea
              placeholder="Вставьте образовательный текст для анализа"
              value={analysisText}
              onChange={(e) => setAnalysisText(e.target.value)}
              rows={6}
              style={{ width: "100%", marginBottom: 8 }}
            />
            <button onClick={runAnalyze} disabled={!analysisText.trim()}>
              Запустить анализ
            </button>
            {analysisError && (
              <div style={{ marginTop: 8, color: "#b91c1c" }}>
                {analysisError}
              </div>
            )}
            {analysisResult && (
              <div style={{ marginTop: 12 }}>
                <div>Узлы: {analysisResult.total}</div>
                <div>Связи: {analysisResult.edges?.length ?? 0}</div>
                <ul>
                  {analysisResult.items?.map((item: any) => (
                    <li key={item.idx}>
                      <strong>#{item.idx}</strong> {item.text}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
        {activeTab === "graph" && (
          <>
            <h2 style={{ marginTop: 0 }}>Граф знаний</h2>
            {taxonomyError && (
              <div style={{ marginBottom: 8, color: "#b91c1c" }}>
                {taxonomyError}
              </div>
            )}
            {taxonomyLevels.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  marginBottom: 12,
                }}
              >
                {taxonomyLevels.map((level) => (
                  <span
                    key={level.level}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "4px 8px",
                      border: "1px solid #e5e7eb",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  >
                    <span
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: level.color,
                        display: "inline-block",
                      }}
                    />
                    {level.label}
                  </span>
                ))}
              </div>
            )}
            {analysisResult ? (
              <div>
                <div>Узлы: {analysisResult.total}</div>
                <div>Связи: {analysisResult.edges?.length ?? 0}</div>
                <ul>
                  {analysisResult.edges?.map((edge: any, idx: number) => (
                    <li key={`${edge.source}-${edge.target}-${idx}`}>
                      {edge.source} → {edge.target} (вес {edge.weight})
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div>Сначала запустите анализ текста.</div>
            )}
          </>
        )}
      </section>
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
  );
}
