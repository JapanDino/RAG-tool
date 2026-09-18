import { useEffect, useRef } from "react";

import styles from "../styles/program-evidence-routes.module.css";

export type ProgramEvidenceRouteKind = "gap" | "prerequisite";

type EvidenceAnchor = {
  title: string;
  context: string;
  excerpt: string;
  evidence_state: "live" | "manual" | "missing";
  review_label: string;
};

export type ProgramEvidenceRouteData = {
  mode: "program_evidence_route";
  route_kind: ProgramEvidenceRouteKind;
  state: "candidate" | "clear" | "empty" | "partial";
  program_title: string;
  program_version: number;
  headline: string;
  candidate: {
    focus_key: string;
    candidate_type:
      | "coverage_gap"
      | "assessment_gap"
      | "evidence_gap"
      | "duplication_check"
      | "needs_evidence"
      | "order_check"
      | "declared_order";
    subject: string;
    title: string;
    detail: string;
    declared_rationale: string | null;
    confidence_label: string;
    review_label: string;
    evidence_status: "none" | "declared" | "missing";
    evidence: EvidenceAnchor[];
    evidence_truncated: boolean;
  } | null;
  analysis_truncated: boolean;
  action_target: "audit" | "prerequisites";
  action_label: string;
  limitations: string[];
  read_only: true;
};

type Props = {
  programTitle: string;
  selectedKind: ProgramEvidenceRouteKind;
  busy: boolean;
  error: string;
  errorRecovery: "retry" | "refresh";
  result: ProgramEvidenceRouteData | null;
  onSelectKind: (kind: ProgramEvidenceRouteKind) => void;
  onRun: () => void;
  onRefresh: () => void;
  onOpenEvidence: (result: ProgramEvidenceRouteData) => void;
};

const ROUTE_COPY = {
  gap: {
    label: "Пробелы",
    detail: "Где нет курса, проверки, доступного основания или нужен разбор повтора.",
    code: "GAP",
  },
  prerequisite: {
    label: "Предпосылки",
    detail: "Какая явно сохранённая связь требует оснований или сверки порядка.",
    code: "PRE",
  },
};

const TYPE_LABELS: Record<
  NonNullable<ProgramEvidenceRouteData["candidate"]>["candidate_type"],
  string
> = {
  coverage_gap: "Нет связи с курсом",
  assessment_gap: "Нет заявленной проверки",
  evidence_gap: "Источник недоступен",
  duplication_check: "Сверить повтор этапа",
  needs_evidence: "Не хватает оснований",
  order_check: "Сверить порядок",
  declared_order: "Объявленный порядок подтверждён картой",
};

function focusAndReveal(element: HTMLElement | null) {
  if (!element) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.focus({ preventScroll: true });
  element.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "center",
  });
}

export function ProgramEvidenceRoutes({
  programTitle,
  selectedKind,
  busy,
  error,
  errorRecovery,
  result,
  onSelectKind,
  onRun,
  onRefresh,
  onOpenEvidence,
}: Props) {
  const resultRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (result) focusAndReveal(resultRef.current);
  }, [result]);

  useEffect(() => {
    if (error) focusAndReveal(errorRef.current);
  }, [error]);

  return (
    <section className={styles.shell} aria-labelledby="program-evidence-routes-title">
      <header className={styles.header}>
        <div>
          <span>Развилка методической проверки</span>
          <h2 id="program-evidence-routes-title">Какой вопрос проверить сейчас</h2>
          <p>
            Выберите одну ветвь. Помощник прочитает только сохранённую карту и
            приведёт к существующим доказательствам.
          </p>
        </div>
        {!result && !error ? (
          <button type="button" onClick={onRun} disabled={busy}>
            {busy ? "Проверяем выбранный вопрос…" : "Проверить выбранный вопрос"}
          </button>
        ) : null}
      </header>

      <div className={styles.workbench}>
        <div className={styles.switchboard}>
          <div className={styles.sourceRail} aria-hidden="true">
            <i />
            <span />
            <b />
          </div>
          <div className={styles.routeChoices} role="group" aria-label="Вопрос проверки">
            {(Object.keys(ROUTE_COPY) as ProgramEvidenceRouteKind[]).map((kind) => {
              const copy = ROUTE_COPY[kind];
              const selected = selectedKind === kind;
              return (
                <button
                  type="button"
                  key={kind}
                  className={selected ? styles.routeSelected : styles.routeChoice}
                  aria-pressed={selected}
                  onClick={() => onSelectKind(kind)}
                  disabled={busy}
                >
                  <span>{copy.code}</span>
                  <strong>{copy.label}</strong>
                  <small>{copy.detail}</small>
                </button>
              );
            })}
          </div>
          <p className={styles.boundary}>
            Это маршрутизация проверки, а не оценка программы или работы людей.
          </p>
        </div>

        <div className={styles.resultSheet} aria-busy={busy}>
          {busy ? (
            <div className={styles.loading} role="status">
              <div aria-hidden="true"><i /><span /><i /><span /><i /></div>
              <strong>Сверяем роль, версию карты и основания</strong>
              <p>Другие ветви и данные программы не изменяются.</p>
            </div>
          ) : error ? (
            <div className={styles.error} role="alert" tabIndex={-1} ref={errorRef}>
              <strong>Выбранный вопрос не проверен</strong>
              <p>{error}</p>
              <button type="button" onClick={errorRecovery === "refresh" ? onRefresh : onRun}>
                {errorRecovery === "refresh" ? "Обновить карту программы" : "Попробовать снова"}
              </button>
            </div>
          ) : result ? (
            <article className={styles.result} data-state={result.state}>
              <div className={styles.resultLead}>
                <span>
                  {ROUTE_COPY[result.route_kind].code} · версия карты {result.program_version}
                </span>
                <h3 tabIndex={-1} ref={resultRef}>{result.headline}</h3>
                <p>{result.program_title}</p>
              </div>

              {result.analysis_truncated ? (
                <div className={styles.partial} role="status">
                  <strong>Проверена не вся карта</strong>
                  <span>Показанный маршрут неполный — продолжите ручную проверку.</span>
                </div>
              ) : null}

              {result.candidate ? (
                <div className={styles.candidate}>
                  <div className={styles.candidateHeader}>
                    <span>{TYPE_LABELS[result.candidate.candidate_type]}</span>
                    <small>{result.candidate.subject}</small>
                    <h4>{result.candidate.title}</h4>
                    <p>{result.candidate.detail}</p>
                  </div>
                  {result.candidate.declared_rationale ? (
                    <blockquote>
                      <span>Обоснование автора карты</span>
                      {result.candidate.declared_rationale}
                    </blockquote>
                  ) : null}
                  <div className={styles.methodLabels}>
                    <span>{result.candidate.confidence_label}</span>
                    <span>{result.candidate.review_label}</span>
                  </div>
                  {result.candidate.evidence.length ? (
                    <ol className={styles.evidenceList}>
                      {result.candidate.evidence.map((item, index) => (
                        <li key={`${item.title}-${index}`} data-state={item.evidence_state}>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <div>
                            <strong>{item.title}</strong>
                            <small>{item.context}</small>
                            {item.excerpt ? <p>{item.excerpt}</p> : null}
                            <em>{item.review_label}</em>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <div className={styles.noEvidence}>
                      Сохранённых оснований нет — помощник не подставляет вымышленный источник.
                    </div>
                  )}
                  {result.candidate.evidence_truncated ? (
                    <div className={styles.evidenceTruncated}>Показана только первая часть оснований.</div>
                  ) : null}
                </div>
              ) : (
                <div className={styles.emptyResult}>
                  <strong>
                    {result.state === "clear" ? "Автоматический сигнал отсутствует" : "Ветка пока пуста"}
                  </strong>
                  <p>
                    {result.route_kind === "gap"
                      ? "Откройте доказательства для ручной методической сверки: отсутствие сигнала не означает, что программа полна."
                      : "Помощник не придумывает предпосылки. Их можно явно задать в существующем разделе программы."}
                  </p>
                </div>
              )}

              <footer>
                <details>
                  <summary>Границы выбранной проверки</summary>
                  <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                </details>
                <button type="button" onClick={() => onOpenEvidence(result)}>
                  {result.action_label}
                </button>
              </footer>
            </article>
          ) : (
            <div className={styles.idle}>
              <span>{ROUTE_COPY[selectedKind].code} · ожидает запуска</span>
              <strong>{programTitle}</strong>
              <p>Выбранная ветвь ещё не читала карту и ничего в ней не меняла.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
