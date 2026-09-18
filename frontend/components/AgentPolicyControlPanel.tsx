import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "../styles/agent-policy-control.module.css";

type ModelMode =
  | "approved_host_with_safe_fallback"
  | "deterministic_only";

type PolicySettings = {
  learner_enabled: boolean;
  instructor_enabled: boolean;
  program_enabled: boolean;
  model_mode: ModelMode;
};

type Policy = PolicySettings & {
  organization_id: number;
  version: number;
  updated_at: string | null;
  safety_boundaries: string[];
};

type PolicyChange = {
  field: keyof PolicySettings;
  label: string;
  before: string;
  after: string;
  impact: string;
};

type Preview = {
  current: Policy;
  proposed: PolicySettings;
  changes: PolicyChange[];
  confirmation: "apply_agent_policy";
};

type Props = {
  organizationId: number;
  organizationName: string;
  identity: string;
  revision?: number;
  onChanged?: () => void;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const ROUTES: Array<{
  field: "learner_enabled" | "instructor_enabled" | "program_enabled";
  marker: string;
  title: string;
  audience: string;
  detail: string;
}> = [
  {
    field: "learner_enabled",
    marker: "01",
    title: "Помощник ученика",
    audience: "Ученики",
    detail: "Объяснение материала, подсказки и самопроверка с опорой на курс.",
  },
  {
    field: "instructor_enabled",
    marker: "02",
    title: "Рабочий помощник",
    audience: "Преподаватели",
    detail: "Разбор курса, находок аудита и проверяемых черновиков улучшений.",
  },
  {
    field: "program_enabled",
    marker: "03",
    title: "Маршрут программы",
    audience: "Методисты и архитекторы",
    detail: "Проверка карты компетенций, пробелов и линий пререквизитов.",
  },
];

const SAFETY_COPY: Record<string, string> = {
  evidence_required: "Ответы и выводы показывают проверяемые основания.",
  hidden_conversation_memory_disabled:
    "Скрытая память между репликами не передаётся модели.",
  canvas_writes_disabled:
    "Агент не меняет Canvas: изменения остаются предварительным просмотром.",
  individual_surveillance_disabled:
    "Административные экраны не показывают личные диалоги и наблюдение за людьми.",
};

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function policyApi<T>(
  path: string,
  identity: string,
  init?: RequestInit
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Dev-User", identity);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let message = "Настройки агента временно недоступны.";
    try {
      const payload = await response.json();
      message = payload?.detail?.message || payload?.detail || message;
    } catch {
      // The status-specific recovery below remains safe without a response body.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

function settingsFrom(policy: Policy): PolicySettings {
  return {
    learner_enabled: policy.learner_enabled,
    instructor_enabled: policy.instructor_enabled,
    program_enabled: policy.program_enabled,
    model_mode: policy.model_mode,
  };
}

export default function AgentPolicyControlPanel({
  organizationId,
  organizationName,
  identity,
  revision = 0,
  onChanged,
}: Props) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [draft, setDraft] = useState<PolicySettings | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<"preview" | "apply" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const scopeRef = useRef("");
  const previewRef = useRef<Preview | null>(null);
  const mainHeadingRef = useRef<HTMLHeadingElement>(null);
  const previewHeadingRef = useRef<HTMLHeadingElement>(null);
  const previewButtonRef = useRef<HTMLButtonElement>(null);
  previewRef.current = preview;

  const load = useCallback(
    async (preserveDraft = false) => {
      setLoading(true);
      setError("");
      try {
        const next = await policyApi<Policy>(
          `/organizations/${organizationId}/agent-policy`,
          identity
        );
        setPolicy(next);
        if (!preserveDraft) setDraft(settingsFrom(next));
      } catch (caught) {
        const status = caught instanceof ApiError ? caught.status : 0;
        setError(
          status === 404
            ? "У этой учётной записи нет доступа к настройкам организации."
            : "Не удалось загрузить политику. Другие функции Canvas не затронуты."
        );
      } finally {
        setLoading(false);
      }
    },
    [identity, organizationId]
  );

  useEffect(() => {
    const scope = `${organizationId}:${identity}`;
    if (scopeRef.current !== scope) {
      scopeRef.current = scope;
      setPolicy(null);
      setDraft(null);
      setPreview(null);
      setNotice("");
    }
    void load(Boolean(previewRef.current));
  }, [identity, load, organizationId, revision]);

  useEffect(() => {
    if (preview) previewHeadingRef.current?.focus();
  }, [preview]);

  const dirty = useMemo(() => {
    if (!policy || !draft) return false;
    return (Object.keys(settingsFrom(policy)) as Array<keyof PolicySettings>).some(
      (field) => draft[field] !== policy[field]
    );
  }, [draft, policy]);

  const updateDraft = <K extends keyof PolicySettings>(
    field: K,
    value: PolicySettings[K]
  ) => {
    if (pending) return;
    setDraft((current) => (current ? { ...current, [field]: value } : current));
    setPreview(null);
    setError("");
    setNotice("");
  };

  const recoverConflict = async () => {
    setPreview(null);
    setNotice(
      "Другой администратор уже изменил политику. Текущая версия обновлена, а ваш черновик сохранён — проверьте различия ещё раз."
    );
    await load(true);
    requestAnimationFrame(() => previewButtonRef.current?.focus());
  };

  const requestPreview = async () => {
    if (!policy || !draft || !dirty || pending) return;
    setPending("preview");
    setError("");
    setNotice("");
    try {
      const next = await policyApi<Preview>(
        `/organizations/${organizationId}/agent-policy/preview`,
        identity,
        {
          method: "POST",
          body: JSON.stringify({ ...draft, expected_version: policy.version }),
        }
      );
      setPreview(next);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        await recoverConflict();
      } else {
        setError("Не удалось подготовить проверку изменений. Черновик сохранён.");
      }
    } finally {
      setPending(null);
    }
  };

  const apply = async () => {
    if (!policy || !draft || !preview?.changes.length || pending) return;
    setPending("apply");
    setError("");
    try {
      const next = await policyApi<Policy>(
        `/organizations/${organizationId}/agent-policy`,
        identity,
        {
          method: "PATCH",
          body: JSON.stringify({
            ...preview.proposed,
            expected_version: preview.current.version,
            confirmation: "apply_agent_policy",
          }),
        }
      );
      setPolicy(next);
      setDraft(settingsFrom(next));
      setPreview(null);
      setNotice(`Настройки применены. Действует версия ${next.version}.`);
      onChanged?.();
      requestAnimationFrame(() => mainHeadingRef.current?.focus());
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        await recoverConflict();
      } else {
        setError("Настройки не применены. Черновик сохранён, можно повторить.");
      }
    } finally {
      setPending(null);
    }
  };

  if (loading && !policy) {
    return (
      <section className={styles.panel} aria-busy="true" aria-label="Политика AI-агента">
        <span className={styles.loadingMark} aria-hidden="true" />
        <div>
          <span className={styles.kicker}>Диспетчер маршрутов</span>
          <h2>Загружаем правила школьного агента…</h2>
          <p>Canvas продолжает работать независимо от этой проверки.</p>
        </div>
      </section>
    );
  }

  if (!policy || !draft) {
    return (
      <section className={`${styles.panel} ${styles.errorPanel}`} aria-labelledby="agent-policy-title">
        <div>
          <span className={styles.kicker}>Диспетчер маршрутов</span>
          <h2 id="agent-policy-title">Настройки не загрузились</h2>
          <p role="alert">{error}</p>
        </div>
        <button type="button" className={styles.secondaryButton} onClick={() => void load()}>
          Проверить снова
        </button>
      </section>
    );
  }

  return (
    <section className={styles.panel} aria-labelledby="agent-policy-title">
      <header className={styles.heading}>
        <div>
          <span className={styles.kicker}>Диспетчер маршрутов · {organizationName}</span>
          <h2 id="agent-policy-title" ref={mainHeadingRef} tabIndex={-1}>Кому и как помогает агент</h2>
          <p>
            Настройте доступные рабочие маршруты. Уже сохранённые результаты остаются
            видимыми их владельцам; новые и незавершённые задания следуют текущей политике.
          </p>
        </div>
        <span className={styles.versionBadge}>Версия {policy.version}</span>
      </header>

      {notice && <div className={styles.notice} role="status">{notice}</div>}
      {error && <div className={styles.errorNotice} role="alert">{error}</div>}

      {!preview ? (
        <>
          <div className={styles.routeBoard} aria-label="Доступные маршруты агента">
            <div className={styles.canvasOrigin} aria-hidden="true">
              <span>C</span>
              <strong>Canvas</strong>
              <small>роль и контекст курса</small>
            </div>
            <div className={styles.routeSpine} aria-hidden="true"><i /><i /><i /></div>
            <div className={styles.routeCards}>
              {ROUTES.map((route) => {
                const enabled = draft[route.field];
                return (
                  <button
                    key={route.field}
                    type="button"
                    role="switch"
                    aria-checked={enabled}
                    className={`${styles.routeCard} ${enabled ? styles.enabled : styles.paused}`}
                    onClick={() => updateDraft(route.field, !enabled)}
                    disabled={Boolean(pending)}
                  >
                    <span className={styles.routeMarker}>{route.marker}</span>
                    <span className={styles.routeCopy}>
                      <small>{route.audience}</small>
                      <strong>{route.title}</strong>
                      <span>{route.detail}</span>
                    </span>
                    <span className={styles.routeState}>{enabled ? "Доступен" : "На паузе"}</span>
                  </button>
                );
              })}
              <div className={`${styles.routeCard} ${styles.fixedRoute}`}>
                <span className={styles.routeMarker}>04</span>
                <span className={styles.routeCopy}>
                  <small>Администраторы</small>
                  <strong>Диагностика и восстановление</strong>
                  <span>Контроль подключения, агрегатов и политики организации.</span>
                </span>
                <span className={styles.routeState}>Всегда доступен</span>
              </div>
            </div>
          </div>

          <fieldset className={styles.modelRoute} disabled={Boolean(pending)}>
            <legend>Маршрут сложных AI-задач</legend>
            <label className={draft.model_mode === "approved_host_with_safe_fallback" ? styles.selectedModel : ""}>
              <input
                type="radio"
                name="agent-model-mode"
                checked={draft.model_mode === "approved_host_with_safe_fallback"}
                onChange={() => updateDraft("model_mode", "approved_host_with_safe_fallback")}
              />
              <span><strong>Школьный AI-сервис + безопасный резерв</strong><small>Разрешает обращение к настроенному школьному хосту. При сбое агент завершает задачу безопасным резервным сценарием.</small></span>
            </label>
            <label className={draft.model_mode === "deterministic_only" ? styles.selectedModel : ""}>
              <input
                type="radio"
                name="agent-model-mode"
                checked={draft.model_mode === "deterministic_only"}
                onChange={() => updateDraft("model_mode", "deterministic_only")}
              />
              <span><strong>Только детерминированный режим</strong><small>Агент не обращается к модельному хосту и использует только заранее проверенные инструменты и безопасные ответы.</small></span>
            </label>
          </fieldset>

          <div className={styles.boundaries}>
            <div>
              <span className={styles.kicker}>Неизменяемые границы</span>
              <h3>Эти правила нельзя ослабить с экрана</h3>
            </div>
            <ul>
              {policy.safety_boundaries.map((boundary) => (
                <li key={boundary}>{SAFETY_COPY[boundary] || boundary}</li>
              ))}
            </ul>
          </div>

          <footer className={styles.actions}>
            <span>{dirty ? "Есть неприменённые изменения" : "Политика соответствует сохранённой версии"}</span>
            <button
              ref={previewButtonRef}
              type="button"
              className={styles.primaryButton}
              onClick={() => void requestPreview()}
              disabled={!dirty || Boolean(pending)}
            >
              {pending === "preview" ? "Сверяем влияние…" : "Проверить изменения"}
            </button>
          </footer>
        </>
      ) : (
        <div className={styles.preview}>
          <div className={styles.previewHeading}>
            <span className={styles.kicker}>Предварительный просмотр</span>
            <h3 ref={previewHeadingRef} tabIndex={-1}>Что изменится после подтверждения</h3>
            <p>Canvas и сохранённые материалы не изменяются этой операцией.</p>
          </div>
          <ol>
            {preview.changes.map((change, index) => (
              <li key={change.field}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{change.label}</strong>
                  <p><del>{change.before}</del><b aria-hidden="true">→</b><ins>{change.after}</ins></p>
                  <small>{change.impact}</small>
                </div>
              </li>
            ))}
          </ol>
          <div className={styles.previewActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => {
                setPreview(null);
                requestAnimationFrame(() => previewButtonRef.current?.focus());
              }}
              disabled={Boolean(pending)}
            >
              Вернуться к редактированию
            </button>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={() => void apply()}
              disabled={Boolean(pending)}
            >
              {pending === "apply" ? "Применяем…" : "Применить настройки"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
