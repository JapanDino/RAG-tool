import { useEffect, useId, useRef, useState } from "react";
import AnswerLayout, { AnswerDiagram, AnswerSection } from "./AnswerLayout";
import MaterialImage, { Illustration } from "./MaterialImage";
import s from "../styles/portal.module.css";

export type ReadingContext = {
    document_id: number;
    chunk_id?: number;
    quote?: string;
};
export type Citation = {
    document_id: number;
    chunk_id: number;
    title: string;
    quote: string;
    page?: number;
};
export type PortalAPI = (path: string, init?: RequestInit) => Promise<any>;
type Message = {
    role: "user" | "assistant";
    content: string;
    citations?: Citation[];
    sections?: AnswerSection[];
    diagram?: AnswerDiagram;
    images?: Illustration[];
    review_id?: string;
    feedback_key?: string;
    feedback?: string;
};
type Exercise = {
    id: string;
    question: string;
    attempts: number;
    feedback?: string;
    hint?: string;
    correct: boolean;
    can_reveal: boolean;
    citations: Citation[];
    topic?: string;
    question_number?: number;
    total_questions?: number;
    draft_answer?: string;
    completed?: boolean;
    history?: { question: string; correct: boolean; attempts: number }[];
};

export default function CourseChat({
    token,
    api,
    scope,
    context,
    onSource,
    seed,
    compact = false,
    allowReview = true,
    active = true,
    preview = false,
}: {
    token: string;
    api: PortalAPI;
    scope?: string;
    context?: ReadingContext;
    onSource: (id: number, chunk?: number, page?: number) => void;
    seed?: { text: string; nonce: number };
    compact?: boolean;
    allowReview?: boolean;
    active?: boolean;
    preview?: boolean;
}) {
    const id = useId();
    const [messages, setMessages] = useState<Message[]>([]);
    const [question, setQuestion] = useState("");
    const [style, setStyle] = useState("auto");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [practiceError, setPracticeError] = useState("");
    const [status, setStatus] = useState("");
    const [draft, setDraft] = useState("");
    const [quality, setQuality] = useState<boolean | null>(null);
    const [preferencesError, setPreferencesError] = useState("");
    const [preferencesRetry, setPreferencesRetry] = useState(0);
    const [share, setShare] = useState(false);
    const [remember, setRemember] = useState(false);
    const [ready, setReady] = useState(false);
    const [notes, setNotes] = useState("");
    const [exercise, setExercise] = useState<Exercise | null>(null);
    const [resumable, setResumable] = useState<Exercise | null>(null);
    const [saveStatus, setSaveStatus] = useState("");
    const [attempt, setAttempt] = useState("");
    const [solution, setSolution] = useState<{
        answer: string;
        explanation: string;
    } | null>(null);
    const abort = useRef<AbortController | null>(null);
    const textarea = useRef<HTMLTextAreaElement>(null);
    const log = useRef<HTMLDivElement>(null);
    const storageKey = scope
        ? `course-workspace:${scope}:${preview ? "preview:" : ""}${context?.document_id || "course"}`
        : null;
    useEffect(() => {
        if (preview) return;
        let live = true;
        api(`/study/current?document_id=${context?.document_id || 0}`)
            .then((state) => {
                if (live && state?.id) setResumable(state);
            })
            .catch(() => {
                if (live)
                    setPracticeError(
                        "Не удалось восстановить тренировку. Источник мог измениться; можно начать новую.",
                    );
            });
        return () => {
            live = false;
        };
    }, [api, context?.document_id, preview]);
    useEffect(() => {
        if (!exercise?.question_number || exercise.completed) return;
        if (busy) {
            setSaveStatus("");
            return;
        }
        if (attempt === (exercise.draft_answer || "")) {
            setSaveStatus(attempt ? "Черновик ответа сохранён" : "");
            return;
        }
        let live = true;
        setSaveStatus("Сохраняем ответ…");
        const timer = setTimeout(() => {
            api(`/study/${exercise.id}/draft`, {
                method: "PUT",
                body: JSON.stringify({
                    answer: attempt,
                    question_number: exercise.question_number,
                }),
            })
                .then(() => {
                    if (live) setSaveStatus("Черновик ответа сохранён");
                })
                .catch(() => {
                    if (live)
                        setSaveStatus(
                            "Не удалось сохранить черновик. Не закрывайте страницу до повтора.",
                        );
                });
        }, 600);
        return () => {
            live = false;
            clearTimeout(timer);
        };
    }, [
        api,
        exercise?.id,
        exercise?.question_number,
        exercise?.completed,
        exercise?.draft_answer,
        attempt,
        busy,
    ]);
    useEffect(() => {
        if (!active) return;
        let live = true;
        let pending = false;
        const refreshPreferences = async () => {
            if (pending || document.visibilityState === "hidden") return;
            pending = true;
            try {
                const p = await api("/preferences");
                if (live) {
                    const enabled = Boolean(p.quality_enabled && allowReview);
                    setQuality(enabled);
                    if (!enabled) setShare(false);
                    setPreferencesError("");
                }
            } catch {
                if (live) {
                    setQuality(null);
                    setShare(false);
                    setPreferencesError(
                        "Не удалось обновить настройки курса. Повторите загрузку перед отправкой вопроса.",
                    );
                }
            } finally {
                pending = false;
            }
        };
        void refreshPreferences();
        window.addEventListener("focus", refreshPreferences);
        document.addEventListener("visibilitychange", refreshPreferences);
        return () => {
            live = false;
            window.removeEventListener("focus", refreshPreferences);
            document.removeEventListener(
                "visibilitychange",
                refreshPreferences,
            );
        };
    }, [api, allowReview, active, preferencesRetry]);
    useEffect(() => () => abort.current?.abort(), []);
    useEffect(() => {
        try {
            if (storageKey) {
                const saved = JSON.parse(
                    localStorage.getItem(storageKey) || "null",
                );
                if (saved && Array.isArray(saved.messages)) {
                    setMessages(saved.messages.slice(-20));
                    setNotes(String(saved.notes || "").slice(0, 12000));
                    setRemember(true);
                }
            }
        } catch {
            setError("Локальная история недоступна в этом браузере.");
        }
        setReady(true);
    }, [storageKey]);
    useEffect(() => {
        if (!ready || !storageKey) return;
        try {
            if (remember)
                localStorage.setItem(
                    storageKey,
                    JSON.stringify({
                        messages: messages
                            .slice(-20)
                            .map(({ feedback_key, review_id, ...m }) => m),
                        notes,
                    }),
                );
            else localStorage.removeItem(storageKey);
        } catch {
            setError("Не удалось сохранить историю на этом устройстве.");
        }
    }, [messages, notes, remember, ready, storageKey]);
    useEffect(() => {
        if (seed) {
            setQuestion(seed.text);
            textarea.current?.focus();
        }
    }, [seed]);
    useEffect(() => {
        const container = log.current;
        if (!container) return;
        const last = container.querySelector<HTMLElement>(
            "article:last-of-type",
        );
        container.scrollTop =
            !draft &&
            !status &&
            messages[messages.length - 1]?.role === "assistant" &&
            last
                ? last.offsetTop - 16
                : container.scrollHeight;
    }, [messages, draft, status]);

    async function ask() {
        if (busy || !question.trim() || quality === null) return;
        const content = question.trim();
        const previous = messages;
        setMessages([...previous, { role: "user", content }]);
        setQuestion("");
        setError("");
        setBusy(true);
        setDraft("");
        const controller = new AbortController();
        abort.current = controller;
        let finished = false;
        try {
            const response = await fetch("/api-proxy/portal/chat/stream", {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    message: content,
                    history: previous.slice(-6).map((m) => ({
                        role: m.role,
                        content: [
                            m.content,
                            ...(m.sections || []).map((b) =>
                                [b.heading, b.body, ...b.bullets].join("\n"),
                            ),
                        ]
                            .join("\n")
                            .slice(0, 4000),
                    })),
                    response_style: style,
                    context,
                    share_for_review: quality && share,
                    preview,
                }),
                signal: controller.signal,
            });
            if (!response.ok) {
                const body = await response.json().catch(() => ({}));
                throw new Error(
                    typeof body.detail === "string"
                        ? body.detail
                        : "Не удалось отправить вопрос. Попробуйте ещё раз.",
                );
            }
            if (!response.body)
                throw new Error("Браузер не поддерживает потоковый ответ.");
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            for (;;) {
                const { done, value } = await reader.read();
                buffer += decoder.decode(value, { stream: !done });
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";
                for (const line of lines) {
                    if (!line.trim()) continue;
                    const event = JSON.parse(line);
                    if (event.event === "status") setStatus(event.message);
                    if (event.event === "draft") setDraft(event.answer);
                    if (event.event === "error") throw new Error(event.message);
                    if (event.event === "result") {
                        const a = event.result;
                        setMessages([
                            ...previous,
                            { role: "user", content },
                            { ...a, role: "assistant", content: a.answer },
                        ]);
                        finished = true;
                    }
                }
                if (done) break;
            }
            if (!finished)
                throw new Error("Соединение прервалось. Повторите вопрос.");
            setStyle("auto");
        } catch (e) {
            if (!finished) {
                setMessages(previous);
                setQuestion(content);
            }
            setError(
                controller.signal.aborted
                    ? "Ответ остановлен. Вопрос можно отправить повторно."
                    : e instanceof TypeError
                      ? "Нет связи с сервисом. Проверьте подключение и повторите вопрос."
                      : e instanceof Error
                        ? e.message
                        : "Ошибка ответа",
            );
        } finally {
            controller.abort();
            setBusy(false);
            setDraft("");
            setStatus("");
            abort.current = null;
        }
    }
    async function practice(action: () => Promise<void>) {
        setBusy(true);
        setPracticeError("");
        try {
            await action();
        } catch (e) {
            setPracticeError(
                e instanceof Error
                    ? e.message
                    : "Не удалось выполнить действие",
            );
        } finally {
            setBusy(false);
        }
    }
    function startPractice() {
        void practice(async () => {
            const topic =
                question.trim() ||
                [...messages].reverse().find((m) => m.role === "user")
                    ?.content ||
                context?.quote ||
                "Основные идеи выбранного материала";
            setExercise(
                await api("/study", {
                    method: "POST",
                    body: JSON.stringify({
                        message: topic,
                        context,
                        share_for_review: false,
                    }),
                }),
            );
            setAttempt("");
            setSolution(null);
            setSaveStatus("");
            setResumable(null);
        });
    }
    const openCitation = (c: Citation) =>
        onSource(c.document_id, c.chunk_id, c.page);
    return (
        <section
            className={compact ? s.sideChat : s.panel}
            aria-label="Чат по материалам"
        >
            <div className={s.sectionHead}>
                <h2>
                    {compact ? "Разобрать материал" : "Спросите о теме курса"}
                </h2>
                <button
                    disabled={busy || !messages.length}
                    onClick={() => setMessages([])}
                >
                    Очистить диалог
                </button>
            </div>
            <p className={s.muted}>
                Объяснения по материалам курса и рекомендованной литературе.
                Проверяйте ответы по источникам.
            </p>
            {preview && (
                <p className={s.disclosure}>
                    Проверка преподавателя. Чат использует выбранный материал,
                    включая черновик. Материал не публикуется; вопросы не
                    попадают в журнал учеников и общие счётчики. Проверьте смысл
                    ответа и цитаты перед публикацией.
                </p>
            )}
            {preferencesError && (
                <div role="alert" className={s.error}>
                    <p>{preferencesError}</p>
                    <button onClick={() => setPreferencesRetry((n) => n + 1)}>
                        Загрузить настройки повторно
                    </button>
                </div>
            )}
            {quality && (
                <div className={s.disclosure}>
                    <p>
                        Преподаватель включил журнал качества. По вашему выбору
                        вопрос и ответ будут доступны ему без имени и ID, с
                        удалением обнаруженных имён и контактов. По содержанию
                        вас всё ещё могут узнать.
                    </p>
                    <label>
                        <input
                            type="checkbox"
                            checked={share}
                            onChange={(e) => setShare(e.target.checked)}
                            disabled={busy}
                        />{" "}
                        Добавлять мои вопросы и ответы в журнал качества
                    </label>
                </div>
            )}
            <div
                className={s.messages}
                ref={log}
                role="log"
                aria-label="Диалог с помощником"
                aria-live="polite"
            >
                {!messages.length && !busy && (
                    <div className={s.empty}>
                        <h3>С чего начнём?</h3>
                        <p>Выберите вопрос или напишите свой.</p>
                        <div className={s.suggestions}>
                            {[
                                "Объясни основную идею темы",
                                "Сравни ключевые понятия",
                                "Помоги разобраться в примере",
                            ].map((q) => (
                                <button
                                    key={q}
                                    onClick={() => {
                                        setQuestion(q);
                                        textarea.current?.focus();
                                    }}
                                >
                                    {q} →
                                </button>
                            ))}
                        </div>
                    </div>
                )}
                {messages.map((m, i) => (
                    <article
                        key={i}
                        className={m.role === "user" ? s.user : s.assistant}
                    >
                        <strong>{m.role === "user" ? "Вы" : "Помощник"}</strong>
                        <p>{m.content}</p>
                        {m.role === "assistant" && (
                            <AnswerLayout
                                sections={m.sections}
                                diagram={m.diagram}
                                citations={m.citations || []}
                                busy={busy}
                                onSource={(doc, chunk) => onSource(doc, chunk)}
                            />
                        )}
                        {!!m.images?.length && (
                            <div className={s.illustrations}>
                                {m.images.map((img) => (
                                    <MaterialImage
                                        key={img.id}
                                        image={img}
                                        token={token}
                                        onSource={() =>
                                            onSource(
                                                img.document_id,
                                                img.chunk_id || undefined,
                                                img.page || undefined,
                                            )
                                        }
                                    />
                                ))}
                            </div>
                        )}
                        {m.citations?.map((c) => (
                            <details key={c.chunk_id}>
                                <summary>
                                    Источник: {c.title}
                                    {c.page ? ` · стр. ${c.page}` : ""}
                                </summary>
                                <blockquote>{c.quote}</blockquote>
                                <button onClick={() => openCitation(c)}>
                                    Открыть материал
                                </button>
                            </details>
                        ))}
                        {m.review_id && m.feedback_key && (
                            <div
                                className={s.actions}
                                aria-label="Оценить ответ"
                            >
                                {[
                                    ["helpful", "Полезно"],
                                    ["unclear", "Непонятно"],
                                    ["incorrect", "Ошибка"],
                                    ["wrong_source", "Не тот источник"],
                                ].map(([value, label]) => (
                                    <button
                                        key={value}
                                        disabled={busy}
                                        aria-pressed={m.feedback === value}
                                        onClick={() =>
                                            void practice(async () => {
                                                await api(
                                                    `/quality/${m.review_id}/feedback`,
                                                    {
                                                        method: "POST",
                                                        body: JSON.stringify({
                                                            feedback: value,
                                                            feedback_key:
                                                                m.feedback_key,
                                                        }),
                                                    },
                                                );
                                                setMessages((all) =>
                                                    all.map((x, n) =>
                                                        n === i
                                                            ? {
                                                                  ...x,
                                                                  feedback:
                                                                      value,
                                                              }
                                                            : x,
                                                    ),
                                                );
                                            })
                                        }
                                    >
                                        {label}
                                    </button>
                                ))}
                            </div>
                        )}
                    </article>
                ))}
                {busy && status && <p role="status">{status}</p>}
                {draft && (
                    <article className={s.assistant}>
                        <strong>
                            Предварительный ответ · источники ещё проверяются
                        </strong>
                        <p>{draft}</p>
                    </article>
                )}
            </div>
            {context?.quote && (
                <blockquote className={s.selection}>
                    Выбранный фрагмент: {context.quote}
                </blockquote>
            )}
            <form
                className={s.ask}
                onSubmit={(e) => {
                    e.preventDefault();
                    void ask();
                }}
            >
                {!!messages.length && (
                    <div className={s.followUps}>
                        <p className={s.muted}>
                            Продолжить разбор: выберите вопрос, затем отправьте
                            его.
                        </p>
                        <div>
                            {[
                                [
                                    "Объясни проще",
                                    "Объясни простыми словами",
                                    "simple",
                                ],
                                ["По шагам", "Разбери по шагам", "steps"],
                                [
                                    "Покажи схему",
                                    "Покажи схему связей",
                                    "diagram",
                                ],
                            ].map(([label, prompt, value]) => (
                                <button
                                    type="button"
                                    key={value}
                                    disabled={busy}
                                    onClick={() => {
                                        setQuestion(
                                            `${prompt}: ${[...messages].reverse().find((m) => m.role === "user")?.content || "тема курса"}`.slice(
                                                0,
                                                4000,
                                            ),
                                        );
                                        setStyle(value);
                                        textarea.current?.focus();
                                    }}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    </div>
                )}
                {error && (
                    <p role="alert" className={s.error}>
                        {error}
                    </p>
                )}
                <label htmlFor={id}>Ваш вопрос</label>
                <textarea
                    id={id}
                    ref={textarea}
                    rows={3}
                    maxLength={4000}
                    value={question}
                    onChange={(e) => {
                        setQuestion(e.target.value);
                        setStyle("auto");
                    }}
                    placeholder="Например: объясни эту тему на простом примере"
                />
                <div className={s.composerFooter}>
                    {!preview && (
                        <button
                            type="button"
                            disabled={busy || quality === null}
                            onClick={startPractice}
                        >
                            Проверь понимание
                        </button>
                    )}
                    {busy && abort.current ? (
                        <button
                            key="stop"
                            type="button"
                            onClick={(e) => {
                                e.preventDefault();
                                abort.current?.abort();
                            }}
                        >
                            Остановить ответ
                        </button>
                    ) : (
                        <button
                            key="send"
                            type="submit"
                            className={s.primary}
                            disabled={
                                busy || !question.trim() || quality === null
                            }
                        >
                            {busy
                                ? "Готовим…"
                                : error && question
                                  ? "Повторить вопрос"
                                  : "Отправить"}
                        </button>
                    )}
                </div>
            </form>
            {!preview && !exercise && resumable && (
                <div className={s.disclosure}>
                    <p>
                        {resumable.completed
                            ? "Завершённая тренировка"
                            : "Сохранённая тренировка"}
                        : {resumable.topic}. Вопрос {resumable.question_number}{" "}
                        из {resumable.total_questions}.
                    </p>
                    <button
                        disabled={busy}
                        onClick={() =>
                            void practice(async () => {
                                const current = await api(
                                    `/study/current?document_id=${context?.document_id || 0}`,
                                );
                                if (!current?.id)
                                    throw new Error(
                                        "Срок тренировки истёк. Начните новую.",
                                    );
                                setExercise(current);
                                setAttempt(current.draft_answer || "");
                                setSolution(null);
                                setSaveStatus("");
                            })
                        }
                    >
                        {resumable.completed
                            ? "Открыть результат"
                            : "Продолжить тренировку"}
                    </button>
                </div>
            )}
            {!preview && (
                <p className={s.muted}>
                    Тренировка состоит из трёх вопросов. Прогресс и черновик
                    ответа сохраняются в вашей учётной записи на 7 дней после
                    последнего изменения, отдельно от журнала преподавателя.
                </p>
            )}
            {practiceError && !exercise && (
                <p role="alert" className={s.error}>
                    {practiceError}
                </p>
            )}
            {exercise && (
                <section className={s.exercise} aria-label="Учебное упражнение">
                    <div className={s.sectionHead}>
                        <h3>Проверка понимания</h3>
                        <button
                            disabled={busy}
                            onClick={() =>
                                void practice(async () => {
                                    if (
                                        exercise.question_number &&
                                        !exercise.completed
                                    )
                                        await api(
                                            `/study/${exercise.id}/draft`,
                                            {
                                                method: "PUT",
                                                body: JSON.stringify({
                                                    answer: attempt,
                                                    question_number:
                                                        exercise.question_number,
                                                }),
                                            },
                                        );
                                    setResumable({
                                        ...exercise,
                                        draft_answer: attempt,
                                    });
                                    setExercise(null);
                                })
                            }
                        >
                            Закрыть упражнение
                        </button>
                    </div>
                    <p>
                        {exercise.completed
                            ? "Тренировка завершена"
                            : `Вопрос ${exercise.question_number || 1} из ${exercise.total_questions || 3}`}
                    </p>
                    {!exercise.completed && <p>{exercise.question}</p>}
                    {!!exercise.history?.length && (
                        <details open={exercise.completed}>
                            <summary>Результаты вопросов</summary>
                            <ol>
                                {exercise.history.map((item, i) => (
                                    <li key={i}>
                                        {item.question} —{" "}
                                        {item.correct
                                            ? "ответ принят помощником"
                                            : "нужно повторить"}
                                        , попыток: {item.attempts}.
                                    </li>
                                ))}
                            </ol>
                        </details>
                    )}
                    <p className={s.muted}>
                        Тренировка с ИИ; оценка в Canvas не выставляется.
                        Прогресс хранится 7 дней после последнего изменения.
                    </p>
                    {practiceError && (
                        <p role="alert" className={s.error}>
                            {practiceError}
                        </p>
                    )}
                    {!exercise.completed && (
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                void practice(async () => {
                                    setExercise(
                                        await api(
                                            `/study/${exercise.id}/attempt`,
                                            {
                                                method: "POST",
                                                body: JSON.stringify({
                                                    answer: attempt,
                                                    question_number:
                                                        exercise.question_number,
                                                }),
                                            },
                                        ),
                                    );
                                });
                            }}
                        >
                            <label htmlFor={`${id}-attempt`}>Ваш ответ</label>
                            <textarea
                                id={`${id}-attempt`}
                                value={attempt}
                                onChange={(e) => setAttempt(e.target.value)}
                                rows={3}
                                maxLength={3000}
                                disabled={busy}
                            />
                            {saveStatus && <p role="status">{saveStatus}</p>}
                            <button disabled={busy || !attempt.trim()}>
                                Проверить ответ
                            </button>
                        </form>
                    )}
                    {exercise.feedback && (
                        <p role="status">
                            {exercise.feedback} Попыток: {exercise.attempts}.
                        </p>
                    )}
                    {exercise.hint && (
                        <p>
                            <strong>Подсказка:</strong> {exercise.hint}
                        </p>
                    )}
                    <div className={s.actions}>
                        {!exercise.completed && exercise.question_number && (
                            <button
                                disabled={busy || !exercise.attempts}
                                onClick={() =>
                                    void practice(async () => {
                                        const next = await api(
                                            `/study/${exercise.id}/next`,
                                            {
                                                method: "POST",
                                                body: JSON.stringify({
                                                    question_number:
                                                        exercise.question_number,
                                                }),
                                            },
                                        );
                                        setExercise(next);
                                        setAttempt(next.draft_answer || "");
                                        setSolution(null);
                                        setSaveStatus("");
                                    })
                                }
                            >
                                {exercise.question_number === 3
                                    ? "Завершить тренировку"
                                    : "Следующий вопрос"}
                            </button>
                        )}
                        <button disabled={busy} onClick={startPractice}>
                            Новое упражнение
                        </button>
                        {exercise.can_reveal && (
                            <button
                                disabled={busy}
                                onClick={() =>
                                    void practice(async () =>
                                        setSolution(
                                            await api(
                                                `/study/${exercise.id}/solution`,
                                                { method: "POST" },
                                            ),
                                        ),
                                    )
                                }
                            >
                                Показать решение
                            </button>
                        )}
                    </div>
                    <p className={s.muted}>
                        «Новое упражнение» заменит сохранённую тренировку в этом
                        разделе.
                    </p>
                    {solution && (
                        <div>
                            <h4>Разбор решения</h4>
                            <p>{solution.answer}</p>
                            <p>{solution.explanation}</p>
                        </div>
                    )}
                    {exercise.citations
                        .filter(
                            (c, i, all) =>
                                all.findIndex(
                                    (x) => x.document_id === c.document_id,
                                ) === i,
                        )
                        .map((c) => (
                            <button
                                key={c.chunk_id}
                                onClick={() => openCitation(c)}
                            >
                                Источник: {c.title}
                            </button>
                        ))}
                </section>
            )}
            <details className={s.privacy}>
                <summary>Моя история и заметки</summary>
                <p>
                    Можно сохранить последние 20 сообщений и заметки в этом
                    браузере. Они доступны при входе в этот же курс под вашей
                    учётной записью. На общем устройстве выключайте сохранение
                    перед выходом.
                </p>
                <label>
                    <input
                        type="checkbox"
                        checked={remember}
                        disabled={!storageKey}
                        onChange={(e) => setRemember(e.target.checked)}
                    />{" "}
                    Сохранять на этом устройстве
                </label>
                <label htmlFor={`${id}-notes`}>Мои заметки</label>
                <textarea
                    id={`${id}-notes`}
                    rows={3}
                    maxLength={12000}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                />
                <div className={s.actions}>
                    <button
                        onClick={() => {
                            const data = new Blob(
                                [
                                    messages
                                        .map(
                                            (m) =>
                                                `${m.role === "user" ? "Вы" : "Помощник"}: ${m.content}\n${(m.sections || []).map((x) => [x.heading, x.body, ...x.bullets].join("\n")).join("\n")}\n${m.citations?.map((c) => `Источник: ${c.title}${c.page ? `, стр. ${c.page}` : ""}\n${c.quote}`).join("\n") || ""}`,
                                        )
                                        .join("\n\n") +
                                        "\n\nЗаметки:\n" +
                                        notes,
                                ],
                                { type: "text/plain;charset=utf-8" },
                            );
                            const url = URL.createObjectURL(data);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = "course-notes.txt";
                            a.click();
                            setTimeout(() => URL.revokeObjectURL(url), 1000);
                        }}
                    >
                        Скачать диалог и заметки
                    </button>
                    <button
                        disabled={busy}
                        onClick={() => {
                            setRemember(false);
                            setMessages([]);
                            setNotes("");
                        }}
                    >
                        Удалить историю и заметки
                    </button>
                </div>
            </details>
            <details className={s.privacy}>
                <summary>Кто видит мой диалог?</summary>
                <p>
                    Вопрос, краткий контекст переписки и выбранные источники
                    передаются настроенному сервису модели. Личная история
                    остаётся в этом браузере при включённом сохранении. Журнал
                    преподавателя включается отдельно и требует вашего выбора
                    выше; записи в нём очищаются от обнаруженных имён и
                    контактов и хранятся до 30 дней. Полная анонимность текста
                    не гарантируется. Ответы в упражнениях не попадают в журнал.
                </p>
            </details>
        </section>
    );
}
