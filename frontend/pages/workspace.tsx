import Head from "next/head";
import Link from "next/link";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "../styles/workspace.module.css";


type Role =
  | "student"
  | "instructor"
  | "methodologist"
  | "program_designer"
  | "administrator";

type DevelopmentIdentity = {
  email: string;
  display_name: string;
  primary_role: Role;
};

type CourseAccess = {
  id: number;
  organization_id: number;
  title: string;
  description: string;
  source_type: string;
  roles: Role[];
  actions: string[];
  updated_at?: string | null;
};

type IdentityContext = {
  user: { id: number; email: string; display_name: string; is_active: boolean };
  organizations: {
    id: number;
    slug: string;
    name: string;
    is_active: boolean;
    role: Role;
  }[];
  courses: CourseAccess[];
  auth_mode: string;
};

type RoleMeta = {
  label: string;
  eyebrow: string;
  heading: string;
  description: string;
  navigation: string[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const IDENTITY_STORAGE_KEY = "rag-dev-user";

const ROLE_META: Record<Role, RoleMeta> = {
  student: {
    label: "Ученик",
    eyebrow: "Моё обучение",
    heading: "Продолжайте с того места, где нужна ясность",
    description:
      "Здесь будут объяснения по материалам курса, источники и следующий учебный шаг — без раскрытия готовых ответов.",
    navigation: ["Мои курсы", "Текущая тема", "Сохранённые источники"],
  },
  instructor: {
    label: "Преподаватель",
    eyebrow: "Курсы в работе",
    heading: "Сначала — то, что мешает студентам учиться",
    description:
      "Откройте назначенный курс, проверьте связь целей, материалов и заданий, затем разберите рекомендации по доказательствам.",
    navigation: ["Мои курсы", "Очередь проверки", "Черновики изменений"],
  },
  methodologist: {
    label: "Методист",
    eyebrow: "Методическая проверка",
    heading: "Проверяйте качество курса по наблюдаемым связям",
    description:
      "Смотрите разрывы между целями, материалами и оцениванием, а затем переходите к исходному свидетельству.",
    navigation: ["Курсы на проверке", "Разрывы", "Пакеты доказательств"],
  },
  program_designer: {
    label: "Архитектор программы",
    eyebrow: "Контур программы",
    heading: "Собирайте целостную траекторию из отдельных курсов",
    description:
      "Прослеживайте, где компетенция вводится, развивается и проверяется, а затем открывайте доказательство из конкретного курса.",
    navigation: ["Назначенные курсы", "Компетенции", "Карта программы"],
  },
  administrator: {
    label: "Администратор",
    eyebrow: "Контур организации",
    heading: "Доступы и качество — в разных слоях",
    description:
      "Управляйте назначениями отдельно от учебной аналитики и переходите к курсу только в рамках рабочей необходимости.",
    navigation: ["Обзор", "Доступы", "Состояние системы"],
  },
};

function roleLabel(role: Role) {
  return ROLE_META[role]?.label || role;
}

async function api<T>(
  path: string,
  identity?: string,
  init?: RequestInit
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (identity) headers.set("X-Dev-User", identity);
  const writeKey = process.env.NEXT_PUBLIC_API_WRITE_KEY || "";
  if (writeKey && init?.method && init.method !== "GET") {
    headers.set("X-API-Key", writeKey);
  }
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Не удалось выполнить запрос (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message =
        typeof detail === "string"
          ? detail
          : detail?.message || message;
    } catch {
      // The status-based message is safe to show when the API returns no JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function workspaceError(reason: unknown, offlineMessage: string) {
  if (reason instanceof TypeError) return offlineMessage;
  return reason instanceof Error ? reason.message : String(reason);
}

function CourseThread({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={[styles.courseThread, compact ? styles.courseThreadCompact : ""].join(" ")}
      aria-label="Связь цели, материала и оценивания"
    >
      <span className={styles.threadNode}>
        <i className={styles.threadDot} />
        <span>Цель</span>
      </span>
      <span className={styles.threadLink} aria-hidden="true" />
      <span className={styles.threadNode}>
        <i className={styles.threadDot} />
        <span>Материал</span>
      </span>
      <span className={styles.threadLink} aria-hidden="true" />
      <span className={styles.threadNode}>
        <i className={styles.threadDot} />
        <span>Оценивание</span>
      </span>
    </div>
  );
}

function WorkshopRouteMap({ role }: { role: string }) {
  return (
    <div
      className={styles.workshopRouteMap}
      role="img"
      aria-label="Живая карта курса: цель связана с материалом и оцениванием"
    >
      <span className={styles.orbitKicker}>Живой маршрут</span>
      <span className={`${styles.orbitNode} ${styles.orbitObjective}`}>
        <i />
        <strong>Цель</strong>
      </span>
      <span className={`${styles.orbitNode} ${styles.orbitMaterial}`}>
        <i />
        <strong>Материал</strong>
      </span>
      <span className={`${styles.orbitNode} ${styles.orbitAssessment}`}>
        <i />
        <strong>Проверка</strong>
      </span>
      <span className={styles.orbitCore}>
        <small>Ваш контур</small>
        <strong>{role}</strong>
      </span>
      <span className={styles.orbitPulse} aria-hidden="true" />
    </div>
  );
}

export default function Workspace() {
  const [identities, setIdentities] = useState<DevelopmentIdentity[]>([]);
  const [selectedEmail, setSelectedEmail] = useState("");
  const [context, setContext] = useState<IdentityContext | null>(null);
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [creatingDemo, setCreatingDemo] = useState(false);
  const [error, setError] = useState("");
  const detailPanelRef = useRef<HTMLElement | null>(null);

  const loadIdentities = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const rows = await api<DevelopmentIdentity[]>("/identity/development/users");
      setIdentities(rows);
      const stored = window.localStorage.getItem(IDENTITY_STORAGE_KEY) || "";
      const next = rows.some((item) => item.email === stored)
        ? stored
        : rows[0]?.email || "";
      setSelectedEmail(next);
    } catch (reason) {
      setError(
        workspaceError(
          reason,
          "Не удалось связаться с локальным сервером ролей. Профили не изменены. Запустите API и повторите."
        )
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadContext = useCallback(async (identity: string) => {
    if (!identity) {
      setContext(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const value = await api<IdentityContext>("/identity/me", identity);
      setContext(value);
      setSelectedCourseId((current) =>
        value.courses.some((course) => course.id === current)
          ? current
          : value.courses[0]?.id || null
      );
    } catch (reason) {
      setContext(null);
      setError(
        workspaceError(
          reason,
          "Не удалось загрузить рабочее пространство. Данные и назначения не изменены. Проверьте API и повторите."
        )
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadIdentities();
  }, [loadIdentities]);

  useEffect(() => {
    if (selectedEmail) void loadContext(selectedEmail);
  }, [loadContext, selectedEmail]);

  const handleIdentityChange = (email: string) => {
    window.localStorage.setItem(IDENTITY_STORAGE_KEY, email);
    setSelectedEmail(email);
  };

  const bootstrap = async () => {
    setBootstrapping(true);
    setError("");
    try {
      await api("/identity/development/bootstrap", undefined, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await loadIdentities();
    } catch (reason) {
      setError(
        workspaceError(
          reason,
          "Локальные профили не созданы: сервер ролей недоступен. Запустите API и повторите."
        )
      );
    } finally {
      setBootstrapping(false);
    }
  };

  const createDemoCourse = async () => {
    if (!selectedEmail) return;
    setCreatingDemo(true);
    setError("");
    try {
      await api("/courses/demo", selectedEmail, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await loadContext(selectedEmail);
    } catch (reason) {
      setError(
        workspaceError(
          reason,
          "Демонстрационный курс не создан. Данные не изменены. Проверьте API и повторите."
        )
      );
    } finally {
      setCreatingDemo(false);
    }
  };

  const primaryRole: Role =
    context?.organizations[0]?.role ||
    context?.courses[0]?.roles[0] ||
    identities.find((item) => item.email === selectedEmail)?.primary_role ||
    "student";
  const role = ROLE_META[primaryRole];
  const administratorOrganization =
    context?.organizations.find((item) => item.role === "administrator") || null;
  const canCreateCourse = ["instructor", "administrator"].includes(primaryRole);
  const canOpenLab = ["instructor", "methodologist", "administrator"].includes(
    primaryRole
  );
  const canOpenPrograms = [
    "methodologist",
    "program_designer",
    "administrator",
  ].includes(primaryRole);
  const canOpenProgramOverview = administratorOrganization !== null;
  const programOverviewHref = administratorOrganization
    ? `/workspace/programs/overview?organization=${administratorOrganization.id}`
    : "/workspace/programs/overview";
  const canvasIntegrationHref = administratorOrganization
    ? `/workspace/integrations/lti?organization=${administratorOrganization.id}`
    : "/workspace/integrations/lti";
  const selectedCourse = useMemo(
    () => context?.courses.find((course) => course.id === selectedCourseId) || null,
    [context, selectedCourseId]
  );

  const selectCourse = (courseId: number) => {
    setSelectedCourseId(courseId);
    if (window.matchMedia("(max-width: 1180px)").matches) {
      window.requestAnimationFrame(() => {
        detailPanelRef.current?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto"
            : "smooth",
          block: "start",
        });
      });
    }
  };

  return (
    <>
      <Head>
        <title>Контур обучения</title>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <meta
          name="description"
          content="Рабочее пространство для понятных связей между целями, материалами и оцениванием"
        />
      </Head>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brandBlock}>
            <Link className={styles.mark} href="/workspace" aria-label="Контур обучения">
              К
            </Link>
            <div>
              <div className={styles.brand}>Контур</div>
              <div className={styles.brandNote}>карта живого курса</div>
            </div>
          </div>
          <CourseThread compact />
          <div className={styles.identityControl}>
            <label htmlFor="identity">Рабочая роль</label>
            <select
              id="identity"
              value={selectedEmail}
              onChange={(event) => handleIdentityChange(event.target.value)}
              disabled={!identities.length || loading}
            >
              {!identities.length && <option value="">Роли не настроены</option>}
              {identities.map((identity) => (
                <option key={identity.email} value={identity.email}>
                  {identity.display_name} · {roleLabel(identity.primary_role)}
                </option>
              ))}
            </select>
          </div>
        </header>

        {!loading && identities.length === 0 ? (
          <main className={styles.onboarding}>
            <div className={styles.onboardingMark}>Первый вход</div>
            <h1>Подготовьте безопасные локальные роли</h1>
            <p>
              Будут созданы пять демонстрационных профилей и отдельная организация.
              Это работает только в режиме разработки и не создаёт паролей.
            </p>
            {error && <div className={styles.errorNotice} role="alert">{error}</div>}
            <button
              className={styles.primaryButton}
              type="button"
              onClick={bootstrap}
              disabled={bootstrapping}
            >
              {bootstrapping ? "Создаём роли…" : "Создать локальные роли"}
            </button>
          </main>
        ) : (
          <div className={styles.shell}>
            <aside className={styles.sidebar}>
              <div className={styles.contextLabel}>Вы работаете как</div>
              <div className={styles.roleName}>{role.label}</div>
              <nav aria-label="Разделы рабочего пространства">
                {role.navigation.map((item, index) => {
                  const isProgramMapLink =
                    primaryRole === "program_designer" && item === "Карта программы";
                  const isProgramOverviewLink =
                    primaryRole === "administrator" && item === "Обзор";
                  if (isProgramMapLink || isProgramOverviewLink) {
                    return (
                      <Link
                        className={
                          isProgramOverviewLink ? styles.navActive : styles.navItem
                        }
                        href={
                          isProgramOverviewLink
                            ? programOverviewHref
                            : "/workspace/programs"
                        }
                        key={item}
                      >
                        <span>{item}</span>
                        <small>открыть</small>
                      </Link>
                    );
                  }
                  return (
                    <button
                      className={index === 0 ? styles.navActive : styles.navItem}
                      key={item}
                      type="button"
                      disabled={index !== 0}
                      aria-label={index === 0 ? item : `${item}. Скоро`}
                      title={index === 0 ? undefined : "Раздел появится в следующем этапе"}
                    >
                      <span>{item}</span>
                      {index !== 0 && <small>скоро</small>}
                    </button>
                  );
                })}
              </nav>
              <div className={styles.sidebarFoot}>
                <span>Организация</span>
                <strong>
                  {(primaryRole === "administrator"
                    ? administratorOrganization?.name
                    : context?.organizations[0]?.name) || "Нет назначения"}
                </strong>
              </div>
            </aside>

            <main className={styles.main}>
              {error && (
                <div className={styles.errorNotice} role="alert">
                  <strong>Не удалось загрузить рабочее пространство.</strong>
                  <span>{error}</span>
                  <button type="button" onClick={() => loadContext(selectedEmail)}>
                    Повторить
                  </button>
                </div>
              )}
              <section className={styles.intro}>
                <div className={styles.introBody}>
                  <div className={styles.eyebrow}>{role.eyebrow}</div>
                  <h1>{role.heading}</h1>
                  <p>{role.description}</p>
                  {canOpenProgramOverview && context?.organizations.length ? (
                    <div className={styles.introLinks}>
                      <Link
                        className={styles.curriculumLink}
                        href={programOverviewHref}
                      >
                        <span>Обзор программ</span>
                        <strong>Открыть портфель учебных маршрутов</strong>
                        <small>
                          Только агрегированные связи, без рейтингов и данных учеников
                        </small>
                      </Link>
                      <Link
                        className={`${styles.curriculumLink} ${styles.canvasLink}`}
                        href={canvasIntegrationHref}
                      >
                        <span>Подключение Canvas</span>
                        <strong>Подготовить безопасный LTI-запуск</strong>
                        <small>
                          Публичная конфигурация, черновик регистрации и проверка
                          готовности
                        </small>
                      </Link>
                    </div>
                  ) : canOpenPrograms && context?.organizations.length ? (
                    <Link className={styles.curriculumLink} href="/workspace/programs">
                      <span>Маршрут программы</span>
                      <strong>Открыть карту компетенций</strong>
                      <small>Курсы, уровни освоения и проверяемые доказательства</small>
                    </Link>
                  ) : null}
                </div>
                <WorkshopRouteMap role={role.label} />
              </section>

              <section className={styles.courseSection} aria-labelledby="course-heading">
                <div className={styles.sectionHeading}>
                  <div>
                    <span className={styles.sectionIndex}>Назначено вам</span>
                    <h2 id="course-heading">Курсы</h2>
                  </div>
                  <span className={styles.courseCount}>
                    {context?.courses.length || 0}
                  </span>
                </div>

                {loading ? (
                  <div className={styles.loadingState} aria-live="polite">
                    <span />
                    Загружаем доступные курсы…
                  </div>
                ) : !context?.courses.length ? (
                  <div className={styles.emptyState}>
                    <div className={styles.emptyThread}><CourseThread compact /></div>
                    <h3>Пока нет назначенных курсов</h3>
                    <p>
                      {canCreateCourse
                        ? "Создайте демонстрационный курс, чтобы проверить полный цикл аудита на безопасных учебных данных."
                        : "Администратор организации может добавить вас в курс. Название скрытого курса здесь не отображается."}
                    </p>
                    {canCreateCourse && (
                      <button
                        className={styles.secondaryButton}
                        type="button"
                        onClick={createDemoCourse}
                        disabled={creatingDemo}
                      >
                        {creatingDemo
                          ? "Готовим демонстрационный курс…"
                          : "Создать демонстрационный курс"}
                      </button>
                    )}
                  </div>
                ) : (
                  <div className={styles.courseList}>
                    {context.courses.map((course) => (
                      <button
                        className={[
                          styles.courseRow,
                          selectedCourseId === course.id ? styles.courseRowActive : "",
                        ].join(" ")}
                        key={course.id}
                        type="button"
                        aria-pressed={selectedCourseId === course.id}
                        aria-controls="selected-course-actions"
                        onClick={() => selectCourse(course.id)}
                      >
                        <span className={styles.courseOrdinal}>
                          {String(context.courses.indexOf(course) + 1).padStart(2, "0")}
                        </span>
                        <span className={styles.courseCopy}>
                          <strong>{course.title}</strong>
                          <small>{course.description || "Описание курса пока не добавлено"}</small>
                        </span>
                        <CourseThread compact />
                        <span className={styles.rowAction}>Показать действия</span>
                      </button>
                    ))}
                  </div>
                )}
              </section>
            </main>

            <aside
              className={styles.detailPanel}
              id="selected-course-actions"
              ref={detailPanelRef}
              aria-live="polite"
            >
              {selectedCourse ? (
                <>
                  <div className={styles.detailEyebrow}>Текущий курс</div>
                  <h2>{selectedCourse.title}</h2>
                  <div className={styles.roleTags}>
                    {selectedCourse.roles.map((item) => (
                      <span key={item}>{roleLabel(item)}</span>
                    ))}
                  </div>
                  <CourseThread />
                  <p className={styles.detailText}>
                    Контекст доступа проверен сервером. Доступные действия зависят от
                    роли в этом курсе.
                  </p>
                  {selectedCourse.actions.includes("run_audit") ? (
                    <Link
                      className={styles.primaryLink}
                      href={`/workspace/courses/${selectedCourse.id}`}
                    >
                      Открыть очередь внимания
                    </Link>
                  ) : selectedCourse.actions.includes("ask_tutor") ? (
                    <>
                      <Link
                        className={styles.primaryLink}
                        href={`/workspace/courses/${selectedCourse.id}/tutor`}
                      >
                        Спросить по материалам курса
                      </Link>
                      <div className={styles.inlineNotice}>
                        <strong>Помощник объясняет, а не сдаёт работу за вас</strong>
                        <span>
                          Ответы опираются на источники курса. Для контрольных заданий
                          помощник предложит ход рассуждений вместо готового ответа.
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className={styles.inlineNotice}>
                      <strong>Доступ только для просмотра</strong>
                      <span>Редактирование курса для этой роли недоступно.</span>
                    </div>
                  )}
                </>
              ) : (
                <div className={styles.detailEmpty}>
                  <CourseThread />
                  <p>Выберите курс, чтобы увидеть доступные действия.</p>
                </div>
              )}
              {canOpenLab && (
                <div className={styles.labLink}>
                  <span>Инженерные инструменты</span>
                  <Link href="/">Открыть ML-лабораторию</Link>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </>
  );
}
