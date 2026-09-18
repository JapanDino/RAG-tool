import { useEffect, useRef, useState } from "react";

import { ProgramEvidenceRouteData } from "./ProgramEvidenceRoutes";
import styles from "../styles/program-review-note.module.css";

export type ProgramReviewDecision = "act" | "observe" | "dismiss";

export type ProgramSavedReviewNote = {
  note_ref: string;
  decision: ProgramReviewDecision;
  content: string;
  version: number;
  source_fingerprint: string;
};

export type ProgramReviewDraftData = {
  mode: "program_review_draft";
  state: "draft" | "clear" | "partial";
  program_title: string;
  program_version: number;
  headline: string;
  draft_ref: string | null;
  candidate: ProgramEvidenceRouteData["candidate"];
  content: string | null;
  source_fingerprint: string;
  current_note: ProgramSavedReviewNote | null;
  limitations: string[];
  program_changed: false;
  canvas_changed: false;
};

export type ProgramReviewNoteReceipt = ProgramSavedReviewNote & {
  program_id: number;
  finding_key: string;
  finding_kind:
    | "coverage_gap"
    | "assessment_gap"
    | "evidence_gap"
    | "duplication_check";
  created_at: string;
  updated_at: string;
  program_changed: false;
  canvas_changed: false;
};

export type ProgramReviewNoteSave = {
  draft_ref: string;
  decision: ProgramReviewDecision;
  content: string;
  expected_version: number;
  confirmation: "save_program_review_note";
};

type Props = {
  programTitle: string;
  canAuthor: boolean;
  busy: boolean;
  error: string;
  errorRecovery: "retry" | "refresh";
  result: ProgramReviewDraftData | null;
  onPrepare: () => void;
  onRefresh: () => void;
  onSave: (payload: ProgramReviewNoteSave) => Promise<ProgramReviewNoteReceipt>;
  onDirtyChange: (dirty: boolean) => void;
};

const DECISIONS: { value: ProgramReviewDecision; label: string; detail: string }[] = [
  {
    value: "act",
    label: "В работу",
    detail: "Назначить разбор и вернуться с изменением программы.",
  },
  {
    value: "observe",
    label: "Наблюдать",
    detail: "Сохранить сигнал и сверить его на следующем просмотре.",
  },
  {
    value: "dismiss",
    label: "Не учитывать",
    detail: "Зафиксировать, почему сигнал сейчас не требует действия.",
  },
];

function focusAndReveal(element: HTMLElement | null) {
  if (!element) return;
  element.focus({ preventScroll: true });
  element.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
    block: "center",
  });
}

export function ProgramReviewNotePanel({
  programTitle,
  canAuthor,
  busy,
  error,
  errorRecovery,
  result,
  onPrepare,
  onRefresh,
  onSave,
  onDirtyChange,
}: Props) {
  const [content, setContent] = useState("");
  const [decision, setDecision] = useState<ProgramReviewDecision>("observe");
  const [dirty, setDirty] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveNeedsRefresh, setSaveNeedsRefresh] = useState(false);
  const [receipt, setReceipt] = useState<ProgramReviewNoteReceipt | null>(null);
  const previousDraftRef = useRef<string | null>(null);
  const resultHeadingRef = useRef<HTMLHeadingElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const confirmationRef = useRef<HTMLDivElement>(null);
  const receiptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!result) {
      previousDraftRef.current = null;
      setContent("");
      setDecision("observe");
      setDirty(false);
      setConfirming(false);
      setReceipt(null);
      setSaveError("");
      return;
    }
    if (previousDraftRef.current !== result.draft_ref) {
      if (!dirty) {
        setContent(result.current_note?.content || result.content || "");
        setDecision(result.current_note?.decision || "observe");
      }
      previousDraftRef.current = result.draft_ref;
      setConfirming(false);
      setReceipt(null);
      setSaveError("");
      setSaveNeedsRefresh(false);
      focusAndReveal(resultHeadingRef.current);
    }
  }, [dirty, result]);

  useEffect(() => {
    if (error || saveError) focusAndReveal(alertRef.current);
  }, [error, saveError]);

  useEffect(() => {
    onDirtyChange(dirty);
    if (!dirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    if (confirming) focusAndReveal(confirmationRef.current);
  }, [confirming]);

  useEffect(() => {
    if (receipt) focusAndReveal(receiptRef.current);
  }, [receipt]);

  const handleSave = async () => {
    if (!result?.draft_ref || content.trim().length < 40 || saving) return;
    setSaving(true);
    setSaveError("");
    try {
      const saved = await onSave({
        draft_ref: result.draft_ref,
        decision,
        content: content.trim(),
        expected_version: result.current_note?.version || 0,
        confirmation: "save_program_review_note",
      });
      setReceipt(saved);
      setDirty(false);
      setConfirming(false);
    } catch (reason) {
      const name = reason instanceof Error ? reason.name : "";
      setSaveNeedsRefresh(
        name === "ProgramReviewNoteVersionConflict" ||
          name === "ProgramReviewNoteSourceChanged"
      );
      setSaveError(
        reason instanceof Error
          ? reason.message
          : "Решение не сохранено. Текст остался в форме."
      );
      setConfirming(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={styles.shell} aria-labelledby="program-review-note-title">
      <header className={styles.header}>
        <div>
          <span>Лист решения · человек подтверждает</span>
          <h2 id="program-review-note-title">Зафиксировать следующий шаг</h2>
          <p>
            Помощник соберёт один текущий сигнал и черновик. Решение, формулировка
            и сохранение остаются за автором программы.
          </p>
        </div>
        {canAuthor && !result && !error ? (
          <button type="button" onClick={onPrepare} disabled={busy}>
            {busy ? "Собираем основания…" : "Подготовить заметку решения"}
          </button>
        ) : null}
      </header>

      {!canAuthor ? (
        <div className={styles.readOnly}>
          <span aria-hidden="true">VIEW</span>
          <div>
            <strong>Решение сохраняет архитектор программы или администратор</strong>
            <p>
              Методист может проверять карту и основания выше, но не получает
              скрытого права менять управленческое решение.
            </p>
          </div>
        </div>
      ) : busy ? (
        <div className={styles.loading} role="status" aria-live="polite">
          <i aria-hidden="true" />
          <div>
            <strong>Сверяем текущую версию и основания</strong>
            <p>Карта программы и Canvas в это время не меняются.</p>
          </div>
        </div>
      ) : error ? (
        <div className={styles.alert} role="alert" tabIndex={-1} ref={alertRef}>
          <strong>Черновик не подготовлен</strong>
          <p>{error}</p>
          <button type="button" onClick={errorRecovery === "refresh" ? onRefresh : onPrepare}>
            {errorRecovery === "refresh" ? "Обновить основания" : "Попробовать снова"}
          </button>
        </div>
      ) : result?.state === "draft" && result.candidate && result.content && result.draft_ref ? (
        <div className={styles.reviewDesk}>
          <aside className={styles.evidenceMargin}>
            <span>Основание · {result.source_fingerprint.replace("sha256:", "")}</span>
            <h3 tabIndex={-1} ref={resultHeadingRef}>{result.headline}</h3>
            <p className={styles.subject}>{result.candidate.subject}</p>
            <strong>{result.candidate.title}</strong>
            <p>{result.candidate.detail}</p>
            <dl className={styles.evidenceMeta}>
              <div>
                <dt>Уверенность правила</dt>
                <dd>{result.candidate.confidence_label}</dd>
              </div>
              <div>
                <dt>Статус проверки</dt>
                <dd>{result.candidate.review_label}</dd>
              </div>
              <div>
                <dt>Состояние источника</dt>
                <dd>
                  {result.candidate.evidence_status === "declared"
                    ? "Есть сохранённое основание"
                    : result.candidate.evidence_status === "missing"
                      ? "Источник недоступен"
                      : "Основание не заявлено"}
                </dd>
              </div>
              {result.candidate.evidence_truncated ? (
                <div data-warning="true">
                  <dt>Граница выдачи</dt>
                  <dd>Показана только первая часть оснований</dd>
                </div>
              ) : null}
            </dl>
            {result.candidate.evidence.length ? (
              <ol>
                {result.candidate.evidence.map((item, index) => (
                  <li key={`${item.title}-${index}`}>
                    <b>{String(index + 1).padStart(2, "0")}</b>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.context}</small>
                      {item.excerpt ? <p>{item.excerpt}</p> : null}
                      <em>
                        {item.evidence_state === "live"
                          ? "Источник доступен"
                          : item.evidence_state === "manual"
                            ? "Основание заявлено автором"
                            : "Источник недоступен"}
                        {` · ${item.review_label}`}
                      </em>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <div className={styles.missingEvidence}>
                Доступного источника нет — в заметке нельзя утверждать больше,
                чем видно по карте.
              </div>
            )}
          </aside>

          <div className={styles.notePaper}>
            <div className={styles.paperHeading}>
              <div>
                <span>Программа · версия {result.program_version}</span>
                <strong>{result.program_title}</strong>
              </div>
              <span className={styles.versionStamp}>
                {result.current_note ? `v${result.current_note.version}` : "NEW"}
              </span>
            </div>

            <fieldset className={styles.decisions}>
              <legend>Ваше решение</legend>
              {DECISIONS.map((item) => (
                <label key={item.value} data-selected={decision === item.value}>
                  <input
                    type="radio"
                    name="program-review-decision"
                    value={item.value}
                    checked={decision === item.value}
                    onChange={() => {
                      setDecision(item.value);
                      setDirty(true);
                      setReceipt(null);
                    }}
                  />
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.detail}</small>
                  </span>
                </label>
              ))}
            </fieldset>

            <label className={styles.editor}>
              <span>Заметка автора программы</span>
              <textarea
                value={content}
                maxLength={2000}
                rows={10}
                onChange={(event) => {
                  setContent(event.target.value);
                  setDirty(true);
                  setReceipt(null);
                }}
              />
              <small data-invalid={content.trim().length < 40}>
                {content.length}/2000 · минимум 40 знаков
              </small>
              {dirty ? (
                <strong className={styles.dirtyStatus} role="status">
                  Несохранённые изменения
                </strong>
              ) : null}
            </label>

            {saveError ? (
              <div className={styles.alert} role="alert" tabIndex={-1} ref={alertRef}>
                <strong>Решение не сохранено</strong>
                <p>{saveError} Ваш текст остался в форме.</p>
                {saveNeedsRefresh ? (
                  <button type="button" onClick={onRefresh}>Обновить основания</button>
                ) : null}
              </div>
            ) : null}

            {receipt ? (
              <div
                className={styles.receipt}
                role="status"
                tabIndex={-1}
                ref={receiptRef}
              >
                <span>Сохранено · v{receipt.version}</span>
                <strong>Решение записано в историю программы</strong>
                <p>Карта программы и Canvas не изменены.</p>
              </div>
            ) : null}

            {confirming ? (
              <div
                className={styles.confirmation}
                role="group"
                aria-label="Подтверждение решения"
                tabIndex={-1}
                ref={confirmationRef}
              >
                <div>
                  <span>Подтвердите запись</span>
                  <strong>{DECISIONS.find((item) => item.value === decision)?.label}</strong>
                  <p>
                    Основание {result.source_fingerprint}. Будет сохранена только
                    заметка; карта программы и Canvas не изменятся.
                  </p>
                </div>
                <div>
                  <button type="button" className={styles.secondary} onClick={() => setConfirming(false)}>
                    Вернуться к тексту
                  </button>
                  <button type="button" onClick={() => void handleSave()} disabled={saving}>
                    {saving ? "Сохраняем…" : "Подтвердить и сохранить"}
                  </button>
                </div>
              </div>
            ) : (
              <div className={styles.actions}>
                <details>
                  <summary>Что именно изменится</summary>
                  <ul>{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                </details>
                <button
                  type="button"
                  onClick={() => setConfirming(true)}
                  disabled={content.trim().length < 40 || saving}
                >
                  Сохранить решение
                </button>
              </div>
            )}
          </div>
        </div>
      ) : result ? (
        <div className={styles.clearState}>
          <span>{result.state === "partial" ? "PARTIAL" : "CLEAR"}</span>
          <h3 tabIndex={-1} ref={resultHeadingRef}>{result.headline}</h3>
          <p>
            {result.state === "partial"
              ? "Проверена не вся карта, поэтому помощник не создаёт уверенный черновик."
              : "Текущий автоматический маршрут не нашёл подходящего сигнала. Это не означает, что программа проверена полностью."}
          </p>
          <button type="button" onClick={onPrepare}>Проверить ещё раз</button>
        </div>
      ) : (
        <div className={styles.idle}>
          <div aria-hidden="true"><i /><span /><i /></div>
          <span>DECISION · ожидает запуска</span>
          <strong>{programTitle}</strong>
          <p>
            Сначала будет собран один проверяемый сигнал. Пока вы не подтвердите
            текст, в историю программы ничего не запишется.
          </p>
        </div>
      )}
    </section>
  );
}
