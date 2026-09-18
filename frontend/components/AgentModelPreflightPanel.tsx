import { useCallback, useEffect, useRef, useState } from "react";

import styles from "../styles/agent-model-preflight.module.css";

type ProfileId = "deepseek_openai_v1" | "gemma_openai_v1";
type CheckStatus = "passed" | "blocked" | "external";

type Profile = {
  id: ProfileId;
  label: string;
  contract: "openai_chat_completions_v1";
  summary: string;
};

type PreflightCheck = {
  code: string;
  status: CheckStatus;
  owner: "application" | "system_administrator";
  label: string;
  detail: string;
};

type Preflight = {
  schema_version: 1;
  profile: Profile;
  available_profiles: Profile[];
  status:
    | "configuration_required"
    | "configuration_blocked"
    | "ready_for_credentialed_probe";
  configuration_state: "disabled" | "setup_required" | "misconfigured" | "configured";
  organization_model_route: "allowed" | "deterministic_only" | "not_assessed";
  network_probe_performed: false;
  credentials_included: false;
  course_data_used: false;
  checks: PreflightCheck[];
  required_server_fields: string[];
  operator_command: string;
  limitations: string[];
  bundle_fingerprint: string;
};

type Props = {
  organizationId: number;
  identity: string;
  revision?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const PROFILE_SHORT: Record<ProfileId, string> = {
  deepseek_openai_v1: "DeepSeek",
  gemma_openai_v1: "Gemma",
};

const STATUS_COPY: Record<
  Preflight["status"],
  { label: string; detail: string; tone: "ready" | "attention" | "blocked" }
> = {
  configuration_required: {
    label: "Пакет готов, сервер ждёт настройки",
    detail: "Локальный контракт проверен. Системному администратору нужно заполнить серверную конфигурацию.",
    tone: "attention",
  },
  configuration_blocked: {
    label: "Серверную настройку нужно исправить",
    detail: "Один из безопасных серверных ограничителей не прошёл проверку. Значения остаются скрытыми.",
    tone: "blocked",
  },
  ready_for_credentialed_probe: {
    label: "Можно переходить к внешней проверке",
    detail: "Серверная форма конфигурации принята. Доступность хоста и качество модели ещё не проверялись.",
    tone: "ready",
  },
};

function stageState(checks: PreflightCheck[], status: CheckStatus) {
  return checks.filter((check) => check.status === status);
}

function plural(count: number, one: string, few: string, many: string) {
  const lastTwo = count % 100;
  const last = count % 10;
  if (last === 1 && lastTwo !== 11) return one;
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return few;
  return many;
}

function validateSafeDownload(value: unknown, profile: ProfileId): value is Preflight {
  if (!value || typeof value !== "object") return false;
  const report = value as Partial<Preflight>;
  return Boolean(
    report.schema_version === 1 &&
      report.profile?.id === profile &&
      report.network_probe_performed === false &&
      report.credentials_included === false &&
      report.course_data_used === false &&
      typeof report.bundle_fingerprint === "string" &&
      /^sha256:[a-f0-9]{16}$/.test(report.bundle_fingerprint)
  );
}

export default function AgentModelPreflightPanel({
  organizationId,
  identity,
  revision = 0,
}: Props) {
  const [profile, setProfile] = useState<ProfileId>("deepseek_openai_v1");
  const [pendingProfile, setPendingProfile] = useState<ProfileId | null>(null);
  const [report, setReport] = useState<Preflight | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const [downloadState, setDownloadState] = useState("");
  const requestSequence = useRef(0);
  const activeProfile = useRef<ProfileId>("deepseek_openai_v1");

  const load = useCallback(async (targetProfile: ProfileId) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setLoading(true);
    setPendingProfile(targetProfile);
    setError("");
    try {
      const response = await fetch(
        `${API_BASE}/organizations/${organizationId}/agent-model/preflight?profile=${targetProfile}`,
        {
          headers: { "X-Dev-User": identity },
          cache: "no-store",
        }
      );
      if (!response.ok) throw new Error(`status ${response.status}`);
      const next = (await response.json()) as Preflight;
      if (next.profile?.id !== targetProfile) throw new Error("profile mismatch");
      if (sequence === requestSequence.current) {
        activeProfile.current = targetProfile;
        setProfile(targetProfile);
        setReport(next);
      }
    } catch {
      if (sequence === requestSequence.current) {
        setError(
          "Паспорт подключения не загрузился. Canvas, агент и серверная конфигурация не изменены."
        );
      }
    } finally {
      if (sequence === requestSequence.current) {
        setLoading(false);
        setPendingProfile(null);
      }
    }
  }, [identity, organizationId]);

  useEffect(() => {
    void load(activeProfile.current);
  }, [load, revision]);

  const chooseProfile = (next: ProfileId) => {
    if (next === profile || downloading) return;
    setDownloadState("");
    void load(next);
  };

  const download = async () => {
    if (!report || downloading) return;
    setDownloading(true);
    setError("");
    setDownloadState("");
    try {
      const reportProfile = report.profile.id;
      const response = await fetch(
        `${API_BASE}/organizations/${organizationId}/agent-model/preflight/export?profile=${reportProfile}`,
        {
          headers: { "X-Dev-User": identity },
          cache: "no-store",
        }
      );
      if (!response.ok) throw new Error(`status ${response.status}`);
      const text = await response.text();
      const parsed: unknown = JSON.parse(text);
      if (!validateSafeDownload(parsed, reportProfile)) throw new Error("unsafe export");
      const blob = new Blob([text], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `agent-model-preflight-${PROFILE_SHORT[reportProfile].toLowerCase()}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setDownloadState(
        `Пакет ${parsed.bundle_fingerprint} скачан. Передайте его системному администратору без добавления секретов.`
      );
    } catch {
      setError("Пакет не скачан. Текущий паспорт сохранён на экране — повторите загрузку.");
    } finally {
      setDownloading(false);
    }
  };

  if (loading && !report) {
    return (
      <section className={styles.panel} aria-busy="true" aria-label="Паспорт подключения AI-сервиса">
        <span className={styles.loadingSeal} aria-hidden="true">AI</span>
        <div>
          <span className={styles.kicker}>Передача инфраструктуре</span>
          <h2>Собираем безопасный паспорт подключения…</h2>
          <p>Проверка выполняется без обращения к модельному хосту и без данных курса.</p>
        </div>
      </section>
    );
  }

  if (!report) {
    return (
      <section className={`${styles.panel} ${styles.errorPanel}`} aria-labelledby="model-preflight-title">
        <div>
          <span className={styles.kicker}>Передача инфраструктуре</span>
          <h2 id="model-preflight-title">Паспорт временно недоступен</h2>
          <p role="alert">{error}</p>
        </div>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={() => void load(activeProfile.current)}
        >
          Собрать снова
        </button>
      </section>
    );
  }

  const status = STATUS_COPY[report.status];
  const contractChecks = report.checks.filter(
    (check) => check.code === "profile_contract_supported"
  );
  const contractPassed = stageState(contractChecks, "passed");
  const serverChecks = report.checks.filter(
    (check) => check.owner === "application" && check.code !== "profile_contract_supported"
  );
  const serverBlocked = stageState(serverChecks, "blocked");
  const external = stageState(report.checks, "external");

  return (
    <section
      className={styles.panel}
      aria-labelledby="model-preflight-title"
      aria-busy={loading}
    >
      <header className={styles.heading}>
        <div>
          <span className={styles.kicker}>Передача инфраструктуре · без секретов</span>
          <h2 id="model-preflight-title">Паспорт подключения AI-сервиса</h2>
          <p>
            Выберите семейство совместимости и передайте системному администратору
            только проверочный контракт — без адреса, ключа, модели и материалов Canvas.
          </p>
        </div>
        <span className={`${styles.statusBadge} ${styles[status.tone]}`}>
          {status.label}
        </span>
      </header>

      <div className={styles.profileSwitch} aria-label="Семейство совместимости">
        {report.available_profiles.map((item) => (
          <button
            type="button"
            aria-pressed={profile === item.id}
            key={item.id}
            onClick={() => chooseProfile(item.id)}
            disabled={downloading}
          >
            <span>{PROFILE_SHORT[item.id]}</span>
            <small>OpenAI-совместимый контракт</small>
          </button>
        ))}
      </div>

      {error && <div className={styles.errorNotice} role="alert">{error}</div>}
      <div className={styles.liveRegion} aria-live="polite">
        {pendingProfile
          ? `Обновляем профиль ${PROFILE_SHORT[pendingProfile]}…`
          : downloadState}
      </div>

      <div className={styles.passport}>
        <div className={styles.passportSpine} aria-hidden="true">
          <i /><i /><i /><i /><i />
        </div>
        <ol className={styles.stages} aria-label="Этапы проверки подключения">
          <li>
            <span className={styles.stageNumber}>01</span>
            <div>
              <small>Приложение · выполнено локально</small>
              <h3>Контракт {PROFILE_SHORT[report.profile.id]} распознаётся</h3>
              <p>{report.profile.summary}</p>
              <strong className={contractPassed.length ? styles.passedMark : styles.blockedMark}>
                {contractPassed.length
                  ? "Локальная проверка контракта пройдена"
                  : "Локальная проверка контракта заблокирована"}
              </strong>
            </div>
          </li>
          <li>
            <span className={styles.stageNumber}>02</span>
            <div>
              <small>Сервер · значения скрыты</small>
              <h3>{status.label}</h3>
              <p>{status.detail}</p>
              <strong className={serverBlocked.length ? styles.blockedMark : styles.passedMark}>
                {serverBlocked.length
                  ? `${serverBlocked.length} ${plural(serverBlocked.length, "пункт требует", "пункта требуют", "пунктов требуют")} настройки`
                  : "Безопасная форма конфигурации принята"}
              </strong>
            </div>
          </li>
          <li>
            <span className={styles.stageNumber}>03</span>
            <div>
              <small>Системный администратор · ещё не выполнено</small>
              <h3>Проверить реальный хост в школьной сети</h3>
              <p>Доступность, TLS, выбранная модель, строгий ответ и задержка остаются внешними проверками.</p>
              <strong className={styles.externalMark}>
                {external.length} {plural(external.length, "внешняя проверка", "внешние проверки", "внешних проверок")} в пакете
              </strong>
            </div>
          </li>
        </ol>
      </div>

      {report.organization_model_route === "deterministic_only" && (
        <div className={styles.policyNote}>
          <strong>Использование школьного AI-сервиса сейчас на паузе</strong>
          <span>Паспорт можно подготовить заранее. Агент не обратится к хосту, пока администратор не изменит политику организации.</span>
        </div>
      )}

      <div className={styles.receipt}>
        <div className={styles.receiptCopy}>
          <span className={styles.kicker}>Отрывной пакет передачи</span>
          <h3>{PROFILE_SHORT[report.profile.id]} · fingerprint {report.bundle_fingerprint}</h3>
          <ul aria-label="Границы экспортируемого пакета">
            <li>Сеть не проверялась</li>
            <li>Секреты не включены</li>
            <li>Данные курса не использованы</li>
          </ul>
        </div>
        <button
          type="button"
          className={styles.primaryButton}
          onClick={() => void download()}
          disabled={downloading || loading}
        >
          {downloading ? "Готовим пакет…" : "Скачать пакет для системного администратора"}
        </button>
      </div>

      <footer className={styles.footer}>
        <span>Этот паспорт подтверждает только локальный контракт и форму конфигурации.</span>
        <span>Он не доказывает качество модели или готовность реального хоста.</span>
      </footer>
    </section>
  );
}
