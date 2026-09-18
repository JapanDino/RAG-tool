import Head from "next/head";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { ApiRequestError, SESSION_ENDED_EVENT, authenticatedJson } from "../lib/auth-api";
import styles from "../styles/canvas-companion.module.css";


type CourseMapItemType =
  | "page"
  | "assignment"
  | "file"
  | "external"
  | "section"
  | "unsupported";

type CourseMapItem = {
  source_ref: string;
  title: string;
  item_type: CourseMapItemType;
  position: number;
  available: boolean;
  supported: boolean;
  destination_url?: string | null;
  destination_provenance?: "canvas" | "external" | null;
};

type CourseMapModule = {
  id: number;
  source_ref: string;
  title: string;
  position: number;
  items: CourseMapItem[];
};

type CourseMap = {
  version: "1";
  read_only: true;
  exact_context: true;
  course: {
    id: number;
    title: string;
    syllabus_summary?: string | null;
    destination_url?: string | null;
  };
  modules: CourseMapModule[];
  total_items: number;
  truncated: boolean;
};

type AgentEvidence = {
  evidence_ref: string;
  title: string;
  excerpt: string;
  module_title?: string | null;
  open_url?: string | null;
  source_label?: string | null;
  provenance?: "canvas" | "external" | null;
};

type AgentRun = {
  run_id: string;
  status: "queued" | "routing" | "tool_running" | "generating" | "completed" | "abstained" | "failed";
  user_state: { label: string; recovery_action?: string | null };
  response?: {
    mode: "answer" | "guidance" | "self_check" | "abstained" | "source_action" | "workflow_plan";
    content?: string;
    confidence?: { band: "supported" | "partial" | "insufficient"; explanation: string };
    evidence?: AgentEvidence[];
    title?: string;
    label?: string;
    open_url?: string;
    provenance?: "canvas" | "external";
    feedback_url?: string;
  } | null;
};

type AgentAccepted = {
  status_url: string;
  execute_url: string;
  conversation_id: string;
};
type AgentStage = "idle" | "submitting" | AgentRun["status"];
type AgentAction = {
  message: string;
  sourceTask: boolean;
  selection?: { module_ref: string; evidence_ref?: string };
  materialTitle: string | null;
  moduleTitle: string | null;
};
type AgentTurn = {
  id: string;
  action: AgentAction;
  run: AgentRun;
};
type ActionError = {
  kind: "agent" | "feedback" | "delete";
  message: string;
  feedbackStatus?: "helpful" | "unhelpful";
  feedbackRunId?: string;
  feedbackUrl?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const MAX_SESSION_TURNS = 8;

function materialWord(count: number) {
  const lastTwo = count % 100;
  if (lastTwo >= 11 && lastTwo <= 14) return "материалов";
  const last = count % 10;
  if (last === 1) return "материал";
  if (last >= 2 && last <= 4) return "материала";
  return "материалов";
}
const ITEM_LABELS: Record<CourseMapItemType, string> = {
  page: "Страница",
  assignment: "Задание",
  file: "Файл",
  external: "Внешний источник",
  section: "Раздел",
  unsupported: "Материал Canvas",
};

function ItemMark({ type }: { type: CourseMapItemType }) {
  const glyphs: Record<CourseMapItemType, string> = {
    page: "¶",
    assignment: "✓",
    file: "↓",
    external: "↗",
    section: "§",
    unsupported: "?",
  };
  return <span className={styles.itemMark} data-type={type} aria-hidden="true">{glyphs[type]}</span>;
}

function turnLabel(run: AgentRun) {
  if (run.response?.mode === "guidance") return "Подсказка";
  if (run.response?.mode === "self_check") return "Самопроверка";
  if (run.response?.mode === "source_action") return "Источник";
  if (run.status === "abstained") return "Недостаточно данных";
  if (run.status === "failed") return "Не завершено";
  return "Объяснение";
}

function Boundary({ status, retry }: { status: number | null; retry: () => void }) {
  const expired = status === 401;
  const unavailable = status === 404;
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => { headingRef.current?.focus(); }, []);
  return (
    <main className={styles.boundary} role="alert" aria-live="assertive">
      <span className={styles.boundaryMark} aria-hidden="true">{expired ? "↺" : unavailable ? "—" : "!"}</span>
      <p>{expired ? "Сеанс завершён" : unavailable ? "Помощник здесь недоступен" : "Маршрут не загрузился"}</p>
      <h1 ref={headingRef} tabIndex={-1}>
        {expired
          ? "Откройте помощника ещё раз из курса Canvas"
          : unavailable
            ? "Вернитесь в текущий курс Canvas"
            : "Проверьте соединение и попробуйте снова"}
      </h1>
      <span>
        {expired || unavailable
          ? "Название и материалы курса не показываются, пока доступ не подтверждён."
          : "Ваши действия не потеряны — курс можно загрузить повторно."}
      </span>
      {!expired && !unavailable && <button type="button" onClick={retry}>Загрузить снова</button>}
    </main>
  );
}

export default function CanvasCompanionPage() {
  const [courseMap, setCourseMap] = useState<CourseMap | null>(null);
  const [selectedRef, setSelectedRef] = useState("");
  const [loading, setLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [question, setQuestion] = useState("");
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [agentTurns, setAgentTurns] = useState<AgentTurn[]>([]);
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState("");
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentStage, setAgentStage] = useState<AgentStage>("idle");
  const [actionError, setActionError] = useState<ActionError | null>(null);
  const [lastAgentAction, setLastAgentAction] = useState<AgentAction | null>(null);
  const [feedbackByRun, setFeedbackByRun] = useState<Record<string, "helpful" | "unhelpful">>({});
  const [feedbackBusyRun, setFeedbackBusyRun] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [historyDeleted, setHistoryDeleted] = useState(false);

  useEffect(() => {
    const endSession = () => {
      setCourseMap(null);
      setErrorStatus(401);
      setAgentRun(null);
      setAgentTurns([]);
      setActiveTurnId(null);
      setConversationId("");
      setQuestion("");
      setAgentStage("idle");
      setLastAgentAction(null);
      setFeedbackByRun({});
      setFeedbackBusyRun(null);
      setDeleteConfirm(false);
      setHistoryDeleted(false);
      setActionError(null);
    };
    window.addEventListener(SESSION_ENDED_EVENT, endSession);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, endSession);
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setErrorStatus(null);
    authenticatedJson<CourseMap>(API_BASE, "/course-map", "")
      .then((payload) => {
        if (!active) return;
        setCourseMap(payload);
        const first = payload.modules
          .flatMap((module) => module.items)
          .find((item) => item.item_type !== "section");
        setSelectedRef(first?.source_ref || "");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setCourseMap(null);
        setErrorStatus(error instanceof ApiRequestError ? error.status : 0);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [reloadKey]);

  const flatItems = useMemo(
    () => courseMap?.modules.flatMap((module) => module.items) || [],
    [courseMap]
  );
  const selected = flatItems.find((item) => item.source_ref === selectedRef) || null;
  const selectedModule = courseMap?.modules.find((module) =>
    module.items.some((item) => item.source_ref === selectedRef)
  );
  const activeTurn = agentTurns.find((turn) => turn.id === activeTurnId) || null;
  function selectMaterial(sourceRef: string) {
    if (
      sourceRef === selectedRef ||
      agentBusy ||
      deleteBusy ||
      deleteConfirm ||
      Boolean(feedbackBusyRun)
    ) return;
    setSelectedRef(sourceRef);
    setAgentRun(null);
    setActiveTurnId(null);
    setAgentStage("idle");
    setActionError(null);
    setLastAgentAction(null);
  }

  function handleBoundaryError(error: unknown) {
    if (error instanceof ApiRequestError && [401, 404].includes(error.status)) {
      setCourseMap(null);
      setErrorStatus(error.status);
      setAgentRun(null);
      setAgentTurns([]);
      setActiveTurnId(null);
      setConversationId("");
      setQuestion("");
      setAgentStage("idle");
      setLastAgentAction(null);
      setFeedbackByRun({});
      setFeedbackBusyRun(null);
      setDeleteConfirm(false);
      setHistoryDeleted(false);
      setActionError(null);
      return true;
    }
    return false;
  }

  async function askAgent(
    messageOverride?: string,
    sourceTask = false,
    actionOverride?: AgentAction,
  ) {
    const normalized = (actionOverride?.message ?? messageOverride ?? question).trim();
    if (
      !normalized ||
      agentBusy ||
      deleteBusy ||
      deleteConfirm ||
      Boolean(feedbackBusyRun) ||
      (!actionOverride && !sourceTask && !selected?.supported) ||
      (!actionOverride && sourceTask && !selected?.destination_url)
    ) return;
    const action: AgentAction = actionOverride || {
      message: normalized,
      sourceTask,
      selection: selectedModule ? {
        module_ref: selectedModule.source_ref,
        ...(sourceTask && selected ? { evidence_ref: selected.source_ref } : {}),
      } : undefined,
      materialTitle: selected?.title || null,
      moduleTitle: selectedModule?.title || null,
    };
    setLastAgentAction(action);
    setAgentBusy(true);
    setActionError(null);
    setAgentRun(null);
    setActiveTurnId(null);
    setAgentStage("submitting");
    setHistoryDeleted(false);
    try {
      const requestId = crypto.randomUUID();
      const requestBody = {
        contract_version: "agent.v1" as const,
        message: normalized,
        client_request_id: requestId,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        ...(action.selection ? { selection: action.selection } : {}),
      };
      const accepted = await authenticatedJson<AgentAccepted>(API_BASE, "/agent/v1/messages", "", {
        method: "POST",
        headers: { "Idempotency-Key": requestId },
        body: JSON.stringify(requestBody),
      });
      setConversationId(accepted.conversation_id);
      setQuestion("");
      setAgentStage("queued");
      await new Promise((resolve) => window.setTimeout(resolve, 140));
      let current: AgentRun | null = null;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        current = await authenticatedJson<AgentRun>(API_BASE, accepted.execute_url, "", {
          method: "POST",
          body: JSON.stringify(requestBody),
        });
        setAgentStage(current.status);
        setAgentRun(current);
        if (["completed", "abstained", "failed"].includes(current.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 180));
      }
      if (!current || !["completed", "abstained", "failed"].includes(current.status)) {
        throw new Error("Ответ занял больше времени, чем ожидалось. Попробуйте ещё раз.");
      }
      const completedTurn: AgentTurn = {
        id: current.run_id,
        action,
        run: current,
      };
      setAgentTurns((turns) => [
        ...turns.filter((turn) => turn.id !== completedTurn.id),
        completedTurn,
      ].slice(-MAX_SESSION_TURNS));
      setActiveTurnId(completedTurn.id);
    } catch (error) {
      setAgentStage("failed");
      if (!handleBoundaryError(error)) {
        setQuestion("");
        setActionError({
          kind: "agent",
          message: error instanceof Error ? error.message : "Ответ сейчас не подготовился.",
        });
      }
    } finally {
      setAgentBusy(false);
    }
  }

  async function rateAgent(
    runId: string,
    feedbackUrl: string,
    status: "helpful" | "unhelpful",
  ) {
    if (feedbackBusyRun || agentBusy || deleteBusy || deleteConfirm) return;
    setFeedbackBusyRun(runId);
    setActionError(null);
    try {
      await authenticatedJson<{ status: "helpful" | "unhelpful" }>(API_BASE, feedbackUrl, "", {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setFeedbackByRun((current) => ({ ...current, [runId]: status }));
    } catch (error) {
      if (!handleBoundaryError(error)) {
        setActionError({
          kind: "feedback",
          message: error instanceof Error ? error.message : "Оценка ответа не сохранилась.",
          feedbackStatus: status,
          feedbackRunId: runId,
          feedbackUrl,
        });
      }
    } finally {
      setFeedbackBusyRun(null);
    }
  }

  async function deleteHistory() {
    if (deleteBusy || agentBusy || Boolean(feedbackBusyRun) || !deleteConfirm) return;
    setDeleteBusy(true);
    setActionError(null);
    try {
      await authenticatedJson(API_BASE, `/courses/${courseMap?.course.id}/qa/history`, "", {
        method: "DELETE",
        body: JSON.stringify({ confirmation: "delete_my_tutor_history" }),
      });
      setAgentRun(null);
      setAgentTurns([]);
      setActiveTurnId(null);
      setConversationId("");
      setQuestion("");
      setAgentStage("idle");
      setFeedbackByRun({});
      setFeedbackBusyRun(null);
      setLastAgentAction(null);
      setDeleteConfirm(false);
      setHistoryDeleted(true);
    } catch (error) {
      if (!handleBoundaryError(error)) {
        setActionError({
          kind: "delete",
          message: error instanceof Error ? error.message : "История не удалилась.",
        });
      }
    } finally {
      setDeleteBusy(false);
    }
  }

  if (loading) {
    return (
      <main className={styles.loading} aria-busy="true" aria-live="polite">
        <div aria-hidden="true"><i/><i/><i/></div>
        <span>Собираем маршрут текущего курса…</span>
      </main>
    );
  }
  if (!courseMap) {
    return <Boundary status={errorStatus} retry={() => setReloadKey((value) => value + 1)}/>;
  }

  return (
    <>
      <Head>
        <title>{courseMap.course.title} — Помощник курса</title>
        <meta name="robots" content="noindex,nofollow"/>
      </Head>
      <main className={styles.page}>
        <header className={styles.hero}>
          <div className={styles.heroCopy}>
            <span className={styles.location}><i aria-hidden="true">К</i> Вы в курсе Canvas</span>
            <h1>{courseMap.course.title}</h1>
            <p>{courseMap.course.syllabus_summary || "Выберите материал в знакомом порядке курса или задайте вопрос по опубликованным источникам."}</p>
          </div>
          <aside className={styles.courseTicket} aria-label="Текущий курс подтверждён">
            <span>Помощник курса</span>
            <strong>Маршрут открыт</strong>
            <small><i aria-hidden="true">✓</i> Текущий курс подтверждён</small>
          </aside>
        </header>

        <nav className={styles.actions} aria-label="Основные действия">
          {courseMap.course.destination_url && (
            <a
              className={styles.primaryAction}
              href={courseMap.course.destination_url}
              target="_top"
            >
              <span>Продолжить по курсу</span>
              <small>Открыть текущий курс в Canvas</small>
            </a>
          )}
          <a
            className={styles.askAction}
            href="#course-assistant"
          >
            <span>Задать вопрос здесь</span>
            <small>{selectedModule ? `Помощник уже ограничен разделом «${selectedModule.title}»` : "Получить объяснение с источниками"}</small>
          </a>
          {selected?.destination_url && (
            <a
              className={styles.sourceAction}
              href={selected.destination_url}
              target={selected.destination_provenance === "external" ? "_blank" : "_top"}
              rel={selected.destination_provenance === "external" ? "noopener noreferrer" : undefined}
            >
              <span>{selected.destination_provenance === "external" ? "Открыть вне Canvas ↗" : "Открыть источник"}</span>
              <small>{selected.title}</small>
            </a>
          )}
        </nav>

        {courseMap.modules.length === 0 ? (
          <section className={styles.empty}>
            <span aria-hidden="true">○</span>
            <h2>В маршруте пока нет доступных материалов</h2>
            <p>Вернитесь в модули Canvas или уточните у преподавателя, когда откроется следующий раздел.</p>
          </section>
        ) : (
          <div className={styles.workspace}>
            <section className={styles.route} aria-labelledby="route-title">
              <header>
                <div><span>Карта курса</span><h2 id="route-title">Идите по знакомому порядку</h2></div>
                <strong>{courseMap.total_items} {materialWord(courseMap.total_items)}</strong>
              </header>
              {courseMap.modules.map((module, moduleIndex) => (
                <article className={styles.module} key={module.source_ref}>
                  <div className={styles.moduleHeading}>
                    <i aria-hidden="true">{String(moduleIndex + 1).padStart(2, "0")}</i>
                    <h3>{module.title}</h3>
                  </div>
                  <ul>
                    {module.items.map((item) => item.item_type === "section" ? (
                      <li className={styles.sectionRow} key={item.source_ref}>
                        <ItemMark type={item.item_type}/>
                        <span><strong>{item.title}</strong><small>{ITEM_LABELS[item.item_type]}</small></span>
                      </li>
                    ) : (
                      <Fragment key={item.source_ref}>
                        <li>
                          <button
                            type="button"
                            className={styles.itemButton}
                            data-selected={selectedRef === item.source_ref}
                            onClick={() => selectMaterial(item.source_ref)}
                            aria-pressed={selectedRef === item.source_ref}
                            disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun)}
                          >
                            <ItemMark type={item.item_type}/>
                            <span><strong>{item.title}</strong><small>{ITEM_LABELS[item.item_type]}</small></span>
                            {item.destination_provenance === "external" && <em>вне Canvas ↗</em>}
                          </button>
                        </li>
                        {selectedRef === item.source_ref && (
                          <li className={styles.mobileInlineAction}>
                            <a className={styles.mobileSelectedAsk} href="#course-assistant">
                              <strong>Задать вопрос по выбранному разделу</strong>
                              <small>{module.title}</small>
                            </a>
                          </li>
                        )}
                      </Fragment>
                    ))}
                  </ul>
                </article>
              ))}
              {courseMap.truncated && <p className={styles.truncated}>Показана первая часть большого маршрута. Остальные материалы остаются в модулях Canvas.</p>}
            </section>

            <aside className={styles.material} id="course-assistant">
              <span className={styles.materialEyebrow}>Помощник по курсу</span>
              {selected ? (
                <>
                  <div className={styles.pinnedMaterial}>
                    <ItemMark type={selected.item_type}/>
                    <span><small>{ITEM_LABELS[selected.item_type]}</small><strong>{selected.title}</strong></span>
                  </div>
                  {selected.supported ? (
                    <div className={styles.supported}><i aria-hidden="true">✓</i><span><strong>Граница вопроса закреплена</strong><small>Поиск ограничен разделом «{selectedModule?.title}». Если опоры не хватит, помощник так и скажет.</small></span></div>
                  ) : (
                    <div className={styles.unsupported}><i aria-hidden="true">?</i><span><strong>Тип пока не поддерживается</strong><small>Материал не будет выдан за обычную страницу. Если ссылка доступна, откройте оригинал в Canvas.</small></span></div>
                  )}
                  {!selected.destination_url && (
                    <p className={styles.noLink}>Безопасной ссылки на этот материал нет. Откройте его из списка модулей Canvas.</p>
                  )}
                </>
              ) : (
                <div className={styles.pickPrompt}><i aria-hidden="true">←</i><strong>Выберите материал слева</strong><p>Здесь появится понятный тип и ссылка на исходную страницу.</p></div>
              )}
              <section className={styles.conversation} aria-labelledby="conversation-title">
                <header>
                  <div>
                    <span>Диалог этой сессии</span>
                    <h2 id="conversation-title">Вопросы по маршруту курса</h2>
                  </div>
                  <strong>{agentTurns.length}/{MAX_SESSION_TURNS}</strong>
                </header>
                <p className={styles.memoryBoundary}>
                  Каждый вопрос проверяется заново по текущему разделу. Предыдущий текст
                  не отправляется модели скрыто.
                </p>
                {agentTurns.length ? (
                  <ol className={styles.turnList} aria-label="Вопросы этой сессии">
                    {agentTurns.map((turn, index) => (
                      <li key={turn.id}>
                        <button
                          type="button"
                          data-active={activeTurnId === turn.id}
                          aria-pressed={activeTurnId === turn.id}
                          disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun)}
                          onClick={() => {
                            setAgentRun(turn.run);
                            setActiveTurnId(turn.id);
                            setActionError(null);
                          }}
                        >
                          <i aria-hidden="true">{String(index + 1).padStart(2, "0")}</i>
                          <span>
                            <small>
                              {turn.action.moduleTitle || "Текущий курс"}
                              {turn.action.materialTitle ? ` · ${turn.action.materialTitle}` : ""}
                            </small>
                            <b>{turn.action.message}</b>
                          </span>
                          <em>{turnLabel(turn.run)}</em>
                        </button>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <div className={styles.emptyConversation}>
                    Первый вопрос станет началом маршрута. Ответ останется рядом с той
                    частью курса, по которой вы спрашивали.
                  </div>
                )}
              </section>
              <form className={styles.agentForm} onSubmit={(event) => { event.preventDefault(); void askAgent(); }}>
                <label htmlFor="course-agent-question">Что нужно разобрать?</label>
                <textarea
                  id="course-agent-question"
                  value={question}
                  maxLength={1000}
                  onChange={(event) => {
                    setQuestion(event.target.value);
                    if (actionError?.kind === "agent") setActionError(null);
                  }}
                  placeholder="Например: почему найденные фрагменты помогают сформировать ответ?"
                  disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun) || !selected?.supported}
                />
                <div className={styles.starters} aria-label="Быстрые варианты вопроса">
                  <button
                    type="button"
                    disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun) || !selected?.supported}
                    onClick={() => void askAgent(`Дай подсказку по материалу «${selected?.title || "выбранный материал"}», но не готовый ответ на задание`)}
                  >Получить подсказку</button>
                  <button
                    type="button"
                    disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun) || !selected?.supported}
                    onClick={() => void askAgent(`Проверь меня по материалу «${selected?.title || "выбранный материал"}» без оценки`)}
                  >Проверить себя</button>
                  <button
                    type="button"
                    disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun) || !selected?.destination_url}
                    onClick={() => void askAgent("Открой источник этого материала", true)}
                  >Открыть источник</button>
                </div>
                <button className={styles.askButton} type="submit" disabled={agentBusy || deleteBusy || deleteConfirm || Boolean(feedbackBusyRun) || !question.trim() || !selected?.supported}>
                  {agentBusy ? "Ищем опору в курсе…" : "Разобраться"}
                </button>
              </form>

              <div className={styles.agentResult} aria-live="polite" aria-busy={agentBusy}>
                {actionError && (
                  <div className={styles.agentError} role="alert">
                    <strong>{actionError.kind === "feedback" ? "Оценка не сохранилась" : actionError.kind === "delete" ? "История не удалилась" : "Ответ не подготовился"}</strong>
                    <span>{actionError.message}</span>
                    <button
                      type="button"
                      onClick={() => {
                        if (
                          actionError.kind === "feedback" &&
                          actionError.feedbackStatus &&
                          actionError.feedbackRunId &&
                          actionError.feedbackUrl
                        ) {
                          void rateAgent(
                            actionError.feedbackRunId,
                            actionError.feedbackUrl,
                            actionError.feedbackStatus,
                          );
                        }
                        else if (actionError.kind === "delete") void deleteHistory();
                        else if (lastAgentAction) void askAgent(undefined, false, lastAgentAction);
                      }}
                    >Попробовать снова</button>
                  </div>
                )}
                {agentBusy && !["completed", "abstained", "failed"].includes(agentStage) && (
                  <section className={styles.agentProgress} data-stage={agentStage} role="status">
                    <span className={styles.resultLabel}>Помощник работает в границах курса</span>
                    <h2>{agentStage === "submitting" ? "Передаём вопрос помощнику" : agentStage === "queued" ? "Запрос принят" : agentStage === "routing" ? "Проверяем доступ к материалу" : agentStage === "tool_running" ? "Проверяем выбранный источник" : "Ищем опору в разделе"}</h2>
                    <p>{agentStage === "submitting" ? "Текст ещё не принят — дождитесь подтверждения." : agentStage === "queued" ? "Сейчас начнём с выбранного материала." : agentStage === "routing" ? "Уточняем курс, роль и доступность раздела." : agentStage === "tool_running" ? "Ссылка откроется только после повторной проверки." : "Собираем ответ только из доступных материалов курса."}</p>
                    <div className={styles.progressTrack} aria-hidden="true"><i/><i/><i/></div>
                  </section>
                )}
                {agentRun && ["completed", "abstained", "failed"].includes(agentRun.status) && (
                  <section data-mode={agentRun.response?.mode || agentRun.status}>
                    <span className={styles.resultLabel}>{agentRun.response?.mode === "guidance" ? "Подсказка без готового ответа" : agentRun.response?.mode === "self_check" ? "Самопроверка без оценки" : agentRun.response?.mode === "source_action" ? "Проверенный переход" : agentRun.status === "abstained" ? "Нужна другая опора" : agentRun.status === "failed" ? "Сбой помощника" : "Объяснение по материалам"}</span>
                    <h2>{agentRun.user_state.label}</h2>
                    {agentRun.response?.content && <p className={styles.answerText}>{agentRun.response.content}</p>}
                    {agentRun.response?.confidence && <p className={styles.confidence} data-band={agentRun.response.confidence.band}>{agentRun.response.confidence.explanation}</p>}
                    {!!agentRun.response?.evidence?.length && (
                      <div className={styles.evidenceList}>
                        <h3>Опора в курсе</h3>
                        {agentRun.response.evidence.map((item) => (
                          <blockquote key={item.evidence_ref}>
                            <strong>{item.title}</strong>
                            {item.module_title && <small>{item.module_title}</small>}
                            <p>{item.excerpt}</p>
                            {item.open_url && (
                              <a
                                className={styles.evidenceSource}
                                href={`${API_BASE}${item.open_url}`}
                                target={item.provenance === "external" ? "_blank" : "_top"}
                                rel={item.provenance === "external" ? "noopener noreferrer" : undefined}
                              >{item.source_label || "Открыть источник"}</a>
                            )}
                          </blockquote>
                        ))}
                      </div>
                    )}
                    {agentRun.response?.mode === "source_action" && agentRun.response.open_url && (
                      <a
                        className={styles.openSourceButton}
                        href={`${API_BASE}${agentRun.response.open_url}`}
                        target={agentRun.response.provenance === "external" ? "_blank" : "_top"}
                        rel={agentRun.response.provenance === "external" ? "noopener noreferrer" : undefined}
                      >{agentRun.response.label || "Открыть источник"}</a>
                    )}
                    {agentRun.response?.feedback_url && (
                      <div className={styles.feedbackActions} aria-label="Оценка ответа помощника">
                        <span>Помогло разобраться?</span>
                        <button
                          type="button"
                          aria-pressed={feedbackByRun[agentRun.run_id] === "helpful"}
                          disabled={Boolean(feedbackBusyRun) || agentBusy || deleteBusy || deleteConfirm}
                          onClick={() => void rateAgent(agentRun.run_id, agentRun.response!.feedback_url!, "helpful")}
                        >Да, помогло</button>
                        <button
                          type="button"
                          aria-pressed={feedbackByRun[agentRun.run_id] === "unhelpful"}
                          disabled={Boolean(feedbackBusyRun) || agentBusy || deleteBusy || deleteConfirm}
                          onClick={() => void rateAgent(agentRun.run_id, agentRun.response!.feedback_url!, "unhelpful")}
                        >Не помогло</button>
                      </div>
                    )}
                    {!agentRun.response?.content && agentRun.response?.mode !== "source_action" && <p className={styles.recoveryText}>Попробуйте выбрать другой материал или сформулировать вопрос точнее.</p>}
                    {agentRun.status === "failed" && activeTurn && (
                      <button className={styles.retryAgentButton} type="button" onClick={() => void askAgent(undefined, false, activeTurn.action)}>Повторить этот запрос</button>
                    )}
                  </section>
                )}
              </div>
              <div className={styles.dataControls}>
                {historyDeleted && <p role="status">История помощника удалена.</p>}
                {!deleteConfirm ? (
                  <button type="button" disabled={agentBusy || Boolean(feedbackBusyRun)} onClick={() => setDeleteConfirm(true)}>Удалить мою историю помощника</button>
                ) : (
                  <div role="group" aria-label="Подтверждение удаления истории">
                    <strong>Удалить вопросы, ответы и оценки этого курса?</strong>
                    <button type="button" disabled={deleteBusy || agentBusy || Boolean(feedbackBusyRun)} onClick={() => void deleteHistory()}>{deleteBusy ? "Удаляем…" : "Да, удалить"}</button>
                    <button
                      type="button"
                      disabled={deleteBusy || agentBusy || Boolean(feedbackBusyRun)}
                      onClick={() => {
                        setDeleteConfirm(false);
                        if (actionError?.kind === "delete") setActionError(null);
                      }}
                    >Отмена</button>
                  </div>
                )}
              </div>
              <footer>Помощник не видит оценки, работы других учеников и скрытые материалы.</footer>
            </aside>
          </div>
        )}
      </main>
    </>
  );
}
