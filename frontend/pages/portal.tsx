import Head from "next/head";
import {
    FormEvent,
    ReactNode,
    useCallback,
    useEffect,
    useRef,
    useState,
} from "react";
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

function Modal({
    title,
    onClose,
    children,
    returnFocus,
}: {
    title: string;
    onClose: () => void;
    children: ReactNode;
    returnFocus: HTMLElement | null;
}) {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => {
        const dialog = ref.current!;
        const previous = returnFocus;
        dialog.showModal();
        dialog
            .querySelector<HTMLElement>("button, select, textarea, input")
            ?.focus();
        const overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        return () => {
            dialog.close();
            document.body.style.overflow = overflow;
            previous?.focus();
        };
    }, [returnFocus]);
    return (
        <dialog
            ref={ref}
            className={s.dialog}
            aria-label={title}
            onKeyDown={(e) => {
                if (e.key !== "Tab") return;
                const controls = Array.from(
                    e.currentTarget.querySelectorAll<HTMLElement>(
                        "button:not(:disabled), select:not(:disabled), textarea:not(:disabled), input:not(:disabled), a[href]",
                    ),
                );
                const first = controls[0];
                const last = controls[controls.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last?.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first?.focus();
                }
            }}
            onCancel={(e) => {
                e.preventDefault();
                onClose();
            }}
        >
            {children}
        </dialog>
    );
}

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
    const [search, setSearch] = useState("");
    const [publication, setPublication] = useState("all");
    const [loaded, setLoaded] = useState(false);
    const questionRef = useRef<HTMLTextAreaElement>(null);
    const dialogTrigger = useRef<HTMLElement | null>(null);
    const messagesRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        const container = messagesRef.current;
        if (container) container.scrollTop = container.scrollHeight;
    }, [messages, busy]);

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
                    setFeedbackDoc(null);
                    throw new Error(
                        "Сессия завершилась. Откройте помощника заново из курса Canvas.",
                    );
                }
                const body = await response.json().catch(() => ({}));
                if (response.status === 429)
                    throw new Error(
                        "Достигнут часовой лимит запросов. Попробуйте позже.",
                    );
                if (response.status === 503)
                    throw new Error(
                        "Сервис временно недоступен. Попробуйте позже или сообщите преподавателю.",
                    );
                if (response.status === 404)
                    throw new Error(
                        "Материал больше недоступен. Обновите страницу, чтобы увидеть актуальную библиотеку.",
                    );
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
            const saved = sessionStorage.getItem("canvas_portal_token") || "";
            setToken(saved);
            if (!saved) setLoaded(true);
        } catch {
            setLoaded(true);
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
            })
            .finally(() => {
                if (active) setLoaded(true);
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
            return true;
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Не удалось выполнить запрос",
            );
            return false;
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
            .map(({ role, content }) => ({
                role,
                content: content.slice(0, 4000),
            }));
        setMessages((prev) => [...prev, { role: "user", content }]);
        setQuestion("");
        const sent = await run(async () => {
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
        if (!sent) {
            setMessages((prev) =>
                prev.length === messages.length + 1 ? prev.slice(0, -1) : prev,
            );
            setQuestion((current) => current || content);
        }
    }
    const teacher = session?.role === "teacher";
    const visibleMaterials = materials.filter(
        (m) =>
            m.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
            (publication === "all" ||
                m.published === (publication === "published")),
    );
    const sectionTitle = {
        chat: "Чат",
        materials: "Материалы",
        analysis: "Анализ курса",
        summary: "Обратная связь",
    }[tab];

    return (
        <main
            className={s.page}
            onClickCapture={(e) => {
                if (!source && feedbackDoc === null) {
                    const button = (e.target as HTMLElement).closest("button");
                    if (button) dialogTrigger.current = button;
                }
            }}
        >
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
            <a className={s.skip} href="#course-content">
                Перейти к содержимому
            </a>
            <header className={s.header}>
                <div className={s.courseMark} aria-hidden="true">
                    <svg
                        width="24"
                        height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                    >
                        <path d="M4 4h6a3 3 0 0 1 2 1 3 3 0 0 1 2-1h6v15h-6a3 3 0 0 0-2 1 3 3 0 0 0-2-1H4z" />
                        <path d="M12 5v15" />
                    </svg>
                </div>
                <div className={s.courseTitle}>
                    <span className={s.eyebrow}>Помощник курса</span>
                    <h1>{session?.title || "Canvas LMS"}</h1>
                </div>
                {session && (
                    <span className={s.badge}>
                        {teacher ? "Преподаватель" : "Ученик"}
                    </span>
                )}
            </header>
            {error && (!session || tab !== "chat") && (
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
                <section className={s.panel} id="course-content" tabIndex={-1}>
                    <h2>
                        {loaded ? "Войдите через Canvas" : "Загружаем курс…"}
                    </h2>
                    <p>
                        Откройте свой курс и выберите «Помощник курса» в меню.
                        Отдельный пароль не нужен.
                    </p>
                </section>
            ) : (
                <div className={s.layout}>
                    <aside className={s.sidebar}>
                        <p className={s.navTitle}>Навигация курса</p>
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
                                    aria-current={
                                        tab === id ? "page" : undefined
                                    }
                                    onClick={() => {
                                        setTab(id);
                                        if (id === "analysis")
                                            void run(async () =>
                                                setAnalysis(
                                                    await api("/analysis"),
                                                ),
                                            );
                                        if (id === "summary")
                                            void run(async () =>
                                                setSummary(
                                                    await api("/summary"),
                                                ),
                                            );
                                    }}
                                    disabled={busy}
                                >
                                    {title}
                                </button>
                            ))}
                        </nav>
                        <p className={s.navNote}>
                            {teacher
                                ? "Публикуйте материалы, чтобы ученики могли использовать их в чате."
                                : "Ответы и источники из материалов вашего курса."}
                        </p>
                    </aside>
                    <div
                        className={s.content}
                        id="course-content"
                        tabIndex={-1}
                    >
                        <div className={s.breadcrumb}>
                            Помощник курса <span aria-hidden="true">/</span>{" "}
                            <span>{sectionTitle}</span>
                        </div>
                        {busy && tab !== "chat" && (
                            <p role="status" className={s.loading}>
                                Обрабатываем запрос…
                            </p>
                        )}
                        {tab === "chat" && (
                            <section className={s.panel}>
                                <div className={s.sectionHead}>
                                    <h2>Спросите о теме курса</h2>
                                    <button
                                        onClick={() => setMessages([])}
                                        disabled={busy || messages.length === 0}
                                    >
                                        Очистить диалог
                                    </button>
                                </div>
                                <p className={s.muted}>
                                    Задавайте вопросы по материалам и
                                    рекомендованной литературе. Источники
                                    появятся под ответом.
                                </p>
                                <div
                                    className={s.messages}
                                    ref={messagesRef}
                                    role="log"
                                    aria-label="Диалог с помощником"
                                    aria-live="polite"
                                >
                                    {messages.length === 0 && (
                                        <div className={s.empty}>
                                            <span
                                                className={s.emptyIcon}
                                                aria-hidden="true"
                                            >
                                                ?
                                            </span>
                                            <h3>С чего начнём?</h3>
                                            <p>
                                                Выберите вопрос или напишите
                                                свой.
                                            </p>
                                            <div className={s.suggestions}>
                                                {[
                                                    "Объясни основную идею темы",
                                                    "Сравни ключевые понятия",
                                                    "Помоги разобраться в примере",
                                                ].map((text) => (
                                                    <button
                                                        key={text}
                                                        onClick={() => {
                                                            setQuestion(text);
                                                            questionRef.current?.focus();
                                                        }}
                                                    >
                                                        {text}{" "}
                                                        <span aria-hidden="true">
                                                            →
                                                        </span>
                                                    </button>
                                                ))}
                                            </div>
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
                                        <p role="status">
                                            Обрабатываем запрос…
                                        </p>
                                    )}
                                </div>
                                <form onSubmit={ask} className={s.ask}>
                                    {error && (
                                        <p role="alert" className={s.error}>
                                            {error}
                                        </p>
                                    )}
                                    <label htmlFor="question">Ваш вопрос</label>
                                    <textarea
                                        id="question"
                                        ref={questionRef}
                                        value={question}
                                        maxLength={4000}
                                        rows={3}
                                        onChange={(e) =>
                                            setQuestion(e.target.value)
                                        }
                                        placeholder="Например: объясни эту тему на простом примере"
                                    />
                                    <div className={s.composerFooter}>
                                        <span className={s.muted}>
                                            Проверяйте ответы по источникам.
                                        </span>
                                        <button
                                            className={s.primary}
                                            disabled={busy || !question.trim()}
                                        >
                                            {busy
                                                ? "Готовим ответ…"
                                                : "Отправить"}
                                        </button>
                                    </div>
                                </form>
                                <details className={s.privacy}>
                                    <summary>Кто видит мой диалог?</summary>
                                    <p>
                                        Диалог не сохраняется в истории сервера
                                        и не показывается преподавателю. Вопрос
                                        и найденные фрагменты передаются
                                        настроенному сервису модели.
                                    </p>
                                </details>
                            </section>
                        )}

                        {tab === "materials" && (
                            <section className={s.panel}>
                                <h2>Библиотека курса</h2>
                                {teacher && (
                                    <details className={s.upload}>
                                        <summary>
                                            Добавить материалы в курс
                                        </summary>
                                        <p>
                                            Добавляйте PDF, TXT, MD или DOCX до
                                            10 МБ и 60 000 символов. PDF — до 40
                                            страниц с текстовым слоем; сканы без
                                            распознанного текста не
                                            поддерживаются. Новые материалы
                                            видны только вам, пока вы их не
                                            опубликуете.
                                        </p>
                                        <p>
                                            Публикуйте только материалы,
                                            разрешённые всем ученикам пилотного
                                            курса. Индивидуальные условия
                                            доступа Canvas здесь не
                                            воспроизводятся.
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
                                                    if (
                                                        file &&
                                                        file.size >
                                                            10 * 1024 * 1024
                                                    ) {
                                                        setError(
                                                            "Лимит файла: 10 МБ. Разделите документ на главы.",
                                                        );
                                                        return;
                                                    }
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
                                            До 30 страниц за запуск. Тесты и
                                            ответы учеников не импортируются.
                                            Повторный импорт снимает публикацию
                                            предыдущих копий.
                                        </p>
                                    </details>
                                )}
                                <div className={s.toolbar}>
                                    <label className={s.search}>
                                        Поиск по названию
                                        <input
                                            type="search"
                                            value={search}
                                            placeholder="Найти материал"
                                            onChange={(e) =>
                                                setSearch(e.target.value)
                                            }
                                        />
                                    </label>
                                    {teacher && (
                                        <label>
                                            Публикация
                                            <select
                                                aria-label="Публикация"
                                                value={publication}
                                                onChange={(e) =>
                                                    setPublication(
                                                        e.target.value,
                                                    )
                                                }
                                            >
                                                <option value="all">
                                                    Все материалы
                                                </option>
                                                <option value="published">
                                                    Опубликованные
                                                </option>
                                                <option value="draft">
                                                    Черновики
                                                </option>
                                            </select>
                                        </label>
                                    )}
                                    <span
                                        className={s.resultCount}
                                        role="status"
                                    >
                                        Материалов: {visibleMaterials.length}
                                    </span>
                                </div>
                                {materials.length === 0 && (
                                    <p className={s.empty}>
                                        Пока нет доступных материалов.
                                    </p>
                                )}
                                {materials.length > 0 &&
                                    visibleMaterials.length === 0 && (
                                        <p className={s.empty}>
                                            Ничего не найдено. Измените название
                                            или фильтр.
                                        </p>
                                    )}
                                {visibleMaterials.map((m) => (
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
                                                            void run(
                                                                async () => {
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
                                                                },
                                                            )
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
                                                        setRating("clear");
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
                                <p className={s.muted}>
                                    Анализ включает опубликованные материалы и
                                    черновики. Один фрагмент может относиться к
                                    нескольким уровням.
                                </p>
                                {analysis && (
                                    <>
                                        <p>{analysis.note}</p>
                                        <p>
                                            Обработано фрагментов:{" "}
                                            {analysis.chunks_analyzed} (лимит{" "}
                                            {analysis.limit}).
                                        </p>
                                        {analysis.chunks_analyzed === 0 && (
                                            <p className={s.empty}>
                                                Пока нечего анализировать.
                                                Добавьте материалы в библиотеку
                                                курса.
                                            </p>
                                        )}
                                        <div className={s.stats}>
                                            {[
                                                "remember",
                                                "understand",
                                                "apply",
                                                "analyze",
                                                "evaluate",
                                                "create",
                                            ].map((level) => (
                                                <div key={level}>
                                                    <strong>
                                                        {analysis.distribution[
                                                            level
                                                        ] || 0}
                                                    </strong>
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
                                                        .map(
                                                            (l) =>
                                                                labels[l] || l,
                                                        )
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
                                            {[
                                                "questions",
                                                "answers_with_sources",
                                                "no_context",
                                                "errors",
                                            ].map((kind) => (
                                                <div key={kind}>
                                                    <strong>
                                                        {summary.metrics[
                                                            kind
                                                        ] || 0}
                                                    </strong>
                                                    <span>
                                                        {labels[kind] || kind}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                        <h3>Отзывы о материалах</h3>
                                        <p className={s.muted}>
                                            Количество менее пяти скрыто.
                                            Свободные комментарии преподавателю
                                            не показываются в пилотной версии.
                                        </p>
                                        {summary.feedback.length === 0 ? (
                                            <p>Пока нет отзывов.</p>
                                        ) : (
                                            <ul>
                                                {summary.feedback.map(
                                                    (f, i) => (
                                                        <li key={i}>
                                                            {f.title} —{" "}
                                                            {labels[f.rating]}:{" "}
                                                            {f.count ??
                                                                "менее 5"}
                                                        </li>
                                                    ),
                                                )}
                                            </ul>
                                        )}
                                    </>
                                )}
                            </section>
                        )}
                    </div>
                </div>
            )}

            {source && (
                <Modal
                    returnFocus={dialogTrigger.current}
                    title={source.title}
                    onClose={() => setSource(null)}
                >
                    <section>
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
                </Modal>
            )}
            {feedbackDoc !== null && (
                <Modal
                    returnFocus={dialogTrigger.current}
                    title="Отзыв о материале"
                    onClose={() => {
                        if (!busy) setFeedbackDoc(null);
                    }}
                >
                    <form
                        className={s.feedbackForm}
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
                        <p className={s.feedbackTitle}>
                            {
                                materials.find(
                                    (m) => m.document_id === feedbackDoc,
                                )?.title
                            }
                        </p>
                        {error && (
                            <p role="alert" className={s.error}>
                                {error}
                            </p>
                        )}
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
                </Modal>
            )}
        </main>
    );
}
