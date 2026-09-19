import { useId, useState } from "react";
import { PortalAPI } from "./CourseChat";
import s from "../styles/portal.module.css";

export type TeacherReview = {
    decision: string;
    levels: string[];
    knowledge: string[];
    comment: string;
    revision: number;
    updated_at: string;
};
const levels = {
    remember: "Запомнить",
    understand: "Понять",
    apply: "Применить",
    analyze: "Проанализировать",
    evaluate: "Оценить",
    create: "Создать",
};
const knowledge = {
    factual: "Фактическое",
    conceptual: "Концептуальное",
    procedural: "Процедурное",
    metacognitive: "Метакогнитивное",
};
export default function BloomReviewForm({
    example,
    api,
    onSaved,
}: {
    example: {
        chunk_id?: number;
        text_hash?: string;
        levels: string[];
        knowledge?: string[];
        review?: TeacherReview | null;
    };
    api: PortalAPI;
    onSaved: () => Promise<void>;
}) {
    const formId = useId();
    const [saved, setSaved] = useState(example.review);
    const [decision, setDecision] = useState(
        example.review?.decision || "confirmed",
    );
    const [selected, setSelected] = useState(
        example.review?.levels || example.levels,
    );
    const [types, setTypes] = useState(
        example.review?.knowledge || example.knowledge || [],
    );
    const [comment, setComment] = useState(example.review?.comment || "");
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    if (!example.chunk_id || !example.text_hash) return null;
    const toggle = (values: string[], key: string) =>
        values.includes(key)
            ? values.filter((v) => v !== key)
            : [...values, key];
    return (
        <form
            className={s.reviewEntry}
            aria-label="Экспертная разметка фрагмента"
            onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                setMessage("");
                try {
                    const result = await api(
                        `/analysis/${example.chunk_id}/review`,
                        {
                            method: "PUT",
                            body: JSON.stringify({
                                text_hash: example.text_hash,
                                revision: saved?.revision || 0,
                                decision,
                                levels:
                                    decision === "confirmed"
                                        ? example.levels
                                        : selected,
                                knowledge:
                                    decision === "confirmed"
                                        ? example.knowledge || []
                                        : types,
                                comment,
                            }),
                        },
                    );
                    setSaved(result);
                    setMessage(
                        "Разметка сохранена. Автоматический результат сохранён отдельно.",
                    );
                    await onSaved();
                } catch (e) {
                    setError(
                        e instanceof Error
                            ? e.message
                            : "Не удалось сохранить разметку",
                    );
                } finally {
                    setBusy(false);
                }
            }}
        >
            <h4>Решение преподавателя</h4>
            <p className={s.muted}>
                Относится ко всему фрагменту. Можно выбрать несколько процессов
                и типов знания. Это предметное суждение, а не независимая
                валидация алгоритма.
            </p>
            {saved && (
                <p>
                    Сохранено:{" "}
                    {saved.decision === "confirmed"
                        ? "Подтверждено"
                        : saved.decision === "corrected"
                          ? "Исправлено"
                          : "Недостаточно контекста"}
                    . Версия правки: {saved.revision}.
                </p>
            )}
            <label htmlFor={`${formId}-decision`}>Решение</label>
            <select
                id={`${formId}-decision`}
                value={decision}
                disabled={busy}
                onChange={(e) => setDecision(e.target.value)}
            >
                <option value="confirmed">
                    Подтвердить автоматическую разметку
                </option>
                <option value="corrected">Исправить разметку</option>
                <option value="needs_context">Недостаточно контекста</option>
            </select>
            {decision === "corrected" && (
                <>
                    <fieldset disabled={busy}>
                        <legend>Когнитивные процессы</legend>
                        <div className={s.reviewChoices}>
                            {Object.entries(levels).map(([key, label]) => (
                                <label key={key}>
                                    <input
                                        type="checkbox"
                                        checked={selected.includes(key)}
                                        onChange={() =>
                                            setSelected(toggle(selected, key))
                                        }
                                    />
                                    {label}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                    <fieldset disabled={busy}>
                        <legend>Типы знания</legend>
                        <div className={s.reviewChoices}>
                            {Object.entries(knowledge).map(([key, label]) => (
                                <label key={key}>
                                    <input
                                        type="checkbox"
                                        checked={types.includes(key)}
                                        onChange={() =>
                                            setTypes(toggle(types, key))
                                        }
                                    />
                                    {label}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                    <p className={s.muted}>
                        Оставьте выбор пустым, если в этом фрагменте нет
                        учебного требования.
                    </p>
                </>
            )}
            <label>
                Обоснование преподавателя
                <textarea
                    value={comment}
                    maxLength={2000}
                    rows={3}
                    disabled={busy}
                    onChange={(e) => setComment(e.target.value)}
                />
            </label>
            <button disabled={busy}>
                {busy ? "Сохраняем…" : "Сохранить разметку"}
            </button>
            {message && <p role="status">{message}</p>}
            {error && (
                <p role="alert" className={s.error}>
                    {error}
                </p>
            )}
        </form>
    );
}
