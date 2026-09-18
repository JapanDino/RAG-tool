import Head from "next/head";
import Link from "next/link";
import { useRouter } from "next/router";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import CanvasSyncPanel, {
  CanvasOAuthResult,
  CanvasSyncPreview,
  InstructorCanvasOAuthStatus,
} from "../../../components/CanvasSyncPanel";
import {
  ApiRequestError,
  authenticatedJson,
  clearSessionCsrf,
  SESSION_ENDED_EVENT,
} from "../../../lib/auth-api";
import styles from "../../../styles/teacher-workspace.module.css";


type EvidenceExcerpt = {
  object_type: string;
  object_id?: number | null;
  document_id?: number | null;
  quote: string;
  source_start?: number | null;
  source_end?: number | null;
};

type CopilotCitation = {
  source_id: string;
  document_id?: number;
  document_title: string;
  module_title?: string | null;
  quote: string;
  source_url?: string | null;
  score: number;
};

type CopilotSuggestion = {
  id?: number;
  draft_ref?: string;
  finding_id: number;
  action_type: "create_material" | "create_assessment" | "revise_assessment";
  title: string;
  draft: string;
  target_bloom_level: string;
  rationale: string;
  citations: CopilotCitation[];
  confidence: number;
  insufficient_context: boolean;
  status: "draft" | "accepted" | "rejected";
  version: number;
  limitations: string[];
  reviewed_by?: string | null;
};

type AttentionFinding = {
  id: number;
  finding_type: string;
  severity: "info" | "low" | "medium" | "high";
  status: "new" | "confirmed" | "rejected" | "resolved" | "ignored";
  title: string;
  description: string;
  recommendation: string;
  confidence: number;
  confidence_band: "strong" | "review" | "weak";
  confidence_label: string;
  attention_label: string;
  thread_focus: "objective_material" | "objective_assessment" | "whole_course";
  evidence: EvidenceExcerpt[];
  uncertainty_reasons: string[];
  reviewed_by?: string | null;
  reviewed_at?: string | null;
};

type TutorPolicy = {
  course_id: number;
  enabled: boolean;
  answer_style: "balanced" | "guided" | "concise";
  version: number;
  safety: {
    student_visible_content_only: boolean;
    assessment_guard: boolean;
    abstain_without_support: boolean;
    citations_required: boolean;
  };
  updated_at?: string | null;
};

type TutorDataPolicy = {
  organization_id: number;
  retention_days: 30 | 90 | 180 | 365;
  version: number;
  automatic_purge: boolean;
  student_self_delete: boolean;
  updated_at?: string | null;
};

type TeacherWorkspace = {
  course: {
    id: number;
    title: string;
    description: string;
    source_type: string;
  };
  latest_audit?: {
    id: number;
    status: string;
    progress: number;
    created_at?: string | null;
    finished_at?: string | null;
    failure_message?: string | null;
  } | null;
  health: {
    objectives_total: number;
    materials_total: number;
    assessments_total: number;
    objective_material_coverage: number;
    objective_assessment_coverage: number;
    findings_total: number;
    high_severity_findings: number;
    findings_reviewed: number;
  };
  tutor_quality: {
    period_days: number;
    minimum_feedback_sample: number;
    signal: "empty" | "early" | "coverage" | "review" | "limited" | "steady";
    questions_total: number;
    answer_responses: number;
    supported_answers: number;
    guidance_answers: number;
    abstained_answers: number;
    answers_needing_review: number;
    rated_answers: number;
    helpful_answers?: number | null;
    helpful_rate?: number | null;
  };
  tutor_policy: TutorPolicy;
  findings: AttentionFinding[];
};

type IdentityContext = {
  user: { email: string; display_name: string };
  courses: {
    id: number;
    organization_id: number;
    roles: string[];
    actions: string[];
  }[];
};

type InstructorAgentPriority = {
  finding_ref: string;
  title: string;
  severity: AttentionFinding["severity"];
  status: AttentionFinding["status"];
  confidence: number;
  confidence_label: string;
  evidence_count: number;
};

type InstructorGapCandidate = {
  gap_ref: string;
  topic_label: string;
  module_title?: string | null;
  signal_kind: "repeated_unsupported" | "low_helpfulness" | "mixed";
  signal_label: string;
  cohort_band: "3–5" | "6–10" | "11+";
  event_band: "3–5" | "6–10" | "11+";
  confidence: number;
  confidence_label: string;
  evidence: { kind: "course_excerpt"; source_label: string; excerpt: string };
};

type InstructorInterventionDraft = {
  mode: "intervention_draft";
  intervention_ref: string;
  title: string;
  content: string;
  rationale: string;
  confidence: number;
  citations: { kind: "course_excerpt"; source_label: string; excerpt: string }[];
  signal_kind: InstructorGapCandidate["signal_kind"];
  cohort_band: InstructorGapCandidate["cohort_band"];
  event_band: InstructorGapCandidate["event_band"];
  review_status: "draft" | "accepted" | "rejected";
  review_version: number;
  limitations: string[];
};

type InstructorAgentRun = {
  run_id: string;
  status:
    | "queued"
    | "routing"
    | "tool_running"
    | "generating"
    | "completed"
    | "abstained"
    | "failed";
  user_state: { label: string; recovery_action?: string | null };
  response?: (
    | {
        mode: "course_summary";
        course_title: string;
        headline: string;
        health: {
          audit_state: "missing" | "queued" | "running" | "done" | "failed";
          findings_total: number;
          high_severity_findings: number;
          findings_reviewed: number;
        };
        priorities: InstructorAgentPriority[];
        limitations: string[];
      }
    | {
        mode: "finding_review";
        finding_ref: string;
        title: string;
        severity: AttentionFinding["severity"];
        status: AttentionFinding["status"];
        description: string;
        recommendation: string;
        confidence: number;
        confidence_label: string;
        evidence: { kind: "course_excerpt"; source_label: string; excerpt: string }[];
        limitations: string[];
      }
    | {
        mode: "question_gaps";
        course_title: string;
        window_days: 30;
        privacy_threshold: string;
        candidates: InstructorGapCandidate[];
        limitations: string[];
      }
    | {
        mode: "improvement_draft";
        draft_ref: string;
        title: string;
        action_type: CopilotSuggestion["action_type"];
        target_bloom_level: string;
        content: string;
        rationale: string;
        confidence: number;
        citations: { kind: "course_excerpt"; source_label: string; excerpt: string }[];
        insufficient_context: boolean;
        review_status: CopilotSuggestion["status"];
        review_version: number;
        limitations: string[];
      }
    | {
        mode: "canvas_change_preview";
        change_set_ref: string;
        course_title: string;
        title: string;
        operation: "create_page" | "create_assignment" | "update_assignment";
        ready_for_canvas: boolean;
        module_title?: string | null;
        content: string;
        confidence: number;
        review_status: "accepted";
        warnings: string[];
        read_only: true;
      }
  ) | null;
};

type AgentAccepted = { execute_url: string };
type InstructorDraftReview = {
  mode: "reviewed_draft";
  draft_ref: string;
  status: "accepted" | "rejected";
  version: number;
  content: string;
  canvas_changed: false;
};
type InstructorInterventionReview = {
  mode: "reviewed_intervention";
  intervention_ref: string;
  status: "accepted" | "rejected";
  version: number;
  content: string;
  edit_distance_ratio: number;
  decision_latency_seconds: number;
  canvas_changed: false;
};
type InterventionRecovery = "" | "refresh" | "retry";
type InstructorAgentStage = "idle" | "submitting" | InstructorAgentRun["status"];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const IDENTITY_STORAGE_KEY = "rag-dev-user";

const STATUS_LABELS: Record<AttentionFinding["status"], string> = {
  new: "Ждёт решения",
  confirmed: "Подтверждено",
  rejected: "Отклонено",
  resolved: "Исправлено",
  ignored: "Отложено",
};

const SEVERITY_LABELS: Record<AttentionFinding["severity"], string> = {
  high: "Высокое влияние",
  medium: "Среднее влияние",
  low: "Низкое влияние",
  info: "Наблюдение",
};

const EVIDENCE_LABELS: Record<string, string> = {
  learning_objective: "Учебная цель",
  learning_material: "Материал",
  assessment_item: "Задание",
  course_source: "Источник курса",
};

const DRAFT_ACTION_LABELS: Record<CopilotSuggestion["action_type"], string> = {
  create_material: "Новый фрагмент материала",
  create_assessment: "Новое задание",
  revise_assessment: "Переработанное задание",
};

const BLOOM_LEVEL_LABELS: Record<string, string> = {
  remember: "запоминание",
  understand: "понимание",
  apply: "применение",
  analyze: "анализ",
  evaluate: "оценка",
  create: "создание",
};

const CANVAS_CHANGE_LABELS: Record<
  "create_page" | "create_assignment" | "update_assignment",
  string
> = {
  create_page: "Новая страница",
  create_assignment: "Новое задание",
  update_assignment: "Обновление задания",
};

function canvasChangeWarning(warning: string) {
  if (warning.includes("Course is not connected to Canvas")) {
    return "Для реальной публикации сначала потребуется связать этот курс с курсом Canvas.";
  }
  if (warning.includes("Canvas course ID is required")) {
    return "Перед публикацией потребуется выбрать точный курс Canvas.";
  }
  if (warning.includes("assignment ID could not be mapped")) {
    return "Не удалось однозначно найти задание в Canvas — цель нужно будет выбрать вручную.";
  }
  return warning;
}

async function api<T>(
  path: string,
  identity: string,
  init?: RequestInit
): Promise<T> {
  try {
    return await authenticatedJson<T>(API_BASE, path, identity, init);
  } catch (reason) {
    if (reason instanceof ApiRequestError && reason.status === 404) {
      throw new ApiRequestError(
        "Курс недоступен или у вас нет нужной роли.",
        404
      );
    }
    throw reason;
  }
}

function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

function focusAndReveal(element: HTMLElement | null) {
  if (!element) return;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.focus({ preventScroll: true });
  element.scrollIntoView({
    behavior: reducedMotion ? "auto" : "smooth",
    block: "start",
  });
}

function InstructorReviewBrief({
  stage,
  run,
  error,
  openingPriorityRef,
  evidenceReady,
  draftStatus,
  previewReady,
  errorScope,
  onRun,
  onOpenPriority,
  onRetryEvidence,
  canRetryEvidence,
}: {
  stage: InstructorAgentStage;
  run: InstructorAgentRun | null;
  error: string;
  openingPriorityRef: string;
  evidenceReady: boolean;
  draftStatus: CopilotSuggestion["status"] | null;
  previewReady: boolean;
  errorScope: "summary" | "evidence" | "";
  onRun: () => void;
  onOpenPriority: (priority: InstructorAgentPriority) => void;
  onRetryEvidence: () => void;
  canRetryEvidence: boolean;
}) {
  const busy = ["submitting", "queued", "routing", "tool_running", "generating"].includes(stage);
  const summary = run?.response?.mode === "course_summary" ? run.response : null;
  const threadStates = [
    summary ? "done" : busy ? "active" : "ready",
    evidenceReady ? "done" : summary ? "active" : "waiting",
    draftStatus ? (previewReady || draftStatus !== "draft" ? "done" : "active") : evidenceReady ? "active" : "waiting",
  ] as const;
  const stateCopy = {
    ready: "готов к началу",
    waiting: "ещё не начат",
    active: "текущий шаг",
    done: "завершён",
  } as const;
  const progressLabel =
    stage === "submitting"
      ? "Передаём запрос"
      : stage === "queued"
        ? "Запрос принят"
        : stage === "routing"
          ? "Проверяем курс и роль"
          : "Собираем приоритеты и доказательства";

  return (
    <section className={styles.instructorBrief} aria-labelledby="instructor-brief-title">
      <header className={styles.instructorBriefHeader}>
        <div>
          <span>Помощник преподавателя · текущий курс</span>
          <h2 id="instructor-brief-title">С чего начать проверку</h2>
          <p>
            Помощник собирает до трёх приоритетов из последней проверки. Вопросы,
            оценки и переписка отдельных учеников сюда не попадают.
          </p>
        </div>
        <button type="button" onClick={onRun} disabled={busy}>
          {busy ? "Собираем сводку…" : summary ? "Обновить сводку" : "Проверить приоритет"}
        </button>
      </header>

      <ol className={styles.reviewThread} aria-label="Путь от приоритета к проверенному черновику">
        <li data-state={threadStates[0]} aria-current={threadStates[0] === "active" ? "step" : undefined}>
          <i>{threadStates[0] === "done" ? "✓" : "1"}</i><span><strong>Приоритет</strong><small>Только текущий курс · {stateCopy[threadStates[0]]}</small></span>
        </li>
        <li data-state={threadStates[1]} aria-current={threadStates[1] === "active" ? "step" : undefined}>
          <i>{threadStates[1] === "done" ? "✓" : "2"}</i><span><strong>Доказательство</strong><small>Проверяет преподаватель · {stateCopy[threadStates[1]]}</small></span>
        </li>
        <li data-state={threadStates[2]} aria-current={threadStates[2] === "active" ? "step" : undefined}>
          <i>{threadStates[2] === "done" ? "✓" : "3"}</i><span><strong>Черновик</strong><small>Canvas не меняется · {stateCopy[threadStates[2]]}</small></span>
        </li>
      </ol>

      {busy && (
        <div className={styles.instructorBriefProgress} role="status" aria-live="polite">
          <span className={styles.spinner} />
          <div><strong>{progressLabel}</strong><small>Решения и материалы курса не изменяются.</small></div>
        </div>
      )}

      {error && (
        <div className={styles.instructorBriefError} role="alert">
          <div><strong>{errorScope === "evidence" ? (canRetryEvidence ? "Доказательства не открылись" : "Приоритет устарел") : "Сводка не подготовилась"}</strong><span>{error}</span></div>
          <button type="button" onClick={errorScope === "evidence" ? onRetryEvidence : onRun}>
            {errorScope === "evidence" ? (canRetryEvidence ? "Повторить открытие" : "Обновить сводку") : "Попробовать снова"}
          </button>
        </div>
      )}

      {summary && !busy && (
        <div className={styles.instructorBriefResult} aria-live="polite">
          <div className={styles.instructorBriefVerdict}>
            <span>Рекомендация на сейчас</span>
            <h3>{summary.headline}</h3>
            <dl>
              <div><dt>Всего наблюдений</dt><dd>{summary.health.findings_total}</dd></div>
              <div><dt>Высокое влияние</dt><dd>{summary.health.high_severity_findings}</dd></div>
              <div><dt>Уже проверено</dt><dd>{summary.health.findings_reviewed}</dd></div>
            </dl>
          </div>
          {summary.priorities.length ? (
            <div className={styles.instructorPriorities}>
              {summary.priorities.map((priority, index) => (
                <article key={priority.finding_ref}>
                  <div>
                    <span data-severity={priority.severity}>0{index + 1} · {SEVERITY_LABELS[priority.severity]}</span>
                    <small>{priority.evidence_count} {russianPlural(priority.evidence_count, ["фрагмент", "фрагмента", "фрагментов"])} в опоре</small>
                  </div>
                  <h3>{priority.title}</h3>
                  <p>{priority.confidence_label} · {percentage(priority.confidence)}</p>
                  <button
                    type="button"
                    onClick={() => onOpenPriority(priority)}
                    disabled={!!openingPriorityRef}
                  >
                    {openingPriorityRef === priority.finding_ref
                      ? "Проверяем доказательства…"
                      : "Открыть доказательства"}
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.instructorBriefEmpty}>
              В завершённой проверке нет наблюдений, которые требуют решения прямо сейчас.
            </div>
          )}
          <details className={styles.instructorBriefLimits}>
            <summary>Границы этой сводки</summary>
            <ul>{summary.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </details>
        </div>
      )}
    </section>
  );
}

function CourseImprovementLoop({
  stage,
  run,
  error,
  draft,
  draftText,
  actionBusy,
  actionError,
  actionRecovery,
  failedCandidate,
  resultHeadingRef,
  draftHeadingRef,
  decisionStatusRef,
  onRun,
  onPrepare,
  onDraftText,
  onReview,
}: {
  stage: InstructorAgentStage;
  run: InstructorAgentRun | null;
  error: string;
  draft: InstructorInterventionDraft | null;
  draftText: string;
  actionBusy: boolean;
  actionError: string;
  actionRecovery: InterventionRecovery;
  failedCandidate: InstructorGapCandidate | null;
  resultHeadingRef: React.RefObject<HTMLHeadingElement>;
  draftHeadingRef: React.RefObject<HTMLHeadingElement>;
  decisionStatusRef: React.RefObject<HTMLElement>;
  onRun: () => void;
  onPrepare: (candidate: InstructorGapCandidate) => void;
  onDraftText: (value: string) => void;
  onReview: (status: "accepted" | "rejected") => void;
}) {
  const busy = ["submitting", "queued", "routing", "tool_running", "generating"].includes(stage);
  const result = run?.response?.mode === "question_gaps" ? run.response : null;
  const hasOpenDraft = draft?.review_status === "draft";

  return (
    <section className={styles.improvementLoop} aria-labelledby="improvement-loop-title">
      <header className={styles.improvementLoopHeader}>
        <div>
          <span>Общий сигнал · последние 30 дней</span>
          <h2 id="improvement-loop-title">Где ученикам не хватает опоры</h2>
          <p>
            Помощник показывает тему только тогда, когда одна и та же трудность
            повторилась у нескольких активных учеников и связана с материалом курса.
          </p>
        </div>
        <button type="button" onClick={onRun} disabled={busy || actionBusy || hasOpenDraft}>
          {busy
            ? "Проверяем общий сигнал…"
            : hasOpenDraft
              ? "Сначала примите решение"
              : result
                ? "Обновить сигнал"
                : "Найти повторяющиеся трудности"}
        </button>
      </header>

      <div className={styles.privacyTape} aria-label="Сигнал становится видимым только после порога приватности">
        <div className={styles.privacyMarks} aria-hidden="true">
          <i /><i /><i />
        </div>
        <span className={styles.privacyJoin} aria-hidden="true" />
        <div className={styles.privacySignal}>
          <span>Порог приватности</span>
          <strong>Только общий сигнал</strong>
          <small>Не менее трёх учеников · без вопросов и имён</small>
        </div>
      </div>

      {busy && (
        <div className={styles.improvementProgress} role="status" aria-live="polite">
          <span className={styles.spinner} />
          <div>
            <strong>Ищем повторение и проверяем опору в курсе</strong>
            <small>Скрытые или единичные обращения не появятся в результате.</small>
          </div>
        </div>
      )}

      {error && (
        <div className={styles.improvementError} role="alert">
          <div><strong>Общий сигнал не подготовился</strong><span>{error}</span></div>
          <button type="button" onClick={onRun}>Попробовать снова</button>
        </div>
      )}

      {result && !busy && (
        <div className={styles.improvementResult} aria-live="polite">
          <div className={styles.improvementResultHeading}>
            <div>
              <span>Результат проверки</span>
              <h3 ref={resultHeadingRef} tabIndex={-1}>
                {result.candidates.length
                  ? "Есть общий сигнал для улучшения"
                  : "Пока недостаточно общего сигнала"}
              </h3>
            </div>
            <small>{result.privacy_threshold}</small>
          </div>

          {result.candidates.length ? (
            <div className={styles.gapCandidates}>
              {result.candidates.map((candidate) => (
                <article className={styles.gapCandidate} key={candidate.gap_ref}>
                  <div className={styles.gapCandidateTopline}>
                    <span>Повторяющаяся трудность</span>
                    <small>{candidate.confidence_label}</small>
                  </div>
                  <h4>{candidate.topic_label}</h4>
                  {candidate.module_title && <p className={styles.gapModule}>{candidate.module_title}</p>}
                  <p>{candidate.signal_label}</p>
                  <dl className={styles.gapBands}>
                    <div><dt>Охват группы</dt><dd>{candidate.cohort_band}</dd></div>
                    <div><dt>Повторения</dt><dd>{candidate.event_band}</dd></div>
                  </dl>
                  <div className={styles.gapEvidence}>
                    <span>Опора в курсе · {candidate.evidence.source_label}</span>
                    <blockquote>«{candidate.evidence.excerpt}»</blockquote>
                  </div>
                  <button
                    type="button"
                    onClick={() => onPrepare(candidate)}
                    disabled={actionBusy || hasOpenDraft}
                  >
                    {actionBusy ? "Готовим материал…" : "Подготовить материал"}
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <div className={styles.improvementEmpty}>
              <span aria-hidden="true">◎</span>
              <div>
                <strong>Ничего не нужно разбирать прямо сейчас</strong>
                <p>
                  Темы ниже порога приватности и трудности без подтверждения в
                  текущих материалах остаются скрытыми. Это нормальный результат.
                </p>
              </div>
            </div>
          )}

          <details className={styles.improvementLimits}>
            <summary>Что этот сигнал не означает</summary>
            <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
          </details>
        </div>
      )}

      {actionError && !draft && (
        <div className={styles.improvementActionError} role="alert">
          <div>
            <strong>Материал не подготовился</strong>
            <span>{actionError}</span>
          </div>
          <button
            type="button"
            onClick={
              actionRecovery === "retry" && failedCandidate
                ? () => onPrepare(failedCandidate)
                : onRun
            }
          >
            {actionRecovery === "retry" ? "Попробовать снова" : "Обновить сигнал"}
          </button>
        </div>
      )}

      {draft && (
        <article className={styles.interventionSheet} aria-labelledby="intervention-title">
          <header>
            <div>
              <span>Материал для проверки</span>
              <h3 id="intervention-title" ref={draftHeadingRef} tabIndex={-1}>{draft.title}</h3>
              <p>{draft.rationale}</p>
            </div>
            <strong
              ref={decisionStatusRef}
              data-status={draft.review_status}
              role={draft.review_status === "draft" ? undefined : "status"}
              aria-label={
                draft.review_status === "accepted"
                  ? "Принято"
                  : draft.review_status === "rejected"
                    ? "Отклонено"
                    : undefined
              }
              aria-live="polite"
              tabIndex={-1}
            >
              {draft.review_status === "draft"
                ? "Ждёт решения"
                : draft.review_status === "accepted"
                  ? "Принято"
                  : "Отклонено"}
            </strong>
          </header>

          <label className={styles.interventionEditor}>
            <span>Текст материала</span>
            <textarea
              value={draftText}
              onChange={(event) => onDraftText(event.target.value)}
              disabled={actionBusy || draft.review_status !== "draft"}
              rows={10}
              maxLength={6000}
            />
          </label>

          <div className={styles.interventionEvidence}>
            <span>Проверяемая опора</span>
            {draft.citations.map((citation, index) => (
              <blockquote key={`${citation.source_label}-${index}`}>
                <strong>{citation.source_label}</strong>
                <p>«{citation.excerpt}»</p>
              </blockquote>
            ))}
          </div>

          {actionError && (
            <div className={styles.localActionError} role="alert">
              <span>{actionError}</span>
              {actionRecovery === "refresh" && (
                <button type="button" onClick={onRun}>Обновить сигнал</button>
              )}
            </div>
          )}

          <footer>
            <div>
              <strong>Canvas не изменён</strong>
              <span>Решение сохраняется только внутри помощника.</span>
            </div>
            {draft.review_status === "draft" && (
              <div className={styles.interventionActions}>
                <button type="button" className={styles.rejectButton} onClick={() => onReview("rejected")} disabled={actionBusy}>
                  Отклонить
                </button>
                <button type="button" className={styles.confirmButton} onClick={() => onReview("accepted")} disabled={actionBusy || draftText.trim().length < 10}>
                  {actionBusy ? "Сохраняем…" : "Принять после проверки"}
                </button>
              </div>
            )}
          </footer>
        </article>
      )}
    </section>
  );
}

function russianPlural(
  count: number,
  forms: [one: string, few: string, many: string]
) {
  const mod100 = Math.abs(count) % 100;
  const mod10 = mod100 % 10;
  if (mod100 >= 11 && mod100 <= 19) return forms[2];
  if (mod10 === 1) return forms[0];
  if (mod10 >= 2 && mod10 <= 4) return forms[1];
  return forms[2];
}

function CourseThread({ focus }: { focus: AttentionFinding["thread_focus"] }) {
  const materialGap = focus === "objective_material";
  const assessmentGap = focus === "objective_assessment";
  const wholeCourse = focus === "whole_course";
  return (
    <div className={styles.courseThread} aria-label="Связь учебной цели, материала и оценивания">
      <span className={styles.threadNode}><i />Цель</span>
      <span className={materialGap ? styles.threadGap : wholeCourse ? styles.threadUnknown : styles.threadLine}>
        {materialGap && <em>разрыв</em>}
      </span>
      <span className={styles.threadNode}><i />Материал</span>
      <span className={assessmentGap ? styles.threadGap : wholeCourse ? styles.threadUnknown : styles.threadLine}>
        {assessmentGap && <em>проверить</em>}
      </span>
      <span className={styles.threadNode}><i />Оценивание</span>
    </div>
  );
}

function TutorQualityPanel({
  quality,
}: {
  quality: TeacherWorkspace["tutor_quality"];
}) {
  const total = quality.questions_total;
  const share = (count: number) => (total ? count / total : 0);
  const answerShare = share(quality.answer_responses);
  const guidanceShare = share(quality.guidance_answers);
  const abstainedShare = share(quality.abstained_answers);
  const supportedShare = quality.answer_responses
    ? quality.supported_answers / quality.answer_responses
    : 0;
  const state = quality.signal;
  const feedbackRemaining = Math.max(
    quality.minimum_feedback_sample - quality.rated_answers,
    0
  );
  const verdict = {
    empty: {
      label: "Ждём первые обращения",
      text: "Качественный вывод появится после реальных вопросов учеников.",
      next: "Проверьте, опубликованы ли материалы, к которым должен обращаться помощник.",
    },
    review: {
      label: "Нужна проверка опоры",
      text: `${quality.answers_needing_review} ${russianPlural(quality.answers_needing_review, ["обычный ответ требует", "обычных ответа требуют", "обычных ответов требуют"])} проверки: уверенность ниже порога или не показан источник.`,
      next: "Проверьте помощника на ключевых темах и качество опубликованных источников.",
    },
    coverage: {
      label: "Материалов часто не хватает",
      text: "Больше трети обращений завершаются честным отказом. Это повод проверить покрытие материалов курса.",
      next: "Проверьте, опубликованы ли нужные материалы и закрывают ли они основные темы курса.",
    },
    early: {
      label: "Пока мало данных",
      text: "Сводка уже считает режимы ответа, но устойчивый вывод лучше делать после пяти реальных обращений.",
      next: "Проверьте помощника отдельно на ключевых темах — тесты преподавателя не изменят эту сводку.",
    },
    limited: {
      label: "Мало обычных объяснений",
      text: "Обращений уже достаточно для первой картины, но обычных ответов пока меньше трёх — оценивать устойчивость опоры рано.",
      next: "Проверьте границы assessment-политики и доступность опубликованных материалов курса.",
    },
    steady: {
      label: "Опора выглядит устойчивой",
      text: "В обычных ответах не найдено слабой уверенности или пропавших источников. Продолжайте следить за обратной связью.",
      next: "Повторяйте контрольную проверку после заметного обновления материалов курса.",
    },
  }[state];

  return (
    <section className={styles.tutorQuality} aria-labelledby="tutor-quality-title">
      <header className={styles.tutorQualityHeader}>
        <div>
          <span className={styles.tutorEyebrow}>Помощник курса · последние {quality.period_days} дней</span>
          <h2 id="tutor-quality-title">Качество помощи без чтения переписки</h2>
        </div>
        <div className={styles.tutorVolume}>
          <strong>{total}</strong>
          <span>{russianPlural(total, ["обращение ученика", "обращения учеников", "обращений учеников"])}</span>
        </div>
      </header>

      {total === 0 ? (
        <div className={styles.tutorEmpty}>
          <span aria-hidden="true">◎</span>
          <div>
            <strong>Ждём первые вопросы по материалам</strong>
            <p>Тесты преподавателя сюда не попадают. Картина появится только по обращениям активных учеников курса.</p>
          </div>
        </div>
      ) : (
        <div className={styles.tutorQualityGrid}>
          <article className={styles.tutorVerdict} data-state={state}>
            <span>Что важно сейчас</span>
            <h3>{verdict.label}</h3>
            <p>{verdict.text}</p>
            <p className={styles.tutorNextStep}><strong>Следующий шаг:</strong> {verdict.next}</p>
            <div>
              <strong>{quality.supported_answers} из {quality.answer_responses}</strong>
              <span>обычных ответов показали источник · {percentage(supportedShare)}</span>
            </div>
          </article>

          <article className={styles.responseMix}>
            <div className={styles.responseMixHeading}>
              <div>
                <span>Как помощник отвечал</span>
                <strong>Режимы ответа</strong>
              </div>
              <small>Всего {total}</small>
            </div>
            <div
              className={styles.responseBar}
              role="img"
              aria-label={`Обычные ответы ${quality.answer_responses}, учебные подсказки ${quality.guidance_answers}, честные отказы ${quality.abstained_answers}`}
            >
              <i className={styles.responseAnswer} style={{ width: percentage(answerShare) }} />
              <i className={styles.responseGuidance} style={{ width: percentage(guidanceShare) }} />
              <i className={styles.responseAbstained} style={{ width: percentage(abstainedShare) }} />
            </div>
            <dl className={styles.responseLegend}>
              <div>
                <dt><i className={styles.responseAnswer} />Объяснил по материалам</dt>
                <dd><strong>{quality.answer_responses}</strong><span>{percentage(answerShare)}</span></dd>
              </div>
              <div>
                <dt><i className={styles.responseGuidance} />Оставил учебную подсказку</dt>
                <dd><strong>{quality.guidance_answers}</strong><span>{percentage(guidanceShare)}</span></dd>
              </div>
              <div>
                <dt><i className={styles.responseAbstained} />Честно отказался</dt>
                <dd><strong>{quality.abstained_answers}</strong><span>{percentage(abstainedShare)}</span></dd>
              </div>
            </dl>
          </article>
        </div>
      )}

      <footer className={styles.tutorQualityFooter}>
        <div>
          <span>Обратная связь</span>
          {quality.helpful_rate == null ? (
            <strong>
              Нужно ещё {feedbackRemaining} {russianPlural(feedbackRemaining, ["оценка", "оценки", "оценок"])}, чтобы показать долю полезных ответов
            </strong>
          ) : (
            <strong>
              {percentage(quality.helpful_rate)} полезных · {quality.helpful_answers ?? 0} из {quality.rated_answers}
            </strong>
          )}
        </div>
        <p>
          В этой сводке нет имён, вопросов, текстов ответов и рейтингов учеников. Она оценивает сервис, а не людей.
        </p>
      </footer>
    </section>
  );
}

const TUTOR_STYLES: {
  value: TutorPolicy["answer_style"];
  title: string;
  description: string;
}[] = [
  {
    value: "balanced",
    title: "Объяснить и связать",
    description: "Короткое объяснение с контекстом и источниками.",
  },
  {
    value: "guided",
    title: "Вести вопросами",
    description: "Опорные шаги, затем объяснение и вопрос для самопроверки.",
  },
  {
    value: "concise",
    title: "Коротко по сути",
    description: "Минимальное полезное объяснение без лишнего разворачивания.",
  },
];

function TutorPolicyPanel({
  policy,
  canEdit,
  busy,
  onSave,
}: {
  policy: TutorPolicy;
  canEdit: boolean;
  busy: boolean;
  onSave: (enabled: boolean, style: TutorPolicy["answer_style"], version: number) => Promise<void>;
}) {
  const [enabled, setEnabled] = useState(policy.enabled);
  const [answerStyle, setAnswerStyle] = useState(policy.answer_style);

  useEffect(() => {
    setEnabled(policy.enabled);
    setAnswerStyle(policy.answer_style);
  }, [policy.answer_style, policy.enabled, policy.version]);

  const dirty = enabled !== policy.enabled || answerStyle !== policy.answer_style;

  return (
    <section className={styles.tutorPolicy} aria-labelledby="tutor-policy-title">
      <header className={styles.tutorPolicyHeader}>
        <div>
          <span>Правила диалога</span>
          <h2 id="tutor-policy-title">Как помощник помогает ученикам</h2>
          <p>Вы выбираете педагогическую подачу. Защита заданий и скрытых материалов остаётся включённой.</p>
        </div>
        <label className={styles.policySwitch} data-enabled={enabled}>
          <span>
            <strong>{enabled ? "Помощник включён" : "Помощник на паузе"}</strong>
            <small>{enabled ? "Ученики могут задавать новые вопросы" : "История сохранена, новые вопросы остановлены"}</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            disabled={!canEdit || busy}
          />
          <i aria-hidden="true" />
        </label>
      </header>

      <div className={styles.policyBody}>
        <fieldset className={styles.styleChoices} disabled={!canEdit || busy}>
          <legend>Стиль обычного объяснения</legend>
          {TUTOR_STYLES.map((option) => (
            <button
              type="button"
              key={option.value}
              className={answerStyle === option.value ? styles.styleChoiceActive : styles.styleChoice}
              aria-pressed={answerStyle === option.value}
              onClick={() => setAnswerStyle(option.value)}
            >
              <span>{option.value === "balanced" ? "01" : option.value === "guided" ? "02" : "03"}</span>
              <strong>{option.title}</strong>
              <p>{option.description}</p>
            </button>
          ))}
        </fieldset>

        <aside className={styles.safetyRail} aria-label="Неизменяемые ограничения помощника">
          <span>Всегда включено</span>
          <h3>Границы нельзя ослабить настройкой</h3>
          <ul>
            <li><i>✓</i>Только доступные ученику материалы</li>
            <li><i>✓</i>Подсказка вместо готового ответа на проверочную</li>
            <li><i>✓</i>Честный отказ без достаточной опоры</li>
            <li><i>✓</i>Источники рядом с фактическим ответом</li>
          </ul>
        </aside>
      </div>

      <footer className={styles.policyFooter}>
        <span>
          Версия правил {policy.version}
          {!canEdit && " · только просмотр в вашей роли"}
        </span>
        {canEdit && (
          <button
            type="button"
            disabled={!dirty || busy}
            onClick={() => void onSave(enabled, answerStyle, policy.version)}
          >
            {busy ? "Сохраняем…" : "Сохранить правила"}
          </button>
        )}
      </footer>
    </section>
  );
}

function TutorDataGovernancePanel({
  policy,
  busy,
  onSave,
}: {
  policy: TutorDataPolicy;
  busy: boolean;
  onSave: (retentionDays: TutorDataPolicy["retention_days"], version: number) => void;
}) {
  const [retentionDays, setRetentionDays] = useState(policy.retention_days);

  useEffect(() => setRetentionDays(policy.retention_days), [policy.retention_days]);

  return (
    <section className={styles.dataGovernance} aria-labelledby="data-governance-title">
      <header className={styles.dataGovernanceHeader}>
        <div>
          <span>Управление данными организации</span>
          <h2 id="data-governance-title">Сколько хранить историю помощника</h2>
          <p>
            Единое правило для курсов организации. Ученики всегда могут удалить
            свою историю раньше установленного срока.
          </p>
        </div>
        <label>
          <span>Срок хранения</span>
          <select
            value={retentionDays}
            onChange={(event) =>
              setRetentionDays(Number(event.target.value) as TutorDataPolicy["retention_days"])
            }
            disabled={busy}
          >
            <option value={30}>30 дней</option>
            <option value={90}>90 дней</option>
            <option value={180}>180 дней</option>
            <option value={365}>365 дней</option>
          </select>
        </label>
      </header>

      <div className={styles.governanceThread} aria-label="Жизненный цикл данных тьютора">
        <span><i />Вопрос ученика<small>виден только в разрешённом контексте</small></span>
        <em aria-hidden="true" />
        <span><i />Хранится до {retentionDays} дней<small>единый срок для организации</small></span>
        <em aria-hidden="true" />
        <span><i />Удаление<small>текст и feedback стираются автоматически</small></span>
      </div>

      <footer className={styles.dataGovernanceFooter}>
        <p>
          Очистка запускается ежедневно. Журнал хранит только факт, срок и
          количество удалённых записей — без вопросов и ответов.
        </p>
        <div>
          <span>Версия политики {policy.version}</span>
          <button
            type="button"
            disabled={busy || retentionDays === policy.retention_days}
            onClick={() => onSave(retentionDays, policy.version)}
          >
            {busy ? "Сохраняем…" : "Сохранить срок"}
          </button>
        </div>
      </footer>
    </section>
  );
}

export default function TeacherCourseWorkspace() {
  const router = useRouter();
  const [identity, setIdentity] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const [sessionMode, setSessionMode] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [sessionEnded, setSessionEnded] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [workspace, setWorkspace] = useState<TeacherWorkspace | null>(null);
  const [selectedFindingId, setSelectedFindingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState<"confirmed" | "rejected" | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, CopilotSuggestion[]>>({});
  const [draftText, setDraftText] = useState("");
  const [draftBusy, setDraftBusy] = useState(false);
  const [policyBusy, setPolicyBusy] = useState(false);
  const [dataPolicy, setDataPolicy] = useState<TutorDataPolicy | null>(null);
  const [dataPolicyBusy, setDataPolicyBusy] = useState(false);
  const [dataPolicyError, setDataPolicyError] = useState("");
  const [isOrganizationAdmin, setIsOrganizationAdmin] = useState(false);
  const [canManagePolicy, setCanManagePolicy] = useState(false);
  const [canvasSync, setCanvasSync] = useState<CanvasSyncPreview | null>(null);
  const [canvasSyncLoading, setCanvasSyncLoading] = useState(false);
  const [canvasSyncFailed, setCanvasSyncFailed] = useState(false);
  const [canvasHandoff, setCanvasHandoff] = useState<InstructorCanvasOAuthStatus | null>(null);
  const [canvasHandoffLoading, setCanvasHandoffLoading] = useState(false);
  const [canvasHandoffFailed, setCanvasHandoffFailed] = useState(false);
  const [canvasOAuthResult, setCanvasOAuthResult] = useState<CanvasOAuthResult>(null);
  const [canvasOAuthBusy, setCanvasOAuthBusy] = useState(false);
  const [instructorAgentRun, setInstructorAgentRun] = useState<InstructorAgentRun | null>(null);
  const [instructorAgentStage, setInstructorAgentStage] = useState<InstructorAgentStage>("idle");
  const [instructorAgentError, setInstructorAgentError] = useState("");
  const [instructorAgentErrorScope, setInstructorAgentErrorScope] = useState<"summary" | "evidence" | "">("");
  const [instructorOpeningPriorityRef, setInstructorOpeningPriorityRef] = useState("");
  const [instructorEvidenceRef, setInstructorEvidenceRef] = useState("");
  const [failedInstructorPriority, setFailedInstructorPriority] = useState<InstructorAgentPriority | null>(null);
  const [gapAgentRun, setGapAgentRun] = useState<InstructorAgentRun | null>(null);
  const [gapAgentStage, setGapAgentStage] = useState<InstructorAgentStage>("idle");
  const [gapAgentError, setGapAgentError] = useState("");
  const [interventionDraft, setInterventionDraft] = useState<InstructorInterventionDraft | null>(null);
  const [interventionText, setInterventionText] = useState("");
  const [interventionBusy, setInterventionBusy] = useState(false);
  const [interventionError, setInterventionError] = useState("");
  const [interventionRecovery, setInterventionRecovery] = useState<InterventionRecovery>("");
  const [failedInterventionCandidate, setFailedInterventionCandidate] = useState<InstructorGapCandidate | null>(null);
  const [instructorDraftRef, setInstructorDraftRef] = useState("");
  const [canvasChangePreview, setCanvasChangePreview] = useState<
    Extract<NonNullable<InstructorAgentRun["response"]>, { mode: "canvas_change_preview" }> | null
  >(null);
  const [canvasChangeBusy, setCanvasChangeBusy] = useState(false);
  const [draftError, setDraftError] = useState("");
  const [draftFailureAction, setDraftFailureAction] = useState<"generate" | "accept" | "reject" | "regenerate" | "">("");
  const [canvasChangeError, setCanvasChangeError] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const evidenceHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const draftHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const previewHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const gapResultHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const interventionHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const interventionDecisionRef = useRef<HTMLElement | null>(null);

  const courseId = Number(router.query.courseId);

  useEffect(() => {
    if (!router.isReady) return;
    const launchedFromLti = router.query.lti === "1";
    if (launchedFromLti) {
      setIdentity("");
      setSessionMode(true);
      setAuthReady(true);
      return;
    }
    const stored = window.localStorage.getItem(IDENTITY_STORAGE_KEY) || "";
    if (!stored) {
      void router.replace("/workspace");
      return;
    }
    setIdentity(stored);
    setSessionMode(false);
    setAuthReady(true);
  }, [router]);

  useEffect(() => {
    if (!sessionMode) return;
    const endSession = () => {
      setWorkspace(null);
      setInstructorAgentRun(null);
      setInstructorAgentStage("idle");
      setInstructorAgentError("");
      setInstructorAgentErrorScope("");
      setInstructorOpeningPriorityRef("");
      setInstructorEvidenceRef("");
      setFailedInstructorPriority(null);
      setGapAgentRun(null);
      setGapAgentStage("idle");
      setGapAgentError("");
      setInterventionDraft(null);
      setInterventionText("");
      setInterventionBusy(false);
      setInterventionError("");
      setInterventionRecovery("");
      setFailedInterventionCandidate(null);
      setInstructorDraftRef("");
      setCanvasChangePreview(null);
      setCanvasChangeBusy(false);
      setDraftError("");
      setDraftFailureAction("");
      setCanvasChangeError("");
      setCanvasSync(null);
      setCanvasSyncFailed(false);
      setCanvasHandoff(null);
      setCanvasHandoffFailed(false);
      setCanvasOAuthResult(null);
      setDisplayName("");
      setLoading(false);
      setError("");
      setErrorStatus(null);
      setSessionEnded(true);
    };
    window.addEventListener(SESSION_ENDED_EVENT, endSession);
    return () => window.removeEventListener(SESSION_ENDED_EVENT, endSession);
  }, [sessionMode]);

  const loadCanvasSync = useCallback(async () => {
    if (
      !authReady ||
      !sessionMode ||
      sessionEnded ||
      !Number.isFinite(courseId) ||
      courseId < 1
    ) return;
    setCanvasSyncLoading(true);
    setCanvasSyncFailed(false);
    try {
      const value = await api<CanvasSyncPreview>(
        `/courses/${courseId}/canvas-sync-preview`,
        ""
      );
      setCanvasSync(value);
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status === 401) {
        setSessionEnded(true);
        return;
      }
      setCanvasSyncFailed(true);
    } finally {
      setCanvasSyncLoading(false);
    }
  }, [authReady, courseId, sessionEnded, sessionMode]);

  const loadCanvasHandoff = useCallback(async () => {
    if (
      !authReady ||
      !sessionMode ||
      sessionEnded ||
      !Number.isFinite(courseId) ||
      courseId < 1
    ) return;
    setCanvasHandoffLoading(true);
    setCanvasHandoffFailed(false);
    try {
      const value = await api<InstructorCanvasOAuthStatus>(
        `/courses/${courseId}/canvas-oauth-handoff`,
        ""
      );
      setCanvasHandoff(value);
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status === 401) {
        setSessionEnded(true);
        return;
      }
      setCanvasHandoffFailed(true);
    } finally {
      setCanvasHandoffLoading(false);
    }
  }, [authReady, courseId, sessionEnded, sessionMode]);

  const loadWorkspace = useCallback(async () => {
    if (!authReady || sessionEnded || !Number.isFinite(courseId) || courseId < 1) return;
    setLoading(true);
    setError("");
    setErrorStatus(null);
    try {
      const identityContext = await api<IdentityContext>("/identity/me", identity);
      setDisplayName(identityContext.user.display_name);
      const access = identityContext.courses.find((item) => item.id === courseId);
      if (!access?.actions.includes("review_findings")) {
        throw new Error("Курс недоступен или у вас нет нужной роли.");
      }
      setCanManagePolicy(access.actions.includes("manage_content"));
      const administrator = access.roles.includes("administrator");
      setIsOrganizationAdmin(administrator);
      const policyRequest = administrator
        ? api<TutorDataPolicy>(
            `/organizations/${access.organization_id}/tutor-data-policy`,
            identity
          )
            .then((value) => ({ value, error: "" }))
            .catch(() => ({
              value: null,
              error:
                "Не удалось загрузить срок хранения. Остальные данные курса доступны.",
            }))
        : Promise.resolve({ value: null, error: "" });
      const [value, policyResult] = await Promise.all([
        api<TeacherWorkspace>(`/courses/${courseId}/teacher-workspace`, identity),
        policyRequest,
      ]);
      setWorkspace(value);
      setDataPolicy(policyResult.value);
      setDataPolicyError(policyResult.error);
      setSelectedFindingId((current) =>
        value.findings.some((item) => item.id === current)
          ? current
          : value.findings[0]?.id || null
      );
    } catch (reason) {
      setWorkspace(null);
      if (reason instanceof ApiRequestError) {
        setErrorStatus(reason.status);
        if (sessionMode && reason.status === 401) {
          setSessionEnded(true);
          return;
        }
      }
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [authReady, courseId, identity, sessionEnded, sessionMode]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    void loadCanvasSync();
  }, [loadCanvasSync]);

  useEffect(() => {
    void loadCanvasHandoff();
  }, [loadCanvasHandoff]);

  useEffect(() => {
    if (!router.isReady || !sessionMode) return;
    const raw = router.query.canvas_oauth;
    const result =
      raw === "connected" || raw === "denied" || raw === "failed" ? raw : null;
    if (!result) return;
    setCanvasOAuthResult(result);
    void router.replace(
      {
        pathname: router.pathname,
        query: { courseId: String(courseId), lti: "1" },
      },
      undefined,
      { shallow: true }
    );
  }, [courseId, router, sessionMode]);

  const startCanvasOAuth = useCallback(async () => {
    if (!sessionMode || sessionEnded || canvasOAuthBusy) return;
    setCanvasOAuthBusy(true);
    setCanvasOAuthResult(null);
    try {
      const value = await api<{ authorization_url: string }>(
        `/courses/${courseId}/canvas-oauth-handoff/start`,
        "",
        { method: "POST" }
      );
      window.location.assign(new URL(value.authorization_url, API_BASE).toString());
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status === 401) {
        setSessionEnded(true);
        return;
      }
      setCanvasOAuthResult("failed");
      await loadCanvasHandoff();
    } finally {
      setCanvasOAuthBusy(false);
    }
  }, [canvasOAuthBusy, courseId, loadCanvasHandoff, sessionEnded, sessionMode]);

  const disconnectCanvasOAuth = useCallback(async () => {
    if (!sessionMode || sessionEnded || canvasOAuthBusy) return false;
    setCanvasOAuthBusy(true);
    setCanvasOAuthResult(null);
    try {
      await api(`/courses/${courseId}/canvas-oauth-handoff/disconnect`, "", {
        method: "POST",
      });
      await Promise.all([loadCanvasHandoff(), loadCanvasSync()]);
      return true;
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status === 401) {
        setSessionEnded(true);
        return false;
      }
      setCanvasOAuthResult("failed");
      return false;
    } finally {
      setCanvasOAuthBusy(false);
    }
  }, [
    canvasOAuthBusy,
    courseId,
    loadCanvasHandoff,
    loadCanvasSync,
    sessionEnded,
    sessionMode,
  ]);

  useEffect(() => {
    if (!workspace?.latest_audit || !["queued", "running"].includes(workspace.latest_audit.status)) {
      return;
    }
    const timer = window.setInterval(() => void loadWorkspace(), 2000);
    return () => window.clearInterval(timer);
  }, [loadWorkspace, workspace?.latest_audit]);

  const selectedFinding = useMemo(
    () => workspace?.findings.find((item) => item.id === selectedFindingId) || null,
    [selectedFindingId, workspace]
  );
  const openFindingCount = workspace?.findings.filter(
    (item) => item.status === "new"
  ).length || 0;
  const currentSuggestions = selectedFindingId
    ? suggestions[selectedFindingId] || []
    : [];
  const currentSuggestion = currentSuggestions[0] || null;

  const runInstructorSummary = useCallback(async () => {
    const busy = ["submitting", "queued", "routing", "tool_running", "generating"].includes(
      instructorAgentStage
    );
    if (!sessionMode || sessionEnded || busy) return;
    setInstructorAgentError("");
    setInstructorAgentErrorScope("summary");
    setInstructorAgentRun(null);
    setInstructorAgentStage("submitting");
    try {
      const requestId = crypto.randomUUID();
      const requestBody = {
        contract_version: "agent.v1" as const,
        message: "Сводка курса",
        client_request_id: requestId,
      };
      const accepted = await authenticatedJson<AgentAccepted>(
        API_BASE,
        "/agent/v1/messages",
        "",
        {
          method: "POST",
          headers: { "Idempotency-Key": requestId },
          body: JSON.stringify(requestBody),
        }
      );
      setInstructorAgentStage("queued");
      await new Promise((resolve) => window.setTimeout(resolve, 140));
      let current: InstructorAgentRun | null = null;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        current = await authenticatedJson<InstructorAgentRun>(
          API_BASE,
          accepted.execute_url,
          "",
          { method: "POST", body: JSON.stringify(requestBody) }
        );
        setInstructorAgentStage(current.status);
        setInstructorAgentRun(current);
        if (["completed", "abstained", "failed"].includes(current.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 180));
      }
      if (!current || current.status !== "completed" || current.response?.mode !== "course_summary") {
        throw new Error(
          current?.user_state.label ||
          "Сводка заняла больше времени, чем ожидалось. Попробуйте ещё раз."
        );
      }
      setInstructorAgentErrorScope("");
      setInstructorEvidenceRef("");
      setFailedInstructorPriority(null);
      setInstructorDraftRef("");
      setSuggestions({});
      setDraftText("");
      setDraftError("");
      setDraftFailureAction("");
      setCanvasChangePreview(null);
      setCanvasChangeError("");
    } catch (reason) {
      setInstructorAgentStage("failed");
      setInstructorAgentError(
        reason instanceof Error ? reason.message : "Сводка сейчас недоступна."
      );
    }
  }, [instructorAgentStage, sessionEnded, sessionMode]);

  const runQuestionGaps = useCallback(async () => {
    const busy = ["submitting", "queued", "routing", "tool_running", "generating"].includes(
      gapAgentStage
    );
    if (!sessionMode || sessionEnded || busy || interventionBusy) return;
    setGapAgentError("");
    setGapAgentRun(null);
    setGapAgentStage("submitting");
    setInterventionDraft(null);
    setInterventionText("");
    setInterventionError("");
    setInterventionRecovery("");
    setFailedInterventionCandidate(null);
    try {
      const requestId = crypto.randomUUID();
      const requestBody = {
        contract_version: "agent.v1" as const,
        message: "Непонятные темы",
        client_request_id: requestId,
      };
      const accepted = await authenticatedJson<AgentAccepted>(
        API_BASE,
        "/agent/v1/messages",
        "",
        {
          method: "POST",
          headers: { "Idempotency-Key": requestId },
          body: JSON.stringify(requestBody),
        }
      );
      setGapAgentStage("queued");
      await new Promise((resolve) => window.setTimeout(resolve, 140));
      let current: InstructorAgentRun | null = null;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        current = await authenticatedJson<InstructorAgentRun>(
          API_BASE,
          accepted.execute_url,
          "",
          { method: "POST", body: JSON.stringify(requestBody) }
        );
        setGapAgentStage(current.status);
        setGapAgentRun(current);
        if (["completed", "abstained", "failed"].includes(current.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 180));
      }
      if (!current || current.status !== "completed" || current.response?.mode !== "question_gaps") {
        throw new Error(
          current?.user_state.label ||
          "Проверка заняла больше времени, чем ожидалось. Попробуйте ещё раз."
        );
      }
      window.requestAnimationFrame(() => focusAndReveal(gapResultHeadingRef.current));
    } catch (reason) {
      setGapAgentStage("failed");
      setGapAgentError(
        reason instanceof Error ? reason.message : "Общий сигнал сейчас недоступен."
      );
    }
  }, [gapAgentStage, interventionBusy, sessionEnded, sessionMode]);

  const prepareIntervention = useCallback(async (candidate: InstructorGapCandidate) => {
    if (!sessionMode || sessionEnded || interventionBusy) return;
    setInterventionBusy(true);
    setInterventionError("");
    setInterventionRecovery("");
    setFailedInterventionCandidate(candidate);
    try {
      const drafted = await authenticatedJson<InstructorInterventionDraft>(
        API_BASE,
        `/agent/v1/gaps/${candidate.gap_ref}/draft`,
        "",
        { method: "POST" }
      );
      setInterventionDraft(drafted);
      setInterventionText(drafted.content);
      setFailedInterventionCandidate(null);
      window.requestAnimationFrame(() => focusAndReveal(interventionHeadingRef.current));
    } catch (reason) {
      const stale = reason instanceof ApiRequestError && reason.status === 404;
      setInterventionError(
        stale
          ? "Сигнал относится к прошлому состоянию курса. Обновите проверку."
          : reason instanceof Error
            ? reason.message
            : "Материал сейчас не подготовился."
      );
      setInterventionRecovery(stale ? "refresh" : "retry");
    } finally {
      setInterventionBusy(false);
    }
  }, [interventionBusy, sessionEnded, sessionMode]);

  const reviewIntervention = useCallback(async (status: "accepted" | "rejected") => {
    if (!interventionDraft || !sessionMode || sessionEnded || interventionBusy) return;
    setInterventionBusy(true);
    setInterventionError("");
    setInterventionRecovery("");
    try {
      const reviewed = await authenticatedJson<InstructorInterventionReview>(
        API_BASE,
        `/agent/v1/interventions/${interventionDraft.intervention_ref}/review`,
        "",
        {
          method: "PATCH",
          body: JSON.stringify({
            status,
            expected_version: interventionDraft.review_version,
            ...(status === "accepted" ? { content: interventionText } : {}),
          }),
        }
      );
      setInterventionDraft((current) => current ? {
        ...current,
        content: reviewed.content,
        review_status: reviewed.status,
        review_version: reviewed.version,
        limitations: [
          "Решение преподавателя сохранено; новый вариант создаётся отдельно.",
          "Canvas не изменён.",
        ],
      } : current);
      setInterventionText(reviewed.content);
      window.requestAnimationFrame(() => focusAndReveal(interventionDecisionRef.current));
    } catch (reason) {
      const stale = reason instanceof ApiRequestError && [404, 409].includes(reason.status);
      setInterventionError(
        stale
          ? "Сигнал или черновик устарел. Обновите общий сигнал и подготовьте материал снова."
          : reason instanceof Error
            ? reason.message
            : "Решение сейчас не сохранилось."
      );
      setInterventionRecovery(stale ? "refresh" : "retry");
    } finally {
      setInterventionBusy(false);
    }
  }, [interventionBusy, interventionDraft, interventionText, sessionEnded, sessionMode]);

  const openInstructorPriority = useCallback(async (priority: InstructorAgentPriority) => {
    if (!sessionMode || sessionEnded || instructorOpeningPriorityRef) return;
    setInstructorOpeningPriorityRef(priority.finding_ref);
    setInstructorAgentError("");
    setInstructorAgentErrorScope("evidence");
    setFailedInstructorPriority(priority);
    try {
      const requestId = crypto.randomUUID();
      const requestBody = {
        contract_version: "agent.v1" as const,
        message: "Аудит курса",
        client_request_id: requestId,
        selection: { evidence_ref: priority.finding_ref },
      };
      const accepted = await authenticatedJson<AgentAccepted>(
        API_BASE,
        "/agent/v1/messages",
        "",
        {
          method: "POST",
          headers: { "Idempotency-Key": requestId },
          body: JSON.stringify(requestBody),
        }
      );
      let inspected: InstructorAgentRun | null = null;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        inspected = await authenticatedJson<InstructorAgentRun>(
          API_BASE,
          accepted.execute_url,
          "",
          { method: "POST", body: JSON.stringify(requestBody) }
        );
        if (["completed", "abstained", "failed"].includes(inspected.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 160));
      }
      if (
        !inspected ||
        inspected.status !== "completed" ||
        inspected.response?.mode !== "finding_review" ||
        inspected.response.finding_ref !== priority.finding_ref
      ) {
        throw new Error(
          inspected?.user_state.label || "Доказательства сейчас недоступны."
        );
      }
      const reviewedFinding = inspected.response;
      const finding = workspace?.findings.find((item) =>
        item.title === reviewedFinding.title &&
        item.severity === reviewedFinding.severity &&
        Math.abs(item.confidence - reviewedFinding.confidence) < 0.0001
      );
      if (!finding) {
        throw new Error(
          "Приоритет относится к другой версии проверки. Обновите страницу и соберите сводку снова."
        );
      }
      setSelectedFindingId(finding.id);
      setInstructorEvidenceRef(priority.finding_ref);
      setInstructorAgentErrorScope("");
      setFailedInstructorPriority(null);
      setInstructorDraftRef("");
      setCanvasChangePreview(null);
      setNotice("");
      window.requestAnimationFrame(() => {
        focusAndReveal(evidenceHeadingRef.current);
      });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Доказательства сейчас недоступны.";
      setInstructorAgentError(message);
      if (/другой версии|устар/i.test(message)) setFailedInstructorPriority(null);
    } finally {
      setInstructorOpeningPriorityRef("");
    }
  }, [instructorOpeningPriorityRef, sessionEnded, sessionMode, workspace]);

  const loadSuggestions = useCallback(
    async (findingId: number) => {
      if (!authReady || sessionEnded || sessionMode) return;
      try {
        const rows = await api<(Omit<CopilotSuggestion, "limitations"> & { limitations?: string[] })[]>(
          `/findings/${findingId}/copilot`,
          identity
        );
        const normalized = rows.map((item) => ({
          ...item,
          version: item.version || 1,
          limitations: item.limitations || [
            "Черновик требует отдельной проверки преподавателя.",
            "Canvas не изменён.",
          ],
        }));
        setSuggestions((current) => ({ ...current, [findingId]: normalized }));
        setDraftText(normalized[0]?.draft || "");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    },
    [authReady, identity, sessionEnded, sessionMode]
  );

  useEffect(() => {
    if (selectedFindingId) void loadSuggestions(selectedFindingId);
  }, [loadSuggestions, selectedFindingId]);

  const reviewFinding = async (status: "confirmed" | "rejected") => {
    if (!selectedFinding || !authReady || sessionEnded) return;
    setReviewing(status);
    setNotice("");
    setError("");
    setErrorStatus(null);
    try {
      await api(`/findings/${selectedFinding.id}`, identity, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setNotice(status === "confirmed" ? "Подтверждено" : "Отклонено");
      await loadWorkspace();
    } catch (reason) {
      if (!(reason instanceof ApiRequestError && reason.status === 401)) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
    } finally {
      setReviewing(null);
    }
  };

  const generateDraft = async () => {
    if (!selectedFinding || !authReady || sessionEnded || selectedFinding.status !== "confirmed") return;
    setDraftBusy(true);
    setCanvasChangePreview(null);
    setDraftError("");
    setDraftFailureAction("");
    setCanvasChangeError("");
    setNotice("");
    setError("");
    try {
      if (sessionMode) {
        const summary =
          instructorAgentRun?.response?.mode === "course_summary"
            ? instructorAgentRun.response
            : null;
        const priority = summary?.priorities.find((item) =>
          item.title === selectedFinding.title &&
          item.severity === selectedFinding.severity &&
          Math.abs(item.confidence - selectedFinding.confidence) < 0.0001
        );
        if (!priority) {
          throw new Error(
            "Сначала обновите сводку и откройте этот приоритет через помощника."
          );
        }
        const requestId = crypto.randomUUID();
        const requestBody = {
          contract_version: "agent.v1" as const,
          message: "Черновик улучшения",
          client_request_id: requestId,
          selection: { evidence_ref: priority.finding_ref },
        };
        const accepted = await authenticatedJson<AgentAccepted>(
          API_BASE,
          "/agent/v1/messages",
          "",
          {
            method: "POST",
            headers: { "Idempotency-Key": requestId },
            body: JSON.stringify(requestBody),
          }
        );
        let drafted: InstructorAgentRun | null = null;
        for (let attempt = 0; attempt < 5; attempt += 1) {
          drafted = await authenticatedJson<InstructorAgentRun>(
            API_BASE,
            accepted.execute_url,
            "",
            { method: "POST", body: JSON.stringify(requestBody) }
          );
          if (["completed", "abstained", "failed"].includes(drafted.status)) break;
          await new Promise((resolve) => window.setTimeout(resolve, 180));
        }
        if (
          !drafted ||
          drafted.status !== "completed" ||
          drafted.response?.mode !== "improvement_draft"
        ) {
          throw new Error(
            drafted?.user_state.label || "Черновик сейчас не подготовился."
          );
        }
        const draftResponse = drafted.response;
        setInstructorDraftRef(draftResponse.draft_ref);
        const safeSuggestion: CopilotSuggestion = {
          draft_ref: draftResponse.draft_ref,
          finding_id: selectedFinding.id,
          action_type: draftResponse.action_type,
          title: draftResponse.title,
          draft: draftResponse.content,
          target_bloom_level: draftResponse.target_bloom_level,
          rationale: draftResponse.rationale,
          citations: draftResponse.citations.map((citation, index) => ({
            source_id: `S${index + 1}`,
            document_title: citation.source_label,
            quote: citation.excerpt,
            score: draftResponse.confidence,
          })),
          confidence: draftResponse.confidence,
          insufficient_context: draftResponse.insufficient_context,
          status: draftResponse.review_status,
          version: draftResponse.review_version,
          limitations: draftResponse.limitations,
        };
        setSuggestions((current) => ({
          ...current,
          [selectedFinding.id]: [safeSuggestion],
        }));
        setDraftText(safeSuggestion.draft);
        window.requestAnimationFrame(() => focusAndReveal(draftHeadingRef.current));
        setNotice(
          draftResponse.insufficient_context
            ? "Контекста курса недостаточно для надёжного черновика."
            : "Черновик подготовлен. Проверьте текст и источники."
        );
        return;
      }
      const suggestion = await api<Omit<CopilotSuggestion, "limitations">>(
        `/findings/${selectedFinding.id}/copilot`,
        identity,
        {
          method: "POST",
          body: JSON.stringify({ top_k: 5, language: "ru" }),
        }
      );
      const normalizedSuggestion: CopilotSuggestion = {
        ...suggestion,
        version: suggestion.version || 1,
        limitations: [
          "Черновик требует отдельной проверки преподавателя.",
          "Canvas не изменён.",
        ],
      };
      setSuggestions((current) => ({
        ...current,
        [selectedFinding.id]: [
          normalizedSuggestion,
          ...(current[selectedFinding.id] || []),
        ],
      }));
      setDraftText(normalizedSuggestion.draft);
      setNotice(
        suggestion.insufficient_context
          ? "Контекста курса недостаточно для надёжного черновика."
          : "Черновик подготовлен. Проверьте текст и источники."
      );
    } catch (reason) {
      setDraftError(reason instanceof Error ? reason.message : String(reason));
      setDraftFailureAction("generate");
    } finally {
      setDraftBusy(false);
    }
  };

  const reviewDraft = async (status: "accepted" | "rejected") => {
    if (!currentSuggestion || !authReady || sessionEnded) return;
    setDraftBusy(true);
    setDraftError("");
    setDraftFailureAction("");
    setNotice("");
    setError("");
    try {
      if (sessionMode) {
        const draftRef = currentSuggestion.draft_ref || instructorDraftRef;
        if (!draftRef) {
          throw new Error("Связанный черновик устарел. Подготовьте новый вариант.");
        }
        const reviewed = await authenticatedJson<InstructorDraftReview>(
          API_BASE,
          `/agent/v1/drafts/${draftRef}/review`,
          "",
          {
            method: "PATCH",
            body: JSON.stringify({
              status,
              expected_version: currentSuggestion.version,
              ...(status === "accepted" ? { content: draftText } : {}),
            }),
          }
        );
        setSuggestions((current) => ({
          ...current,
          [currentSuggestion.finding_id]: (current[currentSuggestion.finding_id] || []).map(
            (item) => item.draft_ref === draftRef
              ? {
                  ...item,
                  draft: reviewed.content,
                  status: reviewed.status,
                  version: reviewed.version,
                  limitations: [
                    "Решение преподавателя сохранено; новый вариант создаётся отдельно.",
                    "Canvas не изменён.",
                  ],
                }
              : item
          ),
        }));
        if (status === "rejected") {
          setInstructorDraftRef("");
          setCanvasChangePreview(null);
        } else {
          window.requestAnimationFrame(() => focusAndReveal(previewHeadingRef.current));
        }
        setNotice(
          status === "accepted"
            ? "Черновик принят и сохранён. Canvas не изменён."
            : "Черновик отклонён. Canvas не изменён."
        );
        return;
      }
      if (!currentSuggestion.id) {
        throw new Error("Черновик больше недоступен. Обновите рабочее место.");
      }
      await api(`/copilot/suggestions/${currentSuggestion.id}`, identity, {
        method: "PATCH",
        body: JSON.stringify({
          status,
          ...(status === "accepted" ? { draft: draftText } : {}),
        }),
      });
      await loadSuggestions(currentSuggestion.finding_id);
      if (status === "rejected") {
        setInstructorDraftRef("");
        setCanvasChangePreview(null);
      }
      setNotice(
        status === "accepted"
          ? "Черновик принят и сохранён. Canvas не изменён."
          : "Черновик отклонён. Canvas не изменён."
      );
    } catch (reason) {
      setDraftError(reason instanceof Error ? reason.message : String(reason));
      const stale =
        (reason instanceof ApiRequestError && [404, 409].includes(reason.status)) ||
        (reason instanceof Error && /устар|state changed|другой версии/i.test(reason.message));
      setDraftFailureAction(
        stale ? "regenerate" : status === "accepted" ? "accept" : "reject"
      );
    } finally {
      setDraftBusy(false);
    }
  };

  const previewCanvasChange = async () => {
    if (
      !sessionMode ||
      sessionEnded ||
      canvasChangeBusy ||
      !instructorDraftRef ||
      currentSuggestion?.status !== "accepted"
    ) return;
    setCanvasChangeBusy(true);
    setCanvasChangePreview(null);
    setCanvasChangeError("");
    setNotice("");
    setError("");
    try {
      const requestId = crypto.randomUUID();
      const requestBody = {
        contract_version: "agent.v1" as const,
        message: "Изменения Canvas",
        client_request_id: requestId,
        selection: { evidence_ref: instructorDraftRef },
      };
      const accepted = await authenticatedJson<AgentAccepted>(
        API_BASE,
        "/agent/v1/messages",
        "",
        {
          method: "POST",
          headers: { "Idempotency-Key": requestId },
          body: JSON.stringify(requestBody),
        }
      );
      let previewed: InstructorAgentRun | null = null;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        previewed = await authenticatedJson<InstructorAgentRun>(
          API_BASE,
          accepted.execute_url,
          "",
          { method: "POST", body: JSON.stringify(requestBody) }
        );
        if (["completed", "abstained", "failed"].includes(previewed.status)) break;
        await new Promise((resolve) => window.setTimeout(resolve, 180));
      }
      if (
        !previewed ||
        previewed.status !== "completed" ||
        previewed.response?.mode !== "canvas_change_preview"
      ) {
        throw new Error(
          previewed?.user_state.label || "Предпросмотр изменения сейчас недоступен."
        );
      }
      setCanvasChangePreview(previewed.response);
      setNotice("Предпросмотр готов. Canvas не изменён.");
      window.requestAnimationFrame(() => focusAndReveal(previewHeadingRef.current));
    } catch (reason) {
      setCanvasChangeError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCanvasChangeBusy(false);
    }
  };

  const saveTutorPolicy = async (
    enabled: boolean,
    answerStyle: TutorPolicy["answer_style"],
    expectedVersion: number
  ) => {
    if (!authReady || sessionEnded || !canManagePolicy) return;
    setPolicyBusy(true);
    setNotice("");
    setError("");
    try {
      await api<TutorPolicy>(`/courses/${courseId}/tutor-policy`, identity, {
        method: "PATCH",
        body: JSON.stringify({
          enabled,
          answer_style: answerStyle,
          expected_version: expectedVersion,
        }),
      });
      setNotice("Правила помощника сохранены. Защитные границы остались включены.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPolicyBusy(false);
    }
  };

  const saveTutorDataPolicy = async (
    retentionDays: TutorDataPolicy["retention_days"],
    expectedVersion: number
  ) => {
    if (!authReady || sessionEnded || !dataPolicy) return;
    setDataPolicyBusy(true);
    setNotice("");
    setError("");
    try {
      await api<TutorDataPolicy>(
        `/organizations/${dataPolicy.organization_id}/tutor-data-policy`,
        identity,
        {
          method: "PATCH",
          body: JSON.stringify({
            retention_days: retentionDays,
            expected_version: expectedVersion,
          }),
        }
      );
      setNotice("Срок хранения сохранён. Право ученика удалить историю осталось включено.");
      await loadWorkspace();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setDataPolicyBusy(false);
    }
  };

  const logout = async () => {
    if (!sessionMode || loggingOut) return;
    setLoggingOut(true);
    setError("");
    try {
      await api<void>("/identity/session/logout", "", { method: "POST" });
      clearSessionCsrf();
      setWorkspace(null);
      setCanvasSync(null);
      setDisplayName("");
      setSessionEnded(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoggingOut(false);
    }
  };

  if (sessionEnded) {
    return (
      <div className={styles.page}>
        <main className={styles.centerState} aria-live="polite">
          <div className={styles.stateCode}>Сессия завершена</div>
          <h1>Вы вышли из курса</h1>
          <p>Доступ закрыт на этом устройстве. Чтобы вернуться, снова откройте инструмент из Canvas.</p>
        </main>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>{workspace ? `${workspace.course.title} — Контур` : "Курс — Контур"}</title>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </Head>
      <div className={styles.page}>
        <header className={styles.header}>
          {sessionMode ? (
            <span className={styles.canvasContext}><i /> Доступ через Canvas</span>
          ) : (
            <Link className={styles.backLink} href="/workspace">
              <span aria-hidden="true">←</span> Все курсы
            </Link>
          )}
          {sessionMode ? (
            <span className={styles.brand}>Контур</span>
          ) : (
            <Link className={styles.brand} href="/workspace">Контур</Link>
          )}
          <div className={styles.sessionIdentity}>
            <span>{displayName || identity || "Проверяем роль…"}</span>
            {sessionMode && !sessionEnded && (
              <button type="button" onClick={() => void logout()} disabled={loggingOut}>
                {loggingOut ? "Выходим…" : "Выйти"}
              </button>
            )}
          </div>
        </header>

        {loading && !workspace ? (
          <main className={styles.centerState} aria-live="polite">
            <span className={styles.spinner} />
            <h1>Проверяем доступ к курсу</h1>
            <p>Подтверждаем роль и собираем картину последней проверки.</p>
          </main>
        ) : error && !workspace ? (
          <main className={styles.centerState}>
            <div className={styles.stateCode}>{errorStatus === 404 ? "Доступ не подтверждён" : "Связь с курсом"}</div>
            <h1>{errorStatus === 404 ? "Этот курс не открыт в вашей рабочей роли" : "Не удалось загрузить рабочее место"}</h1>
            <p>
              {errorStatus === 404
                ? sessionMode
                  ? "Курс больше не назначен этой роли. Снова откройте инструмент из Canvas после проверки доступа."
                  : `${error} Название недоступного курса не раскрывается.`
                : `${error} Доступ и сохранённые решения не изменены.`}
            </p>
            {errorStatus !== 404 && (
              <button className={styles.primaryLink} type="button" onClick={() => void loadWorkspace()}>
                Повторить
              </button>
            )}
            {!sessionMode && errorStatus === 404 && <Link className={styles.primaryLink} href="/workspace">Вернуться к моим курсам</Link>}
          </main>
        ) : workspace ? (
          <main className={styles.main}>
            <section className={styles.courseHero}>
              <div>
                <div className={styles.eyebrow}>Очередь внимания преподавателя</div>
                <h1>{workspace.course.title}</h1>
                <p>{workspace.course.description || "Описание курса пока не добавлено."}</p>
              </div>
              <div className={styles.auditStamp}>
                <span>Последняя проверка</span>
                <strong>
                  {workspace.latest_audit
                    ? workspace.latest_audit.status === "done"
                      ? "Завершена"
                      : workspace.latest_audit.status === "failed"
                        ? "Нужен повтор"
                        : `Выполняется · ${workspace.latest_audit.progress}%`
                    : "Ещё не запускалась"}
                </strong>
              </div>
            </section>

            {sessionMode && (
              <CanvasSyncPanel
                preview={canvasSync}
                loading={canvasSyncLoading}
                requestFailed={canvasSyncFailed}
                onRefresh={() => void loadCanvasSync()}
                handoff={canvasHandoff}
                handoffLoading={canvasHandoffLoading}
                handoffFailed={canvasHandoffFailed}
                oauthResult={canvasOAuthResult}
                actionBusy={canvasOAuthBusy}
                onConnect={() => void startCanvasOAuth()}
                onRetryHandoff={() => void loadCanvasHandoff()}
                onDisconnect={disconnectCanvasOAuth}
              />
            )}

            {workspace.latest_audit?.status === "done" && (
              <section className={styles.healthStrip} aria-label="Состояние курса">
                <div><strong>{workspace.health.objectives_total}</strong><span>учебных целей</span></div>
                <div><strong>{percentage(workspace.health.objective_material_coverage)}</strong><span>поддержаны материалами</span></div>
                <div><strong>{percentage(workspace.health.objective_assessment_coverage)}</strong><span>проверяются заданиями</span></div>
                <div className={workspace.health.high_severity_findings ? styles.healthRisk : ""}>
                  <strong>{workspace.health.high_severity_findings}</strong><span>с высоким влиянием</span>
                </div>
              </section>
            )}

            {sessionMode && (
              <InstructorReviewBrief
                stage={instructorAgentStage}
                run={instructorAgentRun}
                error={instructorAgentError}
                openingPriorityRef={instructorOpeningPriorityRef}
                evidenceReady={!!instructorEvidenceRef}
                draftStatus={currentSuggestion?.status || null}
                previewReady={!!canvasChangePreview}
                errorScope={instructorAgentErrorScope}
                onRun={() => void runInstructorSummary()}
                onOpenPriority={(priority) => void openInstructorPriority(priority)}
                onRetryEvidence={() => {
                  if (failedInstructorPriority) {
                    void openInstructorPriority(failedInstructorPriority);
                  } else {
                    void runInstructorSummary();
                  }
                }}
                canRetryEvidence={!!failedInstructorPriority}
              />
            )}

            {sessionMode && (
              <CourseImprovementLoop
                stage={gapAgentStage}
                run={gapAgentRun}
                error={gapAgentError}
                draft={interventionDraft}
                draftText={interventionText}
                actionBusy={interventionBusy}
                actionError={interventionError}
                actionRecovery={interventionRecovery}
                failedCandidate={failedInterventionCandidate}
                resultHeadingRef={gapResultHeadingRef}
                draftHeadingRef={interventionHeadingRef}
                decisionStatusRef={interventionDecisionRef}
                onRun={() => void runQuestionGaps()}
                onPrepare={(candidate) => void prepareIntervention(candidate)}
                onDraftText={setInterventionText}
                onReview={(status) => void reviewIntervention(status)}
              />
            )}

            <TutorQualityPanel quality={workspace.tutor_quality} />

            <TutorPolicyPanel
              policy={workspace.tutor_policy}
              canEdit={canManagePolicy}
              busy={policyBusy}
              onSave={saveTutorPolicy}
            />

            {dataPolicy && (
              <TutorDataGovernancePanel
                policy={dataPolicy}
                busy={dataPolicyBusy}
                onSave={saveTutorDataPolicy}
              />
            )}

            {isOrganizationAdmin && dataPolicyError && (
              <section className={styles.dataGovernanceFailure} role="alert">
                <div>
                  <span>Управление данными организации</span>
                  <h2>Срок хранения временно недоступен</h2>
                  <p>{dataPolicyError} Настройки и история не изменены.</p>
                </div>
                <button type="button" onClick={() => void loadWorkspace()}>
                  Повторить
                </button>
              </section>
            )}

            {error && (
              <div className={styles.errorNotice} role="alert">
                <span>{error}</span>
                <button type="button" onClick={loadWorkspace}>Повторить</button>
              </div>
            )}
            {notice && <div className={styles.successNotice} role="status">{notice}</div>}

            {!workspace.latest_audit ? (
              <section className={styles.emptyState}>
                <CourseThread focus="whole_course" />
                <div className={styles.stateCode}>Нет результатов проверки</div>
                <h2>Сначала добавьте материалы и запустите аудит</h2>
                <p>Курс уже сохранён. Откройте инструменты курса, добавьте цели, материалы и задания — после этого очередь соберётся автоматически.</p>
                <Link className={styles.primaryLink} href={`/?course=${workspace.course.id}`}>
                  Подготовить и проверить курс
                </Link>
              </section>
            ) : workspace.latest_audit.status === "failed" ? (
              <section className={styles.emptyState}>
                <div className={styles.stateCode}>Проверка не завершена</div>
                <h2>Исходные материалы сохранены</h2>
                <p>{workspace.latest_audit.failure_message}</p>
                <Link className={styles.primaryLink} href={`/?course=${workspace.course.id}`}>
                  Проверить настройки и повторить
                </Link>
              </section>
            ) : ["queued", "running"].includes(workspace.latest_audit.status) ? (
              <section className={styles.emptyState} aria-live="polite">
                <span className={styles.spinner} />
                <div className={styles.stateCode}>Аудит выполняется</div>
                <h2>Связываем цели, материалы и задания</h2>
                <p>Готово {workspace.latest_audit.progress}%. Очередь обновится автоматически.</p>
              </section>
            ) : !workspace.findings.length ? (
              <section className={styles.emptyState}>
                <CourseThread focus="whole_course" />
                <div className={styles.stateCode}>Очередь пуста</div>
                <h2>Значимых разрывов не найдено</h2>
                <p>Результат относится только к текущей версии материалов. После изменения курса запустите аудит снова.</p>
                <Link className={styles.secondaryLink} href={`/?course=${workspace.course.id}`}>
                  Открыть полный отчёт
                </Link>
              </section>
            ) : (
              <section className={styles.reviewLayout} id="review-workbench">
                <aside className={styles.queue}>
                  <div className={styles.queueHeading}>
                    <div>
                      <span>Требует внимания</span>
                      <h2>Найденные разрывы</h2>
                    </div>
                    <strong title="Ждут решения">{openFindingCount}</strong>
                  </div>
                  <div className={styles.queueList}>
                    {workspace.findings.map((finding) => (
                      <button
                        className={[
                          styles.queueItem,
                          selectedFindingId === finding.id ? styles.queueItemActive : "",
                        ].join(" ")}
                        key={finding.id}
                        type="button"
                        onClick={() => {
                          setSelectedFindingId(finding.id);
                          setInstructorEvidenceRef("");
                          setFailedInstructorPriority(null);
                          setInstructorDraftRef("");
                          setCanvasChangePreview(null);
                          setDraftError("");
                          setDraftFailureAction("");
                          setCanvasChangeError("");
                          setInstructorAgentError("");
                          setInstructorAgentErrorScope("");
                          setNotice("");
                        }}
                      >
                        <span className={styles.queueMeta}>
                          <em data-severity={finding.severity}>{finding.attention_label}</em>
                          <small>{STATUS_LABELS[finding.status]}</small>
                        </span>
                        <strong>{finding.title}</strong>
                        <span>{finding.confidence_label}</span>
                      </button>
                    ))}
                  </div>
                </aside>

                {selectedFinding && (
                  <article className={styles.findingDetail}>
                    <div className={styles.findingHeader}>
                      <div>
                        <span className={styles.severity} data-severity={selectedFinding.severity}>
                          {SEVERITY_LABELS[selectedFinding.severity]}
                        </span>
                        <h2 ref={evidenceHeadingRef} tabIndex={-1}>{selectedFinding.title}</h2>
                      </div>
                      <span className={styles.statusBadge} data-status={selectedFinding.status}>
                        {STATUS_LABELS[selectedFinding.status]}
                      </span>
                    </div>

                    <CourseThread focus={selectedFinding.thread_focus} />

                    <p className={styles.description}>{selectedFinding.description}</p>

                    <section className={styles.confidenceBlock} data-band={selectedFinding.confidence_band}>
                      <div>
                        <span>Надёжность вывода</span>
                        <strong>{selectedFinding.confidence_label}</strong>
                      </div>
                      <b>{percentage(selectedFinding.confidence)}</b>
                    </section>

                    <section className={styles.evidenceSection}>
                      <div className={styles.detailLabel}>На чём основан вывод</div>
                      {selectedFinding.evidence.length ? (
                        <div className={styles.evidenceList}>
                          {selectedFinding.evidence.map((item, index) => (
                            <blockquote key={`${item.document_id}-${index}`}>
                              <span>{EVIDENCE_LABELS[item.object_type] || "Источник курса"}</span>
                              <p>{item.quote}</p>
                              {item.document_id && <small>Документ {item.document_id}</small>}
                            </blockquote>
                          ))}
                        </div>
                      ) : (
                        <div className={styles.missingEvidence}>
                          Источник не удалось показать. Не принимайте решение без ручной проверки курса.
                        </div>
                      )}
                    </section>

                    <section className={styles.recommendation}>
                      <div className={styles.detailLabel}>Что можно сделать</div>
                      <p>{selectedFinding.recommendation}</p>
                    </section>

                    {!!selectedFinding.uncertainty_reasons.length && (
                      <details className={styles.uncertainty}>
                        <summary>Почему вывод может быть неточным</summary>
                        <ul>
                          {selectedFinding.uncertainty_reasons.map((reason) => <li key={reason}>{reason}</li>)}
                        </ul>
                      </details>
                    )}

                    <footer className={styles.reviewActions}>
                      <div>
                        <span>Ваше решение сохраняется в истории проверки.</span>
                        {selectedFinding.reviewed_by && (
                          <small>Последнее решение: {selectedFinding.reviewed_by}</small>
                        )}
                      </div>
                      <button
                        className={styles.rejectButton}
                        type="button"
                        disabled={
                          !!reviewing ||
                          !["new", "confirmed", "ignored"].includes(selectedFinding.status)
                        }
                        onClick={() => reviewFinding("rejected")}
                      >
                        {reviewing === "rejected" ? "Отклоняем…" : "Отклонить"}
                      </button>
                      <button
                        className={styles.confirmButton}
                        type="button"
                        disabled={
                          !!reviewing ||
                          !["new", "rejected", "resolved", "ignored"].includes(
                            selectedFinding.status
                          )
                        }
                        onClick={() => reviewFinding("confirmed")}
                      >
                        {reviewing === "confirmed" ? "Подтверждаем…" : "Подтвердить"}
                      </button>
                    </footer>

                    <section className={styles.remediation}>
                      <div className={styles.remediationHeading}>
                        <div>
                          <span className={styles.detailLabel}>Черновик исправления</span>
                          <h3>Подготовить следующий шаг по материалам курса</h3>
                        </div>
                        {currentSuggestion && (
                          <span className={styles.draftStatus} data-status={currentSuggestion.status}>
                            {currentSuggestion.status === "accepted"
                              ? "Принят"
                              : currentSuggestion.status === "rejected"
                                ? "Отклонён"
                                : "Черновик"}
                          </span>
                        )}
                      </div>

                      {draftError && (
                        <div className={styles.localActionError} role="alert">
                          <div>
                            <strong>
                              {draftFailureAction === "generate"
                                ? "Черновик не подготовился"
                                : draftFailureAction === "regenerate"
                                  ? "Черновик устарел"
                                : "Решение по черновику не сохранилось"}
                            </strong>
                            <span>{draftError}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              if (["generate", "regenerate"].includes(draftFailureAction)) void generateDraft();
                              if (draftFailureAction === "accept") void reviewDraft("accepted");
                              if (draftFailureAction === "reject") void reviewDraft("rejected");
                            }}
                            disabled={draftBusy}
                          >
                            {draftFailureAction === "regenerate" ? "Подготовить новый вариант" : "Повторить"}
                          </button>
                        </div>
                      )}

                      {!currentSuggestion && selectedFinding.status !== "confirmed" ? (
                        <div className={styles.draftLocked}>
                          Сначала подтвердите наблюдение после проверки доказательств. Генерация не заменяет методическое решение.
                        </div>
                      ) : !currentSuggestion ? (
                        <div className={styles.draftStart}>
                          <p>Сервис найдёт релевантные фрагменты курса и подготовит редактируемый вариант. Без источников принятие будет заблокировано.</p>
                          <button type="button" onClick={generateDraft} disabled={draftBusy}>
                            {draftBusy ? "Ищем контекст…" : "Подготовить черновик"}
                          </button>
                        </div>
                      ) : (
                        <div className={styles.draftWorkspace}>
                          <div className={styles.draftMeta}>
                            <span>{DRAFT_ACTION_LABELS[currentSuggestion.action_type]}</span>
                            <span>Уровень: {BLOOM_LEVEL_LABELS[currentSuggestion.target_bloom_level] || currentSuggestion.target_bloom_level}</span>
                          </div>
                          <h4 ref={draftHeadingRef} tabIndex={-1}>{currentSuggestion.title}</h4>
                          <section className={styles.draftConfidence}>
                            <div>
                              <span>Уверенность помощника</span>
                              <strong>{percentage(currentSuggestion.confidence)}</strong>
                            </div>
                            <ul>
                              {currentSuggestion.limitations.map((limitation) => (
                                <li key={limitation}>{limitation}</li>
                              ))}
                            </ul>
                          </section>
                          {currentSuggestion.insufficient_context && (
                            <div className={styles.draftWarning}>
                              Материалов курса недостаточно для надёжного исправления. Добавьте контекст и подготовьте черновик снова.
                            </div>
                          )}
                          <label className={styles.draftEditor}>
                            <span>Текст черновика</span>
                            <textarea
                              value={draftText}
                              onChange={(event) => setDraftText(event.target.value)}
                              disabled={currentSuggestion.status === "accepted" || draftBusy}
                              rows={9}
                            />
                          </label>
                          <div className={styles.draftRationale}>
                            <strong>Почему это закрывает разрыв</strong>
                            <p>{currentSuggestion.rationale}</p>
                          </div>
                          <div className={styles.draftSources}>
                            <strong>Источники остаются рядом с черновиком</strong>
                            {currentSuggestion.citations.map((citation) => (
                              <blockquote key={`${currentSuggestion.id}-${citation.source_id}`}>
                                <span>[{citation.source_id}] {citation.document_title}</span>
                                <p>{citation.quote}</p>
                                {citation.source_url && (
                                  <a href={citation.source_url} target="_blank" rel="noreferrer">
                                    Открыть источник ↗
                                  </a>
                                )}
                              </blockquote>
                            ))}
                          </div>
                          <div className={styles.canvasBoundary}>
                            Принятие сохранит проверенный черновик в проекте. Canvas не будет изменён.
                          </div>
                          <div className={styles.draftActions}>
                            {currentSuggestion.status === "draft" ? (
                              <>
                                <button
                                  className={styles.rejectButton}
                                  type="button"
                                  onClick={() => reviewDraft("rejected")}
                                  disabled={draftBusy}
                                >
                                  {draftBusy ? "Сохраняем…" : "Отклонить черновик"}
                                </button>
                                <button
                                  className={styles.confirmButton}
                                  type="button"
                                  onClick={() => reviewDraft("accepted")}
                                  disabled={
                                    draftBusy ||
                                    currentSuggestion.insufficient_context ||
                                    draftText.trim().length < 10
                                  }
                                >
                                  {draftBusy ? "Сохраняем…" : "Принять после проверки"}
                                </button>
                              </>
                            ) : selectedFinding.status === "confirmed" ? (
                              <button
                                className={styles.secondaryAction}
                                type="button"
                                onClick={generateDraft}
                                disabled={draftBusy}
                              >
                                {draftBusy ? "Ищем контекст…" : "Подготовить новый вариант"}
                              </button>
                            ) : null}
                          </div>
                          {sessionMode && currentSuggestion.status === "accepted" && (
                            <section className={styles.canvasChangeWorkshop} aria-live="polite">
                              <div className={styles.canvasChangeHeading}>
                                <div>
                                  <span>Шаг 3 · только просмотр</span>
                                  <h5 ref={previewHeadingRef} tabIndex={-1}>Как это будет выглядеть в Canvas</h5>
                                </div>
                                <strong>Canvas не изменён</strong>
                              </div>
                              {!instructorDraftRef && !canvasChangePreview ? (
                                <p className={styles.canvasChangeUnavailable}>
                                  Этот вариант был создан раньше. Подготовьте новый вариант через помощника,
                                  чтобы получить связанный безопасный предпросмотр.
                                </p>
                              ) : (
                                <>
                                  <button
                                    className={styles.canvasPreviewButton}
                                    type="button"
                                    onClick={previewCanvasChange}
                                    disabled={canvasChangeBusy || !instructorDraftRef}
                                  >
                                    {canvasChangeBusy
                                      ? "Собираем предпросмотр…"
                                      : canvasChangePreview
                                        ? "Обновить предпросмотр"
                                        : "Показать изменения для Canvas"}
                                  </button>
                                  {canvasChangeError && (
                                    <div className={styles.localActionError} role="alert">
                                      <div>
                                        <strong>Предпросмотр не собрался</strong>
                                        <span>{canvasChangeError}</span>
                                      </div>
                                      <button
                                        type="button"
                                        onClick={() => void previewCanvasChange()}
                                        disabled={canvasChangeBusy}
                                      >
                                        Повторить
                                      </button>
                                    </div>
                                  )}
                                  {canvasChangePreview && (
                                    <article className={styles.canvasChangeCard}>
                                      <header>
                                        <span>{CANVAS_CHANGE_LABELS[canvasChangePreview.operation]}</span>
                                        <em>
                                          {canvasChangePreview.ready_for_canvas
                                            ? "Цель определена"
                                            : "Нужно выбрать место вручную"}
                                        </em>
                                      </header>
                                      <h6>{canvasChangePreview.title}</h6>
                                      <p className={styles.canvasChangeTarget}>
                                        {canvasChangePreview.module_title
                                          ? `Раздел: ${canvasChangePreview.module_title}`
                                          : `Курс: ${canvasChangePreview.course_title}`}
                                      </p>
                                      <div className={styles.canvasChangeContent}>
                                        {canvasChangePreview.content}
                                      </div>
                                      {!!canvasChangePreview.warnings.length && (
                                        <ul>
                                          {canvasChangePreview.warnings.map((warning) => (
                                            <li key={warning}>{canvasChangeWarning(warning)}</li>
                                          ))}
                                        </ul>
                                      )}
                                      <footer>
                                        <span>Принято преподавателем</span>
                                        <strong>Предпросмотр · без публикации</strong>
                                      </footer>
                                    </article>
                                  )}
                                </>
                              )}
                            </section>
                          )}
                        </div>
                      )}
                    </section>
                  </article>
                )}
              </section>
            )}

            <div className={styles.expertPath}>
              <span>Нужны матрица, протокол или выгрузка?</span>
              <Link href={`/?course=${workspace.course.id}`}>Открыть полный отчёт</Link>
            </div>
          </main>
        ) : null}
      </div>
    </>
  );
}
