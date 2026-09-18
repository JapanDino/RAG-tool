import { FormEvent, useEffect, useState } from "react";

import styles from "../styles/program-prerequisites.module.css";

export type PrerequisiteStructuralState =
  | "declared_order"
  | "order_check"
  | "needs_evidence";

export type PrerequisiteEvidence = {
  contribution_id: number;
  competency_id: number;
  course_id: number;
  course_title: string;
  course_position: number;
  stage: "introduced" | "developed" | "assessed";
  evidence_state: "live" | "manual" | "missing";
  evidence_label: string;
  evidence_excerpt: string;
  evidence_review_status: string;
};

export type PrerequisiteRelation = {
  id: number;
  program_id: number;
  prerequisite_competency_id: number;
  prerequisite_competency_code: string;
  prerequisite_competency_title: string;
  target_competency_id: number;
  target_competency_code: string;
  target_competency_title: string;
  rationale: string;
  structural_state: PrerequisiteStructuralState;
  structural_state_label: string;
  confidence_label: string;
  prerequisite_assessment: PrerequisiteEvidence | null;
  target_start: PrerequisiteEvidence | null;
  updated_at?: string | null;
};

type CompetencyOption = {
  id: number;
  code: string;
  title: string;
};

type Props = {
  relations: PrerequisiteRelation[];
  competencies: CompetencyOption[];
  truncated: boolean;
  canEdit: boolean;
  onSave: (payload: {
    prerequisite_competency_id: number;
    target_competency_id: number;
    rationale: string;
  }) => Promise<void>;
  onDelete: (relationId: number) => Promise<void>;
  onReload: () => Promise<void>;
};

const STATE_COPY: Record<
  PrerequisiteStructuralState,
  { eyebrow: string; action: string }
> = {
  declared_order: {
    eyebrow: "Структура совпадает с заявленным порядком",
    action:
      "Основания расположены последовательно; это не подтверждает готовность студента",
  },
  order_check: {
    eyebrow: "Проверьте порядок курсов",
    action: "Требуемая компетенция проверяется не раньше начала следующей",
  },
  needs_evidence: {
    eyebrow: "Не хватает основания",
    action: "Добавьте проверку требования или начало следующей компетенции",
  },
};

const STAGE_COPY = {
  introduced: "вводится",
  developed: "развивается",
  assessed: "проверяется",
};

function reviewStatusCopy(status: string) {
  const labels: Record<string, string> = {
    confirmed: "Источник проверен",
    accepted: "Источник проверен",
    unreviewed: "Источник ещё не проверен",
    human_declared: "Ручное основание автора карты",
    missing: "Источник недоступен",
  };
  return labels[status] || "Статус источника требует проверки";
}

function EvidenceStop({
  title,
  evidence,
  missingCopy,
}: {
  title: string;
  evidence: PrerequisiteEvidence | null;
  missingCopy: string;
}) {
  return (
    <div className={evidence ? styles.evidenceStop : styles.evidenceMissing}>
      <span>{title}</span>
      {evidence ? (
        <>
          <strong>
            {evidence.course_position}. {evidence.course_title}
          </strong>
          <small>
            Компетенция {STAGE_COPY[evidence.stage]} · {evidence.evidence_label}
          </small>
          <blockquote>{evidence.evidence_excerpt}</blockquote>
          <em>
            {evidence.evidence_state === "missing"
              ? "Источник требует повторной привязки"
              : evidence.evidence_state === "manual"
                ? "Основание заявлено автором карты"
                : "Источник доступен в текущей версии курса"}
            {" · "}
            {reviewStatusCopy(evidence.evidence_review_status)}
          </em>
        </>
      ) : (
        <p>{missingCopy}</p>
      )}
    </div>
  );
}

export function ProgramPrerequisitePanel({
  relations,
  competencies,
  truncated,
  canEdit,
  onSave,
  onDelete,
  onReload,
}: Props) {
  const [prerequisiteId, setPrerequisiteId] = useState(competencies[0]?.id || 0);
  const [targetId, setTargetId] = useState(competencies[1]?.id || 0);
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [reloading, setReloading] = useState(false);
  const [refreshRequired, setRefreshRequired] = useState(false);
  const [rationaleDirty, setRationaleDirty] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const selectedRelation = relations.find(
    (relation) =>
      relation.prerequisite_competency_id === prerequisiteId &&
      relation.target_competency_id === targetId
  );

  const rationaleForPair = (nextPrerequisiteId: number, nextTargetId: number) =>
    relations.find(
      (relation) =>
        relation.prerequisite_competency_id === nextPrerequisiteId &&
        relation.target_competency_id === nextTargetId
    )?.rationale || "";

  useEffect(() => {
    if (!competencies.some((item) => item.id === prerequisiteId)) {
      setPrerequisiteId(competencies[0]?.id || 0);
    }
    if (
      !competencies.some((item) => item.id === targetId) ||
      targetId === prerequisiteId
    ) {
      setTargetId(
        competencies.find((item) => item.id !== prerequisiteId)?.id || 0
      );
    }
  }, [competencies, prerequisiteId, targetId]);

  useEffect(() => {
    if (!rationaleDirty) setRationale(selectedRelation?.rationale || "");
  }, [rationaleDirty, selectedRelation?.id, selectedRelation?.rationale]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    const cleanRationale = rationale.trim();
    if (!prerequisiteId || !targetId || prerequisiteId === targetId) {
      setError("Выберите две разные компетенции: требование и следующий шаг.");
      return;
    }
    if (cleanRationale.length < 10) {
      setError("Объясните связь хотя бы одним коротким предложением.");
      return;
    }
    const updating = Boolean(selectedRelation);
    setSaving(true);
    try {
      await onSave({
        prerequisite_competency_id: prerequisiteId,
        target_competency_id: targetId,
        rationale: cleanRationale,
      });
      setRationale(cleanRationale);
      setRationaleDirty(false);
      setSuccess(
        updating
          ? "Линия обновлена. Порядок и основания пересчитаны по текущей карте."
          : "Линия сохранена. Порядок и основания пересчитаны по текущей карте."
      );
    } catch (reason) {
      const actionError =
        reason instanceof Error ? reason : new Error(String(reason));
      if (actionError.name === "ProgramRefreshRequired") {
        setRefreshRequired(true);
        setRationale(cleanRationale);
        setRationaleDirty(true);
        setError(actionError.message);
      } else {
        setError(
          `Линия не сохранена; введённое обоснование осталось в форме. ${actionError.message}`
        );
      }
    } finally {
      setSaving(false);
    }
  };

  const remove = async (relation: PrerequisiteRelation) => {
    const confirmed = window.confirm(
      `Удалить линию «${relation.prerequisite_competency_code} → ${relation.target_competency_code}»? Карта курсов и компетенции не изменятся.`
    );
    if (!confirmed) return;
    setError("");
    setSuccess("");
    setDeletingId(relation.id);
    try {
      await onDelete(relation.id);
      setSuccess("Линия удалена. Карта курсов и компетенции сохранены.");
    } catch (reason) {
      const actionError =
        reason instanceof Error ? reason : new Error(String(reason));
      if (actionError.name === "ProgramRefreshRequired") {
        setRefreshRequired(true);
        setError(actionError.message);
      } else {
        setError(`Линию удалить не удалось; карта не изменена. ${actionError.message}`);
      }
    } finally {
      setDeletingId(null);
    }
  };

  const reload = async () => {
    setReloading(true);
    setError("");
    try {
      await onReload();
      setRefreshRequired(false);
      setSuccess("Карта обновлена. Можно продолжить работу с линиями.");
    } catch (reason) {
      setError(
        `Карту обновить не удалось. Новые изменения заблокированы до обновления. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
    } finally {
      setReloading(false);
    }
  };

  const writeLocked = saving || deletingId !== null || reloading || refreshRequired;

  return (
    <section
      className={styles.panel}
      aria-labelledby="prerequisite-title"
      aria-busy={saving || deletingId !== null || reloading}
    >
      <div className={styles.threadRuler} aria-hidden="true">
        <i />
        <span />
        <b />
      </div>
      <header className={styles.header}>
        <div>
          <span>Явная логика программы</span>
          <h2 id="prerequisite-title">Линии предпосылок</h2>
          <p>
            Зафиксируйте, что студенту нужно освоить раньше. Сервис сверяет только
            сохранённый порядок курсов и показывает основания — он не придумывает
            педагогическую логику за автора программы.
          </p>
        </div>
        <div className={styles.scopeNote}>
          <strong>{relations.length}</strong>
          <span>{relations.length === 1 ? "явная связь" : "явных связей"}</span>
        </div>
      </header>

      {canEdit && competencies.length >= 2 ? (
        <form className={styles.composer} onSubmit={submit}>
          <div className={styles.composerHeading}>
            <strong>{selectedRelation ? "Изменить линию" : "Добавить линию"}</strong>
            <span>
              {selectedRelation
                ? "Для этой пары уже есть линия. Сохранение обновит её обоснование."
                : "Она останется проектным решением до отдельной публикации."}
            </span>
          </div>
          <label>
            <span>Что требуется раньше</span>
            <select
              value={prerequisiteId}
              onChange={(event) => {
                const nextId = Number(event.target.value);
                const nextTargetId =
                  nextId === targetId
                    ? competencies.find((item) => item.id !== nextId)?.id || 0
                    : targetId;
                setPrerequisiteId(nextId);
                setTargetId(nextTargetId);
                setRationale(rationaleForPair(nextId, nextTargetId));
                setRationaleDirty(false);
              }}
              disabled={writeLocked}
            >
              {competencies.map((competency) => (
                <option key={competency.id} value={competency.id}>
                  {competency.code} · {competency.title}
                </option>
              ))}
            </select>
          </label>
          <div className={styles.composerArrow} aria-hidden="true">→</div>
          <label>
            <span>Что идёт следующим</span>
            <select
              value={targetId}
              onChange={(event) => {
                const nextId = Number(event.target.value);
                setTargetId(nextId);
                setRationale(rationaleForPair(prerequisiteId, nextId));
                setRationaleDirty(false);
              }}
              disabled={writeLocked}
            >
              {competencies.map((competency) => (
                <option
                  key={competency.id}
                  value={competency.id}
                  disabled={competency.id === prerequisiteId}
                >
                  {competency.code} · {competency.title}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.rationaleField}>
            <span>Почему эта связь нужна</span>
            <textarea
              value={rationale}
              onChange={(event) => {
                setRationale(event.target.value);
                setRationaleDirty(true);
              }}
              placeholder="Например: методы анализа нужно освоить до проектирования итогового исследования."
              minLength={10}
              maxLength={4000}
              rows={3}
              disabled={writeLocked}
            />
          </label>
          <button type="submit" disabled={writeLocked}>
            {saving
              ? selectedRelation
                ? "Обновляем линию…"
                : "Сохраняем линию…"
              : selectedRelation
                ? "Обновить линию"
                : "Сохранить линию"}
          </button>
        </form>
      ) : !canEdit ? (
        <div className={styles.readOnlyNote}>
          Вы просматриваете логику программы. Изменить её может архитектор программы
          или администратор.
        </div>
      ) : (
        <div className={styles.readOnlyNote}>
          Для линии нужны как минимум две компетенции. Сначала добавьте следующий шаг
          маршрута в редакторе.
        </div>
      )}

      {error ? (
        <div
          className={refreshRequired ? styles.partial : styles.error}
          role="alert"
        >
          <span>{error}</span>
          {refreshRequired ? (
            <button type="button" onClick={() => void reload()} disabled={reloading}>
              {reloading ? "Обновляем карту…" : "Обновить карту"}
            </button>
          ) : null}
        </div>
      ) : null}
      {success ? (
        <div className={styles.success} role="status" tabIndex={-1}>{success}</div>
      ) : null}
      {truncated ? (
        <div className={styles.truncated} role="status">
          Показана ограниченная часть линий. Не принимайте решение о полном маршруте
          по этому списку.
        </div>
      ) : null}

      {!relations.length ? (
        <div className={styles.empty}>
          <strong>Явных предпосылок пока нет</strong>
          <p>
            Карта курсов продолжает работать. Добавьте первую линию, когда порядок
            между двумя компетенциями действительно является правилом программы.
          </p>
        </div>
      ) : (
        <div className={styles.relationList}>
          {relations.map((relation) => {
            const state = STATE_COPY[relation.structural_state];
            return (
              <article
                key={relation.id}
                className={styles.relationCard}
                data-state={relation.structural_state}
              >
                <div className={styles.relationStatus}>
                  <span>{state.eyebrow}</span>
                  <small>{state.action}</small>
                </div>
                <div className={styles.route} aria-label={`${relation.prerequisite_competency_title} — предпосылка для ${relation.target_competency_title}`}>
                  <div className={styles.prerequisiteNode}>
                    <span>{relation.prerequisite_competency_code}</span>
                    <strong>{relation.prerequisite_competency_title}</strong>
                    <small>требуется раньше</small>
                  </div>
                  <div className={styles.routeLine} aria-hidden="true"><span>→</span></div>
                  <div className={styles.targetNode}>
                    <span>{relation.target_competency_code}</span>
                    <strong>{relation.target_competency_title}</strong>
                    <small>следующий шаг</small>
                  </div>
                </div>
                <div className={styles.rationale}>
                  <span>Решение автора программы</span>
                  <p>{relation.rationale}</p>
                  <small>{relation.confidence_label}</small>
                </div>
                <div className={styles.evidencePair}>
                  <EvidenceStop
                    title="Проверка требования"
                    evidence={relation.prerequisite_assessment}
                    missingCopy="В карте пока нет курса, где требуемая компетенция проверяется."
                  />
                  <EvidenceStop
                    title="Начало следующего шага"
                    evidence={relation.target_start}
                    missingCopy="В карте пока нет курса, где начинается следующая компетенция."
                  />
                </div>
                {canEdit ? (
                  <button
                    className={styles.deleteButton}
                    type="button"
                    onClick={() => void remove(relation)}
                    disabled={writeLocked}
                  >
                    {deletingId === relation.id ? "Удаляем линию…" : "Удалить линию"}
                  </button>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
