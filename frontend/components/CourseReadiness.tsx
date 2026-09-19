import { useCallback, useEffect, useState } from "react";
import { PortalAPI } from "./CourseChat";
import s from "../styles/portal.module.css";
type Readiness = {
    counts: Record<string, number>;
    note: string;
    last_import: null | {
        status: string;
        progress: number;
        total: number;
        updated_at: string;
    };
    materials: {
        document_id: number;
        title: string;
        published: boolean;
        chunks: number;
        indexed: number;
        problems: string[];
        preview_checked: boolean;
        checked_at?: string;
        imported_at?: string;
    }[];
};
export default function CourseReadiness({
    api,
    onSource,
    onMaterials,
}: {
    api: PortalAPI;
    onSource: (id: number) => void;
    onMaterials: () => void;
}) {
    const [data, setData] = useState<Readiness | null>(null);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const refresh = useCallback(async () => {
        setBusy(true);
        setError("");
        try {
            setData(await api("/readiness"));
        } catch (e) {
            setError(
                e instanceof Error ? e.message : "Не удалось проверить курс",
            );
        } finally {
            setBusy(false);
        }
    }, [api]);
    useEffect(() => {
        void refresh();
    }, [refresh]);
    return (
        <section className={s.panel}>
            <div className={s.sectionHead}>
                <h2>Готовность курса</h2>
                <button disabled={busy} onClick={() => void refresh()}>
                    {busy ? "Проверяем…" : "Обновить проверку"}
                </button>
            </div>
            <p className={s.muted}>
                Подготовьте источники, проверьте ответы помощника и опубликуйте
                материалы для учеников.
            </p>
            {error && (
                <p role="alert" className={s.error}>
                    {error}
                </p>
            )}
            {data && (
                <>
                    <div className={s.stats}>
                        {Object.entries({
                            total: "Материалов",
                            published: "Опубликовано",
                            drafts: "Черновиков",
                            problems: "С проблемами",
                            preview_checked: "Проверен чат",
                        }).map(([key, label]) => (
                            <div key={key}>
                                <strong>{data.counts[key]}</strong>
                                <span>{label}</span>
                            </div>
                        ))}
                    </div>
                    <p className={s.disclosure}>{data.note}</p>
                    <p>
                        {data.last_import
                            ? `Последний импорт: ${{ queued: "в очереди", running: "выполняется", complete: "завершён", completed: "завершён", failed: "ошибка" }[data.last_import.status] || data.last_import.status}; обработано ${data.last_import.progress} из ${data.last_import.total}. ${new Date(data.last_import.updated_at).toLocaleString("ru-RU")}`
                            : "Импорт Canvas ещё не запускался. Можно также загрузить литературу вручную."}
                    </p>
                    <button onClick={onMaterials}>
                        Открыть материалы и отчёт импорта
                    </button>
                    {!data.materials.length && (
                        <p className={s.empty}>
                            В курсе пока нет источников. Добавьте материалы,
                            затем проверьте помощника.
                        </p>
                    )}
                    {data.materials.map((m) => (
                        <article key={m.document_id} className={s.reviewEntry}>
                            <h3>{m.title}</h3>
                            <p>
                                {m.published ? "Опубликован" : "Черновик"} ·
                                Фрагментов: {m.chunks}; в текущем поисковом
                                индексе: {m.indexed}.
                            </p>
                            {m.problems.length > 0 ? (
                                <ul>
                                    {m.problems.map((p) => (
                                        <li key={p}>{p}</li>
                                    ))}
                                </ul>
                            ) : (
                                <p>Текст подготовлен для поиска.</p>
                            )}
                            <p>
                                {m.preview_checked
                                    ? "Проверка чата: получен ответ с источниками по текущей версии."
                                    : "По текущей версии ещё нет успешной проверки чата преподавателем."}
                            </p>
                            {m.checked_at && m.preview_checked && (
                                <p className={s.muted}>
                                    Проверено{" "}
                                    {new Date(m.checked_at).toLocaleString(
                                        "ru-RU",
                                    )}
                                </p>
                            )}
                            <button onClick={() => onSource(m.document_id)}>
                                Проверить материал и чат
                            </button>
                        </article>
                    ))}
                </>
            )}
        </section>
    );
}
