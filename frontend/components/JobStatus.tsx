import React, { useEffect, useState } from "react";
import styles from "../styles/jobstatus.module.css";

type Props = { jobId: number; apiBase?: string; intervalMs?: number };

export default function JobStatus({
  jobId,
  apiBase = "http://localhost:8000",
  intervalMs = 1500,
}: Props) {
  const [state, setState] = useState<any>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await fetch(`${apiBase}/jobs/${jobId}/state`);
        const j = await r.json();
        if (!cancelled) {
          setState(j);
          setFailed(false);
        }
      } catch {
        if (!cancelled) setFailed(true);
      }
    };
    tick();
    const t = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [jobId, apiBase, intervalMs]);

  if (!state) {
    return (
      <div className={styles.wrap}>
        <div className={styles.top}>
          <span className={[styles.badge, styles.mono].join(" ")}>
            <span className={[styles.dot, failed ? styles.dotBad : ""].join(" ")} />
            job <span className={styles.mono}>{jobId}</span>
          </span>
          <span className={styles.badge}>{failed ? "API недоступен" : "загрузка..."}</span>
        </div>
      </div>
    );
  }

  const c = state.celery || {};
  const status = String(state.status || "unknown");
  const dotClass =
    status === "done"
      ? styles.dotOk
      : status === "failed"
        ? styles.dotBad
        : styles.dotWarn;

  return (
    <div className={styles.wrap}>
      <div className={styles.top}>
        <span className={[styles.badge, styles.mono].join(" ")}>
          <span className={[styles.dot, dotClass].join(" ")} />
          job <span className={styles.mono}>{jobId}</span>
        </span>
        <span className={[styles.badge, styles.mono].join(" ")}>status {status}</span>
      </div>

      <div className={styles.kv}>
        <div className={styles.k}>task_id</div>
        <div className={styles.mono}>{state.task_id || "-"}</div>
        <div className={styles.k}>celery</div>
        <div className={styles.mono}>{c?.state ? `${c.state} (ready=${String(c.ready)})` : "-"}</div>
      </div>
    </div>
  );
}
