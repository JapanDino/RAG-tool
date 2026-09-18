import Head from "next/head";
import Link from "next/link";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import styles from "../../../styles/lti-registration.module.css";
import CanvasOAuthPanel from "../../../components/CanvasOAuthPanel";
import AdminOperationsRoute from "../../../components/AdminOperationsRoute";
import AdminAnalyticsTape from "../../../components/AdminAnalyticsTape";
import AdminDataCustodyRoute from "../../../components/AdminDataCustodyRoute";
import AgentModelReadinessPanel from "../../../components/AgentModelReadinessPanel";
import AgentModelPreflightPanel from "../../../components/AgentModelPreflightPanel";
import AgentPolicyControlPanel from "../../../components/AgentPolicyControlPanel";
import LtiBindingDesk from "../../../components/LtiBindingDesk";
import LtiPilotHealthPanel from "../../../components/LtiPilotHealthPanel";

type IdentityContext = {
  user: { display_name: string };
  organizations: { id: number; name: string; role: string }[];
};

type Readiness = {
  configuration_ready: boolean;
  production_ready: boolean;
  blockers: string[];
  warnings: string[];
  public_origin: string | null;
  configuration_url: string | null;
  login_url: string | null;
  launch_url: string | null;
  jwks_url: string | null;
  key_ids: string[];
  canvas_configuration: Record<string, unknown> | null;
};

type Registration = {
  id: number;
  organization_id: number;
  issuer: string;
  client_id: string;
  deployment_id: string;
  authorization_endpoint: string;
  jwks_url: string;
  tool_launch_url: string;
  is_active: boolean;
  subject_binding_count: number;
  context_binding_count: number;
  verified_launch_count: number;
  last_verified_launch_at: string | null;
  created_at: string;
  updated_at: string;
};

type Draft = {
  issuer: string;
  client_id: string;
  deployment_id: string;
  authorization_endpoint: string;
  jwks_url: string;
};

type PendingState = { id: number; activate: boolean } | null;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const IDENTITY_STORAGE_KEY = "rag-dev-user";
const EMPTY_DRAFT: Draft = {
  issuer: "",
  client_id: "",
  deployment_id: "",
  authorization_endpoint: "",
  jwks_url: "",
};
const API_ERROR_MESSAGES: Record<string, string> = {
  registration_duplicate: "Такое развёртывание Canvas уже зарегистрировано.",
  deactivate_before_editing: "Сначала деактивируйте регистрацию.",
  activate_separately: "Сначала сохраните данные, затем активируйте регистрацию.",
  tool_not_production_ready: "Публичный адрес и постоянный ключ ещё не готовы.",
  platform_host_allowlist_missing: "На сервере не задан список доверенных хостов Canvas.",
  authorization_endpoint_untrusted: "Адрес авторизации не прошёл проверку доверия.",
  jwks_endpoint_untrusted: "Адрес ключей Canvas не прошёл проверку доверия.",
  invalid_identifier: "Проверьте точные идентификаторы без лишних пробелов.",
  invalid_url: "Введите точный HTTPS-адрес.",
  https_required: "Для платформы требуется HTTPS-адрес.",
  tool_configuration_unavailable: "Сначала настройте публичный адрес и ключ сервиса.",
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
    let message = `Не удалось выполнить запрос (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message = Array.isArray(detail)
        ? "Проверьте формат и длину заполненных полей."
        : typeof detail === "string"
          ? detail
          : API_ERROR_MESSAGES[detail?.code] || detail?.message || message;
    } catch {
      // Status-based copy is safe when the API does not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  return response.json();
}

function readinessMessage(code: string) {
  const messages: Record<string, string> = {
    public_origin_missing: "Не задан публичный HTTPS-адрес сервиса.",
    public_jwks_missing: "Не настроен набор публичных ключей.",
    invalid_public_jwks: "Набор публичных ключей имеет неверный формат.",
    public_jwks_too_large: "Набор публичных ключей превышает безопасный размер.",
    private_key_material_rejected: "В конфигурации обнаружен приватный ключ.",
    duplicate_key_id: "Идентификаторы публичных ключей должны быть уникальны.",
    platform_host_allowlist_missing:
      "На сервере не задан точный список доверенных хостов Canvas.",
    development_ephemeral_key: "Сейчас используется временный локальный ключ.",
    development_loopback_origin: "Сейчас указан только локальный адрес сервиса.",
  };
  return messages[code] || "Проверьте серверную конфигурацию подключения.";
}

function formatDate(value: string | null) {
  if (!value) return "Ещё не было";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function StatusRail({ readiness, registrations }: {
  readiness: Readiness;
  registrations: Registration[];
}) {
  const active = registrations.find((item) => item.is_active);
  const verified = registrations.reduce(
    (total, item) => total + item.verified_launch_count,
    0
  );
  const hasLoopbackOrigin = readiness.warnings.includes(
    "development_loopback_origin"
  );
  const hasEphemeralKey = readiness.warnings.includes(
    "development_ephemeral_key"
  );
  const stations = [
    {
      title: "Адрес сервиса",
      state: readiness.public_origin
        ? hasLoopbackOrigin
          ? "Локальный preview"
          : "HTTPS готов"
        : "Нужна инфраструктура",
      tone: readiness.public_origin
        ? hasLoopbackOrigin
          ? "attention"
          : "ready"
        : "blocked",
    },
    {
      title: "Публичный ключ",
      state: readiness.key_ids.length
        ? hasEphemeralKey
          ? "Временный ключ"
          : `${readiness.key_ids.length} в наборе`
        : "Не настроен",
      tone: readiness.key_ids.length
        ? hasEphemeralKey
          ? "attention"
          : "ready"
        : "blocked",
    },
    {
      title: "Регистрация Canvas",
      state: active ? "Активна" : registrations.length ? "Черновик" : "Не начата",
      tone: active ? "ready" : registrations.length ? "attention" : "waiting",
    },
    {
      title: "Первый запуск",
      state: verified ? "Подтверждён" : active ? "Ожидает запуска" : "После активации",
      tone: verified ? "ready" : "waiting",
    },
  ];
  return (
    <ol className={styles.statusRail} aria-label="Этапы подключения Canvas">
      {stations.map((station, index) => (
        <li className={styles[station.tone]} key={station.title}>
          <span className={styles.stationNumber}>{index + 1}</span>
          <div>
            <strong>{station.title}</strong>
            <span>{station.state}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ConnectionOrbit({ ready }: { ready: boolean }) {
  return (
    <div
      className={styles.connectionOrbit}
      role="img"
      aria-label="Защищённый маршрут запуска между Контуром и Canvas"
    >
      <span className={styles.orbitLabel}>Подписанный запуск</span>
      <span className={`${styles.platformNode} ${styles.konturNode}`}>
        <i>К</i>
        <strong>Контур</strong>
        <small>объясняет и проверяет</small>
      </span>
      <span className={styles.connectionPath} aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className={`${styles.platformNode} ${styles.canvasNode}`}>
        <i>C</i>
        <strong>Canvas</strong>
        <small>открывает из курса</small>
      </span>
      <span className={ready ? styles.orbitReady : styles.orbitPreview}>
        {ready ? "Маршрут готов к передаче" : "Маршрут собирается"}
      </span>
    </div>
  );
}

export default function LtiRegistrationPage() {
  const [identity, setIdentity] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationId, setOrganizationId] = useState<number | null>(null);
  const [organizationName, setOrganizationName] = useState("");
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [pendingState, setPendingState] = useState<PendingState>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [changingId, setChangingId] = useState<number | null>(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");
  const [registrationError, setRegistrationError] = useState<{
    id: number;
    message: string;
  } | null>(null);
  const [success, setSuccess] = useState("");
  const [copyState, setCopyState] = useState("");
  const [healthRevision, setHealthRevision] = useState(0);
  const confirmationRef = useRef<HTMLDivElement | null>(null);
  const registrationErrorRef = useRef<HTMLDivElement | null>(null);
  const actionTriggerRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  useEffect(() => {
    if (pendingState) confirmationRef.current?.focus();
  }, [pendingState]);

  useEffect(() => {
    if (registrationError) registrationErrorRef.current?.focus();
  }, [registrationError]);

  const loadData = useCallback(
    async (orgId: number, userIdentity: string, refresh = false) => {
      if (refresh) setRefreshing(true);
      setError("");
      try {
        const [nextReadiness, nextRegistrations] = await Promise.all([
          api<Readiness>(
            `/integrations/lti/organizations/${orgId}/readiness`,
            userIdentity
          ),
          api<Registration[]>(
            `/integrations/lti/organizations/${orgId}/registrations`,
            userIdentity
          ),
        ]);
        setReadiness(nextReadiness);
        setRegistrations(nextRegistrations);
        if (refresh) setHealthRevision((value) => value + 1);
      } catch (reason) {
        if (reason instanceof ApiError && reason.status === 404) {
          setAccessDenied(true);
        } else {
          setError(
            `Состояние подключения не загрузилось. ${
              reason instanceof Error ? reason.message : String(reason)
            }`
          );
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    []
  );

  useEffect(() => {
    const storedIdentity = window.localStorage.getItem(IDENTITY_STORAGE_KEY) || "";
    setIdentity(storedIdentity);
    if (!storedIdentity) {
      setAccessDenied(true);
      setLoading(false);
      return;
    }
    void (async () => {
      try {
        const context = await api<IdentityContext>("/identity/me", storedIdentity);
        const params = new URLSearchParams(window.location.search);
        const requested = params.get("organization");
        const requestedId = Number(requested);
        const organization = requested
          ? Number.isInteger(requestedId) && requestedId > 0
            ? context.organizations.find(
                (item) => item.id === requestedId && item.role === "administrator"
              )
            : undefined
          : context.organizations.find((item) => item.role === "administrator");
        if (!organization) {
          setAccessDenied(true);
          setLoading(false);
          return;
        }
        setDisplayName(context.user.display_name);
        setOrganizationId(organization.id);
        setOrganizationName(organization.name);
        await loadData(organization.id, storedIdentity);
      } catch (reason) {
        setError(
          `Страница подключения не открылась. ${
            reason instanceof Error ? reason.message : String(reason)
          }`
        );
        setLoading(false);
      }
    })();
  }, [loadData]);

  const canvasJson = useMemo(
    () =>
      readiness?.canvas_configuration
        ? JSON.stringify(readiness.canvas_configuration, null, 2)
        : "",
    [readiness]
  );
  const activeRegistration = registrations.find((item) => item.is_active) || null;

  const openOperationsTarget = useCallback(
    (target: "registration" | "pilot" | "model") => {
      const targetIds = {
        registration: "registration-package",
        pilot: "pilot-health-route",
        model: "agent-model-route",
      } as const;
      const element = document.getElementById(targetIds[target]);
      if (!element) return;
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      element.focus({ preventScroll: true });
      element.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "center",
      });
    },
    [],
  );

  const copy = async (value: string, label: string) => {
    setSuccess("");
    setCopyState("");
    try {
      if (!navigator.clipboard || !value) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(value);
      setCopyState(`${label} скопирован.`);
    } catch {
      setCopyState("Копирование недоступно. Выделите значение вручную.");
    }
  };

  const resetForm = () => {
    setDraft(EMPTY_DRAFT);
    setEditingId(null);
  };

  const submitDraft = async (event: FormEvent) => {
    event.preventDefault();
    if (!organizationId) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const path = editingId
        ? `/integrations/lti/organizations/${organizationId}/registrations/${editingId}`
        : `/integrations/lti/organizations/${organizationId}/registrations`;
      await api<Registration>(path, identity, {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify(draft),
      });
      setSuccess(editingId ? "Черновик сохранён." : "Черновик создан. Canvas ещё не подключён.");
      resetForm();
      await loadData(organizationId, identity);
    } catch (reason) {
      setError(
        `Черновик сохранён не был. ${
          reason instanceof Error ? reason.message : String(reason)
        } Введённые значения остались в форме.`
      );
    } finally {
      setSaving(false);
    }
  };

  const editRegistration = (registration: Registration) => {
    setDraft({
      issuer: registration.issuer,
      client_id: registration.client_id,
      deployment_id: registration.deployment_id,
      authorization_endpoint: registration.authorization_endpoint,
      jwks_url: registration.jwks_url,
    });
    setEditingId(registration.id);
    setSuccess("");
    setError("");
    document.getElementById("registration-form")?.scrollIntoView({ block: "start" });
  };

  const changeState = async (registration: Registration, activate: boolean) => {
    if (!organizationId) return;
    setChangingId(registration.id);
    setError("");
    setRegistrationError(null);
    setSuccess("");
    try {
      await api<Registration>(
        `/integrations/lti/organizations/${organizationId}/registrations/${registration.id}`,
        identity,
        { method: "PATCH", body: JSON.stringify({ is_active: activate }) }
      );
      setSuccess(
        activate
          ? "Регистрация активирована. Следующий шаг — явные привязки и реальный запуск из Canvas."
          : "Регистрация деактивирована. Новые LTI-запуски закрыты."
      );
      setPendingState(null);
      await loadData(organizationId, identity, true);
      window.requestAnimationFrame(() =>
        actionTriggerRefs.current[registration.id]?.focus()
      );
    } catch (reason) {
      setRegistrationError({
        id: registration.id,
        message: `${activate ? "Активация" : "Деактивация"} не выполнена. Черновик сохранён. ${
          reason instanceof Error ? reason.message : String(reason)
        }`,
      });
    } finally {
      setChangingId(null);
    }
  };

  if (accessDenied) {
    return (
      <main className={styles.permissionPage}>
        <span>Подключение Canvas</span>
        <h1>Настройки организации недоступны</h1>
        <p>
          Этот маршрут открывает администратор организации. Названия и параметры
          недоступных регистраций здесь не раскрываются.
        </p>
        <Link href="/workspace">Вернуться в рабочее пространство</Link>
      </main>
    );
  }

  return (
    <>
      <Head>
        <title>Подключение Canvas — Контур</title>
        <meta
          name="description"
          content="Проверяемая подготовка LTI 1.3 регистрации для Canvas"
        />
      </Head>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brandBlock}>
            <Link href="/workspace" aria-label="Контур обучения">К</Link>
            <div><strong>Контур организации</strong><span>{organizationName || "Рабочая организация"}</span></div>
          </div>
          <div className={styles.routeMark} aria-label="Маршрут от сервиса к Canvas">
            <span>Контур</span><i /><span>Canvas</span>
          </div>
          <div className={styles.identityBlock}><span>Администратор</span><strong>{displayName || "Проверяем доступ…"}</strong></div>
        </header>

        <main className={styles.main} aria-busy={loading || refreshing}>
          <nav className={styles.breadcrumbs} aria-label="Навигационная цепочка">
            <Link href="/workspace">Рабочее пространство</Link><span>/</span><span>Подключение Canvas</span>
          </nav>

          <section className={styles.hero} aria-labelledby="lti-title">
            <div className={styles.heroCopy}>
              <span className={styles.eyebrow}>Безопасный маршрут LTI 1.3</span>
              <h1 id="lti-title">Подключение без скрытых обещаний</h1>
              <p>
                Подготовьте данные для Canvas, сохраните точные идентификаторы и
                активируйте запуск только после проверки инфраструктуры.
              </p>
              <button
                type="button"
                onClick={() => organizationId && void loadData(organizationId, identity, true)}
                disabled={!organizationId || loading || refreshing}
              >
                {refreshing ? "Проверяем снова…" : "Проверить готовность"}
              </button>
            </div>
            <ConnectionOrbit ready={Boolean(readiness?.production_ready)} />
          </section>

          <aside className={styles.boundary}>
            <strong>Canvas не изменяется с этой страницы</strong>
            <span>
              Здесь нет API-токена, синхронизации курсов, оценок или пользователей.
              Активация лишь разрешает проверку подписанного запуска.
            </span>
          </aside>

          {error && <div className={styles.errorNotice} role="alert"><strong>Действие не завершено</strong><span>{error}</span></div>}
          <div className={styles.liveRegion} aria-live="polite">{success || copyState}</div>

          {organizationId && identity ? (
            <>
              <AdminOperationsRoute
                organizationId={organizationId}
                organizationName={organizationName || "Рабочая организация"}
                identity={identity}
                revision={healthRevision}
                onOpenTarget={openOperationsTarget}
              />
              <AdminDataCustodyRoute
                organizationId={organizationId}
                organizationName={organizationName || "Рабочая организация"}
                identity={identity}
                revision={healthRevision}
              />
              <AdminAnalyticsTape
                organizationId={organizationId}
                organizationName={organizationName || "Рабочая организация"}
                identity={identity}
                revision={healthRevision}
                onOpenTarget={openOperationsTarget}
              />
            </>
          ) : null}

          {loading && !readiness ? (
            <div className={styles.loadingState} aria-live="polite"><i />Проверяем адрес, публичные ключи и регистрации…</div>
          ) : readiness ? (
            <>
              <StatusRail readiness={readiness} registrations={registrations} />

              {organizationId && (
                <div id="pilot-health-route" className={styles.routeFocusTarget} tabIndex={-1}>
                  <LtiPilotHealthPanel
                    organizationId={organizationId}
                    identity={identity}
                    revision={healthRevision}
                  />
                </div>
              )}

              {organizationId && (
                <div id="agent-model-route" className={styles.routeFocusTarget} tabIndex={-1}>
                  <AgentModelReadinessPanel
                    organizationId={organizationId}
                    identity={identity}
                    revision={healthRevision}
                  />
                </div>
              )}

              {organizationId && (
                <div id="agent-policy-route" className={styles.routeFocusTarget} tabIndex={-1}>
                  <AgentPolicyControlPanel
                    organizationId={organizationId}
                    organizationName={organizationName || "Рабочая организация"}
                    identity={identity}
                    revision={healthRevision}
                    onChanged={() => setHealthRevision((current) => current + 1)}
                  />
                </div>
              )}

              {organizationId && (
                <div id="agent-model-preflight-route" className={styles.routeFocusTarget} tabIndex={-1}>
                  <AgentModelPreflightPanel
                    organizationId={organizationId}
                    identity={identity}
                    revision={healthRevision}
                  />
                </div>
              )}

              <div className={styles.contentGrid}>
                <section
                  className={styles.packagePanel}
                  id="registration-package"
                  aria-labelledby="package-title"
                  tabIndex={-1}
                >
                  <div className={styles.sectionHeading}>
                    <div><span>Шаг для администратора Canvas</span><h2 id="package-title">Пакет регистрации</h2></div>
                    <span className={readiness.production_ready ? styles.readyBadge : styles.previewBadge}>
                      {readiness.production_ready ? "Готов к передаче" : readiness.warnings.length ? "Только preview" : "Нужна настройка"}
                    </span>
                  </div>

                  {(readiness.blockers.length > 0 || readiness.warnings.length > 0) && (
                    <div className={styles.readinessNotes}>
                      {readiness.blockers.map((code) => <p className={styles.blocker} key={code}><strong>Нужно исправить</strong>{readinessMessage(code)}</p>)}
                      {readiness.warnings.map((code) => <p className={styles.warning} key={code}><strong>До публикации</strong>{readinessMessage(code)}</p>)}
                    </div>
                  )}

                  <dl className={styles.endpointList}>
                    <div><dt>Публичный адрес</dt><dd>{readiness.public_origin || "Не настроен"}</dd></div>
                    <div><dt>Configuration URL</dt><dd>{readiness.configuration_url || "Появится после настройки адреса"}</dd></div>
                    <div><dt>Key ID</dt><dd>{readiness.key_ids.join(", ") || "Нет публичного ключа"}</dd></div>
                  </dl>

                  <div className={styles.copyActions}>
                    <button type="button" onClick={() => void copy(canvasJson, "Canvas JSON")} disabled={!canvasJson}>Копировать JSON</button>
                    <button type="button" onClick={() => void copy(readiness.configuration_url || "", "Configuration URL")} disabled={!readiness.configuration_url}>Копировать URL</button>
                  </div>
                  <details className={styles.rawConfig}>
                    <summary>Посмотреть сырой JSON</summary>
                    {canvasJson ? <pre tabIndex={0}>{canvasJson}</pre> : <p>JSON появится после настройки публичного адреса и ключа.</p>}
                  </details>
                </section>

                <aside className={styles.nextPanel}>
                  <span>Что делать дальше</span>
                  <h2>{activeRegistration ? "Проверить настоящий запуск" : registrations.length ? "Проверить и активировать" : "Создать черновик"}</h2>
                  <ol>
                    <li>Передайте JSON администратору Canvas.</li>
                    <li>Получите точные Client ID и Deployment ID.</li>
                    <li>Сохраните черновик и проверьте активацию.</li>
                    <li>После привязок откройте инструмент из курса.</li>
                  </ol>
                  <p>Даже активная регистрация не означает, что первый запуск уже прошёл.</p>
                </aside>
              </div>

              <section className={styles.registrationSection} aria-labelledby="registrations-title">
                <div className={styles.sectionHeading}>
                  <div><span>Точные данные платформы</span><h2 id="registrations-title">Регистрации</h2></div>
                  <span className={styles.countBadge}>{registrations.length}</span>
                </div>

                {!registrations.length ? (
                  <div className={styles.emptyState}><strong>Регистраций пока нет</strong><p>Сначала получите параметры Developer Key в Canvas. Сохранение формы создаст только неактивный черновик.</p><a href="#registration-form">Заполнить первый черновик</a></div>
                ) : (
                  <div className={styles.registrationList}>
                    {registrations.map((registration) => (
                      <article className={registration.is_active ? styles.registrationActive : styles.registrationCard} key={registration.id}>
                        <div className={styles.cardTop}>
                          <div><span>{registration.is_active ? "Активная регистрация" : "Неактивный черновик"}</span><h3>{registration.issuer}</h3></div>
                          <span className={registration.is_active ? styles.activeBadge : styles.draftBadge}>{registration.is_active ? "Активна" : "Черновик"}</span>
                        </div>
                        <dl className={styles.registrationMeta}>
                          <div><dt>Client ID</dt><dd>{registration.client_id}</dd></div>
                          <div><dt>Deployment ID</dt><dd>{registration.deployment_id}</dd></div>
                          <div><dt>Пользователи</dt><dd>{registration.subject_binding_count} привязок</dd></div>
                          <div><dt>Курсы</dt><dd>{registration.context_binding_count} привязок</dd></div>
                          <div><dt>Проверенные запуски</dt><dd>{registration.verified_launch_count}</dd></div>
                          <div><dt>Последний запуск</dt><dd>{formatDate(registration.last_verified_launch_at)}</dd></div>
                        </dl>
                        <details className={styles.endpointDetails}><summary>Проверить адреса платформы</summary><dl><div><dt>Авторизация</dt><dd>{registration.authorization_endpoint}</dd></div><div><dt>Ключи Canvas</dt><dd>{registration.jwks_url}</dd></div><div><dt>Запуск инструмента</dt><dd>{registration.tool_launch_url}</dd></div></dl></details>
                        {registrationError?.id === registration.id && (
                          <div
                            className={styles.cardError}
                            ref={registrationErrorRef}
                            role="alert"
                            tabIndex={-1}
                          >
                            <strong>Регистрация не изменилась</strong>
                            <span>{registrationError.message}</span>
                          </div>
                        )}
                        {pendingState?.id === registration.id ? (
                          <div className={styles.confirmation} ref={confirmationRef} role="group" tabIndex={-1} aria-label={pendingState.activate ? "Подтверждение активации" : "Подтверждение деактивации"}>
                            <p><strong>{pendingState.activate ? "Разрешить новые подписанные запуски?" : "Закрыть новые запуски?"}</strong>{pendingState.activate ? " Проверка не создаст пользователей и не прочитает курсы Canvas." : " Существующие привязки и история сохранятся."}</p>
                            <div><button type="button" onClick={() => void changeState(registration, pendingState.activate)} disabled={changingId === registration.id}>{changingId === registration.id ? "Проверяем…" : pendingState.activate ? "Активировать регистрацию" : "Деактивировать регистрацию"}</button><button type="button" onClick={() => { setPendingState(null); window.requestAnimationFrame(() => actionTriggerRefs.current[registration.id]?.focus()); }} disabled={changingId === registration.id}>Отмена</button></div>
                          </div>
                        ) : (
                          <div className={styles.cardActions}>
                            {!registration.is_active && <button type="button" onClick={() => editRegistration(registration)}>Редактировать черновик</button>}
                            <button type="button" ref={(element) => { actionTriggerRefs.current[registration.id] = element; }} className={registration.is_active ? styles.dangerAction : styles.primaryAction} onClick={() => { setRegistrationError(null); setPendingState({ id: registration.id, activate: !registration.is_active }); }} disabled={!registration.is_active && !readiness.production_ready}>{registration.is_active ? "Деактивировать" : readiness.production_ready ? "Проверить и активировать" : "Устраните блокеры выше"}</button>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </section>

              {organizationId && (
                <CanvasOAuthPanel
                  organizationId={organizationId}
                  identity={identity}
                  registrations={registrations}
                />
              )}

              {organizationId && (
                <LtiBindingDesk
                  organizationId={organizationId}
                  identity={identity}
                  registrations={registrations}
                  onResolved={() => setHealthRevision((value) => value + 1)}
                />
              )}

              <section className={styles.formSection} id="registration-form" aria-labelledby="form-title">
                <div className={styles.formIntro}><span>{editingId ? "Редактирование черновика" : "Новая регистрация"}</span><h2 id="form-title">{editingId ? "Исправьте точные значения" : "Сохраните данные из Canvas"}</h2><p>Адрес запуска подставится сервером. Черновик останется неактивным до отдельной проверки.</p></div>
                <form onSubmit={submitDraft}>
                  <label><span>Issuer</span><input type="url" required maxLength={1000} placeholder="https://canvas.school.example" value={draft.issuer} onChange={(event) => setDraft({ ...draft, issuer: event.target.value })} /><small>Точное значение <code>iss</code> вашей Canvas.</small></label>
                  <div className={styles.formPair}>
                    <label><span>Client ID</span><input required maxLength={255} placeholder="10000000000001" value={draft.client_id} onChange={(event) => setDraft({ ...draft, client_id: event.target.value })} /></label>
                    <label><span>Deployment ID</span><input required maxLength={255} placeholder="uuid или ID развёртывания" value={draft.deployment_id} onChange={(event) => setDraft({ ...draft, deployment_id: event.target.value })} /></label>
                  </div>
                  <label><span>Адрес авторизации</span><input type="url" required maxLength={2000} placeholder="https://canvas.school.example/api/lti/authorize_redirect" value={draft.authorization_endpoint} onChange={(event) => setDraft({ ...draft, authorization_endpoint: event.target.value })} /></label>
                  <label><span>Адрес публичных ключей Canvas</span><input type="url" required maxLength={2000} placeholder="https://canvas.school.example/api/lti/security/jwks" value={draft.jwks_url} onChange={(event) => setDraft({ ...draft, jwks_url: event.target.value })} /></label>
                  <div className={styles.formActions}><button type="submit" disabled={saving}>{saving ? "Сохраняем черновик…" : editingId ? "Сохранить черновик" : "Создать неактивный черновик"}</button>{editingId && <button type="button" onClick={resetForm} disabled={saving}>Отменить редактирование</button>}</div>
                </form>
              </section>
            </>
          ) : !error ? (
            <div className={styles.loadingState}>Нет данных о готовности. Обновите проверку.</div>
          ) : null}
        </main>
      </div>
    </>
  );
}
