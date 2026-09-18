import { CSSProperties, useCallback, useEffect, useRef, useState } from "react";

import styles from "../styles/admin-data-custody-route.module.css";

type Retention = {
  state: "available" | "unavailable";
  source: "default" | "organization" | "unavailable";
  retention_days: 30 | 90 | 180 | 365 | null;
  agent_metadata_retention_days: 30;
  automatic_purge: boolean | null;
  student_self_delete: boolean | null;
  label: string;
  detail: string;
};

type PurgeState =
  | "current"
  | "previous_policy"
  | "recorded"
  | "no_receipt"
  | "unavailable";

type PolicyStatus = {
  mode: "admin_policy_status";
  organization_name: string;
  overall_state: "ready" | "attention" | "no_receipt" | "partial";
  headline: string;
  retention: Retention;
  policy_versions: {
    kind: "tutor_data" | "agent_runtime";
    label: string;
    version: string;
    detail: string;
  }[];
  purge_status: {
    state: PurgeState;
    label: string;
    detail: string;
    recorded_at: string | null;
    policy_version: number | null;
    facts: string[];
    evidence_window: string;
  };
  action_label: string;
  limitations: string[];
  read_only: true;
};

type AgentRun = {
  status: "queued" | "routing" | "tool_running" | "completed" | "abstained" | "failed";
  user_state: { label: string };
  response: PolicyStatus | null;
};

type Props = {
  organizationId: number;
  organizationName: string;
  identity: string;
  revision?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const PURGE_LABELS: Record<PurgeState, string> = {
  current: "Текущая версия",
  previous_policy: "Историческая версия",
  recorded: "Квитанция найдена",
  no_receipt: "Удалений не зафиксировано",
  unavailable: "Источник недоступен",
};

class CustodyRequestError extends Error {
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
    let message = "Проверка хранения временно недоступна.";
    try {
      const payload = await response.json();
      message = payload?.error?.message || message;
    } catch {
      // Fixed copy intentionally hides database and server details.
    }
    throw new CustodyRequestError(message, response.status);
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

function formatReceiptDate(value: string | null) {
  if (!value) return null;
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function AdminDataCustodyRoute({
  organizationId,
  organizationName,
  identity,
  revision = 0,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PolicyStatus | null>(null);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [denied, setDenied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const resultRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setResult(null);
    setError("");
    setStale(false);
    setDenied(false);
    setExpanded(false);
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
    setExpanded(false);
    try {
      const organization = await request<{ organization_ref: string }>(
        `/agent/v1/admin-organization?organization_id=${organizationId}`,
        identity,
      );
      const payload = {
        contract_version: "agent.v1",
        message: "Проверь хранение данных и политику",
        selection: { organization_ref: organization.organization_ref },
      };
      const accepted = await request<{ execute_url: string }>(
        "/agent/v1/messages",
        identity,
        {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: JSON.stringify(payload),
        },
      );
      let current: AgentRun | null = null;
      for (let step = 0; step < 4; step += 1) {
        current = await request<AgentRun>(accepted.execute_url, identity, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (["completed", "abstained", "failed"].includes(current.status)) break;
      }
      if (current?.status !== "completed" || current.response?.mode !== "admin_policy_status") {
        throw new CustodyRequestError(
          current?.user_state.label || "Проверка хранения не завершилась.",
          current?.status === "abstained" ? 409 : 503,
        );
      }
      setResult(current.response);
    } catch (reason) {
      const changed = reason instanceof CustodyRequestError && reason.status === 409;
      const accessDenied = reason instanceof CustodyRequestError && reason.status === 404;
      setStale(changed);
      setDenied(accessDenied);
      setError(
        `${
          changed
            ? "Политика или журнал очистки изменились. Проверьте хранение заново."
            : accessDenied
              ? "Доступ к организации больше не подтверждён. Вернитесь в рабочее пространство."
              : reason instanceof Error
                ? reason.message
                : "Проверка хранения временно недоступна."
        } Политика и данные не изменены.`,
      );
    } finally {
      setBusy(false);
    }
  }, [identity, organizationId]);

  const revealBoundaries = () => {
    setExpanded(true);
    window.requestAnimationFrame(() => focusAndReveal(detailRef.current));
  };

  const retentionDays = result?.retention.retention_days;
  const markerPosition = retentionDays
    ? Math.min(100, (30 / retentionDays) * 100)
    : 34;
  const rulerStyle = {
    "--agent-marker": `${markerPosition}%`,
    "--agent-label": `${12 + markerPosition * 0.76}%`,
    "--agent-label-mobile": `${23 + markerPosition * 0.54}%`,
  } as CSSProperties;
  const coincident = retentionDays === 30;

  return (
    <section className={styles.shell} aria-labelledby="admin-data-custody-title">
      <header className={styles.header}>
        <div>
          <span>Хранение данных · только чтение</span>
          <h2 id="admin-data-custody-title">Как долго хранятся данные помощника</h2>
          <p>
            Эффективная политика организации, отдельная граница метаданных агента и последняя
            обезличенная квитанция очистки — без людей, курсов и содержимого диалогов.
          </p>
        </div>
        {!error ? (
          <button
            type="button"
            className={result ? styles.secondaryAction : undefined}
            onClick={() => void run()}
            disabled={busy || denied}
          >
            {busy ? "Сверяем границы…" : result ? "Проверить заново" : "Проверить хранение"}
          </button>
        ) : null}
      </header>

      {busy ? (
        <div className={styles.loading} role="status" aria-live="polite">
          <div aria-hidden="true"><i /><i /></div>
          <p>Читаем политику и последнюю безопасную квитанцию. Очистка не запускается.</p>
        </div>
      ) : error ? (
        <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>
          <div>
            <strong>
              {denied ? "Доступ не подтверждён" : stale ? "Проверка устарела" : "Границы не получены"}
            </strong>
            <span>{error}</span>
          </div>
          {!denied ? (
            <button type="button" onClick={() => void run()}>Повторить проверку</button>
          ) : null}
        </div>
      ) : result ? (
        <article className={styles.result} data-state={result.overall_state}>
          <div className={styles.resultLead}>
            <span>Контур хранения · {result.organization_name}</span>
            <h3 ref={resultRef} tabIndex={-1}>{result.headline}</h3>
            <p>{result.retention.detail}</p>
          </div>

          <div
            className={styles.ruler}
            data-coincident={coincident ? "true" : "false"}
            style={rulerStyle}
            role="img"
            aria-label={
              retentionDays
                ? `Метаданные агента хранятся до 30 дней, учебные данные — до ${retentionDays} дней`
                : "Граница метаданных агента — 30 дней, срок учебных данных временно недоступен"
            }
          >
            <span className={styles.nowMarker}><b>Сейчас</b><small>точка отсчёта</small></span>
            <div className={styles.track} aria-hidden="true">
              <i className={styles.agentMarker} />
            </div>
            <span className={styles.policyMarker}>
              <b>{retentionDays ? `${retentionDays} дней` : "нет данных"}</b>
              <small>учебный помощник</small>
            </span>
            <span className={styles.agentLabel}>
              <b>30 дней</b>
              <small>метаданные агента</small>
            </span>
          </div>

          <div className={styles.evidenceGrid}>
            <section className={styles.versionLedger} aria-labelledby="policy-version-title">
              <header>
                <span>PV / VERSION LEDGER</span>
                <h4 id="policy-version-title">Какие правила действуют</h4>
              </header>
              <ol>
                {result.policy_versions.map((item) => (
                  <li key={item.kind}>
                    <span>{item.kind === "tutor_data" ? "01" : "02"}</span>
                    <div><strong>{item.label}</strong><p>{item.detail}</p></div>
                    <code>{item.version}</code>
                  </li>
                ))}
              </ol>
              <div className={styles.safeguards}>
                <span>
                  Автоочистка
                  <b>{result.retention.automatic_purge === null ? "нет данных" : result.retention.automatic_purge ? "включена" : "выключена"}</b>
                </span>
                <span>
                  Самоудаление учеником
                  <b>{result.retention.student_self_delete === null ? "нет данных" : result.retention.student_self_delete ? "доступно" : "недоступно"}</b>
                </span>
              </div>
            </section>

            <section
              className={styles.receipt}
              data-state={result.purge_status.state}
              aria-labelledby="cleanup-receipt-title"
            >
              <header>
                <span>RCPT / LAST SAFE CLEANUP</span>
                <b>{PURGE_LABELS[result.purge_status.state]}</b>
              </header>
              <h4 id="cleanup-receipt-title">{result.purge_status.label}</h4>
              <p>{result.purge_status.detail}</p>
              {formatReceiptDate(result.purge_status.recorded_at) ? (
                <time dateTime={result.purge_status.recorded_at || undefined}>
                  Записано {formatReceiptDate(result.purge_status.recorded_at)}
                </time>
              ) : null}
              <ul>{result.purge_status.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
              <footer>
                <span>{result.purge_status.evidence_window}</span>
                {result.purge_status.policy_version !== null ? (
                  <code>policy v{result.purge_status.policy_version}</code>
                ) : null}
              </footer>
            </section>
          </div>

          {!expanded ? (
            <button type="button" className={styles.boundaryAction} onClick={revealBoundaries}>
              {result.action_label}
            </button>
          ) : (
            <div
              id="admin-data-custody-detail"
              className={styles.boundaryDetail}
              tabIndex={-1}
              ref={detailRef}
            >
              <div>
                <span>Входит в этот контур</span>
                <ul>
                  <li>ответы учебного помощника и сигналы обратной связи;</li>
                  <li>технические записи запусков агента — по более строгой границе;</li>
                  <li>только агрегированный итог последней безопасной очистки.</li>
                </ul>
              </div>
              <div>
                <span>Не доказывает и не показывает</span>
                <ul>
                  <li>очистку всех хранилищ Canvas или школьной инфраструктуры;</li>
                  <li>людей, курсы, диалоги, оценки или содержимое записей;</li>
                  <li>факт пустого запуска очистки, если удалять было нечего.</li>
                </ul>
              </div>
              <details>
                <summary>Все ограничения проверки</summary>
                <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
              </details>
            </div>
          )}
        </article>
      ) : (
        <div className={styles.idle}>
          <div aria-hidden="true"><span>0</span><i /><span>30</span><i /><span>?</span></div>
          <strong>{organizationName}</strong>
          <p>
            Проверка ещё не запускалась. Она читает только текущую конфигурацию и обезличенный
            журнал; политика, Canvas и данные останутся без изменений.
          </p>
        </div>
      )}
    </section>
  );
}
