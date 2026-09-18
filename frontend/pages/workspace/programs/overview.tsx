import Head from "next/head";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import styles from "../../../styles/program-overview.module.css";

type RouteState =
  | "not_started"
  | "mapping_gap"
  | "assessment_gap"
  | "declared_assessment_complete";

type IdentityContext = {
  user: { display_name: string };
  organizations: { id: number; name: string; role: string }[];
};

type ProgramOverviewItem = {
  program_id: number;
  program_code: string;
  program_title: string;
  program_version: number;
  updated_at?: string | null;
  course_count: number;
  competency_count: number;
  mapped_competency_count: number;
  assessed_competency_count: number;
  unmapped_competency_count: number;
  without_assessment_count: number;
  route_state: RouteState;
  route_state_label: string;
  confidence_label: string;
  review_status: "not_reviewed";
};

type ProgramOverview = {
  organization_id: number;
  analysis_truncated: boolean;
  totals: {
    programs: number;
    courses: number;
    competencies: number;
    mapped_competencies: number;
    assessed_competencies: number;
    programs_requiring_review: number;
    programs_not_started: number;
  };
  programs: ProgramOverviewItem[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const IDENTITY_STORAGE_KEY = "rag-dev-user";

async function api<T>(path: string, identity: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "X-Dev-User": identity },
  });
  if (!response.ok) {
    let message = `Не удалось выполнить запрос (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message =
        typeof detail === "string" ? detail : detail?.message || message;
    } catch {
      // Status copy remains safe when the API does not return JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

function countCopy(count: number, one: string, few: string, many: string) {
  const modulo100 = count % 100;
  const modulo10 = count % 10;
  if (modulo100 >= 11 && modulo100 <= 14) return `${count} ${many}`;
  if (modulo10 === 1) return `${count} ${one}`;
  if (modulo10 >= 2 && modulo10 <= 4) return `${count} ${few}`;
  return `${count} ${many}`;
}

function stateDetail(item: ProgramOverviewItem) {
  if (item.route_state === "not_started") {
    return "В сохранённой карте пока нет одновременно курса и компетенции для проверки маршрута.";
  }
  if (item.route_state === "mapping_gap") {
    return countCopy(
      item.unmapped_competency_count,
      "компетенция ещё не связана с курсом",
      "компетенции ещё не связаны с курсом",
      "компетенций ещё не связаны с курсом"
    );
  }
  if (item.route_state === "assessment_gap") {
    return countCopy(
      item.without_assessment_count,
      "компетенция без заявленной проверки",
      "компетенции без заявленной проверки",
      "компетенций без заявленной проверки"
    );
  }
  return "По сводке каждой компетенции соответствует заявленная проверка. Это не заключение о качестве содержания.";
}

function ProgramThread({ item }: { item: ProgramOverviewItem }) {
  const mappedOnly = Math.max(
    item.mapped_competency_count - item.assessed_competency_count,
    0
  );
  const empty = item.competency_count === 0;
  const label = empty
    ? "Компетенции ещё не добавлены"
    : `${item.assessed_competency_count} с заявленной проверкой; ${mappedOnly} только связаны с курсом; ${item.unmapped_competency_count} без курса`;

  return (
    <div className={styles.programThread} aria-label={label} role="img">
      {empty ? (
        <span className={styles.threadEmpty} />
      ) : (
        <>
          {item.assessed_competency_count ? (
            <span
              className={styles.threadAssessed}
              style={{ flexGrow: item.assessed_competency_count }}
            />
          ) : null}
          {mappedOnly ? (
            <span
              className={styles.threadMapped}
              style={{ flexGrow: mappedOnly }}
            />
          ) : null}
          {item.unmapped_competency_count ? (
            <span
              className={styles.threadUnmapped}
              style={{ flexGrow: item.unmapped_competency_count }}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

export default function ProgramAdministrationOverview() {
  const [identity, setIdentity] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationId, setOrganizationId] = useState<number | null>(null);
  const [organizationName, setOrganizationName] = useState("");
  const [overview, setOverview] = useState<ProgramOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");

  const loadOverview = useCallback(
    async (orgId: number, userIdentity: string, refresh = false) => {
      if (refresh) setRefreshing(true);
      setError("");
      try {
        const value = await api<ProgramOverview>(
          `/organizations/${orgId}/program-administration-overview`,
          userIdentity
        );
        setOverview(value);
      } catch (reason) {
        setError(
          `Сводку программ загрузить не удалось. ${
            refresh ? "Предыдущие данные сохранены. " : ""
          }${reason instanceof Error ? reason.message : String(reason)}`
        );
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
        const search = new URLSearchParams(window.location.search);
        const organizationParam = search.get("organization");
        const requestedOrganizationId = Number(organizationParam);
        const hasExplicitOrganization = organizationParam !== null;
        const validRequestedOrganization =
          Number.isInteger(requestedOrganizationId) && requestedOrganizationId > 0;
        const organization = hasExplicitOrganization
          ? validRequestedOrganization
            ? context.organizations.find(
                (item) =>
                  item.id === requestedOrganizationId &&
                  item.role === "administrator"
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
        await loadOverview(organization.id, storedIdentity);
      } catch (reason) {
        setError(
          `Обзор программ не открылся. ${
            reason instanceof Error ? reason.message : String(reason)
          }`
        );
        setLoading(false);
      }
    })();
  }, [loadOverview]);

  if (accessDenied) {
    return (
      <main className={styles.permissionPage}>
        <span>Доступ к портфелю программ</span>
        <h1>Обзор организации недоступен</h1>
        <p>
          Сводный портфель открывает администратор организации. Недоступные
          программы и их названия здесь не раскрываются.
        </p>
        <Link href="/workspace">Вернуться в рабочее пространство</Link>
      </main>
    );
  }

  return (
    <>
      <Head>
        <title>Обзор программ — Контур</title>
        <meta
          name="description"
          content="Агрегированная структурная сводка образовательных программ"
        />
      </Head>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brandBlock}>
            <Link href="/workspace" aria-label="Контур обучения">
              К
            </Link>
            <div>
              <strong>Контур организации</strong>
              <span>{organizationName || "Рабочая организация"}</span>
            </div>
          </div>
          <div className={styles.headerThread} aria-hidden="true">
            <i />
            <span />
            <i />
            <span />
            <i />
          </div>
          <div className={styles.identityBlock}>
            <span>Администратор</span>
            <strong>{displayName || "Проверяем доступ…"}</strong>
          </div>
        </header>

        <main className={styles.main} aria-busy={loading || refreshing}>
          <nav className={styles.breadcrumbs} aria-label="Навигационная цепочка">
            <Link href="/workspace">Рабочее пространство</Link>
            <span>/</span>
            <span>Обзор программ</span>
          </nav>

          <section className={styles.hero} aria-labelledby="overview-title">
            <div>
              <span>Портфель учебных маршрутов</span>
              <h1 id="overview-title">Где нужна методическая сверка</h1>
              <p>
                Сводка показывает только сохранённые связи между программами,
                курсами, компетенциями и заявленными проверками.
              </p>
            </div>
            <div className={styles.heroActions}>
              <button
                type="button"
                onClick={() =>
                  organizationId && void loadOverview(organizationId, identity, true)
                }
                disabled={!organizationId || loading || refreshing}
              >
                {refreshing ? "Обновляем сводку…" : "Обновить сводку"}
              </button>
              <Link href="/workspace/programs">Открыть карту программ</Link>
            </div>
          </section>

          <aside className={styles.boundary}>
            <strong>Не рейтинг и не оценка сотрудников</strong>
            <span>
              Структурный сигнал помогает выбрать карту для просмотра. Он ничего
              не говорит об успеваемости учеников или качестве работы преподавателя.
            </span>
          </aside>

          {error ? (
            <div className={styles.errorNotice} role="alert">
              <div>
                <strong>Сводка не обновилась</strong>
                <span>{error}</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (organizationId) {
                    void loadOverview(organizationId, identity, true);
                  } else {
                    window.location.reload();
                  }
                }}
                disabled={refreshing}
              >
                Повторить загрузку
              </button>
            </div>
          ) : null}

          {loading && !overview ? (
            <section className={styles.loadingLedger} role="status">
              <strong>Собираем портфель программ</strong>
              <span>Сверяем только агрегированные данные сохранённых карт.</span>
              <div aria-hidden="true">
                <i />
                <i />
                <i />
              </div>
            </section>
          ) : overview ? (
            <section className={styles.portfolio} aria-labelledby="portfolio-title">
              <div className={styles.summary} aria-live="polite">
                <div>
                  <span>Сводная нить</span>
                  <h2 id="portfolio-title">Программы организации</h2>
                </div>
                <p>
                  <strong>
                    {countCopy(
                      overview.totals.programs,
                      "карта",
                      "карты",
                      "карт"
                    )}
                  </strong>
                  <span>
                    {countCopy(
                      overview.totals.competencies,
                      "компетенция",
                      "компетенции",
                      "компетенций"
                    )}
                  </span>
                  <span>
                    {overview.totals.assessed_competencies} с заявленной проверкой
                  </span>
                </p>
              </div>

              {overview.analysis_truncated ? (
                <div className={styles.truncatedNotice} role="status">
                  Показана ограниченная часть портфеля. Итоги относятся только к
                  видимым программам и не описывают всю организацию.
                </div>
              ) : null}

              {!overview.programs.length ? (
                <div className={styles.emptyState}>
                  <strong>В организации пока нет сохранённых программ</strong>
                  <p>
                    Создайте первую программу и добавьте компетенции — после этого
                    она появится в сводном портфеле.
                  </p>
                  <Link href="/workspace/programs">Создать программу на карте</Link>
                </div>
              ) : (
                <div className={styles.ledger}>
                  {overview.programs.map((item) => {
                    const mappedOnly = Math.max(
                      item.mapped_competency_count -
                        item.assessed_competency_count,
                      0
                    );
                    return (
                      <article
                        className={`${styles.programRow} ${styles[item.route_state]}`}
                        key={item.program_id}
                      >
                        <div className={styles.programIdentity}>
                          <span>{item.program_code}</span>
                          <h3>{item.program_title}</h3>
                          <small>Версия карты {item.program_version}</small>
                        </div>
                        <div className={styles.programSignal}>
                          <strong>{item.route_state_label}</strong>
                          <p>{stateDetail(item)}</p>
                          <ProgramThread item={item} />
                          <div className={styles.threadLegend}>
                            <span>{item.assessed_competency_count} с проверкой</span>
                            <span>{mappedOnly} только связаны</span>
                            <span>{item.unmapped_competency_count} без курса</span>
                          </div>
                        </div>
                        <dl className={styles.programCounts}>
                          <div>
                            <dt>Курсы</dt>
                            <dd>{item.course_count}</dd>
                          </div>
                          <div>
                            <dt>Компетенции</dt>
                            <dd>{item.competency_count}</dd>
                          </div>
                          <div>
                            <dt>Заявленные проверки</dt>
                            <dd>{item.assessed_competency_count}</dd>
                          </div>
                        </dl>
                        <div className={styles.programAction}>
                          <span>{item.confidence_label}</span>
                          <small>
                            Методическое решение в продукте не зафиксировано
                          </small>
                          <Link
                            href={
                              item.competency_count === 0
                                ? `/workspace/programs?organization=${overview.organization_id}&program=${item.program_id}`
                                : `/workspace/programs?organization=${overview.organization_id}&program=${item.program_id}&audit=1`
                            }
                          >
                            {item.competency_count === 0
                              ? "Открыть карту"
                              : "Открыть карту и основания"}
                          </Link>
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          ) : null}
        </main>
      </div>
    </>
  );
}
