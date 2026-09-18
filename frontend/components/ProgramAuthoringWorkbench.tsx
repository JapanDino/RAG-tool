import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import styles from "../styles/curriculum-workspace.module.css";

export type AuthoringCourse = {
  id: number;
  title: string;
  description: string;
  in_program: boolean;
  position?: number | null;
};

export type AuthoringContext = {
  program_id: number;
  program_version: number;
  courses: AuthoringCourse[];
  courses_truncated: boolean;
};

export type EvidenceOption = {
  evidence_type: "learning_objective" | "assessment_item";
  evidence_id: number;
  label: string;
  excerpt: string;
  confidence?: number | null;
  review_status: string;
};

type MapCourse = { id: number; title: string; position: number };
type MapContribution = {
  id: number;
  course_id: number;
  stage: "introduced" | "developed" | "assessed";
  rationale: string;
  evidence: {
    state: "live" | "manual" | "missing";
    evidence_type: "learning_objective" | "assessment_item" | "manual_note";
    evidence_id?: number | null;
    label?: string;
    excerpt?: string;
    confidence?: number | null;
    review_status?: string;
  };
};
type MapCompetency = {
  id: number;
  code: string;
  title: string;
  position: number;
  contributions: MapContribution[];
};

function confidenceCopy(value?: number | null) {
  if (value === null || value === undefined) return "Уверенность не рассчитана";
  if (value >= 0.85) return "Источник распознан уверенно";
  if (value >= 0.6) return "Средняя уверенность — источник стоит проверить";
  return "Низкая уверенность — нужна ручная проверка";
}

function reviewStatusCopy(value: string) {
  const labels: Record<string, string> = {
    confirmed: "Подтверждено",
    accepted: "Подтверждено",
    unreviewed: "Ещё не проверено",
    rejected: "Отклонено при проверке",
  };
  return labels[value] || "Требует методической проверки";
}

type ProgramCreationFormProps = {
  creating: boolean;
  creatingDemo: boolean;
  demoAvailable: boolean;
  onCreate: (payload: {
    code: string;
    title: string;
    description: string;
  }) => Promise<void>;
  onCreateDemo: () => Promise<void>;
};

export function ProgramCreationForm({
  creating,
  creatingDemo,
  demoAvailable,
  onCreate,
  onCreateDemo,
}: ProgramCreationFormProps) {
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      await onCreate({ code, title, description });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return (
    <form className={styles.programCreationForm} onSubmit={(event) => void submit(event)}>
      <div className={styles.creationHeading}>
        <span>Настоящая программа</span>
        <strong>Начните с названия и кода</strong>
      </div>
      {error ? <div className={styles.inlineFormError} role="alert">{error}</div> : null}
      <div className={styles.creationFields}>
        <label>
          <span>Код программы</span>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Например, CS-MIDDLE"
            pattern="[A-Za-z0-9](?:[A-Za-z0-9._]|-)*"
            maxLength={80}
            required
          />
        </label>
        <label>
          <span>Название</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Информатика: основная школа"
            maxLength={500}
            required
          />
        </label>
        <label className={styles.creationDescription}>
          <span>Что объединяет программа</span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Кратко опишите возраст, предметную область и ожидаемую траекторию."
            maxLength={4000}
            rows={3}
          />
        </label>
      </div>
      <div className={styles.creationActions}>
        <button
          className={styles.primaryButton}
          type="submit"
          disabled={creating || creatingDemo}
        >
          {creating ? "Создаём программу…" : "Создать программу"}
        </button>
        {demoAvailable ? (
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={() => void onCreateDemo()}
            disabled={creating || creatingDemo}
          >
            {creatingDemo ? "Создаём пример…" : "Создать учебный пример"}
          </button>
        ) : null}
      </div>
      {demoAvailable ? (
        <small>
          Учебный пример нужен только для локальной демонстрации. Для реальной работы
          создайте собственную программу.
        </small>
      ) : null}
    </form>
  );
}

type WorkbenchProps = {
  context: AuthoringContext | null;
  contextLoading: boolean;
  mapCourses: MapCourse[];
  competencies: MapCompetency[];
  selectedCompetencyId: number | null;
  onReload: () => Promise<void>;
  onSetCourseOrder: (courseIds: number[]) => Promise<void>;
  onAddCompetency: (payload: {
    code: string;
    title: string;
    description: string;
    position: number;
  }) => Promise<void>;
  onLoadEvidence: (courseId: number) => Promise<EvidenceOption[]>;
  onSaveContribution: (payload: {
    competency_id: number;
    course_id: number;
    course_position: number;
    stage: "introduced" | "developed" | "assessed";
    rationale: string;
    evidence_type: "learning_objective" | "assessment_item" | "manual_note";
    evidence_id: number | null;
  }) => Promise<void>;
};

export function ProgramAuthoringWorkbench({
  context,
  contextLoading,
  mapCourses,
  competencies,
  selectedCompetencyId,
  onReload,
  onSetCourseOrder,
  onAddCompetency,
  onLoadEvidence,
  onSaveContribution,
}: WorkbenchProps) {
  const [draftCourseIds, setDraftCourseIds] = useState<number[]>([]);
  const [courseDraftDirty, setCourseDraftDirty] = useState(false);
  const [availableCourseId, setAvailableCourseId] = useState("");
  const [competencyCode, setCompetencyCode] = useState("");
  const [competencyTitle, setCompetencyTitle] = useState("");
  const [competencyDescription, setCompetencyDescription] = useState("");
  const [connectionCompetencyId, setConnectionCompetencyId] = useState("");
  const [connectionCourseId, setConnectionCourseId] = useState("");
  const [stage, setStage] = useState<"introduced" | "developed" | "assessed">(
    "introduced"
  );
  const [rationale, setRationale] = useState("");
  const [evidenceKey, setEvidenceKey] = useState("manual_note");
  const [evidenceOptions, setEvidenceOptions] = useState<EvidenceOption[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");
  const [contributionDraftDirty, setContributionDraftDirty] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [actionIssue, setActionIssue] = useState<{
    kind: "conflict" | "partial" | "general";
    message: string;
  } | null>(null);
  const [actionSuccess, setActionSuccess] = useState("");
  const statusRef = useRef<HTMLDivElement>(null);
  const contributionPairRef = useRef("");

  useEffect(() => {
    if (!courseDraftDirty) {
      setDraftCourseIds(mapCourses.map((course) => course.id));
    }
  }, [courseDraftDirty, mapCourses]);

  useEffect(() => {
    if (!connectionCompetencyId && competencies.length) {
      const preferred = competencies.some((item) => item.id === selectedCompetencyId)
        ? selectedCompetencyId
        : competencies[0].id;
      setConnectionCompetencyId(String(preferred));
    }
  }, [competencies, connectionCompetencyId, selectedCompetencyId]);

  useEffect(() => {
    if (!connectionCourseId && mapCourses.length) {
      setConnectionCourseId(String(mapCourses[0].id));
    }
    if (
      connectionCourseId &&
      !mapCourses.some((course) => course.id === Number(connectionCourseId))
    ) {
      setConnectionCourseId(mapCourses[0] ? String(mapCourses[0].id) : "");
    }
  }, [connectionCourseId, mapCourses]);

  const currentContribution = useMemo(() => {
    const competency = competencies.find(
      (item) => item.id === Number(connectionCompetencyId)
    );
    return competency?.contributions.find(
      (item) => item.course_id === Number(connectionCourseId)
    );
  }, [competencies, connectionCompetencyId, connectionCourseId]);

  useEffect(() => {
    const pairKey = `${connectionCompetencyId}:${connectionCourseId}`;
    const pairChanged = contributionPairRef.current !== pairKey;
    if (!pairChanged && contributionDraftDirty) return;
    contributionPairRef.current = pairKey;
    if (pairChanged) setContributionDraftDirty(false);
    if (!currentContribution) {
      setStage("introduced");
      setRationale("");
      setEvidenceKey("manual_note");
      return;
    }
    setStage(currentContribution.stage);
    setRationale(currentContribution.rationale);
    if (
      currentContribution.evidence.state === "live" &&
      currentContribution.evidence.evidence_id
    ) {
      setEvidenceKey(
        `${currentContribution.evidence.evidence_type}:${currentContribution.evidence.evidence_id}`
      );
    } else if (currentContribution.evidence.state === "manual") {
      setEvidenceKey("manual_note");
    } else {
      setEvidenceKey("");
    }
  }, [
    connectionCompetencyId,
    connectionCourseId,
    contributionDraftDirty,
    currentContribution,
  ]);

  useEffect(() => {
    const courseId = Number(connectionCourseId);
    if (!courseId) {
      setEvidenceOptions([]);
      setEvidenceError("");
      return;
    }
    let cancelled = false;
    setEvidenceLoading(true);
    setEvidenceError("");
    void onLoadEvidence(courseId)
      .then((options) => {
        if (!cancelled) setEvidenceOptions(options);
      })
      .catch((reason) => {
        if (!cancelled) {
          setEvidenceOptions([]);
          setEvidenceError(reason instanceof Error ? reason.message : String(reason));
        }
      })
      .finally(() => {
        if (!cancelled) setEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [connectionCourseId, onLoadEvidence]);

  useEffect(() => {
    if (actionSuccess) statusRef.current?.focus();
  }, [actionSuccess]);

  const coursesById = useMemo(
    () => new Map((context?.courses || []).map((course) => [course.id, course])),
    [context]
  );
  const availableCourses = (context?.courses || []).filter(
    (course) => !draftCourseIds.includes(course.id)
  );
  const orderDirty =
    draftCourseIds.length !== mapCourses.length ||
    draftCourseIds.some((courseId, index) => courseId !== mapCourses[index]?.id);
  const writeLocked =
    Boolean(busyAction) ||
    actionIssue?.kind === "conflict" ||
    actionIssue?.kind === "partial";
  const selectedEvidence = useMemo(() => {
    const option = evidenceOptions.find(
      (item) => `${item.evidence_type}:${item.evidence_id}` === evidenceKey
    );
    if (option) return option;
    const evidence = currentContribution?.evidence;
    if (
      evidence?.state === "live" &&
      evidence.evidence_id &&
      `${evidence.evidence_type}:${evidence.evidence_id}` === evidenceKey
    ) {
      return {
        evidence_type: evidence.evidence_type as
          | "learning_objective"
          | "assessment_item",
        evidence_id: evidence.evidence_id,
        label: evidence.label || "Источник курса",
        excerpt: evidence.excerpt || "Текст источника недоступен в текущем ответе.",
        confidence: evidence.confidence,
        review_status: evidence.review_status || "unreviewed",
      };
    }
    return null;
  }, [currentContribution, evidenceKey, evidenceOptions]);

  const moveCourse = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= draftCourseIds.length) return;
    setDraftCourseIds((current) => {
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
    setCourseDraftDirty(true);
  };

  const runAction = async (name: string, action: () => Promise<void>, message: string) => {
    setBusyAction(name);
    setActionIssue(null);
    setActionSuccess("");
    try {
      await action();
      setActionSuccess(message);
    } catch (reason) {
      const error = reason instanceof Error ? reason : new Error(String(reason));
      setActionIssue({
        kind:
          error.name === "ProgramVersionConflict"
            ? "conflict"
            : error.name === "ProgramRefreshRequired"
              ? "partial"
              : "general",
        message: error.message,
      });
      throw reason;
    } finally {
      setBusyAction("");
    }
  };

  const saveOrder = async () => {
    try {
      await runAction(
        "order",
        () => onSetCourseOrder(draftCourseIds),
        "Лента курсов сохранена. Карта ниже уже показывает новый порядок."
      );
      setCourseDraftDirty(false);
    } catch (reason) {
      if (reason instanceof Error && reason.name === "ProgramRefreshRequired") {
        setCourseDraftDirty(false);
      }
      // The preserved draft and inline error are the recovery surface.
    }
  };

  const reloadVersion = async () => {
    const recoveryKind = actionIssue?.kind === "partial" ? "partial" : "conflict";
    setBusyAction("reload");
    try {
      await onReload();
      setActionIssue(null);
      setActionSuccess(
        "Версия карты обновлена. Введённые значения сохранены — действие можно повторить."
      );
    } catch (reason) {
      setActionIssue({
        kind: recoveryKind,
        message: `Карту обновить не удалось. ${
          reason instanceof Error ? reason.message : String(reason)
        }`,
      });
    } finally {
      setBusyAction("");
    }
  };

  const submitCompetency = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await runAction(
        "competency",
        () =>
          onAddCompetency({
            code: competencyCode,
            title: competencyTitle,
            description: competencyDescription,
            position: Math.max(0, ...competencies.map((item) => item.position)) + 1,
          }),
        "Компетенция добавлена и появилась в карте."
      );
      setCompetencyCode("");
      setCompetencyTitle("");
      setCompetencyDescription("");
    } catch (reason) {
      if (reason instanceof Error && reason.name === "ProgramRefreshRequired") {
        setCompetencyCode("");
        setCompetencyTitle("");
        setCompetencyDescription("");
      }
      // Keep the entered competency fields intact.
    }
  };

  const submitContribution = async (event: FormEvent) => {
    event.preventDefault();
    const course = mapCourses.find((item) => item.id === Number(connectionCourseId));
    if (!course || !connectionCompetencyId || !evidenceKey) return;
    const [evidenceType, rawId] = evidenceKey.split(":");
    try {
      await runAction(
        "contribution",
        () =>
          onSaveContribution({
            competency_id: Number(connectionCompetencyId),
            course_id: course.id,
            course_position: course.position,
            stage,
            rationale,
            evidence_type: evidenceType as
              | "learning_objective"
              | "assessment_item"
              | "manual_note",
            evidence_id: rawId ? Number(rawId) : null,
          }),
        currentContribution
          ? "Связь обновлена. Доказательство в карте синхронизировано."
          : "Связь сохранена и добавлена в маршрут компетенции."
      );
      setContributionDraftDirty(false);
    } catch (reason) {
      if (reason instanceof Error && reason.name === "ProgramRefreshRequired") {
        setContributionDraftDirty(false);
      }
      // Keep the selected source and rationale intact.
    }
  };

  return (
    <section
      className={styles.authoringWorkbench}
      aria-labelledby="workbench-title"
      aria-busy={Boolean(busyAction) || contextLoading}
    >
      <div className={styles.workbenchHeader}>
        <div>
          <span>Черновой стол архитектора</span>
          <h2 id="workbench-title">Редактор маршрута</h2>
          <p>Соберите структуру, а затем сразу проверьте её на живой карте ниже.</p>
        </div>
      </div>

      {actionIssue ? (
        <div className={styles.workbenchError} role="alert">
          <div>
            <strong>
              {actionIssue.kind === "partial"
                ? "Изменение сохранено, но карта устарела"
                : actionIssue.kind === "conflict"
                  ? "Карта изменилась в другой вкладке"
                  : "Изменение не применено"}
            </strong>
            <span>{actionIssue.message}</span>
          </div>
          {actionIssue.kind !== "general" ? (
            <button
              type="button"
              onClick={() => void reloadVersion()}
              disabled={Boolean(busyAction)}
            >
              {busyAction === "reload" ? "Обновляем…" : "Обновить карту"}
            </button>
          ) : null}
        </div>
      ) : null}
      {actionSuccess ? (
        <div className={styles.workbenchSuccess} role="status" tabIndex={-1} ref={statusRef}>
          {actionSuccess}
        </div>
      ) : null}

      <section className={styles.courseTape} aria-labelledby="course-tape-title">
        <div className={styles.workbenchSectionHeading}>
          <span>01</span>
          <div>
            <h3 id="course-tape-title">Лента курсов</h3>
            <p>Порядок здесь — реальная последовательность курсов в программе.</p>
          </div>
        </div>
        {contextLoading ? (
          <div className={styles.workbenchLoading} aria-busy="true" role="status">
            Загружаем курсы организации…
          </div>
        ) : context ? (
          <>
            <div className={styles.courseTapeTrack}>
              {draftCourseIds.map((courseId, index) => {
                const course = coursesById.get(courseId);
                return (
                  <article className={styles.courseTapeStop} key={courseId}>
                    <div className={styles.courseTapeNumber}>{index + 1}</div>
                    <div>
                      <strong>{course?.title || `Курс ${courseId}`}</strong>
                      <span>{course?.description || "Описание курса не добавлено."}</span>
                    </div>
                    <div className={styles.courseMoveActions} aria-label={`Порядок курса ${course?.title || courseId}`}>
                      <button
                        type="button"
                        onClick={() => moveCourse(index, -1)}
                        disabled={index === 0 || writeLocked}
                        aria-label={`Переместить курс ${course?.title || courseId} раньше`}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => moveCourse(index, 1)}
                        disabled={index === draftCourseIds.length - 1 || writeLocked}
                        aria-label={`Переместить курс ${course?.title || courseId} позже`}
                      >
                        ↓
                      </button>
                    </div>
                  </article>
                );
              })}
              {!draftCourseIds.length ? (
                <div className={styles.workbenchEmpty}>
                  Лента пуста. Выберите первый курс организации ниже.
                </div>
              ) : null}
            </div>
            <div className={styles.courseTapeControls}>
              <label>
                <span>Курс организации</span>
                <select
                  value={availableCourseId}
                  onChange={(event) => setAvailableCourseId(event.target.value)}
                  disabled={!availableCourses.length || writeLocked}
                >
                  <option value="">Выберите курс</option>
                  {availableCourses.map((course) => (
                    <option key={course.id} value={course.id}>{course.title}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className={styles.secondaryButton}
                disabled={!availableCourseId || writeLocked}
                onClick={() => {
                  setDraftCourseIds((current) => [...current, Number(availableCourseId)]);
                  setCourseDraftDirty(true);
                  setAvailableCourseId("");
                }}
              >
                Добавить курс
              </button>
              <button
                type="button"
                className={styles.workbenchPrimary}
                disabled={!orderDirty || !draftCourseIds.length || writeLocked}
                onClick={() => void saveOrder()}
              >
                {busyAction === "order" ? "Сохраняем…" : "Сохранить порядок"}
              </button>
              {orderDirty ? (
                <button
                  type="button"
                  className={styles.textButton}
                  onClick={() => {
                    setDraftCourseIds(mapCourses.map((course) => course.id));
                    setCourseDraftDirty(false);
                  }}
                  disabled={writeLocked}
                >
                  Отменить черновик
                </button>
              ) : null}
            </div>
            {!context.courses.length ? (
              <p className={styles.workbenchHint}>
                В организации пока нет курсов. Сначала импортируйте или создайте курс в
                рабочем пространстве преподавателя.
              </p>
            ) : null}
            {context.courses_truncated ? (
              <p className={styles.workbenchHint}>
                Показаны первые 500 курсов. Уточнение поиска будет добавлено отдельно.
              </p>
            ) : null}
          </>
        ) : null}
      </section>

      <div className={styles.composerGrid}>
        <form className={styles.composerCard} onSubmit={(event) => void submitCompetency(event)}>
          <div className={styles.workbenchSectionHeading}>
            <span>02</span>
            <div>
              <h3>Новая компетенция</h3>
              <p>Опишите проверяемый результат программы, а не тему урока.</p>
            </div>
          </div>
          <label>
            <span>Код компетенции</span>
            <input
              value={competencyCode}
              onChange={(event) => setCompetencyCode(event.target.value)}
              placeholder="CS-04"
              pattern="[A-Za-z0-9](?:[A-Za-z0-9._]|-)*"
              maxLength={80}
              required
            />
          </label>
          <label>
            <span>Название</span>
            <input
              value={competencyTitle}
              onChange={(event) => setCompetencyTitle(event.target.value)}
              placeholder="Обосновывать выбор алгоритма"
              maxLength={500}
              required
            />
          </label>
          <label>
            <span>Описание</span>
            <textarea
              value={competencyDescription}
              onChange={(event) => setCompetencyDescription(event.target.value)}
              placeholder="Что именно ученик должен уметь объяснить или сделать?"
              rows={4}
              maxLength={4000}
            />
          </label>
          <button className={styles.workbenchPrimary} type="submit" disabled={writeLocked}>
            {busyAction === "competency" ? "Добавляем…" : "Добавить компетенцию"}
          </button>
        </form>

        <form className={styles.composerCard} onSubmit={(event) => void submitContribution(event)}>
          <div className={styles.workbenchSectionHeading}>
            <span>03</span>
            <div>
              <h3>Связь и доказательство</h3>
              <p>Зафиксируйте роль курса и покажите основание этой связи.</p>
            </div>
          </div>
          {!competencies.length || !mapCourses.length ? (
            <div className={styles.workbenchEmpty}>
              {!competencies.length
                ? "Сначала добавьте хотя бы одну компетенцию."
                : "Сначала добавьте курс и сохраните ленту."}
            </div>
          ) : (
            <>
              <div className={styles.pairedFields}>
                <label>
                  <span>Компетенция</span>
                  <select
                    value={connectionCompetencyId}
                    onChange={(event) => setConnectionCompetencyId(event.target.value)}
                    disabled={writeLocked}
                  >
                    {competencies.map((competency) => (
                      <option key={competency.id} value={competency.id}>
                        {competency.code} · {competency.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Курс</span>
                  <select
                    value={connectionCourseId}
                    onChange={(event) => setConnectionCourseId(event.target.value)}
                    disabled={writeLocked}
                  >
                    {mapCourses.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.position}. {course.title}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                <span>Роль курса в маршруте</span>
                <select
                  value={stage}
                  onChange={(event) => {
                    setStage(event.target.value as typeof stage);
                    setContributionDraftDirty(true);
                  }}
                  disabled={writeLocked}
                >
                  <option value="introduced">Вводится</option>
                  <option value="developed">Развивается</option>
                  <option value="assessed">Проверяется</option>
                </select>
              </label>
              <label>
                <span>Источник</span>
                <select
                  value={evidenceKey}
                  onChange={(event) => {
                    setEvidenceKey(event.target.value);
                    setContributionDraftDirty(true);
                  }}
                  disabled={evidenceLoading || writeLocked}
                  required
                >
                  {currentContribution?.evidence.state === "missing" ? (
                    <option value="">Текущий источник недоступен — выберите новый</option>
                  ) : null}
                  <option value="manual_note">Комментарий автора без отдельного источника</option>
                  {evidenceOptions.map((option) => (
                    <option
                      key={`${option.evidence_type}:${option.evidence_id}`}
                      value={`${option.evidence_type}:${option.evidence_id}`}
                    >
                      {option.evidence_type === "learning_objective" ? "Цель" : "Задание"}
                      {" · "}{option.label}
                    </option>
                  ))}
                </select>
              </label>
              {selectedEvidence ? (
                <div className={styles.evidenceChoicePreview} aria-live="polite">
                  <div>
                    <strong>
                      {selectedEvidence.evidence_type === "learning_objective"
                        ? "Цель курса"
                        : "Задание курса"}
                    </strong>
                    <span>{reviewStatusCopy(selectedEvidence.review_status)}</span>
                  </div>
                  <p>{confidenceCopy(selectedEvidence.confidence)}</p>
                  <blockquote>{selectedEvidence.excerpt}</blockquote>
                </div>
              ) : null}
              {evidenceLoading ? (
                <p className={styles.fieldHint} role="status">Загружаем источники курса…</p>
              ) : evidenceError ? (
                <p className={styles.fieldError} role="alert">{evidenceError}</p>
              ) : !evidenceOptions.length ? (
                <p className={styles.fieldHint}>
                  В курсе нет извлечённых целей или заданий. Можно сохранить явный
                  комментарий автора и позже заменить его источником.
                </p>
              ) : (
                <p className={styles.fieldHint}>
                  Источник показывает заявленное основание, а не автоматическую оценку.
                </p>
              )}
              <label>
                <span>Почему курс связан с компетенцией</span>
                <textarea
                  value={rationale}
                  onChange={(event) => {
                    setRationale(event.target.value);
                    setContributionDraftDirty(true);
                  }}
                  placeholder="Опишите наблюдаемое действие ученика и роль выбранного источника."
                  rows={5}
                  minLength={10}
                  maxLength={4000}
                  required
                />
              </label>
              <button
                className={styles.workbenchPrimary}
                type="submit"
                disabled={writeLocked || evidenceLoading || !evidenceKey}
              >
                {busyAction === "contribution"
                  ? "Сохраняем…"
                  : currentContribution
                    ? "Обновить связь"
                    : "Сохранить связь"}
              </button>
            </>
          )}
        </form>
      </div>
    </section>
  );
}
