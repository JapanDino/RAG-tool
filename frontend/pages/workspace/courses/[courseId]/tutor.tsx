import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import React, { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiRequestError,
  authenticatedJson,
  clearSessionCsrf,
  SESSION_ENDED_EVENT,
} from "../../../../lib/auth-api";
import styles from "../../../../styles/student-tutor.module.css";


type CourseAccess = {
  id: number;
  title: string;
  actions: string[];
};

type IdentityContext = {
  user: { email: string; display_name: string };
  courses: CourseAccess[];
};

type CourseDetail = {
  id: number;
  title: string;
  description: string;
  modules: { id: number; title: string; position: number }[];
};

type TutorCourseMap = {
  modules: {
    id: number;
    title: string;
    items: { source_ref: string; title: string; supported: boolean }[];
  }[];
};

type LaunchSource = {
  moduleId: number;
  moduleTitle: string;
  itemTitle: string;
};

type Citation = {
  source_id: string;
  document_id: number;
  document_title: string;
  module_id?: number | null;
  module_title?: string | null;
  quote: string;
  score: number;
};

type TutorAnswer = {
  id: number;
  course_id: number;
  question: string;
  answer: string;
  citations: Citation[];
  confidence: number;
  generation_provider: string;
  insufficient_context: boolean;
  response_mode: "answer" | "guidance" | "abstained";
  policy_reason?: string | null;
  tutor_policy_version: number;
  tutor_answer_style: "balanced" | "guided" | "concise";
  feedback_status: "unreviewed" | "helpful" | "unhelpful";
  created_at?: string | null;
};

type TutorPolicy = {
  course_id: number;
  enabled: boolean;
  answer_style: "balanced" | "guided" | "concise";
  version: number;
};

type TutorDataPolicy = {
  organization_id: number;
  course_id: number;
  retention_days: 30 | 90 | 180 | 365;
  version: number;
  automatic_purge: boolean;
  student_self_delete: boolean;
};

type TutorDataDeletion = {
  reason: "student_request" | "automatic_retention" | "admin_purge";
  policy_version: number;
  answers_deleted: number;
  feedback_events_deleted: number;
  deleted_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const IDENTITY_STORAGE_KEY = "rag-dev-user";
const STARTERS = [
  "Чем два подхода из текущей темы отличаются друг от друга?",
  "Объясни эту тему на простом примере",
  "Какие понятия мне стоит повторить сначала?",
];
const STYLE_META: Record<TutorPolicy["answer_style"], { label: string; description: string }> = {
  balanced: {
    label: "Объяснить и связать",
    description: "Короткое объяснение с контекстом и источниками.",
  },
  guided: {
    label: "Вести вопросами",
    description: "Опорные шаги и вопрос для самопроверки.",
  },
  concise: {
    label: "Коротко по сути",
    description: "Минимальное полезное объяснение по материалам.",
  },
};

async function api<T>(path: string, identity: string, init?: RequestInit): Promise<T> {
  return authenticatedJson<T>(API_BASE, path, identity, init);
}

function answerMeta(answer: TutorAnswer) {
  if (answer.response_mode === "guidance") {
    return {
      label: "Учебная подсказка",
      title: "Разберём ход решения",
      note: "Помощник распознал запрос готового ответа и оставил работу за вами.",
    };
  }
  if (answer.response_mode === "abstained") {
    return {
      label: "Не хватает опоры",
      title: "В материалах курса нет надёжного ответа",
      note: "Лучше уточнить вопрос или обратиться к преподавателю.",
    };
  }
  return {
    label: "По материалам курса",
    title: "Ответ с проверяемой опорой",
    note: "Сверьте вывод с фрагментами источников ниже.",
  };
}

function confidenceLabel(value: number) {
  if (value >= 0.72) return "Опора достаточно устойчива";
  if (value >= 0.48) return "Есть опора, полезна проверка";
  return "Опора ограничена";
}

export default function StudentTutorPage() {
  const router = useRouter();
  const rawCourseId = router.query.courseId;
  const courseId = Number(Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId);
  const rawModuleId = Array.isArray(router.query.moduleId) ? router.query.moduleId[0] : router.query.moduleId;
  const requestedModuleId = Number(rawModuleId);
  const requestedSourceRef = Array.isArray(router.query.source) ? router.query.source[0] : router.query.source;
  const [identity, setIdentity] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [sessionMode, setSessionMode] = useState(false);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [studentName, setStudentName] = useState("");
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [launchSource, setLaunchSource] = useState<LaunchSource | null>(null);
  const [policy, setPolicy] = useState<TutorPolicy | null>(null);
  const [dataPolicy, setDataPolicy] = useState<TutorDataPolicy | null>(null);
  const [answers, setAnswers] = useState<TutorAnswer[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState<"helpful" | "unhelpful" | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingHistory, setDeletingHistory] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleteSuccess, setDeleteSuccess] = useState("");
  const [focusAnswer, setFocusAnswer] = useState(false);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const answerHeadingRef = useRef<HTMLHeadingElement>(null);
  const deleteTriggerRef = useRef<HTMLButtonElement>(null);
  const deleteDialogRef = useRef<HTMLElement>(null);
  const deleteCancelRef = useRef<HTMLButtonElement>(null);
  const deleteConfirmRef = useRef<HTMLButtonElement>(null);
  const deleteStatusRef = useRef<HTMLDivElement>(null);
  const deleteErrorRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!router.isReady || !Number.isFinite(courseId)) return;
    const launchedFromLti = router.query.lti === "1";
    const storedIdentity = window.localStorage.getItem(IDENTITY_STORAGE_KEY) || "";
    const requestIdentity = launchedFromLti ? "" : storedIdentity;
    setIdentity(requestIdentity);
    setSessionMode(launchedFromLti);
    setAuthReady(true);
    setLoading(true);
    setError("");
    setErrorStatus(null);
    setAccessDenied(false);
    if (!launchedFromLti && !storedIdentity) {
      setAccessDenied(true);
      setLoading(false);
      return;
    }
    try {
      const context = await api<IdentityContext>("/identity/me", requestIdentity);
      const access = context.courses.find((item) => item.id === courseId);
      if (!access?.actions.includes("ask_tutor")) {
        setAccessDenied(true);
        return;
      }
      setStudentName(context.user.display_name);
      const [courseDetail, history, tutorPolicy, tutorDataPolicy, courseMap] = await Promise.all([
        api<CourseDetail>(`/courses/${courseId}`, requestIdentity),
        api<TutorAnswer[]>(`/courses/${courseId}/qa`, requestIdentity),
        api<TutorPolicy>(`/courses/${courseId}/tutor-policy`, requestIdentity),
        api<TutorDataPolicy>(`/courses/${courseId}/tutor-data-policy`, requestIdentity),
        launchedFromLti && Number.isInteger(requestedModuleId) && requestedSourceRef
          ? api<TutorCourseMap>("/course-map", requestIdentity)
          : Promise.resolve(null),
      ]);
      setCourse(courseDetail);
      setPolicy(tutorPolicy);
      setDataPolicy(tutorDataPolicy);
      const requestedModule = courseMap?.modules.find(
        (module) => module.id === requestedModuleId
      );
      const requestedItem = requestedModule?.items.find(
        (item) => item.source_ref === requestedSourceRef && item.supported
      );
      setLaunchSource(
        requestedModule && requestedItem
          ? {
              moduleId: requestedModule.id,
              moduleTitle: requestedModule.title,
              itemTitle: requestedItem.title,
            }
          : null
      );
      setAnswers(history);
      setSelectedId(history[0]?.id || null);
    } catch (reason) {
      if (reason instanceof ApiRequestError) {
        setErrorStatus(reason.status);
        if (launchedFromLti && reason.status === 401) {
          setCourse(null);
          setAnswers([]);
          setSessionEnded(true);
          return;
        }
      }
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [courseId, requestedModuleId, requestedSourceRef, router.isReady, router.query.lti]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!sessionMode) return;
    const endSession = () => {
      setCourse(null);
      setAnswers([]);
      setLoading(false);
      setError("");
      setErrorStatus(null);
      setSessionEnded(true);
    };
    window.addEventListener(SESSION_ENDED_EVENT, endSession);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, endSession);
  }, [sessionMode]);

  const selected = useMemo(
    () => answers.find((item) => item.id === selectedId) || answers[0] || null,
    [answers, selectedId]
  );

  useEffect(() => {
    if (focusAnswer && selected) {
      answerHeadingRef.current?.focus();
      setFocusAnswer(false);
    }
  }, [focusAnswer, selected]);

  useEffect(() => {
    if (!deleteDialogOpen) return;
    deleteCancelRef.current?.focus();
  }, [deleteDialogOpen]);

  useEffect(() => {
    if (deleteDialogOpen && deletingHistory) {
      deleteDialogRef.current?.focus();
    }
  }, [deleteDialogOpen, deletingHistory]);

  useEffect(() => {
    if (deleteSuccess) deleteStatusRef.current?.focus();
  }, [deleteSuccess]);

  useEffect(() => {
    if (deleteError) deleteErrorRef.current?.focus();
  }, [deleteError]);

  const ask = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || asking || !authReady || sessionEnded || !policy?.enabled) return;
    setAsking(true);
    setError("");
    setErrorStatus(null);
    try {
      const created = await api<TutorAnswer>(`/courses/${courseId}/qa`, identity, {
        method: "POST",
        body: JSON.stringify({
          question: trimmed,
          language: "ru",
          top_k: 5,
          ...(launchSource ? { module_id: launchSource.moduleId } : {}),
        }),
      });
      setAnswers((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setSelectedId(created.id);
      setQuestion("");
      setFocusAnswer(true);
    } catch (reason) {
      if (!(reason instanceof ApiRequestError && reason.status === 401)) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      setAsking(false);
    }
  };

  const review = async (status: "helpful" | "unhelpful") => {
    if (!selected || feedbackBusy) return;
    setFeedbackBusy(status);
    setError("");
    try {
      const updated = await api<TutorAnswer>(`/qa/answers/${selected.id}`, identity, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setAnswers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setFeedbackBusy(null);
    }
  };

  const closeDeleteDialog = () => {
    if (deletingHistory) return;
    setDeleteDialogOpen(false);
    window.setTimeout(() => deleteTriggerRef.current?.focus(), 0);
  };

  const handleDeleteDialogKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeDeleteDialog();
      return;
    }
    if (event.key !== "Tab") return;
    if (deletingHistory) {
      event.preventDefault();
      deleteDialogRef.current?.focus();
      return;
    }
    const focusable = [deleteCancelRef.current, deleteConfirmRef.current].filter(
      (item): item is HTMLButtonElement => Boolean(item) && !item?.disabled
    );
    if (!focusable.length) return;
    const currentIndex = focusable.indexOf(document.activeElement as HTMLButtonElement);
    const nextIndex = event.shiftKey
      ? (currentIndex <= 0 ? focusable.length : currentIndex) - 1
      : (currentIndex + 1) % focusable.length;
    event.preventDefault();
    focusable[nextIndex].focus();
  };

  const deleteHistory = async () => {
    if (!authReady || sessionEnded || deletingHistory || asking) return;
    setDeletingHistory(true);
    setDeleteError("");
    setDeleteSuccess("");
    try {
      await api<TutorDataDeletion>(`/courses/${courseId}/qa/history`, identity, {
        method: "DELETE",
        body: JSON.stringify({ confirmation: "delete_my_tutor_history" }),
      });
      setAnswers([]);
      setSelectedId(null);
      setDeleteDialogOpen(false);
      setDeleteSuccess("История удалена. Новые вопросы можно задать в любой момент.");
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : String(reason);
      setDeleteError(`Не удалось удалить историю. Сохранённая история не изменилась. ${detail}`);
    } finally {
      setDeletingHistory(false);
    }
  };

  const logout = async () => {
    if (!sessionMode || loggingOut) return;
    setLoggingOut(true);
    setError("");
    try {
      await api<void>("/identity/session/logout", "", { method: "POST" });
      clearSessionCsrf();
      setSessionEnded(true);
      setCourse(null);
      setAnswers([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoggingOut(false);
    }
  };

  if (sessionEnded) {
    return (
      <div className={styles.statePage} aria-live="polite">
        <div className={styles.stateMark}>Сессия завершена</div>
        <h1>Вы вышли из курса</h1>
        <p>Личная история закрыта на этом устройстве. Чтобы вернуться, снова откройте помощника из Canvas.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.statePage} role="status" aria-live="polite" aria-busy="true">
        <span className={styles.loader} />
        <p>Проверяем доступ и собираем учебный контекст курса…</p>
      </div>
    );
  }

  if (accessDenied) {
    return (
      <div className={styles.statePage}>
        <div className={styles.stateMark}>Доступ</div>
        <h1>Учебный помощник недоступен</h1>
        <p>{sessionMode ? "Сессия завершилась или курс больше не назначен. Снова откройте помощника из Canvas." : "Выберите роль, которой назначен этот курс. Скрытые данные курса не раскрываются."}</p>
        {!sessionMode && <Link href="/workspace">Вернуться к курсам</Link>}
      </div>
    );
  }

  if (error && !course) {
    return (
      <div className={styles.statePage} role="alert">
        <div className={styles.stateMark}>{errorStatus === 404 ? "Доступ" : "Связь с курсом"}</div>
        <h1>{errorStatus === 404 ? "Учебный помощник недоступен" : "Не удалось открыть учебный контекст"}</h1>
        <p>{error} Личная история и предыдущие вопросы не изменены.</p>
        <button type="button" onClick={() => void load()}>Повторить</button>
        {!sessionMode && <Link href="/workspace">Вернуться к курсам</Link>}
      </div>
    );
  }

  const meta = selected ? answerMeta(selected) : null;

  return (
    <>
      <Head>
        <title>{course ? `${course.title} — учебный помощник` : "Учебный помощник"}</title>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <meta
          name="description"
          content="Учебный помощник с ответами и источниками только по материалам курса"
        />
      </Head>
      <div className={styles.page}>
        <header className={styles.header}>
          {sessionMode ? (
            <span className={styles.canvasContext}><i /> Доступ через Canvas</span>
          ) : (
            <Link href="/workspace" className={styles.backLink}>← Все курсы</Link>
          )}
          <div className={styles.brand}>Контур <span>/ помощник</span></div>
          <div className={styles.sessionIdentity}>
            <span>{studentName || identity}</span>
            {sessionMode && (
              <button type="button" onClick={() => void logout()} disabled={loggingOut}>
                {loggingOut ? "Выходим…" : "Выйти"}
              </button>
            )}
          </div>
        </header>

        <div className={styles.shell}>
          <aside className={styles.historyPanel}>
            <div className={styles.courseKicker}>Ваш курс</div>
            <h1>{course?.title}</h1>
            <p>{course?.description || "Вопросы и объяснения по загруженным материалам курса."}</p>

            {launchSource && (
              <div className={styles.launchSource}>
                <span>Выбранный раздел</span>
                <strong>{launchSource.moduleTitle}</strong>
                <small>Материал: {launchSource.itemTitle}</small>
                <p>Поиск ответа ограничен опубликованными материалами этого раздела.</p>
              </div>
            )}

            <div className={styles.boundaryCard}>
              <span aria-hidden="true">◎</span>
              <div>
                <strong>Помощник не сдаёт работу за вас</strong>
                <p>Для тестов и контрольных он предложит способ рассуждать, а не готовый ответ.</p>
              </div>
            </div>

            {policy && (
              <div className={styles.policyCard} data-enabled={policy.enabled}>
                <span>{policy.enabled ? "Режим помощи" : "Помощник на паузе"}</span>
                <strong>{STYLE_META[policy.answer_style].label}</strong>
                <p>
                  {policy.enabled
                    ? STYLE_META[policy.answer_style].description
                    : "Преподаватель временно остановил новые вопросы. История сохранена."}
                </p>
              </div>
            )}

            <div className={styles.historyHeading}>
              <span>Мои вопросы</span>
              <b>{answers.length}</b>
            </div>
            <div className={styles.historyList}>
              {answers.map((answer) => (
                <button
                  type="button"
                  key={answer.id}
                  className={answer.id === selected?.id ? styles.historyActive : styles.historyItem}
                  onClick={() => setSelectedId(answer.id)}
                  aria-current={answer.id === selected?.id ? "true" : undefined}
                >
                  <span className={styles.historyMode} data-mode={answer.response_mode} />
                  <span>{answer.question}</span>
                </button>
              ))}
              {!answers.length && (
                <p className={styles.historyEmpty}>
                  Первый вопрос появится здесь. Другие ученики его не увидят.
                </p>
              )}
            </div>

            <div className={styles.privacyNote}>
              <strong>О приватности</strong>
              <p>
                Эту личную историю видите только вы. Другим ученикам она недоступна.
                Преподаватели, методисты и администраторы видят только агрегированные
                показатели качества — без текста вопросов, ответов и вашей личности.
                Они проверяют помощника своими тестовыми вопросами.
              </p>
            </div>

            {dataPolicy && (
              <section className={styles.dataLifecycle} aria-labelledby="data-lifecycle-title">
                <div className={styles.dataLifecycleHeading}>
                  <div>
                    <span>Личная история</span>
                    <strong id="data-lifecycle-title">Ваши данные</strong>
                  </div>
                  <b>{dataPolicy.retention_days} дней</b>
                </div>
                <div
                  className={styles.lifecycleThread}
                  aria-label={`История доступна вам сейчас и автоматически удаляется через ${dataPolicy.retention_days} дней`}
                >
                  <div><i /><span>Сейчас</span><small>доступно вам</small></div>
                  <em aria-hidden="true" />
                  <div><i /><span>Через {dataPolicy.retention_days} дней</span><small>удаляется</small></div>
                </div>
                <p>
                  Удаляются вопросы, ответы, источники и ваши оценки. Техническая
                  запись о факте удаления остаётся без текста переписки.
                </p>
                {deleteSuccess && (
                  <div
                    className={styles.deleteSuccess}
                    role="status"
                    tabIndex={-1}
                    ref={deleteStatusRef}
                  >
                    {deleteSuccess}
                  </div>
                )}
                {deleteError && !deleteDialogOpen && (
                  <div
                    className={styles.deleteError}
                    role="alert"
                    tabIndex={-1}
                    ref={deleteErrorRef}
                  >
                    {deleteError}
                  </div>
                )}
                {answers.length ? (
                  <button
                    type="button"
                    className={styles.deleteHistoryButton}
                    ref={deleteTriggerRef}
                    disabled={asking || deletingHistory}
                    onClick={() => {
                      setDeleteError("");
                      setDeleteSuccess("");
                      setDeleteDialogOpen(true);
                    }}
                  >
                    Удалить мою историю
                  </button>
                ) : (
                  <span className={styles.noHistoryToDelete}>Сохранённой истории пока нет.</span>
                )}
              </section>
            )}
          </aside>

          <main className={styles.studyDesk}>
            <section className={styles.askSection} aria-labelledby="ask-title">
              <div className={styles.sectionKicker}>Учебный стол</div>
              <h2 id="ask-title">Что сейчас непонятно?</h2>
              <div className={styles.mobileBoundary}>
                {policy?.enabled
                  ? `${STYLE_META[policy.answer_style].label} · только по материалам курса`
                  : "Помощник на паузе · предыдущие ответы доступны ниже"}
              </div>
              {policy && !policy.enabled && (
                <div className={styles.pausedNotice} role="status">
                  <strong>Новые вопросы временно остановлены</strong>
                  <p>Преподаватель поставил помощника на паузу. Ваши предыдущие вопросы и источники не удалены.</p>
                </div>
              )}
              <form onSubmit={ask} className={styles.askForm}>
                <label htmlFor="tutor-question">Вопрос по материалам курса</label>
                <textarea
                  id="tutor-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  maxLength={1000}
                  placeholder="Например: объясни разницу между двумя алгоритмами на простом примере"
                  disabled={asking || !policy?.enabled}
                />
                <div className={styles.askActions}>
                  <span>{question.length}/1000 · не добавляйте персональные данные</span>
                  <button type="submit" disabled={asking || !policy?.enabled || question.trim().length < 3}>
                    {asking ? "Ищем опору…" : "Разобраться"}
                  </button>
                </div>
              </form>
              {!answers.length && policy?.enabled && (
                <div className={styles.starters}>
                  <span>Можно начать так</span>
                  <div>
                    {STARTERS.map((starter) => (
                      <button type="button" key={starter} onClick={() => setQuestion(starter)}>
                        {starter}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {error && <div className={styles.error} role="alert">{error}</div>}

            {selected && meta ? (
              <article
                className={styles.answerCard}
                data-mode={selected.response_mode}
                aria-live="polite"
              >
                <div className={styles.answerHeader}>
                  <div>
                    <span className={styles.modeBadge}>{meta.label}</span>
                    <h2 ref={answerHeadingRef} tabIndex={-1}>{meta.title}</h2>
                  </div>
                  <div className={styles.confidence}>
                    <span>Режим: {STYLE_META[selected.tutor_answer_style].label}</span>
                    <span>Надёжность опоры</span>
                    <strong>{confidenceLabel(selected.confidence)}</strong>
                  </div>
                </div>

                <div className={styles.questionNote}>
                  <span>Ваш вопрос</span>
                  <p>{selected.question}</p>
                </div>

                <div className={styles.answerText}>
                  {selected.answer.split("\n").map((paragraph, index) => (
                    paragraph ? <p key={`${selected.id}-${index}`}>{paragraph}</p> : null
                  ))}
                </div>
                <p className={styles.answerNote}>{meta.note}</p>

                {selected.citations.length ? (
                  <section className={styles.sources} aria-labelledby="sources-title">
                    <div className={styles.sourceHeading}>
                      <span>Проверяемая опора</span>
                      <h3 id="sources-title">Фрагменты курса</h3>
                    </div>
                    <div className={styles.sourceList}>
                      {selected.citations.map((citation) => (
                        <blockquote key={`${selected.id}-${citation.source_id}`}>
                          <div>
                            <b>[{citation.source_id}] {citation.document_title}</b>
                            {citation.module_title && <span>{citation.module_title}</span>}
                          </div>
                          <p>{citation.quote}</p>
                        </blockquote>
                      ))}
                    </div>
                  </section>
                ) : (
                  <div className={styles.noSources}>
                    Источники не показаны: надёжной опоры в материалах курса не найдено.
                  </div>
                )}

                <footer className={styles.answerFooter}>
                  <span>Ответ помог разобраться?</span>
                  <div>
                    <button
                      type="button"
                      data-selected={selected.feedback_status === "helpful"}
                      aria-pressed={selected.feedback_status === "helpful"}
                      onClick={() => review("helpful")}
                      disabled={Boolean(feedbackBusy)}
                    >
                      {feedbackBusy === "helpful" ? "Сохраняем…" : "Да, помог"}
                    </button>
                    <button
                      type="button"
                      data-selected={selected.feedback_status === "unhelpful"}
                      aria-pressed={selected.feedback_status === "unhelpful"}
                      onClick={() => review("unhelpful")}
                      disabled={Boolean(feedbackBusy)}
                    >
                      {feedbackBusy === "unhelpful" ? "Сохраняем…" : "Не помог"}
                    </button>
                  </div>
                </footer>
              </article>
            ) : (
              <div className={styles.blankDesk}>
                <div className={styles.threadGraphic} aria-hidden="true">
                  <i /><span /><i /><span /><i />
                </div>
                <h2>Ответ будет связан с источниками</h2>
                <p>Помощник сначала найдёт фрагменты курса, затем ответит или честно скажет, что материала недостаточно.</p>
              </div>
            )}
          </main>
        </div>
        {deleteDialogOpen && (
          <div
            className={styles.dialogBackdrop}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) closeDeleteDialog();
            }}
          >
            <section
              className={styles.deleteDialog}
              ref={deleteDialogRef}
              role="dialog"
              aria-modal="true"
              aria-busy={deletingHistory}
              aria-labelledby="delete-dialog-title"
              aria-describedby="delete-dialog-description"
              tabIndex={-1}
              onKeyDown={handleDeleteDialogKeyDown}
            >
              <span>Личная история</span>
              <h2 id="delete-dialog-title">Удалить всю историю этого курса?</h2>
              <p id="delete-dialog-description">
                Действие нельзя отменить. Будут удалены ваши вопросы, ответы,
                фрагменты источников и оценки ответов.
              </p>
              <div className={styles.preservedNote}>
                Курс, доступ к нему и материалы останутся. В техническом журнале
                сохранится только факт удаления и количество записей — без текста.
              </div>
              {deleteError && (
                <div
                  className={styles.deleteError}
                  role="alert"
                  tabIndex={-1}
                  ref={deleteErrorRef}
                >
                  {deleteError}
                </div>
              )}
              <div className={styles.dialogActions}>
                <button
                  type="button"
                  ref={deleteCancelRef}
                  onClick={closeDeleteDialog}
                  disabled={deletingHistory}
                >
                  Оставить историю
                </button>
                <button
                  type="button"
                  ref={deleteConfirmRef}
                  className={styles.confirmDeleteButton}
                  onClick={() => void deleteHistory()}
                  disabled={deletingHistory}
                >
                  {deletingHistory ? "Удаляем…" : "Удалить историю"}
                </button>
              </div>
            </section>
          </div>
        )}
      </div>
    </>
  );
}
