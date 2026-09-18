import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import styles from "../styles/canvas-oauth-panel.module.css";


type Registration = {
  id: number;
  issuer: string;
  client_id: string;
  is_active: boolean;
};

type Configuration = {
  canvas_api_origin: string;
  oauth_client_id: string;
  version: number;
};

type ConnectionState =
  | "not_configured"
  | "ready_to_connect"
  | "connected"
  | "reconnect_required"
  | "production_disabled";

type Status = {
  schema_version: 1;
  registration_id: number;
  production_connection_enabled: false;
  fake_flow_available: boolean;
  callback_uri: string;
  required_scopes: string[];
  excluded_data: string[];
  configuration: Configuration | null;
  connection: {
    state: ConnectionState;
    owner: "current_user";
    mode: "fake_development" | null;
    granted_scopes: string[];
    expires_at: string | null;
    connected_at: string | null;
  };
};

type Props = {
  organizationId: number;
  identity: string;
  registrations: Registration[];
};

type CallbackResult = "connected" | "denied" | "failed" | null;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const SELECTED_REGISTRATION_KEY = "canvas-oauth-registration";

const ERROR_MESSAGES: Record<string, string> = {
  canvas_api_origin_invalid:
    "Укажите один точный HTTPS-адрес Canvas без пути и завершающего слеша.",
  oauth_client_id_invalid:
    "Укажите отдельный Client ID scoped Developer Key для Canvas API.",
  configuration_conflict:
    "Параметры уже изменились в другой вкладке. Обновите состояние и повторите.",
  disconnect_before_configuration_change:
    "Сначала отключите активное тестовое подключение, затем измените параметры.",
  oauth_configuration_required: "Сначала сохраните параметры Canvas API.",
  production_connection_disabled:
    "Настоящее подключение закрыто до появления Developer Key и одобренного хранилища.",
  secret_store_unavailable:
    "Хранилище доступа недоступно. Переподключитесь после восстановления сервиса.",
};

const STATE_COPY: Record<ConnectionState, { label: string; note: string }> = {
  not_configured: {
    label: "Нужны параметры",
    note: "Сохраните только публичный API-адрес и отдельный Client ID.",
  },
  ready_to_connect: {
    label: "Готов к тесту",
    note: "Можно проверить локальный OAuth-маршрут без обращения к Canvas.",
  },
  connected: {
    label: "Тестовый маршрут собран",
    note: "Проверены одноразовый callback и закрытая передача fake-доступа.",
  },
  reconnect_required: {
    label: "Нужно переподключить",
    note: "Локальный fake-доступ истёк или исчез после перезапуска сервера.",
  },
  production_disabled: {
    label: "Production закрыт",
    note: "Настоящая авторизация не включена и не может начаться с этой страницы.",
  },
};

const SCOPE_LABELS: Record<string, string> = {
  "url:GET|/api/v1/courses/:id": "Название и границы текущего курса",
  "url:GET|/api/v1/courses/:course_id/modules": "Структура модулей",
  "url:GET|/api/v1/courses/:course_id/pages": "Страницы курса",
  "url:GET|/api/v1/courses/:course_id/assignments": "Список заданий без работ учеников",
};

const EXCLUDED_LABELS: Record<string, string> = {
  rosters: "списки класса",
  users: "профили пользователей",
  submissions: "работы учеников",
  grades: "оценки",
  student_activity: "активность учеников",
  canvas_writes: "любые изменения Canvas",
};

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function api<T>(path: string, identity: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Dev-User", identity);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Запрос не завершён (${response.status}).`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message = Array.isArray(detail)
        ? "Проверьте формат заполненных полей. Секреты и лишние параметры не принимаются."
        : ERROR_MESSAGES[detail?.code] || detail?.message || message;
    } catch {
      // A bounded status message is enough when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.json();
}

function formatDate(value: string | null) {
  if (!value) return "Нет данных";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function CanvasOAuthPanel({
  organizationId,
  identity,
  registrations,
}: Props) {
  const [registrationId, setRegistrationId] = useState<number | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [apiOrigin, setApiOrigin] = useState("");
  const [oauthClientId, setOauthClientId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [authorizing, setAuthorizing] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [error, setError] = useState("");
  const [callbackResult, setCallbackResult] = useState<CallbackResult>(null);
  const [returnedRegistrationId, setReturnedRegistrationId] = useState<number | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);
  const errorRef = useRef<HTMLDivElement | null>(null);
  const disconnectTriggerRef = useRef<HTMLButtonElement | null>(null);
  const disconnectConfirmRef = useRef<HTMLDivElement | null>(null);
  const testActionRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("canvas_oauth");
    if (result === "connected" || result === "denied" || result === "failed") {
      setCallbackResult(result);
      const returned = Number(params.get("canvas_registration"));
      if (Number.isInteger(returned) && returned > 0) {
        setReturnedRegistrationId(returned);
      }
      params.delete("canvas_oauth");
      params.delete("canvas_registration");
      const query = params.toString();
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`
      );
    }
  }, []);

  useEffect(() => {
    if (callbackResult) resultRef.current?.focus();
  }, [callbackResult]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  useEffect(() => {
    if (confirmDisconnect) disconnectConfirmRef.current?.focus();
  }, [confirmDisconnect]);

  useEffect(() => {
    if (!registrations.length) {
      setRegistrationId(null);
      setStatus(null);
      return;
    }
    const stored = Number(window.sessionStorage.getItem(SELECTED_REGISTRATION_KEY));
    const storedRegistration = registrations.find((item) => item.id === stored);
    const returnedRegistration = registrations.find(
      (item) => item.id === returnedRegistrationId
    );
    const currentRegistration = registrations.find((item) => item.id === registrationId);
    const next =
      returnedRegistration ||
      storedRegistration ||
      currentRegistration ||
      registrations.find((item) => item.is_active) ||
      registrations[0];
    setRegistrationId(next.id);
    window.sessionStorage.removeItem(SELECTED_REGISTRATION_KEY);
  }, [registrationId, registrations, returnedRegistrationId]);

  const root = registrationId
    ? `/integrations/canvas/oauth/organizations/${organizationId}/registrations/${registrationId}`
    : "";

  const loadStatus = useCallback(async () => {
    if (!registrationId) return;
    setLoading(true);
    setError("");
    try {
      const next = await api<Status>(
        `/integrations/canvas/oauth/organizations/${organizationId}/registrations/${registrationId}`,
        identity
      );
      setStatus(next);
      setApiOrigin(next.configuration?.canvas_api_origin || "");
      setOauthClientId(next.configuration?.oauth_client_id || "");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Состояние подключения не загрузилось."
      );
    } finally {
      setLoading(false);
    }
  }, [identity, organizationId, registrationId]);

  useEffect(() => {
    setStatus(null);
    setConfirmDisconnect(false);
    if (registrationId) void loadStatus();
  }, [loadStatus, registrationId]);

  const saveConfiguration = async (event: FormEvent) => {
    event.preventDefault();
    if (!root) return;
    setSaving(true);
    setError("");
    try {
      await api<Configuration>(`${root}/configuration`, identity, {
        method: "PUT",
        body: JSON.stringify({
          canvas_api_origin: apiOrigin,
          oauth_client_id: oauthClientId,
          expected_version: status?.configuration?.version ?? null,
        }),
      });
      await loadStatus();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Параметры не сохранены.");
    } finally {
      setSaving(false);
    }
  };

  const startAuthorization = async () => {
    if (!root || !registrationId) return;
    setAuthorizing(true);
    setError("");
    try {
      const started = await api<{ authorization_url: string }>(
        `${root}/start`,
        identity,
        { method: "POST" }
      );
      window.sessionStorage.setItem(
        SELECTED_REGISTRATION_KEY,
        String(registrationId)
      );
      window.location.assign(new URL(started.authorization_url, API_BASE).toString());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Тест не начался.");
      setAuthorizing(false);
    }
  };

  const disconnect = async () => {
    if (!root) return;
    setDisconnecting(true);
    setError("");
    try {
      await api(`${root}/disconnect`, identity, { method: "POST" });
      setConfirmDisconnect(false);
      setCallbackResult(null);
      await loadStatus();
      window.requestAnimationFrame(() => testActionRef.current?.focus());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Подключение не отключено.");
    } finally {
      setDisconnecting(false);
    }
  };

  const state = status?.connection.state || "not_configured";
  const stateCopy = STATE_COPY[state];
  const isConnected = state === "connected";
  const canTest = Boolean(
    status?.configuration &&
      status.fake_flow_available &&
      state !== "connected" &&
      state !== "production_disabled"
  );

  return (
    <section className={styles.panel} aria-labelledby="canvas-oauth-title">
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>Отдельный маршрут чтения</span>
          <h2 id="canvas-oauth-title">Подключение Canvas API</h2>
          <p>
            LTI открывает инструмент из курса. Этот маршрут отдельно подтверждает,
            кто может читать только структуру текущего курса.
          </p>
        </div>
        <span className={`${styles.stateBadge} ${styles[`state_${state}`]}`}>
          {loading && !status ? "Проверяем…" : stateCopy.label}
        </span>
      </header>

      <div className={styles.trustRoute} aria-label="Маршрут тестового доступа от Canvas API к текущему курсу">
        <span className={styles.routeNode}><i>C</i><strong>Canvas API</strong><small>точный адрес</small></span>
        <span className={styles.routeLine} aria-hidden="true"><i /><i /><i /></span>
        <span className={styles.oauthSeal}><strong>OAuth</strong><small>одноразово</small></span>
        <span className={styles.routeLine} aria-hidden="true"><i /><i /><i /></span>
        <span className={styles.routeNode}><i>К</i><strong>Текущий курс</strong><small>только чтение</small></span>
      </div>

      {callbackResult && (
        <div
          className={callbackResult === "connected" ? styles.resultSuccess : styles.resultNotice}
          role="status"
          tabIndex={-1}
          ref={resultRef}
        >
          <strong>
            {callbackResult === "connected"
              ? "Тестовый OAuth-маршрут подтверждён"
              : callbackResult === "denied"
                ? "Разрешение не выдано"
                : "Тестовый callback не завершился"}
          </strong>
          <span>
            {callbackResult === "connected"
              ? "Canvas не вызывался: проверены одноразовый state, callback и закрытая передача fake-доступа."
              : callbackResult === "denied"
                ? "Подключение не создано. Можно запустить тест снова, когда будете готовы."
                : "Подключение не создано. Обновите состояние и повторите тест."}
          </span>
        </div>
      )}

      {error && (
        <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>
          <div><strong>Маршрут не изменился</strong><span>{error}</span></div>
          <button type="button" onClick={() => void loadStatus()} disabled={loading}>
            Обновить состояние
          </button>
        </div>
      )}

      {!registrations.length ? (
        <div className={styles.empty}>
          <strong>Сначала нужна LTI-регистрация</strong>
          <p>Создайте черновик выше. API-подключение всегда привязано к одной точной регистрации Canvas.</p>
          <a href="#registration-form">Создать черновик регистрации</a>
        </div>
      ) : (
        <>
          <label className={styles.registrationPicker}>
            <span>Регистрация для маршрута</span>
            <select
              value={registrationId || ""}
              onChange={(event) => setRegistrationId(Number(event.target.value))}
            >
              {registrations.map((registration) => (
                <option value={registration.id} key={registration.id}>
                  {registration.is_active ? "Активна" : "Черновик"} · {registration.issuer} · LTI {registration.client_id}
                </option>
              ))}
            </select>
          </label>

          {loading && !status ? (
            <div className={styles.loading} aria-live="polite"><i />Проверяем конфигурацию и личное подключение…</div>
          ) : status ? (
            <div className={styles.workbench}>
              <form className={styles.configuration} onSubmit={saveConfiguration}>
                <div className={styles.blockHeading}>
                  <span>Несекретная конфигурация</span>
                  <strong>Где находится Canvas API</strong>
                  <p>Эти параметры не дают доступ сами по себе. Секрет и токен здесь не принимаются.</p>
                </div>
                <label>
                  <span>Точный Canvas API origin</span>
                  <input
                    type="url"
                    required
                    maxLength={1000}
                    placeholder="https://canvas.school.example"
                    value={apiOrigin}
                    onChange={(event) => setApiOrigin(event.target.value)}
                    disabled={isConnected || saving}
                  />
                  <small>Только HTTPS, без пути и завершающего слеша.</small>
                </label>
                <label>
                  <span>Client ID для Canvas API</span>
                  <input
                    required
                    maxLength={255}
                    placeholder="Client ID scoped Developer Key"
                    value={oauthClientId}
                    onChange={(event) => setOauthClientId(event.target.value)}
                    disabled={isConnected || saving}
                  />
                  <small>Это не LTI Client ID и не client secret.</small>
                </label>
                <button type="submit" disabled={saving || isConnected}>
                  {saving ? "Сохраняем параметры…" : status.configuration ? "Сохранить параметры" : "Сохранить API-маршрут"}
                </button>
                {isConnected && <p className={styles.lockNote}>Чтобы изменить параметры, сначала явно отключите личное подключение.</p>}
              </form>

              <article className={styles.connectionEvidence}>
                <div className={styles.blockHeading}>
                  <span>Личное подключение</span>
                  <strong>{stateCopy.label}</strong>
                  <p>{stateCopy.note}</p>
                </div>

                {isConnected ? (
                  <>
                    <dl className={styles.connectionMeta}>
                      <div><dt>Владелец</dt><dd>Вы, в этой регистрации</dd></div>
                      <div><dt>Режим</dt><dd>Локальный fake exchange</dd></div>
                      <div><dt>Подключено</dt><dd>{formatDate(status.connection.connected_at)}</dd></div>
                      <div><dt>Истекает</dt><dd>{formatDate(status.connection.expires_at)}</dd></div>
                    </dl>
                    <strong className={styles.listTitle}>Разрешено читать</strong>
                    <ul className={styles.scopeList}>
                      {status.connection.granted_scopes.map((scope) => (
                        <li key={scope}><i aria-hidden="true">✓</i><span>{SCOPE_LABELS[scope] || scope}</span></li>
                      ))}
                    </ul>
                    {confirmDisconnect ? (
                      <div
                        className={styles.disconnectConfirm}
                        role="group"
                        aria-label="Подтверждение отключения"
                        tabIndex={-1}
                        ref={disconnectConfirmRef}
                      >
                        <p><strong>Удалить локальный fake-доступ?</strong> Параметры API останутся, но потребуется новый тест.</p>
                        <div>
                          <button type="button" onClick={() => void disconnect()} disabled={disconnecting}>
                            {disconnecting ? "Отключаем…" : "Отключить тестовое подключение"}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setConfirmDisconnect(false);
                              window.requestAnimationFrame(() =>
                                disconnectTriggerRef.current?.focus()
                              );
                            }}
                            disabled={disconnecting}
                          >
                            Отмена
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        className={styles.secondaryAction}
                        type="button"
                        onClick={() => setConfirmDisconnect(true)}
                        ref={disconnectTriggerRef}
                      >
                        Отключить тестовое подключение
                      </button>
                    )}
                  </>
                ) : (
                  <>
                    <div className={styles.notConnected}>
                      <span aria-hidden="true">→</span>
                      <p>Production остаётся закрыт. Тест создаёт только временную локальную запись и не вызывает Canvas.</p>
                    </div>
                    <button
                      className={styles.primaryAction}
                      type="button"
                      onClick={() => void startAuthorization()}
                      disabled={!canTest || authorizing}
                      ref={testActionRef}
                    >
                      {authorizing
                        ? "Открываем тестовое разрешение…"
                        : state === "reconnect_required"
                          ? "Переподключить тестовый маршрут"
                          : "Проверить тестовое подключение"}
                    </button>
                    {!status.configuration && <p className={styles.actionHint}>Сначала сохраните два несекретных параметра слева.</p>}
                    {state === "production_disabled" && <p className={styles.actionHint}>Нужны Developer Key, одобренное secret store, точный хост и отдельное разрешение на production.</p>}
                  </>
                )}
              </article>
            </div>
          ) : null}

          {status && (
            <footer className={styles.exclusions}>
              <strong>Этот маршрут никогда не включает</strong>
              <ul>
                {status.excluded_data.map((item) => <li key={item}>{EXCLUDED_LABELS[item] || item}</li>)}
              </ul>
              <details>
                <summary>Проверить технические границы</summary>
                <dl>
                  <div><dt>Callback</dt><dd>{status.callback_uri}</dd></div>
                  <div><dt>Scopes</dt><dd>{status.required_scopes.join(" · ")}</dd></div>
                </dl>
              </details>
            </footer>
          )}
        </>
      )}
    </section>
  );
}
