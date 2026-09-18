import React, { useEffect, useRef, useState } from "react";

import styles from "../styles/canvas-sync-panel.module.css";


export type CanvasSyncPreview = {
  schema_version: 2;
  state:
    | "oauth_required"
    | "scope_mismatch"
    | "ready"
    | "course_source_unverified"
    | "source_unavailable";
  read_only: true;
  course_id: number;
  course_title: string;
  boundary?: {
    selection: "lti_current_course";
    canvas_origin: string;
    canvas_course_id: string;
    exact_context_binding: true;
  } | null;
  required_scopes: string[];
  missing_scopes: string[];
  excluded_data: string[];
  manifest?: {
    course_title: string;
    captured_at: string;
    provenance:
      | {
          kind: "synthetic_development";
          canvas_contacted: false;
          generator_version: "canvas-manifest-v1";
        }
      | {
          kind: "test_fixture";
          canvas_contacted: false;
          fixture_version: "canvas-manifest-fixture-v1";
        };
    limits: {
      source_pages_per_collection: 10;
      objects_per_collection: 500;
      preview_items_per_group: 5;
      title_characters: 200;
    };
    groups: Array<{
      kind: "modules" | "pages" | "assignments";
      total: number;
      returned: number;
      preview_truncated: boolean;
      read_truncated: boolean;
      items: Array<{
        source_ref: string;
        title: string;
        published: boolean | null;
      }>;
    }>;
  } | null;
};

export type InstructorCanvasOAuthStatus = {
  schema_version: 1;
  state:
    | "configuration_required"
    | "configuration_mismatch"
    | "ready_to_connect"
    | "connected"
    | "reconnect_required"
    | "production_disabled";
  fake_flow_available: boolean;
  read_only: true;
  required_scopes: string[];
  excluded_data: string[];
  connection: {
    mode: "fake_development" | null;
    connected_at: string | null;
    expires_at: string | null;
  };
};

export type CanvasOAuthResult = "connected" | "denied" | "failed" | null;

type PanelState = CanvasSyncPreview["state"] | "request_failed";

const STATE_COPY: Record<
  PanelState,
  { label: string; title: string; description: string }
> = {
  ready: {
    label: "Состав готов",
    title: "Canvas доступен только для чтения",
    description:
      "Проверили текущий курс и собрали ограниченный состав учебных объектов. Ничего не импортировано, Canvas не изменён.",
  },
  oauth_required: {
    label: "Нужно подключение",
    title: "Администратору нужно разрешить чтение Canvas",
    description:
      "Курс выбран верно, но защищённое OAuth-подключение ещё не настроено. Вставлять личный токен преподавателю не нужно.",
  },
  scope_mismatch: {
    label: "Не хватает доступа",
    title: "Подключение видит не все части курса",
    description:
      "Содержимое курса не запрашивали. Администратор может добавить только недостающие разрешения, не расширяя доступ к людям и оценкам.",
  },
  course_source_unverified: {
    label: "Источник не подтверждён",
    title: "Этот курс ещё не связан с источником Canvas",
    description:
      "Запуск из Canvas подтверждён, но внешний курс нельзя безопасно определить по сохранённым данным. Ничего не читали и не меняли.",
  },
  source_unavailable: {
    label: "Связь прервалась",
    title: "Источник временно не отдал состав курса",
    description:
      "Граница курса и разрешения проверены. Содержимое не импортировано, а сохранённые данные и Canvas не изменены.",
  },
  request_failed: {
    label: "Проверка недоступна",
    title: "Не удалось проверить связь с Canvas",
    description:
      "Рабочее место курса продолжает работать. Содержимое не импортировано, а сохранённые данные и Canvas не изменены.",
  },
};

const SCOPE_LABELS: Record<string, string> = {
  "url:GET|/api/v1/courses/:id": "карточка курса",
  "url:GET|/api/v1/courses/:course_id/modules": "модули",
  "url:GET|/api/v1/courses/:course_id/pages": "страницы",
  "url:GET|/api/v1/courses/:course_id/assignments": "задания",
};

const MANIFEST_GROUP_COPY = {
  modules: { label: "Модули", marker: "М" },
  pages: { label: "Страницы", marker: "С" },
  assignments: { label: "Задания", marker: "З" },
};

function sourceLabel(preview: CanvasSyncPreview | null) {
  if (!preview?.boundary) return "Источник уточняется";
  try {
    const hostname = new URL(preview.boundary.canvas_origin).hostname;
    return `${hostname} · курс ${preview.boundary.canvas_course_id}`;
  } catch {
    return "Подтверждённый источник Canvas";
  }
}

function capturedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "время снимка не указано";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function capturedAtForAnnouncement(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export default function CanvasSyncPanel({
  preview,
  loading,
  requestFailed,
  onRefresh,
  handoff,
  handoffLoading,
  handoffFailed,
  oauthResult,
  actionBusy,
  onConnect,
  onRetryHandoff,
  onDisconnect,
}: {
  preview: CanvasSyncPreview | null;
  loading: boolean;
  requestFailed: boolean;
  onRefresh: () => void;
  handoff: InstructorCanvasOAuthStatus | null;
  handoffLoading: boolean;
  handoffFailed: boolean;
  oauthResult: CanvasOAuthResult;
  actionBusy: boolean;
  onConnect: () => void;
  onRetryHandoff: () => void;
  onDisconnect: () => Promise<boolean>;
}) {
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);
  const confirmationRef = useRef<HTMLDivElement>(null);
  const disconnectRef = useRef<HTMLButtonElement>(null);
  const connectRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (oauthResult) resultRef.current?.focus();
  }, [oauthResult]);

  useEffect(() => {
    if (confirmDisconnect) confirmationRef.current?.focus();
  }, [confirmDisconnect]);

  if (!preview && loading) {
    return (
      <section className={styles.panel} data-state="loading" aria-labelledby="canvas-sync-loading-title" aria-busy="true">
        <header className={styles.heading}>
          <div>
            <span className={styles.eyebrow}>Источник курса · только чтение</span>
            <h2 id="canvas-sync-loading-title">Проверяем границы чтения Canvas</h2>
            <p>Сверяем запуск, текущий курс и четыре разрешения. Содержимое пока не запрашиваем.</p>
          </div>
          <span className={styles.status} role="status"><i aria-hidden="true" />Проверяем связь</span>
        </header>

        <div className={styles.route} aria-label="Проверяем маршрут чтения данных курса">
          <div className={styles.routeStop} data-stop="canvas">
            <i aria-hidden="true">C</i>
            <span><strong>Canvas</strong><small>проверяем подключение</small></span>
          </div>
          <em aria-hidden="true"><i /></em>
          <div className={styles.routeStop} data-stop="course">
            <i aria-hidden="true">К</i>
            <span><strong>Текущий курс</strong><small>сверяем с запуском</small></span>
          </div>
          <em aria-hidden="true"><i /></em>
          <div className={styles.routeStop} data-stop="snapshot">
            <i aria-hidden="true">С</i>
            <span><strong>Состав для проверки</strong><small>ожидает безопасного чтения</small></span>
          </div>
        </div>

        <div className={`${styles.snapshot} ${styles.loadingLedger}`} aria-hidden="true">
          <div><strong>—</strong><span>курс</span></div>
          <div><strong>—</strong><span>модули</span></div>
          <div><strong>—</strong><span>страницы</span></div>
          <div><strong>—</strong><span>задания</span></div>
          <p>Состав ещё не запрашивали</p>
        </div>

        <footer className={styles.footer}>
          <p><strong>За границей:</strong> участники, оценки, отправленные работы и активность учеников. Запись в Canvas отключена.</p>
          <button type="button" disabled>Проверяем…</button>
        </footer>
      </section>
    );
  }

  const state: PanelState = requestFailed || !preview ? "request_failed" : preview.state;
  const copy = STATE_COPY[state];
  const manifest = state === "ready" ? preview?.manifest : null;
  const syntheticManifest = Boolean(
    manifest?.provenance.kind === "synthetic_development" &&
      manifest.provenance.canvas_contacted === false,
  );
  const manifestTotals = manifest
    ? Object.fromEntries(manifest.groups.map((group) => [group.kind, group.total]))
    : null;
  const canRetry = state === "ready" || state === "source_unavailable" || state === "request_failed";
  const canConnect =
    state === "oauth_required" &&
    (handoff?.state === "ready_to_connect" || handoff?.state === "reconnect_required");
  const oauthCopy = (() => {
    if (state !== "oauth_required") return copy;
    if (handoffLoading) {
      return {
        label: "Проверяем подключение",
        title: "Проверяем маршрут чтения курса",
        description: "Рабочее место остаётся доступным, пока мы сверяем настройки подключения.",
      };
    }
    if (handoff?.state === "ready_to_connect") {
      return {
        label: "Можно подключить",
        title: "Подтвердите тестовое чтение этого курса",
        description: "Администратор уже подготовил маршрут. Вы подтверждаете только чтение структуры текущего курса.",
      };
    }
    if (handoff?.state === "reconnect_required") {
      return {
        label: "Нужно повторить",
        title: "Повторите тестовое подключение",
        description: "Временный локальный доступ исчез после перезапуска. Настройки курса сохранились.",
      };
    }
    if (handoff?.state === "production_disabled") {
      return {
        label: "Подключение закрыто",
        title: "Настоящее чтение Canvas пока не включено",
        description: "Рабочее место курса доступно, но обмен данными с Canvas в этой среде выключен.",
      };
    }
    return {
      label: handoffFailed ? "Не удалось проверить" : "Нужна подготовка",
      title: "Администратору нужно подготовить чтение Canvas",
      description: "После безопасной настройки преподаватель сможет подтвердить доступ только к своему текущему курсу.",
    };
  })();
  const displayCopy = syntheticManifest
    ? {
        label: "Локальный тест",
        title: "Состав курса готов к проверке",
        description:
          "Canvas не вызывался. Ниже показан синтетический состав, который проверяет границы будущего чтения, а не содержание реального курса.",
      }
    : oauthCopy;

  const handoffGuidance = (() => {
    if (handoffLoading) return "Проверяем, можно ли открыть личный маршрут чтения для этого курса.";
    if (handoffFailed) return "Статус подключения не загрузился. Рабочее место курса не изменено.";
    if (!handoff) return "Статус личного подключения пока недоступен.";
    if (handoff.state === "configuration_required") {
      return "Администратору нужно подготовить безопасное подключение чтения Canvas для этого курса.";
    }
    if (handoff.state === "configuration_mismatch") {
      return "Администратору нужно сверить адрес Canvas API: он не совпадает с источником этого курса.";
    }
    if (handoff.state === "production_disabled") {
      return "Настоящее подключение ещё не включено. Тестовая кнопка скрыта до завершения безопасной настройки среды.";
    }
    if (handoff.state === "reconnect_required") {
      return "Локальное тестовое подключение исчезло после перезапуска. Повторите одноразовое подтверждение.";
    }
    return "Подтвердите четыре разрешения только на чтение. Canvas не будет вызван в этом локальном тесте.";
  })();

  return (
    <section className={styles.panel} data-state={state} aria-labelledby="canvas-sync-title" aria-busy={loading}>
      <header className={styles.heading}>
        <div>
          <span className={styles.eyebrow}>Источник курса · только чтение</span>
          <h2 id="canvas-sync-title">{displayCopy.title}</h2>
          <p>{displayCopy.description}</p>
        </div>
        <span className={styles.status} role="status" aria-live="polite"><i aria-hidden="true" />{displayCopy.label}</span>
      </header>

      {oauthResult && (
        <div
          className={styles.oauthResult}
          data-result={oauthResult}
          role="status"
          tabIndex={-1}
          ref={resultRef}
        >
          <strong>
            {oauthResult === "connected"
              ? "Тестовое подключение подтверждено"
              : oauthResult === "denied"
                ? "Разрешение не выдано"
                : "Подключение не завершено"}
          </strong>
          <span>
            {oauthResult === "connected"
              ? "Canvas не вызывался — обновляем безопасный состав маршрута."
              : oauthResult === "denied"
                ? "Доступ не сохранён. Можно повторить, когда будете готовы."
                : "Доступ не сохранён. Проверьте состояние сессии и повторите маршрут."}
          </span>
        </div>
      )}

      <div className={styles.route} aria-label="Маршрут чтения данных курса">
        <div className={styles.routeStop} data-stop="canvas">
          <i aria-hidden="true">C</i>
          <span><strong>Canvas</strong><small>{sourceLabel(preview)}</small></span>
        </div>
        <em aria-hidden="true"><i /></em>
        <div className={styles.routeStop} data-stop="course">
          <i aria-hidden="true">К</i>
          <span><strong>Текущий курс</strong><small>выбран запуском, без ручного ID</small></span>
        </div>
        <div className={styles.oauthRail}>
          <i aria-hidden="true" />
          <span data-ready={syntheticManifest || handoff?.state === "connected" ? "true" : "false"}>
            <strong>OAuth</strong>
            <small>
              {syntheticManifest || handoff?.state === "connected"
                ? "подтверждено"
                : canConnect
                  ? handoff?.state === "reconnect_required" ? "повторить" : "готово"
                  : "закрыто"}
            </small>
          </span>
        </div>
        <div className={styles.routeStop} data-stop="snapshot">
          <i aria-hidden="true">С</i>
          <span><strong>Состав для проверки</strong><small>{manifest ? "собран без импорта" : "ожидает безопасного чтения"}</small></span>
        </div>
      </div>

      {manifest ? (
        <>
          <p className={styles.manifestAnnouncement} role="status" aria-live="polite" aria-atomic="true">
            Состав обновлён в {capturedAtForAnnouncement(manifest.captured_at)}: {manifestTotals?.modules ?? 0} модулей, {manifestTotals?.pages ?? 0} страниц, {manifestTotals?.assignments ?? 0} заданий.
          </p>
          <div className={styles.manifestLedger} aria-label="Состав курса перед импортом">
          <header className={styles.manifestHeader}>
            <div>
              <span>Приёмочная ведомость · ничего не импортировано</span>
              <strong>
                {syntheticManifest ? "Синтетический состав" : "Тестовый состав"}
              </strong>
              <p>
                {syntheticManifest
                  ? "Canvas не вызывался. Названия ниже созданы локально для проверки маршрута."
                  : "Тестовый источник не обращался к Canvas."}
              </p>
            </div>
            <dl>
              <div><dt>{syntheticManifest ? "Создано локально" : "Собрано"}</dt><dd>{capturedAt(manifest.captured_at)}</dd></div>
              <div><dt>На экране</dt><dd>до {manifest.limits.preview_items_per_group} на раздел</dd></div>
            </dl>
          </header>

          <div className={styles.manifestGroups}>
            {manifest.groups.map((group) => {
              const groupCopy = MANIFEST_GROUP_COPY[group.kind];
              return (
                <article key={group.kind} data-kind={group.kind}>
                  <header>
                    <i aria-hidden="true">{groupCopy.marker}</i>
                    <div><h3>{groupCopy.label}</h3><span>{group.total} всего</span></div>
                  </header>
                  {group.items.length ? (
                    <ul>
                      {group.items.map((item) => (
                        <li key={item.source_ref}>
                          <div><strong>{item.title}</strong><code>Источник: {item.source_ref}</code></div>
                          <span data-published={item.published === null ? "unknown" : String(item.published)}>
                            {item.published === true
                              ? "опубликовано"
                              : item.published === false
                                ? "черновик"
                                : "статус не указан"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className={styles.manifestEmpty}>В этом разделе объектов не найдено.</p>
                  )}
                  <footer>
                    <strong>Показано {group.returned} из {group.total}</strong>
                    <span>
                      {group.read_truncated
                        ? "Достигнут предел чтения — итог может быть больше."
                        : group.preview_truncated
                          ? "Остальные названия скрыты в кратком просмотре."
                          : "Показан весь найденный раздел."}
                    </span>
                  </footer>
                </article>
              );
            })}
          </div>

          <p className={styles.manifestBoundary}>
            Предел чтения: до {manifest.limits.source_pages_per_collection} страниц ответа и {manifest.limits.objects_per_collection} объектов на раздел. Тексты страниц и заданий, файлы и данные учеников не входят.
          </p>
          </div>
        </>
      ) : state === "scope_mismatch" ? (
        <div className={styles.blocker}>
          <span>Нужно разрешить чтение</span>
          <ul>
            {preview?.missing_scopes.map((scope) => (
              <li key={scope}>{SCOPE_LABELS[scope] || "часть курса"}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className={styles.blocker} aria-live={state === "oauth_required" ? "polite" : undefined}>
          <span>Что делать дальше</span>
          <p>
            {state === "oauth_required"
              ? handoffGuidance
              : state === "course_source_unverified"
                ? "Администратору нужно подтвердить соответствие этого внутреннего курса курсу Canvas."
                : "Повторите проверку. Если Canvas снова не ответит, рабочее место курса останется доступным."}
          </p>
          {canConnect && (
            <button
              type="button"
              className={styles.handoffAction}
              ref={connectRef}
              onClick={onConnect}
              disabled={actionBusy || handoffLoading}
            >
              {actionBusy
                ? "Открываем подтверждение…"
                : handoff?.state === "reconnect_required"
                  ? "Переподключить тестовое чтение"
                  : "Подключить тестовое чтение"}
            </button>
          )}
        </div>
      )}

      <footer className={styles.footer}>
        <p><strong>За границей:</strong> участники, оценки, отправленные работы и активность учеников. Запись в Canvas отключена.</p>
        <div className={styles.footerActions}>
          {handoffFailed && (
            <button type="button" onClick={onRetryHandoff} disabled={handoffLoading}>
              {handoffLoading ? "Проверяем…" : "Проверить подключение"}
            </button>
          )}
          {syntheticManifest && handoff?.state === "connected" && !confirmDisconnect && (
            <button
              type="button"
              className={styles.secondaryAction}
              ref={disconnectRef}
              onClick={() => setConfirmDisconnect(true)}
              disabled={actionBusy}
            >
              Отключить тестовый доступ
            </button>
          )}
          {canRetry && (
            <button type="button" onClick={onRefresh} disabled={loading || actionBusy}>
              {loading
                ? "Проверяем…"
                : syntheticManifest
                  ? "Обновить состав"
                  : state === "ready"
                    ? "Обновить состав"
                    : "Повторить проверку"}
            </button>
          )}
        </div>
      </footer>

      {confirmDisconnect && (
        <div
          className={styles.disconnectConfirm}
          ref={confirmationRef}
          tabIndex={-1}
          role="group"
          aria-label="Подтверждение отключения тестового доступа"
        >
          <p><strong>Отключить личный тестовый доступ?</strong> Настройки администратора останутся, но состав курса снова закроется.</p>
          <div>
            <button
              type="button"
              disabled={actionBusy}
              onClick={async () => {
                const disconnected = await onDisconnect();
                if (disconnected) {
                  setConfirmDisconnect(false);
                  window.setTimeout(() => connectRef.current?.focus(), 0);
                }
              }}
            >
              {actionBusy ? "Отключаем…" : "Отключить тестовый доступ"}
            </button>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => {
                setConfirmDisconnect(false);
                window.setTimeout(() => disconnectRef.current?.focus(), 0);
              }}
            >
              Отмена
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
