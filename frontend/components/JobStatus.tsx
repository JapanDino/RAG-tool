import React, { useEffect, useState } from "react";

type Props = { jobId: number; apiBase?: string; intervalMs?: number };

export default function JobStatus({
  jobId,
  apiBase = "http://localhost:8000",
  intervalMs = 1500,
}: Props) {
  const [state, setState] = useState<any>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await fetch(`${apiBase}/jobs/${jobId}/state`);
        const j = await r.json();
        if (!cancelled) setState(j);
      } catch {}
    };
    tick();
    const t = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [jobId, apiBase, intervalMs]);

  if (!state) return <div>job {jobId}: loading...</div>;
  const c = state.celery || {};
  return (
    <div style={{ fontFamily: "monospace", fontSize: 12 }}>
      <div>job: {jobId}</div>
      <div>status: {state.status}</div>
      {state.task_id && <div>task_id: {state.task_id}</div>}
      {c && c.state && <div>celery: {c.state} (ready={String(c.ready)})</div>}
    </div>
  );
}
