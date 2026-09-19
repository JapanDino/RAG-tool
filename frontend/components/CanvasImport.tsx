import { useEffect, useState } from "react";
import { PortalAPI } from "./CourseChat";
import s from "../styles/portal.module.css";
type Job = {
    id: string;
    status: string;
    progress: number;
    total: number;
    details: {
        title: string;
        status: string;
        reason?: string;
        module?: string;
    }[];
};
export default function CanvasImport({
    api,
    onComplete,
}: {
    api: PortalAPI;
    onComplete: () => Promise<void>;
}) {
    const [job, setJob] = useState<Job | null>(null);
    const [error, setError] = useState("");
    const [starting, setStarting] = useState(false);
    const running = job?.status === "running" || job?.status === "queued";
    useEffect(() => {
        let active = true;
        api("/imports/latest")
            .then((r) => {
                if (active) setJob(r);
            })
            .catch((e) => {
                if (active) setError(e.message);
            });
        return () => {
            active = false;
        };
    }, [api]);
    useEffect(() => {
        if (!running) return;
        let active = true;
        const timer = setInterval(() => {
            api("/imports/latest")
                .then(async (r) => {
                    if (!active) return;
                    setJob(r);
                    if (r && !["running", "queued"].includes(r.status))
                        await onComplete();
                })
                .catch((e) => {
                    if (active) setError(e.message);
                });
        }, 2000);
        return () => {
            active = false;
            clearInterval(timer);
        };
    }, [api, running, onComplete]);
    return (
        <div className={s.importPanel}>
            <button
                disabled={running || starting}
                onClick={async () => {
                    setStarting(true);
                    setError("");
                    try {
                        const r = await api("/imports", { method: "POST" });
                        setJob({
                            id: r.id,
                            status: "queued",
                            progress: 0,
                            total: 0,
                            details: [],
                        });
                    } catch (e) {
                        setError(
                            e instanceof Error ? e.message : "Ошибка импорта",
                        );
                    } finally {
                        setStarting(false);
                    }
                }}
            >
                Импортировать курс Canvas
            </button>
            <p className={s.muted}>
                Страницы, PDF, DOCX, TXT и MD, с привязкой к модулям. До 300
                материалов. Закрытые элементы и модули с условиями доступа
                пропускаются. Повторный импорт снимает публикацию копий:
                проверьте их и опубликуйте заново.
            </p>
            {error && (
                <p role="alert" className={s.error}>
                    {error}
                </p>
            )}
            {job && (
                <div>
                    <p role="status">
                        {running
                            ? "Идёт импорт"
                            : job.status === "complete"
                              ? "Импорт завершён"
                              : "Импорт прерван — можно повторить"}{" "}
                        · {job.progress} из {job.total || "…"}
                    </p>
                    {running && (
                        <progress
                            aria-label="Прогресс импорта"
                            value={job.total ? job.progress : undefined}
                            max={job.total || 1}
                        />
                    )}
                    <details>
                        <summary>
                            Отчёт об импорте ({job.details.length})
                        </summary>
                        <ul className={s.importReport}>
                            {job.details.map((d, i) => (
                                <li key={i}>
                                    <strong>{d.title}</strong> ·{" "}
                                    {d.status === "imported"
                                        ? "Импортирован"
                                        : d.status === "skipped"
                                          ? "Пропущен"
                                          : "Ошибка"}
                                    {d.module && ` · ${d.module}`}
                                    {d.reason && <p>{d.reason}</p>}
                                </li>
                            ))}
                        </ul>
                    </details>
                </div>
            )}
        </div>
    );
}
