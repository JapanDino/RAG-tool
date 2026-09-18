import { useCallback, useEffect, useState } from "react";

import styles from "../styles/agent-model-readiness.module.css";

type RuntimeCounts = {
  total: number;
  succeeded: number;
  fallback: number;
  failed: number;
  p95_latency_ms: number | null;
};

type AgentModelReadiness = {
  schema_version: 1;
  state:
    | "disabled"
    | "setup_required"
    | "misconfigured"
    | "configured"
    | "degraded"
    | "ready";
  available: boolean;
  label: string;
  detail: string;
  recovery_action:
    | "configure_model_host"
    | "check_model_host"
    | "wait_and_retry"
    | null;
  window_minutes: 30;
  counts: RuntimeCounts;
  last_invocation_at: string | null;
};

type Props = {
  organizationId: number;
  identity: string;
  revision?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const ACTION_COPY: Record<NonNullable<AgentModelReadiness["recovery_action"]>, string> = {
  configure_model_host: "Передайте настройки школьного AI-сервиса системному администратору.",
  check_model_host: "Проверьте доступность школьного AI-сервиса.",
  wait_and_retry: "Повторите проверку после восстановления школьного AI-сервиса.",
};

function formatLastCheck(value: string | null) {
  if (!value) return "Запусков ещё не было";
  return `Последний запуск ${new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))}`;
}

function formatObservedAt(value: string | null) {
  if (!value) return "время неизвестно";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function AgentModelReadinessPanel({
  organizationId,
  identity,
  revision = 0,
}: Props) {
  const [readiness, setReadiness] = useState<AgentModelReadiness | null>(null);
  const [observedAt, setObservedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${API_BASE}/organizations/${organizationId}/agent-model/readiness`,
        {
          headers: { "X-Dev-User": identity },
          cache: "no-store",
        }
      );
      if (!response.ok) throw new Error(`status ${response.status}`);
      setReadiness((await response.json()) as AgentModelReadiness);
      setObservedAt(new Date().toISOString());
    } catch {
      setError(
        "Состояние агента не загрузилось. Подключение Canvas и работа курсов не затронуты."
      );
    } finally {
      setLoading(false);
    }
  }, [identity, organizationId]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  if (loading && !readiness) {
    return (
      <section className={styles.panel} aria-busy="true" aria-label="Готовность AI-агента">
        <div className={styles.loadingMark} aria-hidden="true" />
        <div>
          <span className={styles.kicker}>AI-агент школы</span>
          <h2>Загружаем последнее состояние AI-функций…</h2>
          <p>Canvas продолжает работать независимо от этой проверки.</p>
        </div>
      </section>
    );
  }

  if (error && !readiness) {
    return (
      <section className={`${styles.panel} ${styles.errorPanel}`} aria-labelledby="agent-model-title">
        <div>
          <span className={styles.kicker}>AI-агент школы</span>
          <h2 id="agent-model-title">Проверка временно недоступна</h2>
          <p>{error}</p>
        </div>
        <button type="button" onClick={() => void load()}>
          Проверить снова
        </button>
      </section>
    );
  }

  if (!readiness) return null;

  const tone = readiness.available
    ? readiness.state === "ready"
      ? "ready"
      : "attention"
    : readiness.state === "disabled"
      ? "quiet"
      : "blocked";
  return (
    <section className={styles.panel} aria-labelledby="agent-model-title">
      <div className={styles.headingRow}>
        <div>
          <span className={styles.kicker}>AI-агент школы · контроль администратора</span>
          <h2 id="agent-model-title">Готовность AI-функций в Canvas</h2>
        </div>
        <span className={`${styles.statusBadge} ${styles[tone]}`}>
          <i aria-hidden="true" />
          {readiness.label}
        </span>
      </div>

      <div className={styles.route} role="img" aria-label={`Курс Canvas, AI-помощник, школьный AI-сервис: ${readiness.label}`}>
        <div className={styles.routeNode}>
          <span className={styles.nodeIcon}>C</span>
          <strong>Курс Canvas</strong>
          <small>контекст и роль</small>
        </div>
        <span className={styles.routeLine} aria-hidden="true"><i /></span>
        <div className={`${styles.routeNode} ${styles.agentNode}`}>
          <span className={styles.nodeIcon}>A</span>
          <strong>AI-помощник</strong>
          <small>проверяет границы</small>
        </div>
        <span className={`${styles.routeLine} ${
          readiness.state === "ready"
            ? styles.connectedLine
            : readiness.state === "degraded"
              ? styles.degradedLine
              : readiness.state === "configured"
                ? styles.pendingLine
                : styles.stoppedLine
        }`} aria-hidden="true"><i /></span>
        <div className={`${styles.routeNode} ${styles.modelNode}`}>
          <span className={styles.nodeIcon}>M</span>
          <strong>Школьный AI-сервис</strong>
          <small>защищённый доступ</small>
        </div>
      </div>

      <div className={styles.summaryGrid}>
        <div className={styles.explanation}>
          <strong>{readiness.detail}</strong>
          <p>
            {readiness.recovery_action
              ? ACTION_COPY[readiness.recovery_action]
              : "AI-помощник доступен в разрешённых сценариях Canvas."}
          </p>
        </div>
        <dl className={styles.metrics} aria-label={`Работа модели за ${readiness.window_minutes} минут`}>
          <div>
            <dt>Успешно</dt>
            <dd>{readiness.counts.succeeded}</dd>
          </div>
          <div>
            <dt>Без AI-ответа</dt>
            <dd>{readiness.counts.fallback}</dd>
          </div>
          <div>
            <dt>Не выполнено</dt>
            <dd>{readiness.counts.failed}</dd>
          </div>
          <div>
            <dt>95% ответов быстрее</dt>
            <dd>{readiness.counts.p95_latency_ms === null ? "—" : `${readiness.counts.p95_latency_ms} мс`}</dd>
          </div>
        </dl>
      </div>

      {error && (
        <div className={styles.staleNotice} role="alert">
          <div>
            <strong>Показаны предыдущие данные</strong>
            <span>
              {error} Последнее успешное обновление: {formatObservedAt(observedAt)}.
            </span>
          </div>
          <button type="button" onClick={() => void load()} disabled={loading}>
            {loading ? "Проверяем снова…" : "Проверить снова"}
          </button>
        </div>
      )}

      <footer className={styles.footer}>
        <span>{formatLastCheck(readiness.last_invocation_at)}</span>
        <span>Только агрегаты за {readiness.window_minutes} минут · эта статистика не содержит текстов диалогов</span>
      </footer>
    </section>
  );
}
