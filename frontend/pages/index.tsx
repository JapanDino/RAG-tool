import React, { useState } from "react";
import JobStatus from "../components/JobStatus";

export default function Home() {
  const [name, setName] = useState("");
  const [ds, setDs] = useState<number | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [lastJob, setLastJob] = useState<number | undefined>();
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

  return (
    <div style={{maxWidth:720, margin:"40px auto", fontFamily:"sans-serif"}}>
      <h1>RAG Bloom MVP</h1>
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
