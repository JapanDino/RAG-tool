import { useEffect, useState } from "react";
import { PortalAPI } from "./CourseChat";
import s from "../styles/portal.module.css";
type Settings = {
    quality_enabled: boolean;
    allow_solutions: boolean;
    solution_after_attempts: number;
};
type Entry = {
    id: string;
    day: string;
    question: string;
    answer: string;
    feedback?: string;
    status: string;
    document_ids: number[];
};
export default function QualityPanel({
    api,
    onSource,
}: {
    api: PortalAPI;
    onSource: (id: number) => void;
}) {
    const [settings, setSettings] = useState<Settings | null>(null);
    const [entries, setEntries] = useState<Entry[]>([]);
    const [filter, setFilter] = useState("open");
    const [offset, setOffset] = useState(0);
    const [more, setMore] = useState(false);
    const [error, setError] = useState("");
    const [notice, setNotice] = useState("");
    const [busy, setBusy] = useState(false);
    async function refresh() {
        const r = await api(`/quality?status=${filter}&offset=${offset}`);
        setEntries(r.entries);
        setMore(r.has_more);
    }
    useEffect(() => {
        api("/preferences")
            .then(setSettings)
            .catch((e) => setError(e.message));
    }, [api]);
    useEffect(() => {
        let active = true;
        api(`/quality?status=${filter}&offset=${offset}`)
            .then((r) => {
                if (active) {
                    setEntries(r.entries);
                    setMore(r.has_more);
                }
            })
            .catch((e) => {
                if (active) setError(e.message);
            });
        return () => {
            active = false;
        };
    }, [api, filter, offset]);
    async function act(fn: () => Promise<void>) {
        setBusy(true);
        setError("");
        setNotice("");
        try {
            await fn();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Ошибка запроса");
        } finally {
            setBusy(false);
        }
    }
    return (
        <section className={s.panel}>
            <h2>Качество ответов и обучение</h2>
            <p>
                Здесь появляются вопросы и ответы, которыми ученики согласились
                поделиться. ID учеников и точное время не сохраняются в журнале.
                Обнаруженные имена и контакты маскируются. Автоматическое
                удаление личных данных может ошибаться: узнаваемость по
                контексту сохраняется.
            </p>
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
            {settings && (
                <form
                    className={s.settingsForm}
                    onSubmit={(e) => {
                        e.preventDefault();
                        void act(async () => {
                            setSettings(
                                await api("/preferences", {
                                    method: "PUT",
                                    body: JSON.stringify(settings),
                                }),
                            );
                            setNotice("Настройки сохранены");
                        });
                    }}
                >
                    <label>
                        <input
                            type="checkbox"
                            checked={settings.quality_enabled}
                            onChange={(e) =>
                                setSettings({
                                    ...settings,
                                    quality_enabled: e.target.checked,
                                })
                            }
                        />{" "}
                        Предлагать ученикам делиться вопросами и ответами для
                        контроля качества
                    </label>
                    <label>
                        <input
                            type="checkbox"
                            checked={settings.allow_solutions}
                            onChange={(e) =>
                                setSettings({
                                    ...settings,
                                    allow_solutions: e.target.checked,
                                })
                            }
                        />{" "}
                        Разрешить готовые решения в упражнениях
                    </label>
                    <label>
                        Открывать решение после попыток
                        <select
                            value={settings.solution_after_attempts}
                            disabled={!settings.allow_solutions}
                            onChange={(e) =>
                                setSettings({
                                    ...settings,
                                    solution_after_attempts: Number(
                                        e.target.value,
                                    ),
                                })
                            }
                        >
                            {[1, 2, 3, 4, 5].map((n) => (
                                <option key={n}>{n}</option>
                            ))}
                        </select>
                    </label>
                    <p className={s.muted}>
                        Правило применяется к кнопке решения в упражнениях.
                        Обычный чат остаётся помощником по материалам курса.
                    </p>
                    <button className={s.primary} disabled={busy}>
                        Сохранить настройки
                    </button>
                </form>
            )}
            <h3>Журнал качества</h3>
            <p className={s.muted}>
                Хранение до 30 дней. В журнал не входят личные заметки и ответы
                в упражнениях.
            </p>
            <div className={s.toolbar}>
                <label>
                    Статус
                    <select
                        value={filter}
                        onChange={(e) => {
                            setFilter(e.target.value);
                            setOffset(0);
                        }}
                    >
                        <option value="open">Нужно просмотреть</option>
                        <option value="resolved">Просмотрено</option>
                        <option value="all">Все записи</option>
                    </select>
                </label>
                <button disabled={busy} onClick={() => void act(refresh)}>
                    Обновить журнал
                </button>
            </div>
            {!entries.length && (
                <p className={s.empty}>В этом разделе пока нет записей.</p>
            )}
            {entries.map((entry) => (
                <article className={s.reviewEntry} key={entry.id}>
                    <p className={s.muted}>
                        {entry.day} ·{" "}
                        {entry.status === "resolved"
                            ? "Просмотрено"
                            : "Нужно просмотреть"}
                        {entry.feedback
                            ? ` · ${{ helpful: "Полезно", incorrect: "Ошибка", unclear: "Непонятно", wrong_source: "Не тот источник" }[entry.feedback] || entry.feedback}`
                            : ""}
                    </p>
                    <h4>Вопрос ученика</h4>
                    <p>{entry.question}</p>
                    <details>
                        <summary>Ответ помощника</summary>
                        <p className={s.sourceText}>{entry.answer}</p>
                    </details>
                    <div className={s.actions}>
                        {entry.document_ids.map((id, i) => (
                            <button key={id} onClick={() => onSource(id)}>
                                Источник {i + 1}
                            </button>
                        ))}
                        <button
                            disabled={busy}
                            onClick={() =>
                                void act(async () => {
                                    await api(`/quality/${entry.id}`, {
                                        method: "PATCH",
                                        body: JSON.stringify({
                                            status:
                                                entry.status === "open"
                                                    ? "resolved"
                                                    : "open",
                                        }),
                                    });
                                    await refresh();
                                })
                            }
                        >
                            {entry.status === "open"
                                ? "Отметить просмотренным"
                                : "Вернуть на проверку"}
                        </button>
                    </div>
                </article>
            ))}
            <div className={s.actions}>
                <button
                    disabled={offset === 0 || busy}
                    onClick={() => setOffset((n) => Math.max(0, n - 50))}
                >
                    Предыдущие
                </button>
                <button
                    disabled={!more || busy}
                    onClick={() => setOffset((n) => n + 50)}
                >
                    Следующие
                </button>
            </div>
        </section>
    );
}
