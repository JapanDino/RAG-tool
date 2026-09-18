import { useEffect, useMemo, useRef, useState } from "react";

import styles from "../styles/curriculum-workspace.module.css";

type AuditKind =
  | "coverage_gap"
  | "assessment_gap"
  | "evidence_gap"
  | "duplication_check"
  | "sequence_check";

type AuditEvidence = {
  contribution_id: number;
  course_id: number;
  course_title: string;
  course_position: number;
  stage: "introduced" | "developed" | "assessed";
  rationale: string;
  evidence_state: "live" | "manual" | "missing";
  evidence_type: "learning_objective" | "assessment_item" | "manual_note";
  evidence_label: string;
  evidence_excerpt: string;
  evidence_confidence?: number | null;
  evidence_review_status: string;
};

export type ProgramAuditFinding = {
  key: string;
  kind: AuditKind;
  attention: "review" | "watch";
  competency_id: number;
  competency_code: string;
  competency_title: string;
  title: string;
  detail: string;
  confidence: "high" | "medium";
  confidence_label: string;
  review_status: "not_reviewed";
  evidence_status: "none" | "declared" | "missing";
  evidence_truncated: boolean;
  evidence: AuditEvidence[];
};

export type ProgramAuditPreview = {
  program_id: number;
  program_version: number;
  analyzed_competencies: number;
  analyzed_contributions: number;
  analysis_truncated: boolean;
  findings_truncated: boolean;
  counts: {
    total: number;
    review: number;
    watch: number;
    coverage_gap: number;
    assessment_gap: number;
    evidence_gap: number;
    duplication_check: number;
    sequence_check: number;
  };
  findings: ProgramAuditFinding[];
};

type ProgramAuditPanelProps = {
  preview: ProgramAuditPreview | null;
  loading: boolean;
  error: string;
  selectedFindingKey: string | null;
  onRun: () => Promise<void>;
  onSelectFinding: (key: string) => void;
};

const KIND_COPY: Record<
  AuditKind,
  { label: string; marker: string; className: string }
> = {
  coverage_gap: {
    label: "Нет курса",
    marker: "—",
    className: styles.auditFindingRisk,
  },
  assessment_gap: {
    label: "Нет проверки",
    marker: "?",
    className: styles.auditFindingRisk,
  },
  evidence_gap: {
    label: "Источник потерян",
    marker: "×",
    className: styles.auditFindingRisk,
  },
  duplication_check: {
    label: "Сверить повтор",
    marker: "↔",
    className: styles.auditFindingWatch,
  },
  sequence_check: {
    label: "Сверить порядок",
    marker: "↕",
    className: styles.auditFindingWatch,
  },
};

const STAGE_COPY = {
  introduced: "Вводится",
  developed: "Развивается",
  assessed: "Проверяется",
};

function sourceTypeCopy(type: AuditEvidence["evidence_type"]) {
  if (type === "learning_objective") return "Цель курса";
  if (type === "assessment_item") return "Задание курса";
  return "Комментарий автора карты";
}

function sourceConfidenceCopy(value?: number | null, state?: AuditEvidence["evidence_state"]) {
  if (state === "missing") return "Нельзя проверить без источника";
  if (value === null || value === undefined) return "Заявлено автором карты";
  if (value >= 0.85) return "Источник распознан уверенно";
  if (value >= 0.6) return "Средняя уверенность — источник стоит проверить";
  return "Низкая уверенность — нужна ручная проверка";
}

function reviewStatusCopy(value: string) {
  const labels: Record<string, string> = {
    confirmed: "Источник подтверждён",
    accepted: "Источник подтверждён",
    unreviewed: "Источник ещё не проверен",
    human_declared: "Связь заявлена автором карты",
    missing: "Источник недоступен",
  };
  return labels[value] || "Нужна методическая проверка";
}

function countCopy(
  count: number,
  one: string,
  few: string,
  many: string
) {
  const modulo100 = count % 100;
  const modulo10 = count % 10;
  if (modulo100 >= 11 && modulo100 <= 14) return `${count} ${many}`;
  if (modulo10 === 1) return `${count} ${one}`;
  if (modulo10 >= 2 && modulo10 <= 4) return `${count} ${few}`;
  return `${count} ${many}`;
}

export function ProgramAuditPanel({
  preview,
  loading,
  error,
  selectedFindingKey,
  onRun,
  onSelectFinding,
}: ProgramAuditPanelProps) {
  const [focusEvidence, setFocusEvidence] = useState(false);
  const evidenceHeadingRef = useRef<HTMLHeadingElement>(null);
  const selectedFinding = useMemo(
    () =>
      preview?.findings.find((finding) => finding.key === selectedFindingKey) ||
      preview?.findings[0] ||
      null,
    [preview, selectedFindingKey]
  );

  useEffect(() => {
    if (focusEvidence && selectedFinding) {
      evidenceHeadingRef.current?.focus();
      setFocusEvidence(false);
    }
  }, [focusEvidence, selectedFinding]);

  const selectFinding = (key: string) => {
    onSelectFinding(key);
    setFocusEvidence(true);
  };

  if (!preview && !loading && !error) {
    return (
      <section className={styles.auditLauncher} aria-labelledby="audit-launch-title">
        <div className={styles.auditRuler} aria-hidden="true" />
        <div>
          <span>Методическая проверка</span>
          <h2 id="audit-launch-title">Найдите разрыв в маршруте до обсуждения</h2>
          <p>
            Проверка читает только сохранённую карту: где нет курса, проверяющего
            задания, доступного источника, где один этап повторён в нескольких
            курсах или проверка стоит раньше заявленного введения или развития.
          </p>
        </div>
        <button type="button" onClick={() => void onRun()}>
          Проверить маршрут
        </button>
      </section>
    );
  }

  return (
    <section
      className={styles.programAuditPanel}
      aria-labelledby="program-audit-title"
      aria-busy={loading}
    >
      <div className={styles.auditRuler} aria-hidden="true" />
      <div className={styles.auditHeader}>
        <div>
          <span>Контрольная рейка</span>
          <h2 id="program-audit-title">Структурные наблюдения</h2>
          <p>Это проверка заявленных связей, а не оценка программы или преподавателей.</p>
        </div>
        <button type="button" onClick={() => void onRun()} disabled={loading}>
          {loading ? "Проверяем маршрут…" : "Проверить заново"}
        </button>
      </div>

      {error ? (
        <div className={styles.auditError} role="alert">
          <div>
            <strong>Проверка не обновилась</strong>
            <span>{error}</span>
          </div>
          <button type="button" onClick={() => void onRun()} disabled={loading}>
            Повторить проверку
          </button>
        </div>
      ) : null}

      {loading && !preview ? (
        <div className={styles.auditLoading} role="status">
          <div className={styles.auditLoadingRail} aria-hidden="true">
            <i />
            <i />
            <i />
          </div>
          <strong>Сверяем курс за курсом</strong>
          <span>Проверяем только явные связи и доступность их оснований.</span>
        </div>
      ) : preview ? (
        <>
          <div className={styles.auditSummary} aria-live="polite">
            <strong>
              {preview.counts.total
                ? countCopy(
                    preview.counts.total,
                    "структурное наблюдение",
                    "структурных наблюдения",
                    "структурных наблюдений"
                  )
                : "Формальных разрывов не найдено"}
            </strong>
            <span>
              {countCopy(
                preview.counts.review,
                "формальный разрыв",
                "формальных разрыва",
                "формальных разрывов"
              )}
            </span>
            <span>
              {countCopy(
                preview.counts.watch,
                "требует методической сверки",
                "требуют методической сверки",
                "требуют методической сверки"
              )}
            </span>
            <span>
              Проверено компетенций: {preview.analyzed_competencies}; связей: {preview.analyzed_contributions}
            </span>
          </div>

          {preview.analysis_truncated || preview.findings_truncated ? (
            <div className={styles.auditTruncated} role="status">
              Показана ограниченная часть карты. Отсутствие других наблюдений нельзя
              считать подтверждением всей программы.
            </div>
          ) : null}

          {!preview.findings.length ? (
            <div className={styles.auditClearState}>
              <strong>В анализируемой части нет формального разрыва</strong>
              <p>
                Все компетенции связаны с курсами и заявленной проверкой, выбранные
                источники доступны, а одинаковые этапы не повторяются в нескольких
                курсах. Это не доказывает достаточность содержания, отсутствие
                смыслового дублирования или качество учебной последовательности.
              </p>
            </div>
          ) : (
            <div className={styles.auditWorkspace}>
              <div className={styles.auditFindingRail} aria-label="Наблюдения проверки">
                {preview.findings.map((finding) => {
                  const meta = KIND_COPY[finding.kind];
                  const selected = finding.key === selectedFinding?.key;
                  return (
                    <button
                      type="button"
                      key={finding.key}
                      className={`${styles.auditFindingTag} ${meta.className} ${
                        selected ? styles.auditFindingSelected : ""
                      }`}
                      aria-pressed={selected}
                      onClick={() => selectFinding(finding.key)}
                    >
                      <span className={styles.auditFindingMarker} aria-hidden="true">
                        {meta.marker}
                      </span>
                      <span>
                        <small>{meta.label}</small>
                        <strong>{finding.competency_code}</strong>
                        <em>{finding.competency_title}</em>
                      </span>
                      <b>Открыть основание</b>
                    </button>
                  );
                })}
              </div>

              {selectedFinding ? (
                <article className={styles.auditEvidenceSheet}>
                  <div className={styles.auditEvidenceHeading}>
                    <span>{KIND_COPY[selectedFinding.kind].label}</span>
                    <h3 ref={evidenceHeadingRef} tabIndex={-1}>
                      {selectedFinding.title}
                    </h3>
                    <p>{selectedFinding.detail}</p>
                  </div>
                  <dl className={styles.auditFindingMeta}>
                    <div>
                      <dt>Компетенция</dt>
                      <dd>
                        {selectedFinding.competency_code} · {selectedFinding.competency_title}
                      </dd>
                    </div>
                    <div>
                      <dt>Надёжность наблюдения</dt>
                      <dd>{selectedFinding.confidence_label}</dd>
                    </div>
                    <div>
                      <dt>Статус решения</dt>
                      <dd>Методическое решение не зафиксировано</dd>
                    </div>
                  </dl>

                  {!selectedFinding.evidence.length ? (
                    <div className={styles.auditNoEvidence}>
                      <strong>Заявленных связей нет</strong>
                      <p>
                        Основание этого наблюдения — отсутствие курса в сохранённой
                        карте. Содержимое курсов автоматически не интерпретировалось.
                      </p>
                    </div>
                  ) : (
                    <div className={styles.auditEvidenceList}>
                      {selectedFinding.evidence.map((evidence) => (
                        <article
                          key={evidence.contribution_id}
                          className={
                            evidence.evidence_state === "missing"
                              ? styles.auditEvidenceMissing
                              : undefined
                          }
                        >
                          <div className={styles.auditCourseStop}>
                            <span>{evidence.course_position}</span>
                            <div>
                              <strong>{evidence.course_title}</strong>
                              <small>{STAGE_COPY[evidence.stage]}</small>
                            </div>
                          </div>
                          <p className={styles.auditRationale}>{evidence.rationale}</p>
                          <blockquote>{evidence.evidence_excerpt}</blockquote>
                          <dl>
                            <div>
                              <dt>Источник</dt>
                              <dd>{sourceTypeCopy(evidence.evidence_type)}</dd>
                            </div>
                            <div>
                              <dt>Надёжность</dt>
                              <dd>
                                {sourceConfidenceCopy(
                                  evidence.evidence_confidence,
                                  evidence.evidence_state
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>Проверка источника</dt>
                              <dd>{reviewStatusCopy(evidence.evidence_review_status)}</dd>
                            </div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  )}
                  {selectedFinding.evidence_truncated ? (
                    <div className={styles.auditTruncated} role="status">
                      Показана ограниченная часть оснований этого наблюдения. Перед
                      методическим решением откройте полную карту компетенции.
                    </div>
                  ) : null}
                  <div className={styles.auditBoundary}>
                    {selectedFinding.kind === "duplication_check"
                      ? "Наблюдение построено по явной карте. Повтор может быть намеренной спиралью обучения; сигнал не оценивает преподавателя и не доказывает педагогический дефект без методической проверки."
                      : "Наблюдение построено по явной карте. Оно не оценивает преподавателя и не доказывает педагогический дефект без методической проверки."}
                  </div>
                </article>
              ) : null}
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
