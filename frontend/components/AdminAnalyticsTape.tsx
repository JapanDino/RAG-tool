import { useCallback, useEffect, useRef, useState } from "react";

import styles from "../styles/admin-analytics-tape.module.css";

type Target = "integration" | "model";
type SegmentKind = "adoption" | "runtime" | "cost";
type SegmentState =
  | "available"
  | "attention"
  | "suppressed"
  | "no_activity"
  | "unconfigured"
  | "unavailable";
type Trend = "up" | "down" | "stable" | "not_comparable";

type AdminOrganization = {
  organization_ref: string;
};

type AnalyticsBrief = {
  mode: "admin_analytics_brief";
  organization_name: string;
  overall_state: "available" | "attention" | "partial" | "no_activity";
  headline: string;
  segments: {
    kind: SegmentKind;
    state: SegmentState;
    label: string;
    detail: string;
    current_window: string;
    comparison_window: string;
    trend: Trend;
    current_facts: string[];
    previous_facts: string[];
    action_target: Target | null;
    action_label: string | null;
  }[];
  limitations: string[];
  read_only: true;
};

type AgentAccepted = { execute_url: string };
type AgentRun = {
  status: "queued" | "routing" | "tool_running" | "completed" | "abstained" | "failed";
  user_state: { label: string };
  response: AnalyticsBrief | null;
};

type Props = {
  organizationId: number;
  organizationName: string;
  identity: string;
  revision?: number;
  onOpenTarget: (target: "registration" | "model") => void;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const KIND_LABELS: Record<SegmentKind, string> = {
  adoption: "Использование",
  runtime: "Работа AI",
  cost: "Оценка стоимости",
};
const KIND_CODES: Record<SegmentKind, string> = {
  adoption: "A / 28D",
  runtime: "R / 24H",
  cost: "C / 24H",
};
const STATE_LABELS: Record<SegmentState, string> = {
  available: "Данные доступны",
  attention: "Нужна проверка",
  suppressed: "Скрыто для приватности",
  no_activity: "Нет активности",
  unconfigured: "Не настроено",
  unavailable: "Источник недоступен",
};
const TREND_LABELS: Record<Trend, string> = {
  up: "Событий больше",
  down: "Событий меньше",
  stable: "Без изменения",
  not_comparable: "Сравнение недоступно",
};

class TapeRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, identity: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Dev-User", identity);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = "Контрольная лента временно недоступна.";
    try {
      const payload = await response.json();
      message = payload?.error?.message || message;
    } catch {
      // Fixed copy intentionally hides server and provider details.
    }
    throw new TapeRequestError(message, response.status);
  }
  return response.json();
}

function focusAndReveal(element: HTMLElement | null) {
  if (!element) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.focus({ preventScroll: true });
  element.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "center",
  });
}

export default function AdminAnalyticsTape({
  organizationId,
  organizationName,
  identity,
  revision = 0,
  onOpenTarget,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyticsBrief | null>(null);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [denied, setDenied] = useState(false);
  const resultRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setResult(null);
    setError("");
    setStale(false);
    setDenied(false);
  }, [organizationId, revision]);

  useEffect(() => {
    if (result) focusAndReveal(resultRef.current);
  }, [result]);

  useEffect(() => {
    if (error) focusAndReveal(errorRef.current);
  }, [error]);

  const run = useCallback(async () => {
    setBusy(true);
    setError("");
    setStale(false);
    setDenied(false);
    try {
      const organization = await request<AdminOrganization>(
        `/agent/v1/admin-organization?organization_id=${organizationId}`,
        identity,
      );
      const payload = {
        contract_version: "agent.v1",
        message: "Собрать контрольную ленту",
        selection: { organization_ref: organization.organization_ref },
      };
      const accepted = await request<AgentAccepted>("/agent/v1/messages", identity, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      });
      let current: AgentRun | null = null;
      for (let step = 0; step < 4; step += 1) {
        current = await request<AgentRun>(accepted.execute_url, identity, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (["completed", "abstained", "failed"].includes(current.status)) break;
      }
      if (
        current?.status !== "completed" ||
        current.response?.mode !== "admin_analytics_brief"
      ) {
        throw new TapeRequestError(
          current?.user_state.label || "Контрольная лента не завершилась.",
          current?.status === "abstained" ? 409 : 503,
        );
      }
      setResult(current.response);
    } catch (reason) {
      const changed = reason instanceof TapeRequestError && reason.status === 409;
      const accessDenied = reason instanceof TapeRequestError && reason.status === 404;
      setStale(changed);
      setDenied(accessDenied);
      setError(
        `${
          changed
            ? "События или оценочные ставки изменились. Соберите ленту заново."
            : accessDenied
              ? "Доступ к организации больше не подтверждён. Вернитесь в рабочее пространство."
              : reason instanceof Error
                ? reason.message
                : "Контрольная лента временно недоступна."
        } Canvas, AI-хост и настройки организации не изменены.`,
      );
    } finally {
      setBusy(false);
    }
  }, [identity, organizationId]);

  const openTarget = (target: Target) => {
    onOpenTarget(target === "integration" ? "registration" : "model");
  };

  return (
    <section className={styles.tapeShell} aria-labelledby="admin-analytics-title">
      <header className={styles.header}>
        <div>
          <span>Операционный журнал · только агрегаты</span>
          <h2 id="admin-analytics-title">Используют ли сервис — и выдерживает ли AI нагрузку</h2>
          <p>
            Сравнение двух равных периодов без имён, курсов, диалогов и рейтингов. Маленькие группы
            скрываются целиком, а стоимость появляется только при заданных ставках.
          </p>
        </div>
        <button
          type="button"
          className={result ? styles.secondaryAction : undefined}
          onClick={() => void run()}
          disabled={busy || denied}
        >
          {busy
            ? "Печатаем контрольную ленту…"
            : result
              ? "Собрать ленту заново"
              : "Собрать контрольную ленту"}
        </button>
      </header>

      {busy ? (
        <div className={styles.loading} role="status" aria-live="polite">
          <div aria-hidden="true"><i /><i /><i /></div>
          <p>Сверяем использование за 28 дней и работу AI за 24 часа.</p>
        </div>
      ) : error ? (
        <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>
          <div>
            <strong>
              {denied ? "Доступ не подтверждён" : stale ? "Лента устарела" : "Лента не собралась"}
            </strong>
            <span>{error}</span>
          </div>
          {!denied ? (
            <button type="button" onClick={() => void run()}>
              {stale ? "Собрать свежую ленту" : "Попробовать снова"}
            </button>
          ) : null}
        </div>
      ) : result ? (
        <article className={styles.result} data-state={result.overall_state}>
          <div className={styles.resultLead}>
            <span>Контрольная лента · {result.organization_name}</span>
            <h3 ref={resultRef} tabIndex={-1}>{result.headline}</h3>
            <p>Три участка читаются слева направо: использование, runtime и оценка стоимости.</p>
          </div>

          <ol className={styles.tape} aria-label="Контрольная лента использования и нагрузки">
            {result.segments.map((segment) => (
              <li key={segment.kind} data-state={segment.state}>
                <div className={styles.segmentCode}>
                  <span>{KIND_CODES[segment.kind]}</span>
                  <b>{STATE_LABELS[segment.state]}</b>
                </div>
                <small>{KIND_LABELS[segment.kind]}</small>
                <strong>{segment.label}</strong>
                <p>{segment.detail}</p>
                <div className={styles.period}>
                  <span>Сейчас · {segment.current_window}</span>
                  <ul>{segment.current_facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
                </div>
                <div className={styles.comparison}>
                  <span>{TREND_LABELS[segment.trend]}</span>
                  <small>{segment.comparison_window}</small>
                  {segment.previous_facts.length ? (
                    <ul>{segment.previous_facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
                  ) : null}
                </div>
                {segment.action_target && segment.action_label ? (
                  <button type="button" onClick={() => openTarget(segment.action_target!)}>
                    {segment.action_label}
                  </button>
                ) : null}
              </li>
            ))}
          </ol>

          <footer>
            <details>
              <summary>Как читать эту ленту</summary>
              <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
            <span>Ни один показатель не оценивает человека или качество обучения</span>
          </footer>
        </article>
      ) : (
        <div className={styles.idle}>
          <div aria-hidden="true"><i /><i /><i /></div>
          <strong>{organizationName}</strong>
          <p>
            Лента ещё не собрана. Запуск читает только обезличенные технические события и ничего
            не меняет в Canvas или на AI-хосте.
          </p>
        </div>
      )}
    </section>
  );
}
