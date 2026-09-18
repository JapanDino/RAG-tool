import { useCallback, useEffect, useRef, useState } from "react";

import styles from "../styles/admin-operations-route.module.css";

type Target = "registration" | "pilot" | "model" | "retention";
type StationKind =
  | "canvas_configuration"
  | "canvas_launch"
  | "model_runtime"
  | "data_retention";
type StationState =
  | "ready"
  | "attention"
  | "blocked"
  | "not_started"
  | "unavailable";
type OverallState = StationState | "partial";

type AdminOrganization = {
  contract_version: "agent.v1";
  organization_id: number;
  organization_name: string;
  organization_ref: string;
};

type OperationsBrief = {
  mode: "admin_operations_brief";
  organization_name: string;
  overall_state: OverallState;
  headline: string;
  stations: {
    kind: StationKind;
    state: StationState;
    label: string;
    detail: string;
    evidence_window: string;
    facts: string[];
    action_target: Target;
  }[];
  priorities: {
    kind: StationKind;
    attention: "blocker" | "review" | "continue";
    title: string;
    detail: string;
    evidence_label: string;
    action_target: Target;
    action_label: string;
  }[];
  limitations: string[];
  read_only: true;
};

type AgentAccepted = {
  execute_url: string;
};

type AgentRun = {
  status: "queued" | "routing" | "tool_running" | "completed" | "abstained" | "failed";
  user_state: { label: string };
  response: OperationsBrief | null;
};

type Props = {
  organizationId: number;
  organizationName: string;
  identity: string;
  revision?: number;
  onOpenTarget: (target: Exclude<Target, "retention">) => void;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const KIND_LABELS: Record<StationKind, string> = {
  canvas_configuration: "Пакет LTI",
  canvas_launch: "Запуски Canvas",
  model_runtime: "Школьный AI",
  data_retention: "Хранение данных",
};
const STATE_LABELS: Record<StationState, string> = {
  ready: "Готово",
  attention: "Нужно проверить",
  blocked: "Блокер",
  not_started: "Не подтверждено",
  unavailable: "Нет данных",
};

class RouteRequestError extends Error {
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
    let message = "Маршрут временно недоступен.";
    try {
      const payload = await response.json();
      message = payload?.error?.message || message;
    } catch {
      // The fixed fallback intentionally hides provider and server details.
    }
    throw new RouteRequestError(message, response.status);
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

export default function AdminOperationsRoute({
  organizationId,
  organizationName,
  identity,
  revision = 0,
  onOpenTarget,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<OperationsBrief | null>(null);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [retentionExpanded, setRetentionExpanded] = useState(false);
  const resultRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setResult(null);
    setError("");
    setStale(false);
    setRetentionExpanded(false);
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
    setRetentionExpanded(false);
    try {
      const organization = await request<AdminOrganization>(
        `/agent/v1/admin-organization?organization_id=${organizationId}`,
        identity,
      );
      const payload = {
        contract_version: "agent.v1",
        message: "Собери операционный маршрут действий",
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
        current.response?.mode !== "admin_operations_brief"
      ) {
        throw new RouteRequestError(
          current?.user_state.label || "Маршрут не завершился.",
          current?.status === "abstained" ? 409 : 503,
        );
      }
      setResult(current.response);
    } catch (reason) {
      const changed = reason instanceof RouteRequestError && [404, 409].includes(reason.status);
      setStale(changed);
      setError(
        `${
          changed
            ? "Операционное состояние изменилось. Обновите данные и соберите маршрут заново."
            : reason instanceof Error
              ? reason.message
              : "Маршрут временно недоступен."
        } Canvas и настройки организации не изменены.`,
      );
    } finally {
      setBusy(false);
    }
  }, [identity, organizationId]);

  const openTarget = (target: Target) => {
    if (target === "retention") {
      setRetentionExpanded(true);
      window.requestAnimationFrame(() => {
        focusAndReveal(document.getElementById("admin-retention-detail"));
      });
      return;
    }
    onOpenTarget(target);
  };

  const retentionStation = result?.stations.find(
    (station) => station.kind === "data_retention",
  ) || null;

  return (
    <section className={styles.route} aria-labelledby="admin-operations-title">
      <header className={styles.header}>
        <div>
          <span>Помощник администратора · только чтение</span>
          <h2 id="admin-operations-title">Что проверить перед следующим запуском</h2>
          <p>
            Один маршрут по состоянию Canvas, AI-сервиса и хранения данных — без
            пользователей, диалогов и скрытых проверок.
          </p>
        </div>
        <button
          type="button"
          className={result ? styles.secondaryAction : undefined}
          onClick={() => void run()}
          disabled={busy}
        >
          {busy
            ? "Собираем маршрут…"
            : result
              ? "Собрать маршрут действий заново"
              : "Собрать маршрут действий"}
        </button>
      </header>

      {busy ? (
        <div className={styles.loading} role="status" aria-live="polite">
          <div aria-hidden="true"><i /><i /><i /><i /></div>
          <p>Проверяем четыре агрегированных сигнала и выбираем следующий безопасный шаг.</p>
        </div>
      ) : error ? (
        <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>
          <div>
            <strong>{stale ? "Данные маршрута изменились" : "Маршрут не собрался"}</strong>
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => void run()}>
            {stale ? "Обновить маршрут" : "Попробовать снова"}
          </button>
        </div>
      ) : result ? (
        <article className={styles.result} data-state={result.overall_state}>
          <div className={styles.resultLead}>
            <span>Диспетчерский маршрут · {result.organization_name}</span>
            <h3 ref={resultRef} tabIndex={-1}>{result.headline}</h3>
            <p>Четыре станции сведены в одно действие с самым высоким приоритетом.</p>
          </div>

          <ol className={styles.stations} aria-label="Станции операционного маршрута">
            {result.stations.map((station) => (
              <li
                key={station.kind}
                id={`admin-station-${station.kind}`}
                data-state={station.state}
                tabIndex={station.action_target === "retention" ? -1 : undefined}
              >
                <div className={styles.stationTop}>
                  <span>{KIND_LABELS[station.kind]}</span>
                  <b>{STATE_LABELS[station.state]}</b>
                </div>
                <strong>{station.label}</strong>
                <p>{station.detail}</p>
                <ul>{station.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
                <small>{station.evidence_window}</small>
              </li>
            ))}
          </ol>

          <div className={styles.priorityArea}>
            <span className={styles.maintenanceTag}>Сначала</span>
            <ol>
              {result.priorities.map((priority, index) => (
                <li key={`${priority.kind}-${priority.title}`} data-attention={priority.attention}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <small>{priority.evidence_label}</small>
                    <strong>{priority.title}</strong>
                    <p>{priority.detail}</p>
                    {index === 0 ? (
                      <button type="button" onClick={() => openTarget(priority.action_target)}>
                        {priority.action_label}
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          </div>

          {retentionExpanded && retentionStation ? (
            <section
              className={styles.retentionDetail}
              id="admin-retention-detail"
              tabIndex={-1}
              aria-labelledby="admin-retention-detail-title"
            >
              <span>Политика организации · только чтение</span>
              <h4 id="admin-retention-detail-title">Сведения политики хранения</h4>
              <p>{retentionStation.detail}</p>
              <ul>{retentionStation.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
              <small>
                Изменение срока и ручная очистка остаются отдельными подтверждаемыми
                действиями администратора; этот маршрут их не запускает.
              </small>
            </section>
          ) : null}

          <footer>
            <details>
              <summary>Границы этой сводки</summary>
              <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
            <span>Маршрут только читает текущие агрегаты</span>
          </footer>
        </article>
      ) : (
        <div className={styles.idle}>
          <div aria-hidden="true"><i /><i /><i /><i /></div>
          <strong>{organizationName}</strong>
          <p>Помощник ещё ничего не проверял. Запуск не обращается к школьному Canvas и ничего не меняет.</p>
        </div>
      )}
    </section>
  );
}
