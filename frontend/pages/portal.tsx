import Head from "next/head";
import { FormEvent, useCallback, useEffect, useState } from "react";
import s from "../styles/portal.module.css";

type Material = {
    document_id: number;
    title: string;
    published: boolean;
    kind: string;
    source_url?: string;
};
type Citation = {
    document_id: number;
    chunk_id: number;
    title: string;
    quote: string;
    url?: string;
};
type Message = {
    role: "user" | "assistant";
    content: string;
    citations?: Citation[];
};
type Analysis = {
    distribution: Record<string, number>;
    note: string;
    chunks_analyzed: number;
    limit: number;
    examples: {
        document_id: number;
        title: string;
        text: string;
        levels: string[];
    }[];
};
type Summary = {
    metrics: Record<string, number>;
    feedback: { title: string; rating: string; count: number | null }[];
};
const labels: Record<string, string> = {
    remember: "Запомнить",
    understand: "Понять",
    apply: "Применить",
    analyze: "Проанализировать",
    evaluate: "Оценить",
    create: "Создать",
    clear: "Понятно",
    difficult: "Сложно",
    error: "Есть ошибка",
    questions: "Вопросы",
    no_context: "Недостаточно источников",
    answers_with_sources: "Ответы с источниками",
    errors: "Ошибки сервиса",
};

export default function Portal() {
    const [token, setToken] = useState("");
    const [session, setSession] = useState<{
        title: string;
        role: string;
    } | null>(null);
    const [tab, setTab] = useState("chat");
    const [materials, setMaterials] = useState<Material[]>([]);
    const [messages, setMessages] = useState<Message[]>([]);
    const [question, setQuestion] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [analysis, setAnalysis] = useState<Analysis | null>(null);
    const [summary, setSummary] = useState<Summary | null>(null);
    const [source, setSource] = useState<{
        title: string;
        chunks: { id: number; text: string }[];
    } | null>(null);
    const [feedbackDoc, setFeedbackDoc] = useState<number | null>(null);
    const [rating, setRating] = useState("clear");
    const [comment, setComment] = useState("");

    const api = useCallback(
        async (path: string, init: RequestInit = {}) => {
            const headers = new Headers(init.headers);
            headers.set("Authorization", `Bearer ${token}`);
            if (init.body && !(init.body instanceof FormData))
                headers.set("Content-Type", "application/json");
            const response = await fetch(`/api-proxy/portal${path}`, {
                ...init,
                headers,
                cache: "no-store",
            });
            if (!response.ok) {
                if (response.status === 401) {
                    sessionStorage.removeItem("canvas_portal_token");
                    setSession(null);
                    setToken("");
                    setMessages([]);
                    setMaterials([]);
                    setSource(null);
                    throw new Error(
                        "Сессия завершилась. Откройте помощника заново из курса Canvas.",
                    );
                }
                const body = await response.json().catch(() => ({}));
                throw new Error(
                    typeof body.detail === "string"
                        ? body.detail
                        : `Ошибка запроса (${response.status})`,
                );
            }
            return response.json();
        },
        [token],
    );

    useEffect(() => {
        try {
            setToken(sessionStorage.getItem("canvas_portal_token") || "");
        } catch {
            setError(
                "Откройте инструмент из Canvas в новой вкладке и разрешите хранилище сайта.",
            );
        }
    }, []);
    useEffect(() => {
        if (!token) return;
        let active = true;
        Promise.all([api("/session"), api("/materials")])
            .then(([user, docs]) => {
                if (active) {
                    setSession(user);
                    setMaterials(docs);
                }
            })
            .catch((e) => {
                if (active) setError(e.message);
            });
        return () => {
            active = false;
        };
    }, [api, token]);

    async function run(action: () => Promise<void>) {
        setBusy(true);
        setError("");
        setNotice("");
        try {
            await action();
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Не удалось выполнить запрос",
            );
        } finally {
            setBusy(false);
        }
    }
    async function refresh() {
        setMaterials(await api("/materials"));
    }
    async function ask(e: FormEvent) {
        e.preventDefault();
        if (!question.trim() || busy) return;
        const content = question.trim();
        const history = messages
            .slice(-6)
            .map(({ role, content }) => ({ role, content }));
        setMessages((prev) => [...prev, { role: "user", content }]);
        setQuestion("");
        await run(async () => {
            const answer = await api("/chat", {
                method: "POST",
                body: JSON.stringify({ message: content, history }),
            });
            setMessages((prev) => [
                ...prev,
                {
                    role: "assistant",
                    content: answer.answer,
                    citations: answer.citations,
                },
            ]);
        });
    }
    const teacher = session?.role === "teacher";

    return (
        <main className={s.page}>
            <style jsx global>{`
                html,
                body {
                    height: auto;
                    min-height: 100%;
                    overflow: auto;
                }
            `}</style>
            <Head>
                <title>Помощник курса · Canvas</title>
                <meta name="referrer" content="no-referrer" />
            </Head>
            <header className={s.header}>
                <div>
                    <span className={s.eyebrow}>CANVAS · УЧЕБНЫЙ ПОМОЩНИК</span>
                    <h1>{session?.title || "Помощник курса"}</h1>
                    <p>
                        {teacher
                            ? "Материалы, вопросы и обратная связь — в одном месте."
                            : "Разбирайтесь в теме с опорой на материалы вашего курса."}
                    </p>
                </div>
                {session && (
                    <span className={s.badge}>
                        {teacher ? "Преподаватель" : "Ученик"}
                    </span>
                )}
            </header>
            {error && (
                <p role="alert" className={s.error}>
                    {error}
                </p>
            )}
            {notice && (
                <p role="status" className={s.notice}>
                    {notice}
                </p>
            )}
            {!session ? (
                <section className={s.panel}>
                    <h2>Войдите через Canvas</h2>
                    <p>
                        Откройте свой курс и выберите «Помощник курса» в меню.
                        Отдельный пароль не нужен.
                    </p>
                </section>
            ) : (
                <>
                    <nav className={s.tabs} aria-label="Разделы помощника">
                        {[
                            ["chat", "Чат"],
                            ["materials", "Материалы"],
                            ...(teacher
                                ? [
                                      ["analysis", "Анализ курса"],
                                      ["summary", "Обратная связь"],
                                  ]
                                : []),
                        ].map(([id, title]) => (
                            <button
                                key={id}
                                aria-pressed={tab === id}
                                onClick={() => {
                                    setTab(id);
                                    if (id === "analysis")
                                        void run(async () =>
                                            setAnalysis(await api("/analysis")),
                                        );
                                    if (id === "summary")
                                        void run(async () =>
                                            setSummary(await api("/summary")),
                                        );
                                }}
                                disabled={busy}
                            >
                                {title}
                            </button>
                        ))}
                    </nav>

                    {tab === "chat" && (
                        <section className={s.panel}>
                            <div className={s.sectionHead}>
                                <h2>Спросите о теме курса</h2>
                                <button
                                    onClick={() => setMessages([])}
                                    disabled={busy}
                                >
                                    Очистить диалог
                                </button>
                            </div>
                            <p className={s.muted}>
                                Ответы опираются на опубликованные источники.
                                Диалог не сохраняется в истории сервера и не
                                показывается преподавателю; вопрос и найденные
                                фрагменты передаются настроенному сервису
                                модели.
                            </p>
                            <div className={s.messages} aria-live="polite">
                                {messages.length === 0 && (
                                    <div className={s.empty}>
                                        Попросите объяснить понятие, сравнить
                                        подходы или найти нужный фрагмент.
                                    </div>
                                )}
                                {messages.map((m, i) => (
                                    <article
                                        key={i}
                                        className={
                                            m.role === "user"
                                                ? s.user
                                                : s.assistant
                                        }
                                    >
                                        <strong>
                                            {m.role === "user"
                                                ? "Вы"
                                                : "Помощник"}
                                        </strong>
                                        <p>{m.content}</p>
                                        {m.citations?.map((c) => (
                                            <details key={c.chunk_id}>
                                                <summary>
                                                    Источник: {c.title}
                                                </summary>
                                                <blockquote>
                                                    {c.quote}
                                                </blockquote>
                                                <button
                                                    disabled={busy}
                                                    onClick={() =>
                                                        void run(async () =>
                                                            setSource(
                                                                await api(
                                                                    `/materials/${c.document_id}`,
                                                                ),
                                                            ),
                                                        )
                                                    }
                                                >
                                                    Открыть материал
                                                </button>
                                            </details>
                                        ))}
                                    </article>
                                ))}
                                {busy && (
                                    <p role="status">Обрабатываем запрос…</p>
                                )}
                            </div>
                            <form onSubmit={ask} className={s.ask}>
                                <label htmlFor="question">Ваш вопрос</label>
                                <textarea
                                    id="question"
                                    value={question}
                                    maxLength={4000}
                                    rows={3}
                                    onChange={(e) =>
                                        setQuestion(e.target.value)
                                    }
                                    placeholder="Например: объясни эту тему на простом примере"
                                />
                                <button
                                    className={s.primary}
                                    disabled={busy || !question.trim()}
                                >
                                    Отправить
                                </button>
                            </form>
                        </section>
                    )}

                    {tab === "materials" && (
                        <section className={s.panel}>
                            <h2>Библиотека курса</h2>
                            {teacher && (
                                <div className={s.upload}>
                                    <p>
                                        Добавляйте PDF, TXT, MD или DOCX до 10
                                        МБ и 60 000 символов. Новые материалы
                                        видны только вам, пока вы их не
                                        опубликуете.
                                    </p>
                                    <p>
                                        Публикуйте только материалы, разрешённые
                                        всем ученикам пилотного курса.
                                        Индивидуальные условия доступа Canvas
                                        здесь не воспроизводятся.
                                    </p>
                                    <label className={s.file}>
                                        Добавить литературу
                                        <input
                                            type="file"
                                            accept=".pdf,.txt,.md,.docx"
                                            disabled={busy}
                                            onChange={(e) => {
                                                const file =
                                                    e.target.files?.[0];
                                                e.target.value = "";
                                                if (file)
                                                    void run(async () => {
                                                        const body =
                                                            new FormData();
                                                        body.append(
                                                            "file",
                                                            file,
                                                        );
                                                        await api(
                                                            "/materials",
                                                            {
                                                                method: "POST",
                                                                body,
                                                            },
                                                        );
                                                        await refresh();
                                                        setNotice(
                                                            "Материал добавлен в черновики. Проверьте текст перед публикацией.",
                                                        );
                                                    });
                                            }}
                                        />
                                    </label>
                                    <button
                                        disabled={busy}
                                        onClick={() =>
                                            void run(async () => {
                                                const r = await api(
                                                    "/import-canvas",
                                                    { method: "POST" },
                                                );
                                                await refresh();
                                                setNotice(
                                                    `Импортировано: ${r.imported}. Пропущено: ${r.skipped}. За пределами лимита: ${r.remaining}. Материалы Canvas сняты с публикации — проверьте и откройте нужные заново.`,
                                                );
                                            })
                                        }
                                    >
                                        Импортировать страницы Canvas
                                    </button>
                                    <p className={s.muted}>
                                        До 30 страниц за запуск. Тесты и ответы
                                        учеников не импортируются. Повторный
                                        импорт снимает публикацию предыдущих
                                        копий.
                                    </p>
                                </div>
                            )}
                            {materials.length === 0 && (
                                <p className={s.empty}>
                                    Пока нет доступных материалов.
                                </p>
                            )}
                            {materials.map((m) => (
                                <article
                                    key={m.document_id}
                                    className={s.material}
                                >
                                    <div>
                                        <h3>{m.title}</h3>
                                        <span className={s.muted}>
                                            {m.kind === "canvas_page"
                                                ? "Страница Canvas"
                                                : "Литература"}
                                            {teacher &&
                                                ` · ${m.published ? "Опубликовано" : "Черновик"}`}
                                        </span>
                                    </div>
                                    <div className={s.actions}>
                                        <button
                                            disabled={busy}
                                            onClick={() =>
                                                void run(async () =>
                                                    setSource(
                                                        await api(
                                                            `/materials/${m.document_id}`,
                                                        ),
                                                    ),
                                                )
                                            }
                                        >
                                            Читать
                                        </button>
                                        {teacher ? (
                                            <>
                                                <button
                                                    disabled={busy}
                                                    onClick={() =>
                                                        void run(async () => {
                                                            await api(
                                                                `/materials/${m.document_id}`,
                                                                {
                                                                    method: "PATCH",
                                                                    body: JSON.stringify(
                                                                        {
                                                                            published:
                                                                                !m.published,
                                                                        },
                                                                    ),
                                                                },
                                                            );
                                                            await refresh();
                                                        })
                                                    }
                                                >
                                                    {m.published
                                                        ? "Скрыть"
                                                        : "Опубликовать для всех"}
                                                </button>
                                                <button
                                                    disabled={busy}
                                                    onClick={() => {
                                                        if (
                                                            window.confirm(
                                                                `Удалить «${m.title}» из помощника курса?`,
                                                            )
                                                        )
                                                            void run(
                                                                async () => {
                                                                    await api(
                                                                        `/materials/${m.document_id}`,
                                                                        {
                                                                            method: "DELETE",
                                                                        },
                                                                    );
                                                                    await refresh();
                                                                },
                                                            );
                                                    }}
                                                >
                                                    Удалить
                                                </button>
                                            </>
                                        ) : (
                                            <button
                                                disabled={busy}
                                                onClick={() => {
                                                    setFeedbackDoc(
                                                        m.document_id,
                                                    );
                                                    setComment("");
                                                }}
                                            >
                                                Оставить отзыв
                                            </button>
                                        )}
                                    </div>
                                </article>
                            ))}
                        </section>
                    )}

                    {tab === "analysis" && teacher && (
                        <section className={s.panel}>
                            <h2>Когнитивный профиль материалов</h2>
                            {analysis && (
                                <>
                                    <p>{analysis.note}</p>
                                    <p>
                                        Обработано фрагментов:{" "}
                                        {analysis.chunks_analyzed} (лимит{" "}
                                        {analysis.limit}).
                                    </p>
                                    <div className={s.stats}>
                                        {Object.entries(
                                            analysis.distribution,
                                        ).map(([level, count]) => (
                                            <div key={level}>
                                                <strong>{count}</strong>
                                                <span>
                                                    {labels[level] || level}
                                                </span>
                                            </div>
                                        ))}
                                    </div>
                                    <h3>Примеры для проверки</h3>
                                    {analysis.examples.map((e, i) => (
                                        <details key={i}>
                                            <summary>
                                                {e.title} ·{" "}
                                                {e.levels
                                                    .map((l) => labels[l] || l)
                                                    .join(", ")}
                                            </summary>
                                            <p>{e.text}</p>
                                        </details>
                                    ))}
                                </>
                            )}
                        </section>
                    )}

                    {tab === "summary" && teacher && (
                        <section className={s.panel}>
                            <h2>Вопросы и обратная связь</h2>
                            <p>
                                Показатели использования помогают замечать
                                затруднения, но не измеряют освоение курса.
                                Личные диалоги и имена учеников здесь не
                                отображаются.
                            </p>
                            {summary && (
                                <>
                                    <div className={s.stats}>
                                        {Object.entries(summary.metrics).map(
                                            ([kind, count]) => (
                                                <div key={kind}>
                                                    <strong>{count}</strong>
                                                    <span>
                                                        {labels[kind] || kind}
                                                    </span>
                                                </div>
                                            ),
                                        )}
                                    </div>
                                    <h3>Отзывы о материалах</h3>
                                    <p className={s.muted}>
                                        Количество менее пяти скрыто. Свободные
                                        комментарии преподавателю не
                                        показываются в пилотной версии.
                                    </p>
                                    {summary.feedback.length === 0 ? (
                                        <p>Пока нет отзывов.</p>
                                    ) : (
                                        <ul>
                                            {summary.feedback.map((f, i) => (
                                                <li key={i}>
                                                    {f.title} —{" "}
                                                    {labels[f.rating]}:{" "}
                                                    {f.count ?? "менее 5"}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                </>
                            )}
                        </section>
                    )}
                </>
            )}

            {source && (
                <div className={s.overlay}>
                    <section
                        role="dialog"
                        aria-modal="true"
                        aria-label={source.title}
                        className={s.dialog}
                    >
                        <button autoFocus onClick={() => setSource(null)}>
                            Закрыть материал
                        </button>
                        <h2>{source.title}</h2>
                        {source.chunks.map((c) => (
                            <p key={c.id} className={s.sourceText}>
                                {c.text}
                            </p>
                        ))}
                    </section>
                </div>
            )}
            {feedbackDoc !== null && (
                <div className={s.overlay}>
                    <form
                        role="dialog"
                        aria-modal="true"
                        aria-label="Отзыв о материале"
                        className={s.dialog}
                        onSubmit={(e) => {
                            e.preventDefault();
                            void run(async () => {
                                await api(
                                    `/materials/${feedbackDoc}/feedback`,
                                    {
                                        method: "POST",
                                        body: JSON.stringify({
                                            rating,
                                            comment,
                                        }),
                                    },
                                );
                                setFeedbackDoc(null);
                                setNotice(
                                    "Спасибо! Отзыв сохранён без имени в записи отзыва.",
                                );
                            });
                        }}
                    >
                        <h2>Как вам материал?</h2>
                        <p>
                            Преподаватель увидит сводку без имени. Это не полная
                            техническая анонимность. Не указывайте личные данные
                            в комментарии.
                        </p>
                        <label>
                            Оценка
                            <select
                                autoFocus
                                value={rating}
                                onChange={(e) => setRating(e.target.value)}
                            >
                                {["clear", "difficult", "error"].map((r) => (
                                    <option key={r} value={r}>
                                        {labels[r]}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label>
                            Комментарий (необязательно)
                            <textarea
                                value={comment}
                                maxLength={2000}
                                rows={4}
                                onChange={(e) => setComment(e.target.value)}
                            />
                        </label>
                        <div className={s.actions}>
                            <button className={s.primary} disabled={busy}>
                                Отправить отзыв
                            </button>
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => setFeedbackDoc(null)}
                            >
                                Отмена
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </main>
    );
}
