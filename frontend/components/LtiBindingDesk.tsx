import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "../styles/lti-registration.module.css";

type Registration = {
  id: number;
  issuer: string;
  is_active: boolean;
};

type Candidate = {
  id: number;
  candidate_type: "subject" | "context";
  identifier_hint: string;
  seen_count: number;
  first_seen_at: string;
  last_seen_at: string;
  expires_at: string;
};

type UserTarget = {
  id: number;
  display_name: string;
  email: string;
  organization_role: string;
};

type CourseTarget = { id: number; title: string };

type BindingReadiness = {
  registration_id: number;
  registration_active: boolean;
  candidates: Candidate[];
  users: UserTarget[];
  courses: CourseTarget[];
};

type PendingAction = {
  registrationId: number;
  candidateId: number;
  kind: "bind" | "dismiss";
  targetId?: number;
} | null;

type Props = {
  organizationId: number;
  identity: string;
  registrations: Registration[];
  onResolved?: () => void;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function formatMoment(value: string) {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function requestsLabel(count: number) {
  const lastTwo = count % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return "запросов";
  const last = count % 10;
  if (last === 1) return "запрос";
  if (last >= 2 && last <= 4) return "запроса";
  return "запросов";
}

function targetLabel(
  readiness: BindingReadiness,
  candidate: Candidate,
  targetId?: number
) {
  if (!targetId) return "цель не выбрана";
  if (candidate.candidate_type === "subject") {
    const user = readiness.users.find((item) => item.id === targetId);
    return user ? `${user.display_name} · ${user.email}` : "пользователь недоступен";
  }
  return readiness.courses.find((item) => item.id === targetId)?.title || "курс недоступен";
}

async function request<T>(path: string, identity: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  headers.set("X-Dev-User", identity);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = `Запрос не выполнен (${response.status}).`;
    try {
      const payload = await response.json();
      const code = payload?.detail?.code || payload?.detail;
      const messages: Record<string, string> = {
        candidate_unavailable: "Этот запрос уже обработан или срок его хранения закончился.",
        target_not_found: "Выбранный пользователь или курс больше недоступен.",
        binding_conflict: "Такая привязка уже существует. Обновите список.",
      };
      detail = messages[code] || detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export default function LtiBindingDesk({ organizationId, identity, registrations, onResolved }: Props) {
  const [readiness, setReadiness] = useState<Record<number, BindingReadiness>>({});
  const [selectedTargets, setSelectedTargets] = useState<Record<number, string>>({});
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [busyCandidateId, setBusyCandidateId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const confirmationRef = useRef<HTMLDivElement | null>(null);
  const successRef = useRef<HTMLDivElement | null>(null);
  const actionRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const load = useCallback(async () => {
    if (!registrations.length) {
      setReadiness({});
      return;
    }
    setLoading(true);
    setError("");
    try {
      const responses = await Promise.all(
        registrations.map((registration) =>
          request<BindingReadiness>(
            `/integrations/lti/organizations/${organizationId}/registrations/${registration.id}/binding-candidates`,
            identity
          )
        )
      );
      setReadiness(
        Object.fromEntries(responses.map((item) => [item.registration_id, item]))
      );
    } catch (reason) {
      setError(
        `Запросы на привязку не загрузились. ${
          reason instanceof Error ? reason.message : String(reason)
        } Данные и регистрации не изменены.`
      );
    } finally {
      setLoading(false);
    }
  }, [identity, organizationId, registrations]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (pendingAction) confirmationRef.current?.focus();
  }, [pendingAction]);

  useEffect(() => {
    if (success) successRef.current?.focus();
  }, [success]);

  const candidateCount = useMemo(
    () => Object.values(readiness).reduce((total, item) => total + item.candidates.length, 0),
    [readiness]
  );

  const resolve = async () => {
    if (!pendingAction) return;
    const current = readiness[pendingAction.registrationId];
    const candidate = current?.candidates.find(
      (item) => item.id === pendingAction.candidateId
    );
    if (!current || !candidate) return;

    setBusyCandidateId(candidate.id);
    setError("");
    setSuccess("");
    try {
      const path = `/integrations/lti/organizations/${organizationId}/registrations/${pendingAction.registrationId}/binding-candidates/${candidate.id}`;
      await request(
        `${path}/${pendingAction.kind === "bind" ? "bind" : "dismiss"}`,
        identity,
        pendingAction.kind === "bind"
          ? {
              method: "POST",
              body: JSON.stringify({ target_id: pendingAction.targetId }),
            }
          : { method: "POST" }
      );
      setSuccess(
        pendingAction.kind === "bind"
          ? "Привязка сохранена. Запустите курс из Canvas ещё раз."
          : "Запрос скрыт. Если тот же неизвестный идентификатор появится снова, он вернётся в очередь."
      );
      setPendingAction(null);
      setSelectedTargets((currentTargets) => {
        const next = { ...currentTargets };
        delete next[candidate.id];
        return next;
      });
      await load();
      onResolved?.();
    } catch (reason) {
      setError(
        `${reason instanceof Error ? reason.message : String(reason)} ` +
          "Привязка не изменена, запрос остался в очереди."
      );
    } finally {
      setBusyCandidateId(null);
    }
  };

  const cancelPending = () => {
    const candidateId = pendingAction?.candidateId;
    const actionKind = pendingAction?.kind;
    setPendingAction(null);
    if (candidateId && actionKind) {
      window.requestAnimationFrame(() =>
        actionRefs.current[`${candidateId}:${actionKind}`]?.focus()
      );
    }
  };

  return (
    <section className={styles.bindingDesk} aria-labelledby="binding-desk-title">
      <div className={styles.bindingDeskHeading}>
        <div>
          <span>Стол разбора запусков</span>
          <h2 id="binding-desk-title">Связать Canvas с существующими данными</h2>
          <p>
            Здесь появляются только идентификаторы из подписанных запусков. Сервис не
            создаёт пользователей или курсы автоматически и не показывает исходные ID Canvas.
          </p>
        </div>
        <span className={candidateCount ? styles.bindingCountHot : styles.bindingCount}>
          {candidateCount} {requestsLabel(candidateCount)}
        </span>
      </div>

      {success && (
        <div className={styles.bindingSuccess} ref={successRef} role="status" tabIndex={-1}>
          {success}
        </div>
      )}
      {error && (
        <div className={styles.bindingError} role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} disabled={loading}>
            {loading ? "Проверяем…" : "Повторить"}
          </button>
        </div>
      )}

      {error && !Object.keys(readiness).length ? null : loading && !Object.keys(readiness).length ? (
        <div className={styles.bindingLoading}><i aria-hidden="true" />Проверяем входящие запуски…</div>
      ) : !registrations.length ? (
        <div className={styles.bindingEmpty}>
          <strong>Очередь появится после создания регистрации</strong>
          <p>Сначала сохраните точные параметры Canvas в форме ниже.</p>
        </div>
      ) : candidateCount === 0 ? (
        <div className={styles.bindingEmpty}>
          <strong>Неразобранных запусков нет</strong>
          <p>
            После первого подписанного запуска с новым участником или курсом здесь появится
            маскированная карточка для ручной проверки.
          </p>
        </div>
      ) : (
        <div className={styles.bindingRegistrations}>
          {registrations.map((registration) => {
            const current = readiness[registration.id];
            if (!current?.candidates.length) return null;
            return (
              <article className={styles.bindingBatch} key={registration.id}>
                <header>
                  <div>
                    <span>{registration.is_active ? "Активный маршрут" : "Неактивная регистрация"}</span>
                    <h3>{registration.issuer}</h3>
                  </div>
                  <small>{current.candidates.length} в очереди</small>
                </header>
                {!registration.is_active && (
                  <p className={styles.bindingInactiveNote}>
                    Новые запуски сейчас закрыты, но ранее проверенные запросы можно разобрать.
                  </p>
                )}
                <div className={styles.bindingCards}>
                  {current.candidates.map((candidate) => {
                    const isSubject = candidate.candidate_type === "subject";
                    const selected = Number(selectedTargets[candidate.id] || 0);
                    const isPending = pendingAction?.candidateId === candidate.id;
                    return (
                      <div className={styles.bindingCard} key={candidate.id}>
                        <div className={styles.bindingCardIdentity}>
                          <span className={isSubject ? styles.bindingPersonMark : styles.bindingCourseMark} aria-hidden="true">
                            {isSubject ? "У" : "К"}
                          </span>
                          <div>
                            <span>{isSubject ? "Пользователь Canvas" : "Курс Canvas"}</span>
                            <strong>Отпечаток {candidate.identifier_hint}</strong>
                          </div>
                        </div>
                        <dl className={styles.bindingMeta}>
                          <div><dt>Впервые замечен</dt><dd>{formatMoment(candidate.first_seen_at)}</dd></div>
                          <div><dt>Последний раз</dt><dd>{formatMoment(candidate.last_seen_at)}</dd></div>
                          <div><dt>Попыток</dt><dd>{candidate.seen_count}</dd></div>
                          <div><dt>Хранится до</dt><dd>{formatMoment(candidate.expires_at)}</dd></div>
                        </dl>

                        {isPending ? (
                          <div className={styles.bindingConfirmation} ref={confirmationRef} role="group" tabIndex={-1}>
                            <strong>
                              {pendingAction.kind === "bind"
                                ? `Связать с «${targetLabel(current, candidate, pendingAction.targetId)}»?`
                                : "Скрыть этот запрос?"}
                            </strong>
                            <p>
                              {pendingAction.kind === "bind"
                                ? "Будет создана только связь с существующей записью. Аккаунты и курсы не создаются."
                                : "Исходный идентификатор будет удалён. Повторный неизвестный запуск вернёт карточку в очередь."}
                            </p>
                            <div>
                              <button type="button" onClick={() => void resolve()} disabled={busyCandidateId === candidate.id}>
                                {busyCandidateId === candidate.id ? "Сохраняем…" : pendingAction.kind === "bind" ? "Подтвердить привязку" : "Скрыть запрос"}
                              </button>
                              <button type="button" onClick={cancelPending} disabled={busyCandidateId === candidate.id}>Отмена</button>
                            </div>
                          </div>
                        ) : (
                          <div className={styles.bindingControls}>
                            <label>
                              <span>{isSubject ? "Существующий пользователь" : "Существующий курс"}</span>
                              <select
                                value={selectedTargets[candidate.id] || ""}
                                onChange={(event) => setSelectedTargets({ ...selectedTargets, [candidate.id]: event.target.value })}
                              >
                                <option value="">Выберите вручную…</option>
                                {isSubject
                                  ? current.users.map((user) => <option key={user.id} value={user.id}>{user.display_name} · {user.email} · {user.organization_role}</option>)
                                  : current.courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
                              </select>
                            </label>
                            <div>
                              <button
                                type="button"
                                ref={(element) => { actionRefs.current[`${candidate.id}:bind`] = element; }}
                                disabled={!selected}
                                onClick={() => setPendingAction({ registrationId: registration.id, candidateId: candidate.id, kind: "bind", targetId: selected })}
                              >
                                Проверить привязку
                              </button>
                              <button
                                type="button"
                                ref={(element) => { actionRefs.current[`${candidate.id}:dismiss`] = element; }}
                                className={styles.bindingDismiss}
                                onClick={() => setPendingAction({ registrationId: registration.id, candidateId: candidate.id, kind: "dismiss" })}
                              >
                                Не связывать
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
