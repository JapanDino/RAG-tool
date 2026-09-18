import { useEffect, useRef } from "react";

import styles from "../styles/program-route-brief.module.css";

export type ProgramRouteBriefData = {
  mode: "program_route_brief";
  program_title: string;
  program_version: number;
  headline: string;
  counts: {
    courses: number;
    competencies: number;
    assessed_competencies: number;
    learning_only_competencies: number;
    unmapped_competencies: number;
    missing_evidence_cells: number;
  };
  priorities: {
    kind:
      | "coverage_gap"
      | "assessment_gap"
      | "evidence_gap"
      | "duplication_check"
      | "sequence_check";
    attention: "review" | "watch";
    title: string;
    detail: string;
    confidence: "high" | "medium";
    confidence_label: string;
    review_status: "not_reviewed";
    evidence_status: "none" | "declared" | "missing";
    evidence_count: number;
    evidence_truncated: boolean;
  }[];
  analysis_truncated: boolean;
  findings_truncated: boolean;
  limitations: string[];
  read_only: true;
};

type Props = {
  programTitle: string;
  busy: boolean;
  error: string;
  errorRecovery: "retry" | "refresh";
  result: ProgramRouteBriefData | null;
  canAuthorProgram: boolean;
  onRun: () => void;
  onRefresh: () => void;
  onOpenReview: () => void;
};

const KIND_LABELS: Record<ProgramRouteBriefData["priorities"][number]["kind"], string> = {
  coverage_gap: "Нет маршрута через курс",
  assessment_gap: "Нужно уточнить проверку",
  evidence_gap: "Источник недоступен",
  duplication_check: "Проверить повтор",
  sequence_check: "Проверить порядок",
};

function evidenceLabel(
  priority: ProgramRouteBriefData["priorities"][number],
) {
  if (priority.evidence_status === "none") return "Сохранённых оснований нет";
  if (priority.evidence_status === "missing") {
    return `Недоступных оснований: ${priority.evidence_count}${priority.evidence_truncated ? "+" : ""}`;
  }
  return `Оснований в карте: ${priority.evidence_count}${priority.evidence_truncated ? "+" : ""}`;
}

function focusAndReveal(element: HTMLElement | null) {
  if (!element) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.focus({ preventScroll: true });
  element.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
}

export function ProgramRouteBrief({
  programTitle,
  busy,
  error,
  errorRecovery,
  result,
  canAuthorProgram,
  onRun,
  onRefresh,
  onOpenReview,
}: Props) {
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (result) focusAndReveal(resultHeadingRef.current);
  }, [result]);

  useEffect(() => {
    if (error) focusAndReveal(errorRef.current);
  }, [error]);

  return (
    <section className={styles.brief} aria-labelledby="program-route-brief-title">
      <header className={styles.header}>
        <div>
          <span>Помощник методической проверки</span>
          <h2 id="program-route-brief-title">С чего начать проверку программы</h2>
          <p>Один маршрут по сохранённой карте — без оценок людей и данных учеников.</p>
        </div>
        <button type="button" onClick={onRun} disabled={busy}>
          {busy ? "Собираем маршрут…" : result ? "Собрать заново" : "Собрать маршрут проверки"}
        </button>
      </header>

      <div className={styles.compass} aria-label="Карта программы ведёт к методической проверке">
        <span data-state="ready"><i />Сохранённая карта</span>
        <b aria-hidden="true" />
        <span data-state={result ? "current" : "waiting"}><i />Точка старта</span>
        <b aria-hidden="true" />
        <span data-state="waiting"><i />Проверка доказательств</span>
      </div>

      {busy ? (
        <div className={styles.loading} role="status" aria-live="polite">
          <i /><span /><i /><span /><i />
          <p>Проверяем роль, версию карты и сохранённые связи программы.</p>
        </div>
      ) : error ? (
        <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>
          <div>
            <strong>Маршрут не собрался</strong>
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={errorRecovery === "refresh" ? onRefresh : onRun}
          >
            {errorRecovery === "refresh" ? "Обновить карту программы" : "Попробовать снова"}
          </button>
        </div>
      ) : result ? (
        <article className={styles.result}>
          <div className={styles.resultLead}>
            <span>Точка старта · версия карты {result.program_version}</span>
            <h3 ref={resultHeadingRef} tabIndex={-1}>{result.headline}</h3>
            <p>{result.program_title}</p>
          </div>

          {result.analysis_truncated || result.findings_truncated ? (
            <div className={styles.truncationNotice} role="status">
              <strong>Проверена не вся карта</strong>
              <span>
                Программа превысила безопасный предел анализа. Эта точка старта неполная — откройте доказательства и продолжите проверку вручную.
              </span>
            </div>
          ) : null}

          <dl className={styles.counts} aria-label="Факты по сохранённой карте">
            <div><dt>Курсы</dt><dd>{result.counts.courses}</dd></div>
            <div><dt>Компетенции</dt><dd>{result.counts.competencies}</dd></div>
            <div><dt>С проверкой</dt><dd>{result.counts.assessed_competencies}</dd></div>
          </dl>

          {result.priorities.length ? (
            <ol className={styles.priorities}>
              {result.priorities.map((priority, index) => (
                <li key={`${priority.kind}-${priority.title}`}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <small>{KIND_LABELS[priority.kind]}</small>
                    <strong>{priority.title}</strong>
                    <p>{priority.detail}</p>
                    <em>{priority.confidence_label}</em>
                    <div className={styles.priorityMeta}>
                      <span>{evidenceLabel(priority)}</span>
                      <span>Автоматический сигнал · ещё не проверен</span>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <div className={styles.emptyResult}>
              {result.counts.competencies === 0
                ? canAuthorProgram
                  ? "В карте пока нет компетенций. Добавьте первую компетенцию в редакторе маршрута, затем соберите маршрут снова."
                  : "В карте пока нет компетенций. Передайте её архитектору программы или администратору для наполнения."
                : "Базовая карта не показывает явного разрыва. Откройте доказательства и проверьте методическую логику вручную."}
            </div>
          )}

          <footer>
            <details>
              <summary>Границы этой сводки</summary>
              <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
            {result.counts.competencies > 0 ? (
              <button type="button" onClick={onOpenReview}>Открыть проверку доказательств</button>
            ) : null}
          </footer>
        </article>
      ) : (
        <div className={styles.idle}>
          <strong>{programTitle}</strong>
          <p>Помощник пока ничего не анализировал. Запуск только читает текущую карту.</p>
        </div>
      )}
    </section>
  );
}
