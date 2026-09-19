import s from "../styles/portal.module.css";

const levels: Record<string, string> = {
    remember: "Запомнить",
    understand: "Понять",
    apply: "Применить",
    analyze: "Проанализировать",
    evaluate: "Оценить",
    create: "Создать",
};
const knowledge: Record<string, string> = {
    factual: "Фактическое",
    conceptual: "Концептуальное",
    procedural: "Процедурное",
    metacognitive: "Метакогнитивное",
};
const statuses: Record<string, string> = {
    proposed: "Предварительная разметка",
    partial: "Часть действий требует уточнения",
    needs_review: "Нужен контекст",
    no_task: "Явное задание не распознано",
};
export type Analysis = {
    distribution: Record<string, number>;
    knowledge_distribution?: Record<string, number>;
    statuses?: Record<string, number>;
    note: string;
    rubric_version?: string;
    references?: { id: string; title: string; url: string }[];
    chunks_analyzed: number;
    limit: number;
    examples_limit?: number;
    examples: {
        document_id: number;
        chunk_id?: number;
        title: string;
        text: string;
        levels: string[];
        status?: string;
        rationale?: string;
        evidence?: {
            quote: string;
            action: string | null;
            object: string | null;
            level: string | null;
            rule_id: string;
            rationale: string;
            knowledge: string[];
            knowledge_evidence: Record<string, string>;
        }[];
    }[];
};

export default function BloomAnalysis({
    analysis,
    onSource,
}: {
    analysis: Analysis | null;
    onSource: (document: number, chunk?: number) => void;
}) {
    return (
        <section className={s.panel}>
            <h2>Учебные действия по Блуму</h2>
            <p className={s.muted}>
                Анализ включает опубликованные материалы и черновики.
                Размечаются требования заданий и учебных целей. Из сложности
                текста нельзя вывести уровень обучения. Один фрагмент может
                содержать несколько действий.
            </p>
            {analysis && (
                <>
                    <p>{analysis.note}</p>
                    <p>
                        Обработано фрагментов: {analysis.chunks_analyzed} (лимит{" "}
                        {analysis.limit}).
                        {analysis.rubric_version && (
                            <> Версия рубрики: {analysis.rubric_version}.</>
                        )}
                    </p>
                    {analysis.chunks_analyzed === 0 && (
                        <p className={s.empty}>
                            Пока нечего анализировать. Добавьте материалы в
                            библиотеку курса.
                        </p>
                    )}
                    {analysis.statuses && (
                        <p role="status">
                            С предложенным уровнем:{" "}
                            {(analysis.statuses.proposed || 0) +
                                (analysis.statuses.partial || 0)}
                            . Требуют уточнения:{" "}
                            {(analysis.statuses.needs_review || 0) +
                                (analysis.statuses.partial || 0)}
                            . Без распознанного задания:{" "}
                            {analysis.statuses.no_task || 0}. Последнее не
                            означает, что материал бесполезен или относится к
                            низкому уровню.
                        </p>
                    )}
                    <h3>Когнитивные процессы</h3>
                    <p className={s.muted}>
                        Количество фрагментов с предварительным уровнем. Это не
                        проценты освоения; один фрагмент может учитываться в
                        нескольких категориях.
                    </p>
                    <div className={s.stats}>
                        {Object.entries(levels).map(([key, title]) => (
                            <div key={key}>
                                <strong>
                                    {analysis.distribution[key] || 0}
                                </strong>
                                <span>{title}</span>
                            </div>
                        ))}
                    </div>
                    {analysis.knowledge_distribution && (
                        <>
                            <h3>Типы знания</h3>
                            <p className={s.muted}>
                                Отдельное измерение по объекту задания. Если
                                признаков недостаточно, тип не назначается.
                                Наличие одного типа не определяет когнитивный
                                уровень.
                            </p>
                            <div className={s.stats}>
                                {Object.entries(knowledge).map(
                                    ([key, title]) => (
                                        <div key={key}>
                                            <strong>
                                                {analysis
                                                    .knowledge_distribution?.[
                                                    key
                                                ] || 0}
                                            </strong>
                                            <span>{title}</span>
                                        </div>
                                    ),
                                )}
                            </div>
                        </>
                    )}
                    <h3>Примеры для проверки</h3>
                    {analysis.examples_limit && (
                        <p className={s.muted}>
                            Показано {analysis.examples.length} из{" "}
                            {analysis.chunks_analyzed} фрагментов (до{" "}
                            {analysis.examples_limit}); сначала неоднозначные
                            задания. Проверьте, что ученик уже изучал, что
                            требуется получить и по каким критериям.
                        </p>
                    )}
                    {analysis.examples.map((example, i) => (
                        <details key={example.chunk_id || i}>
                            <summary>
                                {example.title} ·{" "}
                                {example.levels.length
                                    ? example.levels
                                          .map(
                                              (level) => levels[level] || level,
                                          )
                                          .join(", ")
                                    : statuses[
                                          example.status || "needs_review"
                                      ]}
                            </summary>
                            {example.status && (
                                <p>
                                    <strong>{statuses[example.status]}</strong>
                                </p>
                            )}
                            <p>{example.text}</p>
                            <p>{example.rationale}</p>
                            {example.evidence?.map((item, j) => (
                                <div className={s.bloomEvidence} key={j}>
                                    <blockquote>{item.quote}</blockquote>
                                    <p>
                                        <strong>
                                            {item.level
                                                ? levels[item.level]
                                                : "Уровень не определён"}
                                            .
                                        </strong>{" "}
                                        {item.rationale}
                                    </p>
                                    {item.action && (
                                        <p>
                                            Действие: {item.action}. Объект:{" "}
                                            {item.object || "не указан"}.
                                        </p>
                                    )}
                                    <p>
                                        Тип знания:{" "}
                                        {item.knowledge.length
                                            ? item.knowledge
                                                  .map((k) => knowledge[k] || k)
                                                  .join(", ")
                                            : "не определён"}
                                        .
                                    </p>
                                    {Object.keys(item.knowledge_evidence)
                                        .length > 0 && (
                                        <p className={s.muted}>
                                            Признаки в задании:{" "}
                                            {Object.entries(
                                                item.knowledge_evidence,
                                            )
                                                .map(
                                                    ([key, quote]) =>
                                                        `${knowledge[key]} — «${quote}»`,
                                                )
                                                .join("; ")}
                                            .
                                        </p>
                                    )}
                                    <p className={s.muted}>
                                        Правило: {item.rule_id}. Предложение
                                        требует проверки преподавателем.
                                    </p>
                                </div>
                            ))}
                            <button
                                onClick={() =>
                                    onSource(
                                        example.document_id,
                                        example.chunk_id,
                                    )
                                }
                            >
                                Открыть контекст в материале
                            </button>
                        </details>
                    ))}
                    {!!analysis.references?.length && (
                        <details className={s.privacy}>
                            <summary>Научная основа и ограничения</summary>
                            <p>
                                Рубрика опирается на публикации ниже. Конкретные
                                автоматические правила — реализация проекта, а
                                не метод, валидированный авторами статей. Списки
                                глаголов сами по себе недостаточны.
                                Предварительная разметка не является оценкой
                                ученика.
                            </p>
                            <ul>
                                {analysis.references.map((ref) => (
                                    <li key={ref.id}>
                                        <a
                                            href={ref.url}
                                            target="_blank"
                                            rel="noreferrer"
                                        >
                                            {ref.title}
                                        </a>
                                    </li>
                                ))}
                            </ul>
                        </details>
                    )}
                </>
            )}
        </section>
    );
}
