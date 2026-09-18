import { useCallback, useEffect, useMemo, useState } from "react";

import styles from "../styles/lti-registration.module.css";

type PilotHealth = {
  schema_version: 1;
  window_days: 7;
  state: "not_started" | "stable" | "review_bindings" | "review_failures";
  known_launches: number;
  accepted_launches: number;
  rejected_launches: number;
  active_registrations: number;
  pending_bindings: { total: number; subjects: number; contexts: number };
  failure_families: {
    code:
      | "binding_required"
      | "platform_configuration"
      | "signature_or_replay"
      | "other";
    count: number;
  }[];
  pause_triggers: ("no_verified_launch" | "repeated_rejections")[];
  last_known_launch_at: string | null;
  generated_at: string;
};

type Props = {
  organizationId: number;
  identity: string;
  revision?: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const FAILURE_LABELS: Record<PilotHealth["failure_families"][number]["code"], string> = {
  binding_required: "Не найдена подтверждённая привязка",
  platform_configuration: "Параметры запуска не совпали",
  signature_or_replay: "Подпись или одноразовый запуск не прошли проверку",
  other: "Другой безопасно скрытый отказ",
};

function formatMoment(value: string | null) {
  if (!value) return "Запусков ещё не было";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function launchLabel(count: number) {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) return "запусков";
  if (mod10 === 1) return "запуск";
  if (mod10 >= 2 && mod10 <= 4) return "запуска";
  return "запусков";
}

function activeRegistrationLabel(count: number) {
  const mod100 = count % 100;
  const mod10 = count % 10;
  if (mod100 >= 11 && mod100 <= 14) return `${count} активных регистраций`;
  if (mod10 === 1) return `${count} активная регистрация`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} активные регистрации`;
  return `${count} активных регистраций`;
}

function stateCopy(health: PilotHealth) {
  const pause = health.pause_triggers.length > 0;
  if (health.state === "stable" && health.active_registrations === 0) {
    return {
      eyebrow: "Регистрация неактивна",
      title: "История запусков сохранена, новые запуски закрыты",
      body: "В семидневном окне есть проверенные запуски, но сейчас активных production-регистраций нет.",
    };
  }
  if (health.state === "stable") {
    return {
      eyebrow: "Маршрут проходит",
      title: "Проверенные запуски доходят до курса",
      body: "За последние семь дней известных отказов и новых запросов на привязку нет.",
    };
  }
  if (health.state === "review_bindings") {
    return {
      eyebrow: "Нужно решение администратора",
      title: "Разберите новые привязки перед продолжением",
      body: "Сервис остановил неизвестные курсы или участников и ничего не создал автоматически.",
    };
  }
  if (health.state === "review_failures") {
    return {
      eyebrow: pause ? "Стоп-сигнал пилота" : "Нужна проверка маршрута",
      title: pause
        ? "Приостановите новые пилотные запуски"
        : "Проверьте причины отклонённых запусков",
      body: pause
        ? "Повторяющиеся отказы достигли безопасного порога. Регистрация не отключена автоматически."
        : "Есть отклонённые запуски, но порог остановки пилота не достигнут.",
    };
  }
  return {
    eyebrow: "Пилот ещё не начался",
    title: "Ждём первый подписанный запуск из Canvas",
    body: "После активации регистрации откройте инструмент из одного несекретного тестового курса.",
  };
}

export default function LtiPilotHealthPanel({
  organizationId,
  identity,
  revision = 0,
}: Props) {
  const [health, setHealth] = useState<PilotHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retryVersion, setRetryVersion] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(
        `${API_BASE}/integrations/lti/organizations/${organizationId}/pilot-health`,
        { headers: { "X-Dev-User": identity } }
      );
      if (!response.ok) throw new Error(`Запрос не выполнен (${response.status}).`);
      setHealth((await response.json()) as PilotHealth);
    } catch (reason) {
      setError(
        `Маршрут запусков не загрузился. ${
          reason instanceof Error ? reason.message : String(reason)
        } Регистрации и привязки не изменены.`
      );
    } finally {
      setLoading(false);
    }
  }, [identity, organizationId]);

  useEffect(() => {
    void load();
  }, [load, retryVersion, revision]);

  const copy = health ? stateCopy(health) : null;
  const shares = useMemo(() => {
    if (!health?.known_launches) return { accepted: 0, rejected: 0 };
    return {
      accepted: (health.accepted_launches / health.known_launches) * 100,
      rejected: (health.rejected_launches / health.known_launches) * 100,
    };
  }, [health]);

  if (loading && !health) {
    return (
      <section className={styles.pilotHealth} aria-busy="true" aria-live="polite">
        <div className={styles.pilotLoading}><i aria-hidden="true" />Собираем маршрут запусков за семь дней…</div>
      </section>
    );
  }

  if (error && !health) {
    return (
      <section className={styles.pilotHealth} aria-labelledby="pilot-health-error">
        <div className={styles.pilotError} role="alert">
          <div><strong id="pilot-health-error">Маршрут временно недоступен</strong><span>{error}</span></div>
          <button type="button" onClick={() => setRetryVersion((value) => value + 1)} disabled={loading}>
            {loading ? "Проверяем…" : "Повторить"}
          </button>
        </div>
      </section>
    );
  }

  if (!health || !copy) return null;

  const pause = health.pause_triggers.length > 0;
  return (
    <section
      className={`${styles.pilotHealth} ${pause ? styles.pilotHealthStop : ""}`}
      aria-labelledby="pilot-health-title"
      aria-busy={loading}
    >
      <header className={styles.pilotHealthHeader}>
        <div>
          <span>{copy.eyebrow}</span>
          <h2 id="pilot-health-title">{copy.title}</h2>
          <p>{copy.body}</p>
        </div>
        <span className={styles.pilotWindow}>7 дней · агрегировано</span>
      </header>

      <div className={styles.launchRoute} role="img" aria-label={`Из ${health.known_launches} известных запусков ${health.accepted_launches} прошли проверку, ${health.rejected_launches} требуют проверки`}>
        <div className={styles.launchStation}>
          <span>Из Canvas</span>
          <strong>{health.known_launches}</strong>
          <small>{launchLabel(health.known_launches)}</small>
        </div>
        <div className={styles.launchTrack} aria-hidden="true">
          <span className={styles.launchAccepted} style={{ flexBasis: `${shares.accepted}%` }} />
          <span className={styles.launchRejected} style={{ flexBasis: `${shares.rejected}%` }} />
        </div>
        <div className={styles.launchStationVerified}>
          <span>Доступ открыт</span>
          <strong>{health.accepted_launches}</strong>
          <small>проверено</small>
        </div>
        <div className={styles.launchBranch} aria-hidden="true" />
        <div className={styles.launchStationReview}>
          <span>Нужна проверка</span>
          <strong>{health.rejected_launches}</strong>
          <small>отклонено</small>
        </div>
      </div>

      <div className={styles.pilotDetails}>
        <div className={styles.pilotLedger}>
          <div className={styles.pilotLedgerHeading}>
            <span>Причины без персональных данных</span>
            <strong>{health.failure_families.length ? "Что проверить" : "Отказов нет"}</strong>
          </div>
          {health.failure_families.length ? (
            <ul>
              {health.failure_families.map((family) => (
                <li key={family.code}><span>{FAILURE_LABELS[family.code]}</span><strong>{family.count}</strong></li>
              ))}
            </ul>
          ) : (
            <p>В этом окне нет известных отклонённых запусков.</p>
          )}
        </div>

        <aside className={styles.pilotAction}>
          <span>Следующее действие</span>
          {health.state === "review_bindings" ? (
            <>
              <strong>{health.pending_bindings.total} запросов ждут решения</strong>
              <p>{health.pending_bindings.subjects} участников · {health.pending_bindings.contexts} курсов. Исходные ID скрыты.</p>
              <a href="#binding-desk-title">Разобрать привязки</a>
            </>
          ) : health.state === "review_failures" ? (
            <>
              <strong>{pause ? "Остановить расширение пилота" : "Сверить регистрацию и тестовый запуск"}</strong>
              <p>Система ничего не отключила. Проверьте параметры и повторите запуск одной тестовой ролью.</p>
              <a href="#registrations-title">Проверить регистрации</a>
            </>
          ) : health.state === "stable" && health.active_registrations === 0 ? (
            <>
              <strong>Проверить и активировать регистрацию</strong>
              <p>Новые запуски закрыты. Сверьте параметры production-регистрации перед отдельной активацией.</p>
              <a href="#registrations-title">Проверить регистрации</a>
            </>
          ) : health.state === "stable" ? (
            <>
              <strong>Продолжить ограниченный пилот</strong>
              <p>Расширяйте только на заранее согласованные роли и один тестовый курс.</p>
            </>
          ) : (
            <>
              <strong>Открыть инструмент из тестового курса</strong>
              <p>Сначала нужна активная регистрация и явные привязки пользователя и курса.</p>
            </>
          )}
        </aside>
      </div>

      <footer className={styles.pilotHealthFooter}>
        <span>Последний известный запуск: {formatMoment(health.last_known_launch_at)}</span>
        <span>{activeRegistrationLabel(health.active_registrations)}</span>
        {error && <span role="status">Обновление не удалось; показан предыдущий агрегат.</span>}
      </footer>
    </section>
  );
}
