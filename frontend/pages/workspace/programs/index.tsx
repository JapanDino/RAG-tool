import Head from "next/head";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AuthoringContext,
  EvidenceOption,
  ProgramAuthoringWorkbench,
  ProgramCreationForm,
} from "../../../components/ProgramAuthoringWorkbench";
import {
  ProgramAuditPanel,
  ProgramAuditPreview,
} from "../../../components/ProgramAuditPanel";
import {
  ProgramEvidenceRouteData,
  ProgramEvidenceRouteKind,
  ProgramEvidenceRoutes,
} from "../../../components/ProgramEvidenceRoutes";
import {
  ProgramReviewDraftData,
  ProgramReviewNotePanel,
  ProgramReviewNoteReceipt,
  ProgramReviewNoteSave,
} from "../../../components/ProgramReviewNotePanel";
import {
  PrerequisiteRelation,
  ProgramPrerequisitePanel,
} from "../../../components/ProgramPrerequisitePanel";
import {
  ProgramRouteBrief,
  ProgramRouteBriefData,
} from "../../../components/ProgramRouteBrief";
import styles from "../../../styles/curriculum-workspace.module.css";

type ProgramRole = "methodologist" | "program_designer" | "administrator";
type CoverageState = "unmapped" | "learning_only" | "assessed";
type ContributionStage = "introduced" | "developed" | "assessed";
type EvidenceState = "live" | "manual" | "missing";

type IdentityContext = {
  user: { display_name: string };
  organizations: {
    id: number;
    name: string;
    role: string;
  }[];
};

type ProgramSummary = {
  id: number;
  organization_id: number;
  code: string;
  title: string;
  description: string;
  version: number;
  competency_count: number;
  course_count: number;
  assessed_competency_count: number;
};

type Contribution = {
  id: number;
  program_id: number;
  competency_id: number;
  course_id: number;
  stage: ContributionStage;
  rationale: string;
  evidence: {
    state: EvidenceState;
    evidence_type: "learning_objective" | "assessment_item" | "manual_note";
    evidence_id?: number | null;
    label: string;
    excerpt: string;
    confidence?: number | null;
    review_status: string;
  };
};

type Competency = {
  id: number;
  code: string;
  title: string;
  description: string;
  position: number;
  coverage_state: CoverageState;
  contributions: Contribution[];
};

type ProgramMap = {
  program: ProgramSummary;
  courses: { id: number; title: string; position: number }[];
  competencies: Competency[];
  prerequisites: PrerequisiteRelation[];
  prerequisites_truncated: boolean;
  counts: {
    competencies: number;
    courses: number;
    mapped_cells: number;
    assessed_competencies: number;
    learning_only_competencies: number;
    unmapped_competencies: number;
    missing_evidence_cells: number;
  };
};

type AgentProgramOption = {
  program_ref: string;
  program_id: number;
  code: string;
  title: string;
  version: number;
};

type AgentAccepted = {
  run_id: string;
  execute_url: string;
};

type AgentProgramRun = {
  status: "queued" | "routing" | "tool_running" | "completed" | "abstained" | "failed";
  user_state: { label: string };
  response:
    | ProgramRouteBriefData
    | ProgramEvidenceRouteData
    | ProgramReviewDraftData
    | null;
};

class StaleProgramMapError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StaleProgramMapError";
  }
}

class ApiRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const PROGRAM_DEMO_AVAILABLE =
  process.env.NEXT_PUBLIC_ENABLE_PROGRAM_DEMO === "1";
const IDENTITY_STORAGE_KEY = "rag-dev-user";
const READ_ROLES = new Set(["methodologist", "program_designer", "administrator"]);
const WRITE_ROLES = new Set(["program_designer", "administrator"]);

const STAGE_META: Record<ContributionStage, { label: string; short: string }> = {
  introduced: { label: "Вводится", short: "В" },
  developed: { label: "Развивается", short: "Р" },
  assessed: { label: "Проверяется", short: "П" },
};

const COVERAGE_META: Record<CoverageState, { label: string; detail: string }> = {
  assessed: {
    label: "Есть проверка",
    detail: "В траектории есть связанное задание курса.",
  },
  learning_only: {
    label: "Только обучение",
    detail: "Компетенция развивается, но проверяемое задание пока не привязано.",
  },
  unmapped: {
    label: "Нет курса",
    detail: "В текущей карте к компетенции ещё не привязан курс.",
  },
};

async function api<T>(path: string, identity: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("X-Dev-User", identity);
  if (init?.body) headers.set("Content-Type", "application/json");
  const writeKey = process.env.NEXT_PUBLIC_API_WRITE_KEY || "";
  if (writeKey && init?.method && init.method !== "GET") {
    headers.set("X-API-Key", writeKey);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Не удалось выполнить запрос (${response.status})`;
    let detailCode = "";
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      detailCode = typeof detail?.code === "string" ? detail.code : "";
      if (detail?.code === "program_version_conflict") {
        message = "Карту уже изменили в другой вкладке. Обновите версию и повторите действие.";
      } else if (detail?.code === "program_review_note_version_conflict") {
        message = "Заметку уже изменили. Обновите основания; ваш текст останется в форме.";
      } else if (detail?.code === "program_review_note_source_changed") {
        message = "Основания программы изменились. Подготовьте черновик заново; ваш текст останется в форме.";
      } else if (detail?.code === "program_course_removal_denied") {
        message = "Текущий курс нельзя убрать этой операцией: на него могут ссылаться сохранённые связи.";
      } else if (detail?.code === "prerequisite_self_link") {
        message = "Компетенция не может быть предпосылкой самой для себя.";
      } else if (detail?.code === "prerequisite_cycle") {
        message = "Эта линия замкнёт маршрут в цикл. Проверьте направление связи.";
      } else if (detail?.code === "prerequisite_limit") {
        message = "Достигнут безопасный предел явных связей для одной программы.";
      } else {
        message =
          typeof detail === "string"
            ? detail
            : detail?.message || payload?.error?.message || message;
      }
    } catch {
      // Status copy remains safe when the API does not return JSON.
    }
    const error = new ApiRequestError(message, response.status);
    if (detailCode === "program_version_conflict") {
      error.name = "ProgramVersionConflict";
    } else if (detailCode === "program_review_note_version_conflict") {
      error.name = "ProgramReviewNoteVersionConflict";
    } else if (detailCode === "program_review_note_source_changed") {
      error.name = "ProgramReviewNoteSourceChanged";
    }
    throw error;
  }
  return response.json();
}

function roleLabel(role: ProgramRole) {
  if (role === "program_designer") return "Архитектор программы";
  if (role === "methodologist") return "Методист";
  return "Администратор";
}

function confidenceCopy(value?: number | null, state?: EvidenceState) {
  if (state === "missing") return "Нельзя проверить без источника";
  if (value === null || value === undefined) return "Заявлено автором карты";
  if (value >= 0.85) return "Источник распознан уверенно";
  if (value >= 0.6) return "Источник стоит проверить";
  return "Низкая уверенность — нужна проверка";
}

function russianCount(value: number, forms: [string, string, string]) {
  const remainder100 = value % 100;
  const remainder10 = value % 10;
  if (remainder100 >= 11 && remainder100 <= 14) return forms[2];
  if (remainder10 === 1) return forms[0];
  if (remainder10 >= 2 && remainder10 <= 4) return forms[1];
  return forms[2];
}

function reviewStatusCopy(value: string) {
  const labels: Record<string, string> = {
    confirmed: "Подтверждено",
    accepted: "Подтверждено",
    unreviewed: "Ещё не проверено",
    human_declared: "Заявлено автором карты",
    missing: "Источник недоступен",
  };
  return labels[value] || "Требует методической проверки";
}

export default function CurriculumWorkspace() {
  const [identity, setIdentity] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationId, setOrganizationId] = useState<number | null>(null);
  const [organizationName, setOrganizationName] = useState("");
  const [role, setRole] = useState<ProgramRole | null>(null);
  const [programs, setPrograms] = useState<ProgramSummary[]>([]);
  const [programListLoaded, setProgramListLoaded] = useState(false);
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null);
  const [programMap, setProgramMap] = useState<ProgramMap | null>(null);
  const [selectedCompetencyId, setSelectedCompetencyId] = useState<number | null>(null);
  const [selectedContributionId, setSelectedContributionId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [mapLoading, setMapLoading] = useState(false);
  const [creatingProgram, setCreatingProgram] = useState(false);
  const [creatingDemo, setCreatingDemo] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorLoadFailed, setEditorLoadFailed] = useState(false);
  const [authoringContext, setAuthoringContext] = useState<AuthoringContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [auditPreview, setAuditPreview] = useState<ProgramAuditPreview | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [programBrief, setProgramBrief] = useState<ProgramRouteBriefData | null>(null);
  const [programBriefBusy, setProgramBriefBusy] = useState(false);
  const [programBriefError, setProgramBriefError] = useState("");
  const [programBriefErrorRecovery, setProgramBriefErrorRecovery] = useState<
    "retry" | "refresh"
  >("retry");
  const [programEvidenceKind, setProgramEvidenceKind] =
    useState<ProgramEvidenceRouteKind>("gap");
  const [programEvidenceRoute, setProgramEvidenceRoute] =
    useState<ProgramEvidenceRouteData | null>(null);
  const [programEvidenceBusy, setProgramEvidenceBusy] = useState(false);
  const [programEvidenceError, setProgramEvidenceError] = useState("");
  const [programEvidenceErrorRecovery, setProgramEvidenceErrorRecovery] = useState<
    "retry" | "refresh"
  >("retry");
  const [programReviewDraft, setProgramReviewDraft] =
    useState<ProgramReviewDraftData | null>(null);
  const [programReviewBusy, setProgramReviewBusy] = useState(false);
  const [programReviewError, setProgramReviewError] = useState("");
  const [programReviewErrorRecovery, setProgramReviewErrorRecovery] = useState<
    "retry" | "refresh"
  >("retry");
  const [programReviewDirty, setProgramReviewDirty] = useState(false);
  const [selectedAuditFindingKey, setSelectedAuditFindingKey] = useState<
    string | null
  >(null);
  const [accessDenied, setAccessDenied] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [focusEvidence, setFocusEvidence] = useState(false);
  const evidenceHeadingRef = useRef<HTMLHeadingElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const auditRequestRef = useRef(0);
  const programBriefRequestRef = useRef(0);
  const programEvidenceRequestRef = useRef(0);
  const programReviewRequestRef = useRef(0);
  const auditRegionRef = useRef<HTMLDivElement>(null);
  const prerequisiteRegionRef = useRef<HTMLDivElement>(null);

  const loadAuditForProgram = useCallback(
    async (programId: number, userIdentity: string) => {
      const requestId = auditRequestRef.current + 1;
      auditRequestRef.current = requestId;
      setAuditLoading(true);
      setAuditError("");
      try {
        const value = await api<ProgramAuditPreview>(
          `/programs/${programId}/audit-preview`,
          userIdentity
        );
        if (auditRequestRef.current !== requestId) return;
        setAuditPreview(value);
        setSelectedAuditFindingKey((current) =>
          value.findings.some((finding) => finding.key === current)
            ? current
            : value.findings[0]?.key || null
        );
      } catch (reason) {
        if (auditRequestRef.current !== requestId) return;
        setAuditError(
          `Маршрут проверить не удалось. Карта и предыдущий результат сохранены. ${
            reason instanceof Error ? reason.message : String(reason)
          }`
        );
      } finally {
        if (auditRequestRef.current === requestId) setAuditLoading(false);
      }
    },
    []
  );

  const loadMap = useCallback(async (
    programId: number,
    userIdentity: string,
    showLoading = true
  ): Promise<boolean> => {
    if (showLoading) setMapLoading(true);
    setError("");
    setEditorLoadFailed(false);
      try {
        const value = await api<ProgramMap>(`/programs/${programId}/map`, userIdentity);
        setProgramMap(value);
        setProgramBrief((current) =>
          current?.program_version === value.program.version &&
          current.program_title === value.program.title
            ? current
            : null
        );
        setProgramBriefError("");
        setProgramBriefErrorRecovery("retry");
        setProgramEvidenceRoute((current) =>
          current?.program_version === value.program.version &&
          current.program_title === value.program.title
            ? current
            : null
        );
        setProgramEvidenceError("");
        setProgramEvidenceErrorRecovery("retry");
        setProgramReviewDraft((current) =>
          current?.program_version === value.program.version &&
          current.program_title === value.program.title
            ? current
            : null
        );
        setProgramReviewError("");
        setProgramReviewErrorRecovery("retry");
        auditRequestRef.current += 1;
        setAuditLoading(false);
        setAuditPreview(null);
      setAuditError("");
      setSelectedAuditFindingKey(null);
      setSelectedCompetencyId((current) =>
        value.competencies.some((item) => item.id === current)
          ? current
          : value.competencies[0]?.id || null
      );
      return true;
    } catch (reason) {
      if (showLoading) {
        setError(
          `Карту программы загрузить не удалось. Текущий выбор сохранён. ${
            reason instanceof Error ? reason.message : String(reason)
          }`
        );
      }
      return false;
    } finally {
      if (showLoading) setMapLoading(false);
    }
  }, []);

  const loadPrograms = useCallback(
    async (
      orgId: number,
      userIdentity: string,
      preferredId?: number,
      requirePreferred = false
    ): Promise<number | null> => {
      const rows = await api<ProgramSummary[]>(
        `/organizations/${orgId}/programs`,
        userIdentity
      );
      setPrograms(rows);
      setProgramListLoaded(true);
      const hasPreferred = rows.some((item) => item.id === preferredId);
      const nextId = hasPreferred
        ? preferredId || null
        : requirePreferred && preferredId
          ? null
          : rows[0]?.id || null;
      setSelectedProgramId(nextId);
      if (nextId) await loadMap(nextId, userIdentity);
      else {
        setProgramMap(null);
        setSelectedCompetencyId(null);
        setSelectedContributionId(null);
      }
      return nextId;
    },
    [loadMap]
  );

  const loadAuthoringContext = useCallback(
    async (programId: number, userIdentity: string) => {
      setContextLoading(true);
      try {
        const value = await api<AuthoringContext>(
          `/programs/${programId}/authoring-context`,
          userIdentity
        );
        setAuthoringContext(value);
      } finally {
        setContextLoading(false);
      }
    },
    []
  );

  const load = useCallback(async () => {
    const storedIdentity = window.localStorage.getItem(IDENTITY_STORAGE_KEY) || "";
    setIdentity(storedIdentity);
    setLoading(true);
    setError("");
    setAccessDenied(false);
    if (!storedIdentity) {
      setAccessDenied(true);
      setLoading(false);
      return;
    }
    try {
      const context = await api<IdentityContext>("/identity/me", storedIdentity);
      const search = new URLSearchParams(window.location.search);
      const organizationParam = search.get("organization");
      const requestedOrganizationId = Number(organizationParam);
      const hasExplicitOrganization = organizationParam !== null;
      const validRequestedOrganization =
        Number.isInteger(requestedOrganizationId) && requestedOrganizationId > 0;
      const organization = hasExplicitOrganization
        ? validRequestedOrganization
          ? context.organizations.find(
              (item) =>
                item.id === requestedOrganizationId && READ_ROLES.has(item.role)
            )
          : undefined
        : context.organizations.find((item) => READ_ROLES.has(item.role));
      if (!organization) {
        setAccessDenied(true);
        return;
      }
      setDisplayName(context.user.display_name);
      setOrganizationId(organization.id);
      setOrganizationName(organization.name);
      setRole(organization.role as ProgramRole);
      const programParam = search.get("program");
      const requestedProgramId = Number(programParam);
      const hasExplicitProgram = programParam !== null;
      const validRequestedProgram =
        Number.isInteger(requestedProgramId) && requestedProgramId > 0;
      if (hasExplicitProgram && !validRequestedProgram) {
        setAccessDenied(true);
        return;
      }
      const preferredProgramId =
        hasExplicitProgram && validRequestedProgram ? requestedProgramId : undefined;
      const selectedId = await loadPrograms(
        organization.id,
        storedIdentity,
        preferredProgramId,
        preferredProgramId !== undefined
      );
      if (preferredProgramId !== undefined && selectedId !== preferredProgramId) {
        setAccessDenied(true);
        return;
      }
      if (
        selectedId &&
        preferredProgramId === selectedId &&
        search.get("audit") === "1"
      ) {
        await loadAuditForProgram(selectedId, storedIdentity);
      }
    } catch (reason) {
      setError(
        `Рабочее пространство программы не загрузилось. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
    } finally {
      setLoading(false);
    }
  }, [loadAuditForProgram, loadPrograms]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedCompetency = useMemo(
    () =>
      programMap?.competencies.find((item) => item.id === selectedCompetencyId) ||
      programMap?.competencies[0] ||
      null,
    [programMap, selectedCompetencyId]
  );

  const selectedContribution = useMemo(
    () =>
      selectedCompetency?.contributions.find(
        (item) => item.id === selectedContributionId
      ) || selectedCompetency?.contributions[0] || null,
    [selectedCompetency, selectedContributionId]
  );
  const firstContributionId = selectedCompetency?.contributions[0]?.id || null;

  useEffect(() => {
    setSelectedContributionId(firstContributionId);
  }, [firstContributionId, selectedCompetency?.id]);

  useEffect(() => {
    if (focusEvidence && selectedContribution) {
      evidenceHeadingRef.current?.focus();
      setFocusEvidence(false);
    }
  }, [focusEvidence, selectedContribution]);

  useEffect(() => {
    if (success) successRef.current?.focus();
  }, [success]);

  const selectProgram = async (programId: number) => {
    if (
      programId !== selectedProgramId &&
      programReviewDirty &&
      !window.confirm(
        "В заметке есть несохранённые изменения. Переключить программу и удалить их?"
      )
    ) {
      return;
    }
    const previousProgramId = selectedProgramId;
    programBriefRequestRef.current += 1;
    setProgramBriefBusy(false);
    programEvidenceRequestRef.current += 1;
    setProgramEvidenceBusy(false);
    programReviewRequestRef.current += 1;
    setProgramReviewBusy(false);
    auditRequestRef.current += 1;
    setAuditLoading(false);
    setSelectedProgramId(programId);
    const loaded = await loadMap(programId, identity);
    if (!loaded) {
      setSelectedProgramId(previousProgramId);
      return;
    }
    setProgramBrief(null);
    setProgramBriefError("");
    setProgramBriefErrorRecovery("retry");
    setProgramEvidenceRoute(null);
    setProgramEvidenceError("");
    setProgramEvidenceErrorRecovery("retry");
    setProgramReviewDraft(null);
    setProgramReviewError("");
    setProgramReviewErrorRecovery("retry");
    setProgramReviewDirty(false);
    setAuditPreview(null);
    setAuditError("");
    setSelectedAuditFindingKey(null);
    setEditorOpen(false);
    setAuthoringContext(null);
    setSelectedContributionId(null);
  };

  const createProgram = async (payload: {
    code: string;
    title: string;
    description: string;
  }) => {
    if (!organizationId || !identity || creatingProgram) return;
    setCreatingProgram(true);
    setError("");
    setSuccess("");
    try {
      const created = await api<ProgramSummary>(
        `/organizations/${organizationId}/programs`,
        identity,
        { method: "POST", body: JSON.stringify(payload) }
      );
      await loadPrograms(organizationId, identity, created.id);
      setSuccess("Программа создана. Теперь добавьте курсы и первую компетенцию.");
    } catch (reason) {
      throw new Error(
        `Программу создать не удалось. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
    } finally {
      setCreatingProgram(false);
    }
  };

  const createDemo = async () => {
    if (!organizationId || !identity || creatingDemo) return;
    setCreatingDemo(true);
    setError("");
    setSuccess("");
    try {
      const result = await api<{ program_id: number; created: boolean }>(
        `/organizations/${organizationId}/programs/demo`,
        identity,
        { method: "POST", body: JSON.stringify({}) }
      );
      await loadPrograms(organizationId, identity, result.program_id);
      setSuccess(
        result.created
          ? "Учебный пример создан. Карта программы готова к просмотру."
          : "Учебный пример уже был создан. Открыта сохранённая карта."
      );
    } catch (reason) {
      setError(
        `Учебный пример создать не удалось. Существующие программы не изменены. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
    } finally {
      setCreatingDemo(false);
    }
  };

  const openEditor = async () => {
    if (!selectedProgramId || !identity) return;
    setEditorOpen(true);
    setError("");
    setSuccess("");
    setEditorLoadFailed(false);
    try {
      await loadAuthoringContext(selectedProgramId, identity);
    } catch (reason) {
      setEditorOpen(false);
      setEditorLoadFailed(true);
      setError(
        `Редактор маршрута не загрузился. Карта доступна только для просмотра; повторите открытие редактора. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
    }
  };

  const loadAuditPreview = async () => {
    if (!selectedProgramId || !identity || auditLoading) return;
    await loadAuditForProgram(selectedProgramId, identity);
  };

  const runProgramRouteBrief = async () => {
    if (!selectedProgramId || !programMap || !identity || programBriefBusy) return;
    const requestId = programBriefRequestRef.current + 1;
    programBriefRequestRef.current = requestId;
    const requestedProgramId = selectedProgramId;
    const requestedVersion = programMap.program.version;
    setProgramBriefBusy(true);
    setProgramBriefError("");
    try {
      const options = await api<{ programs: AgentProgramOption[] }>(
        `/agent/v1/programs?organization_id=${programMap.program.organization_id}&program_id=${requestedProgramId}`,
        identity
      );
      const option = options.programs.find(
        (item) =>
          item.program_id === requestedProgramId && item.version === requestedVersion
      );
      if (!option) {
        throw new StaleProgramMapError(
          "Версия карты изменилась. Обновите программу и соберите маршрут заново. Карта и данные не изменены."
        );
      }
      const payload = {
        contract_version: "agent.v1" as const,
        message: "Покажи карту компетенций",
        selection: { program_ref: option.program_ref },
      };
      const accepted = await api<AgentAccepted>("/agent/v1/messages", identity, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      });
      let run: AgentProgramRun | null = null;
      for (let step = 0; step < 4; step += 1) {
        run = await api<AgentProgramRun>(accepted.execute_url, identity, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (["completed", "abstained", "failed"].includes(run.status)) break;
      }
      if (
        programBriefRequestRef.current !== requestId ||
        selectedProgramId !== requestedProgramId
      ) return;
      if (
        !run ||
        run.status !== "completed" ||
        run.response?.mode !== "program_route_brief"
      ) {
        if (run?.status === "abstained") {
          throw new StaleProgramMapError(
            `${run.user_state.label}. Карта и данные не изменены.`
          );
        }
        throw new Error(run?.user_state.label || "Сервер не вернул готовый маршрут проверки.");
      }
      setProgramBrief(run.response);
      setProgramBriefErrorRecovery("retry");
    } catch (reason) {
      if (programBriefRequestRef.current !== requestId) return;
      setProgramBrief(null);
      setProgramBriefErrorRecovery(
        reason instanceof StaleProgramMapError ? "refresh" : "retry"
      );
      const failureMessage =
        reason instanceof Error ? reason.message : "Маршрут временно недоступен.";
      setProgramBriefError(
        failureMessage.includes("Карта и данные не изменены")
          ? failureMessage
          : `${failureMessage} Карта и данные не изменены.`
      );
    } finally {
      if (programBriefRequestRef.current === requestId) setProgramBriefBusy(false);
    }
  };

  const refreshProgramRouteMap = async () => {
    if (!selectedProgramId || !identity || programBriefBusy) return;
    const requestId = programBriefRequestRef.current + 1;
    programBriefRequestRef.current = requestId;
    setProgramBriefBusy(true);
    const loaded = await loadMap(selectedProgramId, identity, false);
    if (programBriefRequestRef.current !== requestId) return;
    if (loaded) {
      setProgramBriefError("");
      setProgramBriefErrorRecovery("retry");
    } else {
      setProgramBriefError(
        "Обновить карту не удалось. Карта и данные не изменены; попробуйте обновить ещё раз."
      );
      setProgramBriefErrorRecovery("refresh");
    }
    setProgramBriefBusy(false);
  };

  const selectProgramEvidenceKind = (kind: ProgramEvidenceRouteKind) => {
    if (kind === programEvidenceKind) return;
    programEvidenceRequestRef.current += 1;
    setProgramEvidenceBusy(false);
    setProgramEvidenceKind(kind);
    setProgramEvidenceRoute(null);
    setProgramEvidenceError("");
    setProgramEvidenceErrorRecovery("retry");
  };

  const runProgramEvidenceRoute = async () => {
    if (!selectedProgramId || !programMap || !identity || programEvidenceBusy) return;
    const requestId = programEvidenceRequestRef.current + 1;
    programEvidenceRequestRef.current = requestId;
    const requestedProgramId = selectedProgramId;
    const requestedVersion = programMap.program.version;
    const requestedKind = programEvidenceKind;
    setProgramEvidenceBusy(true);
    setProgramEvidenceError("");
    try {
      const options = await api<{ programs: AgentProgramOption[] }>(
        `/agent/v1/programs?organization_id=${programMap.program.organization_id}&program_id=${requestedProgramId}`,
        identity
      );
      const option = options.programs.find(
        (item) =>
          item.program_id === requestedProgramId && item.version === requestedVersion
      );
      if (!option) {
        throw new StaleProgramMapError(
          "Версия карты изменилась. Обновите программу и повторите выбранную проверку. Карта и данные не изменены."
        );
      }
      const payload = {
        contract_version: "agent.v1" as const,
        message:
          requestedKind === "gap"
            ? "Проверь пробел программы"
            : "Проверь предварительные требования программы",
        selection: { program_ref: option.program_ref },
      };
      const accepted = await api<AgentAccepted>("/agent/v1/messages", identity, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      });
      let run: AgentProgramRun | null = null;
      for (let step = 0; step < 4; step += 1) {
        run = await api<AgentProgramRun>(accepted.execute_url, identity, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (["completed", "abstained", "failed"].includes(run.status)) break;
      }
      if (
        programEvidenceRequestRef.current !== requestId ||
        selectedProgramId !== requestedProgramId
      ) return;
      if (
        !run ||
        run.status !== "completed" ||
        run.response?.mode !== "program_evidence_route" ||
        run.response.route_kind !== requestedKind
      ) {
        if (run?.status === "abstained") {
          throw new StaleProgramMapError(
            `${run.user_state.label}. Карта и данные не изменены.`
          );
        }
        throw new Error(
          run?.user_state.label || "Сервер не вернул выбранный доказательный маршрут."
        );
      }
      setProgramEvidenceRoute(run.response);
      setProgramEvidenceErrorRecovery("retry");
    } catch (reason) {
      if (programEvidenceRequestRef.current !== requestId) return;
      setProgramEvidenceRoute(null);
      if (
        reason instanceof ApiRequestError &&
        [401, 403, 404].includes(reason.status)
      ) {
        setProgramEvidenceError("");
        setAccessDenied(true);
        return;
      }
      setProgramEvidenceErrorRecovery(
        reason instanceof StaleProgramMapError ? "refresh" : "retry"
      );
      const failureMessage =
        reason instanceof Error ? reason.message : "Проверка временно недоступна.";
      setProgramEvidenceError(
        failureMessage.includes("Карта и данные не изменены")
          ? failureMessage
          : `${failureMessage} Карта и данные не изменены.`
      );
    } finally {
      if (programEvidenceRequestRef.current === requestId) {
        setProgramEvidenceBusy(false);
      }
    }
  };

  const refreshProgramEvidenceMap = async () => {
    if (!selectedProgramId || !identity || programEvidenceBusy) return;
    const requestId = programEvidenceRequestRef.current + 1;
    programEvidenceRequestRef.current = requestId;
    setProgramEvidenceBusy(true);
    const loaded = await loadMap(selectedProgramId, identity, false);
    if (programEvidenceRequestRef.current !== requestId) return;
    if (loaded) {
      setProgramEvidenceRoute(null);
      setProgramEvidenceError("");
      setProgramEvidenceErrorRecovery("retry");
    } else {
      setProgramEvidenceError(
        "Обновить карту не удалось. Карта и данные не изменены; попробуйте обновить ещё раз."
      );
      setProgramEvidenceErrorRecovery("refresh");
    }
    setProgramEvidenceBusy(false);
  };

  const runProgramReviewDraft = async (useLatestProgramVersion = false) => {
    if (!selectedProgramId || !programMap || !identity || programReviewBusy) return;
    const requestId = programReviewRequestRef.current + 1;
    programReviewRequestRef.current = requestId;
    const requestedProgramId = selectedProgramId;
    const requestedVersion = programMap.program.version;
    setProgramReviewBusy(true);
    setProgramReviewError("");
    try {
      const options = await api<{ programs: AgentProgramOption[] }>(
        `/agent/v1/programs?organization_id=${programMap.program.organization_id}&program_id=${requestedProgramId}`,
        identity
      );
      const option = options.programs.find(
        (item) =>
          item.program_id === requestedProgramId &&
          (useLatestProgramVersion || item.version === requestedVersion)
      );
      if (!option) {
        throw new StaleProgramMapError(
          "Версия карты изменилась. Обновите основания и подготовьте заметку заново. Карта и Canvas не изменены."
        );
      }
      const payload = {
        contract_version: "agent.v1" as const,
        message: "Создай заметку по программе",
        selection: { program_ref: option.program_ref },
      };
      const accepted = await api<AgentAccepted>("/agent/v1/messages", identity, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      });
      let run: AgentProgramRun | null = null;
      for (let step = 0; step < 4; step += 1) {
        run = await api<AgentProgramRun>(accepted.execute_url, identity, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (["completed", "abstained", "failed"].includes(run.status)) break;
      }
      if (
        programReviewRequestRef.current !== requestId ||
        selectedProgramId !== requestedProgramId
      ) return;
      if (
        !run ||
        run.status !== "completed" ||
        run.response?.mode !== "program_review_draft"
      ) {
        if (run?.status === "abstained") {
          throw new StaleProgramMapError(
            `${run.user_state.label}. Карта и Canvas не изменены.`
          );
        }
        throw new Error(
          run?.user_state.label || "Сервер не вернул проверяемый черновик заметки."
        );
      }
      setProgramReviewDraft(run.response);
      setProgramReviewErrorRecovery("retry");
      if (useLatestProgramVersion && option.version !== requestedVersion) {
        await loadMap(requestedProgramId, identity, false);
      }
    } catch (reason) {
      if (programReviewRequestRef.current !== requestId) return;
      if (
        reason instanceof ApiRequestError &&
        [401, 403, 404].includes(reason.status)
      ) {
        setProgramReviewError("");
        setAccessDenied(true);
        return;
      }
      setProgramReviewErrorRecovery(
        reason instanceof StaleProgramMapError ? "refresh" : "retry"
      );
      const message =
        reason instanceof Error
          ? reason.message
          : "Черновик временно недоступен. Карта и Canvas не изменены.";
      setProgramReviewError(message);
    } finally {
      if (programReviewRequestRef.current === requestId) {
        setProgramReviewBusy(false);
      }
    }
  };

  const saveProgramReviewNote = async (
    payload: ProgramReviewNoteSave
  ): Promise<ProgramReviewNoteReceipt> => {
    if (!selectedProgramId || !identity) {
      throw new Error("Сначала выберите программу.");
    }
    const saved = await api<ProgramReviewNoteReceipt>(
      `/programs/${selectedProgramId}/review-note`,
      identity,
      { method: "PUT", body: JSON.stringify(payload) }
    );
    setProgramReviewDraft((current) =>
      current
        ? {
            ...current,
            current_note: {
              note_ref: saved.note_ref,
              decision: saved.decision,
              content: saved.content,
              version: saved.version,
              source_fingerprint: saved.source_fingerprint,
            },
          }
        : current
    );
    return saved;
  };

  const openProgramEvidenceRoute = async (result: ProgramEvidenceRouteData) => {
    if (result.action_target === "audit") {
      if (!selectedProgramId || !identity) return;
      await loadAuditForProgram(selectedProgramId, identity);
      if (result.candidate?.focus_key) {
        setSelectedAuditFindingKey(result.candidate.focus_key);
      }
      window.requestAnimationFrame(() => {
        auditRegionRef.current?.focus({ preventScroll: true });
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        auditRegionRef.current?.scrollIntoView({
          behavior: reducedMotion ? "auto" : "smooth",
          block: "start",
        });
      });
      return;
    }
    window.requestAnimationFrame(() => {
      prerequisiteRegionRef.current?.focus({ preventScroll: true });
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      prerequisiteRegionRef.current?.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    });
  };

  const openProgramEvidenceReview = async () => {
    if (!selectedProgramId || !identity) return;
    await loadAuditForProgram(selectedProgramId, identity);
    window.requestAnimationFrame(() => {
      auditRegionRef.current?.focus({ preventScroll: true });
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      auditRegionRef.current?.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    });
  };

  const reloadEditor = async () => {
    if (!selectedProgramId || !identity) return;
    setError("");
    const loaded = await loadMap(selectedProgramId, identity);
    if (!loaded) throw new Error("Не удалось обновить карту.");
    try {
      await loadAuthoringContext(selectedProgramId, identity);
    } catch (reason) {
      throw new Error(
        `Карта обновлена, но список курсов недоступен. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
    }
  };

  const refreshAfterWrite = async (preferredCompetencyId?: number) => {
    if (!selectedProgramId || !identity) return;
    const loaded = await loadMap(selectedProgramId, identity);
    if (!loaded) {
      const refreshError = new Error(
        "Изменение сохранено, но обновлённая карта не загрузилась. Обновите версию карты перед следующим действием."
      );
      refreshError.name = "ProgramRefreshRequired";
      throw refreshError;
    }
    if (preferredCompetencyId) setSelectedCompetencyId(preferredCompetencyId);
    try {
      await loadAuthoringContext(selectedProgramId, identity);
    } catch (reason) {
      const refreshError = new Error(
        `Изменение сохранено, но редактор не обновился. Обновите карту перед следующим действием. ${
          reason instanceof Error ? reason.message : String(reason)
        }`
      );
      refreshError.name = "ProgramRefreshRequired";
      throw refreshError;
    }
  };

  const setCourseOrder = async (courseIds: number[]) => {
    if (!programMap || !identity) return;
    await api(`/programs/${programMap.program.id}/courses`, identity, {
      method: "PUT",
      body: JSON.stringify({
        expected_version: programMap.program.version,
        course_ids: courseIds,
      }),
    });
    await refreshAfterWrite();
  };

  const addCompetencyFromEditor = async (payload: {
    code: string;
    title: string;
    description: string;
    position: number;
  }) => {
    if (!programMap || !identity) return;
    const created = await api<{ id: number }>(
      `/programs/${programMap.program.id}/competencies`,
      identity,
      {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          expected_version: programMap.program.version,
        }),
      }
    );
    await refreshAfterWrite(created.id);
  };

  const loadEvidenceOptions = useCallback(
    async (courseId: number): Promise<EvidenceOption[]> => {
      if (!selectedProgramId || !identity) return [];
      const value = await api<{ options: EvidenceOption[] }>(
        `/programs/${selectedProgramId}/courses/${courseId}/evidence-options`,
        identity
      );
      return value.options;
    },
    [identity, selectedProgramId]
  );

  const saveContributionFromEditor = async (payload: {
    competency_id: number;
    course_id: number;
    course_position: number;
    stage: ContributionStage;
    rationale: string;
    evidence_type: "learning_objective" | "assessment_item" | "manual_note";
    evidence_id: number | null;
  }) => {
    if (!programMap || !identity) return;
    const saved = await api<{ id: number }>(
      `/programs/${programMap.program.id}/contributions`,
      identity,
      {
        method: "PUT",
        body: JSON.stringify({
          ...payload,
          expected_version: programMap.program.version,
        }),
      }
    );
    await refreshAfterWrite(payload.competency_id);
    setSelectedContributionId(saved.id);
  };

  const refreshPrerequisitesAfterWrite = async (
    action: "saved" | "deleted"
  ) => {
    if (!selectedProgramId || !identity) return;
    const loaded = await loadMap(selectedProgramId, identity, false);
    if (!loaded) {
      const refreshError = new Error(
        action === "saved"
          ? "Линия сохранена, но карта не обновилась. Обновите карту перед следующим изменением."
          : "Линия удалена, но карта не обновилась. Обновите карту перед следующим изменением."
      );
      refreshError.name = "ProgramRefreshRequired";
      throw refreshError;
    }
  };

  const reloadPrerequisiteMap = async () => {
    if (!selectedProgramId || !identity) return;
    const loaded = await loadMap(selectedProgramId, identity, false);
    if (!loaded) throw new Error("Сервер не вернул актуальную версию карты.");
  };

  const savePrerequisite = async (payload: {
    prerequisite_competency_id: number;
    target_competency_id: number;
    rationale: string;
  }) => {
    if (!programMap || !identity) return;
    setSuccess("");
    await api(`/programs/${programMap.program.id}/prerequisites`, identity, {
      method: "PUT",
      body: JSON.stringify({
        ...payload,
        expected_version: programMap.program.version,
      }),
    });
    await refreshPrerequisitesAfterWrite("saved");
  };

  const deletePrerequisite = async (relationId: number) => {
    if (!programMap || !identity) return;
    setSuccess("");
    await api(
      `/programs/${programMap.program.id}/prerequisites/${relationId}`,
      identity,
      {
        method: "DELETE",
        body: JSON.stringify({ expected_version: programMap.program.version }),
      }
    );
    await refreshPrerequisitesAfterWrite("deleted");
  };

  if (loading) {
    return (
      <div className={styles.statePage} aria-live="polite">
        <div className={styles.routeLoader}><i /><span /><i /><span /><i /></div>
        <h1>Собираем карту программы</h1>
        <p>Проверяем доступные программы, компетенции и связанные доказательства.</p>
      </div>
    );
  }

  if (accessDenied) {
    return (
      <div className={styles.statePage}>
        <div className={styles.stateEyebrow}>Доступ к программе</div>
        <h1>Карта программы недоступна</h1>
        <p>
          Её открывают методист, архитектор программы или администратор организации.
          Названия недоступных программ не раскрываются.
        </p>
        <Link href="/workspace">Вернуться в рабочее пространство</Link>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>Карта программы — Контур</title>
        <meta
          name="description"
          content="Проверяемая карта компетенций, курсов и учебных доказательств"
        />
      </Head>
      <div className={styles.page}>
        <header className={styles.header}>
          <div className={styles.brandBlock}>
            <Link href="/workspace" className={styles.mark} aria-label="Контур обучения">
              К
            </Link>
            <div>
              <strong>Контур программы</strong>
              <span>{organizationName}</span>
            </div>
          </div>
          <div className={styles.headerRoute} aria-hidden="true">
            <i /><span /><i /><span /><i />
          </div>
          <div className={styles.identityBlock}>
            <span>{role ? roleLabel(role) : "Рабочая роль"}</span>
            <strong>{displayName}</strong>
          </div>
        </header>

        <main className={styles.main}>
          <div className={styles.breadcrumbs}>
            <Link href="/workspace">Рабочее пространство</Link>
            <span aria-hidden="true">/</span>
            <span>Карта программы</span>
          </div>

          {error && programListLoaded && (
            <div className={styles.errorNotice} role="alert">
              <div>
                <strong>Карта осталась без изменений</strong>
                <span>{error}</span>
              </div>
              <button
                type="button"
                onClick={() =>
                  editorLoadFailed ? void openEditor() : void load()
                }
              >
                {editorLoadFailed
                  ? "Повторить открытие редактора"
                  : "Повторить загрузку"}
              </button>
            </div>
          )}
          {success && (
            <div className={styles.successNotice} role="status" tabIndex={-1} ref={successRef}>
              {success}
            </div>
          )}

          {error && !programListLoaded ? (
            <section className={styles.initialError} aria-labelledby="initial-error-title">
              <div className={styles.stateEyebrow}>Карта временно недоступна</div>
              <h1 id="initial-error-title">Программы не загрузились</h1>
              <p>
                Сохранённые программы и связи не изменены. Проверьте соединение и
                повторите загрузку — создавать новый пример сейчас не нужно.
              </p>
              <button className={styles.primaryButton} type="button" onClick={() => void load()}>
                Повторить загрузку
              </button>
            </section>
          ) : !programs.length ? (
            <section className={styles.emptyProgram} aria-labelledby="empty-program-title">
              <div className={styles.emptyRoute} aria-hidden="true">
                <i /><span /><i /><span /><i />
              </div>
              <div className={styles.stateEyebrow}>Первая программа</div>
              <h1 id="empty-program-title">Соберите курсы в единую траекторию</h1>
              <p>
                Программ пока нет. Карта покажет, где компетенция вводится,
                развивается и действительно проверяется заданием курса.
              </p>
              {role && WRITE_ROLES.has(role) ? (
                <ProgramCreationForm
                  creating={creatingProgram}
                  creatingDemo={creatingDemo}
                  demoAvailable={PROGRAM_DEMO_AVAILABLE}
                  onCreate={createProgram}
                  onCreateDemo={createDemo}
                />
              ) : (
                <div className={styles.readOnlyNotice}>
                  Архитектор программы или администратор создаст первую карту. После
                  этого вы сможете проверить все связи и доказательства.
                </div>
              )}
            </section>
          ) : (
            <>
              <section className={styles.programIntro}>
                <div>
                  <div className={styles.stateEyebrow}>Учебная траектория</div>
                  <h1>
                    {mapLoading
                      ? "Загружаем выбранную программу…"
                      : programMap?.program.title || "Карта программы"}
                  </h1>
                  <p>
                    {mapLoading
                      ? "Предыдущая карта скрыта, пока мы проверяем маршрут новой программы."
                      : programMap?.program.description ||
                        "Загружаем описание программы…"}
                  </p>
                </div>
                <div className={styles.programControls}>
                  <label className={styles.programSelect}>
                    <span>Программа</span>
                    <select
                      value={selectedProgramId || ""}
                      onChange={(event) => void selectProgram(Number(event.target.value))}
                      disabled={mapLoading || contextLoading}
                    >
                      {programs.map((program) => (
                        <option key={program.id} value={program.id}>
                          {program.code} · {program.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  {role && WRITE_ROLES.has(role) ? (
                    <button
                      className={editorOpen ? styles.editorToggleActive : styles.editorToggle}
                      type="button"
                      onClick={() =>
                        editorOpen ? setEditorOpen(false) : void openEditor()
                      }
                      aria-expanded={editorOpen}
                      aria-controls="program-authoring-workbench"
                    >
                      {editorOpen ? "Закрыть редактор" : "Редактировать маршрут"}
                    </button>
                  ) : null}
                </div>
              </section>

              {!mapLoading && programMap ? (
                <ProgramRouteBrief
                  programTitle={programMap.program.title}
                  busy={programBriefBusy}
                  error={programBriefError}
                  errorRecovery={programBriefErrorRecovery}
                  result={programBrief}
                  canAuthorProgram={Boolean(role && WRITE_ROLES.has(role))}
                  onRun={() => void runProgramRouteBrief()}
                  onRefresh={() => void refreshProgramRouteMap()}
                  onOpenReview={() => void openProgramEvidenceReview()}
                />
              ) : null}

              {!mapLoading && programMap ? (
                <ProgramEvidenceRoutes
                  programTitle={programMap.program.title}
                  selectedKind={programEvidenceKind}
                  busy={programEvidenceBusy}
                  error={programEvidenceError}
                  errorRecovery={programEvidenceErrorRecovery}
                  result={programEvidenceRoute}
                  onSelectKind={selectProgramEvidenceKind}
                  onRun={() => void runProgramEvidenceRoute()}
                  onRefresh={() => void refreshProgramEvidenceMap()}
                  onOpenEvidence={(result) => void openProgramEvidenceRoute(result)}
                />
              ) : null}

              {programMap ? (
                <ProgramReviewNotePanel
                  key={programMap.program.id}
                  programTitle={programMap.program.title}
                  canAuthor={Boolean(role && WRITE_ROLES.has(role))}
                  busy={mapLoading || programReviewBusy}
                  error={programReviewError}
                  errorRecovery={programReviewErrorRecovery}
                  result={programReviewDraft}
                  onPrepare={() => void runProgramReviewDraft()}
                  onRefresh={() => void runProgramReviewDraft(true)}
                  onSave={saveProgramReviewNote}
                  onDirtyChange={setProgramReviewDirty}
                />
              ) : null}

              {editorOpen && programMap ? (
                <div id="program-authoring-workbench">
                  <ProgramAuthoringWorkbench
                    context={authoringContext}
                    contextLoading={contextLoading}
                    mapCourses={programMap.courses}
                    competencies={programMap.competencies}
                    selectedCompetencyId={selectedCompetencyId}
                    onReload={reloadEditor}
                    onSetCourseOrder={setCourseOrder}
                    onAddCompetency={addCompetencyFromEditor}
                    onLoadEvidence={loadEvidenceOptions}
                    onSaveContribution={saveContributionFromEditor}
                  />
                </div>
              ) : null}

              {!mapLoading && programMap?.competencies.length ? (
                <div
                  ref={prerequisiteRegionRef}
                  tabIndex={-1}
                  aria-label="Явные линии предпосылок программы"
                  className={styles.auditFocusRegion}
                >
                  <ProgramPrerequisitePanel
                    relations={programMap.prerequisites}
                    competencies={programMap.competencies}
                    truncated={programMap.prerequisites_truncated}
                    canEdit={Boolean(role && WRITE_ROLES.has(role))}
                    onSave={savePrerequisite}
                    onDelete={deletePrerequisite}
                    onReload={reloadPrerequisiteMap}
                  />
                </div>
              ) : null}

              {!mapLoading && programMap?.competencies.length ? (
                <div
                  ref={auditRegionRef}
                  tabIndex={-1}
                  aria-label="Проверка доказательств программы"
                  className={styles.auditFocusRegion}
                >
                  <ProgramAuditPanel
                    preview={auditPreview}
                    loading={auditLoading}
                    error={auditError}
                    selectedFindingKey={selectedAuditFindingKey}
                    onRun={loadAuditPreview}
                    onSelectFinding={setSelectedAuditFindingKey}
                  />
                </div>
              ) : null}

              {mapLoading ? (
                <div
                  className={styles.mapLoading}
                  aria-busy="true"
                  aria-live="polite"
                  role="status"
                >
                  <div className={styles.routeLoader}><i /><span /><i /><span /><i /></div>
                  Загружаем маршрут компетенций…
                </div>
              ) : programMap && !programMap.competencies.length ? (
                <section className={styles.emptyCompetencies}>
                  <div className={styles.stateEyebrow}>Пустая карта</div>
                  <h2>Компетенции ещё не добавлены</h2>
                  <p>
                    Структура программы сохранена. Откройте редактор маршрута, добавьте
                    компетенцию и свяжите её с курсом — результат сразу появится здесь.
                  </p>
                  {role && WRITE_ROLES.has(role) && !editorOpen ? (
                    <button
                      className={styles.primaryButton}
                      type="button"
                      onClick={() => void openEditor()}
                    >
                      Открыть редактор маршрута
                    </button>
                  ) : null}
                </section>
              ) : programMap ? (
                <>
                  <div className={styles.mapSummary} aria-label="Состав текущей карты">
                    <strong>
                      {programMap.counts.competencies}{" "}
                      {russianCount(programMap.counts.competencies, [
                        "компетенция",
                        "компетенции",
                        "компетенций",
                      ])}
                    </strong>
                    <span>
                      {programMap.counts.courses}{" "}
                      {russianCount(programMap.counts.courses, ["курс", "курса", "курсов"])}
                    </span>
                    <span>{programMap.counts.assessed_competencies} с проверкой</span>
                    {programMap.counts.missing_evidence_cells ? (
                      <span className={styles.summaryAttention}>
                        {programMap.counts.missing_evidence_cells}{" "}
                        {russianCount(programMap.counts.missing_evidence_cells, [
                          "источник требует",
                          "источника требуют",
                          "источников требуют",
                        ])}{" "}
                        привязки
                      </span>
                    ) : (
                      <span>Все выбранные источники доступны</span>
                    )}
                  </div>

                  <div className={styles.curriculumShell}>
                    <section className={styles.competencyList} aria-labelledby="competencies-title">
                      <div className={styles.panelHeading}>
                        <span>01</span>
                        <div>
                          <small>Выберите маршрут</small>
                          <h2 id="competencies-title">Компетенции</h2>
                        </div>
                      </div>
                      <div className={styles.competencyButtons}>
                        {programMap.competencies.map((competency) => (
                          <button
                            type="button"
                            key={competency.id}
                            className={
                              competency.id === selectedCompetency?.id
                                ? styles.competencyActive
                                : styles.competencyButton
                            }
                            aria-pressed={competency.id === selectedCompetency?.id}
                            onClick={() => setSelectedCompetencyId(competency.id)}
                          >
                            <span>{competency.code}</span>
                            <strong>{competency.title}</strong>
                            <small data-state={competency.coverage_state}>
                              {COVERAGE_META[competency.coverage_state].label}
                            </small>
                          </button>
                        ))}
                      </div>
                    </section>

                    <section className={styles.routePanel} aria-labelledby="route-title">
                      <div className={styles.panelHeading}>
                        <span>02</span>
                        <div>
                          <small>Маршрут программы</small>
                          <h2 id="route-title">{selectedCompetency?.title}</h2>
                        </div>
                      </div>
                      {selectedCompetency ? (
                        <>
                          <p className={styles.competencyDescription}>
                            {selectedCompetency.description ||
                              "Описание компетенции пока не добавлено."}
                          </p>
                          <div
                            className={styles.coverageNotice}
                            data-state={selectedCompetency.coverage_state}
                          >
                            <strong>
                              {COVERAGE_META[selectedCompetency.coverage_state].label}
                            </strong>
                            <span>
                              {COVERAGE_META[selectedCompetency.coverage_state].detail}
                            </span>
                          </div>
                          <div className={styles.courseRoute}>
                            {programMap.courses.map((course, index) => {
                              const contribution = selectedCompetency.contributions.find(
                                (item) => item.course_id === course.id
                              );
                              return (
                                <div className={styles.courseStop} key={course.id}>
                                  {index > 0 ? <span className={styles.routeLine} aria-hidden="true" /> : null}
                                  {contribution ? (
                                    <button
                                      type="button"
                                      className={styles.mappedStop}
                                      data-stage={contribution.stage}
                                      aria-pressed={contribution.id === selectedContribution?.id}
                                      onClick={() => {
                                        setSelectedContributionId(contribution.id);
                                        setFocusEvidence(true);
                                      }}
                                    >
                                      <b>{STAGE_META[contribution.stage].short}</b>
                                      <span>
                                        <strong>{course.title}</strong>
                                        <small>{STAGE_META[contribution.stage].label}</small>
                                      </span>
                                      <em>Открыть доказательство</em>
                                    </button>
                                  ) : (
                                    <div className={styles.unmappedStop}>
                                      <b>—</b>
                                      <span>
                                        <strong>{course.title}</strong>
                                        <small>Связь не заявлена</small>
                                      </span>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                            {!programMap.courses.length ? (
                              <div className={styles.noCourses}>
                                В программу ещё не включён ни один курс.
                              </div>
                            ) : null}
                          </div>
                        </>
                      ) : null}
                    </section>

                    <aside className={styles.evidencePanel} aria-labelledby="evidence-title">
                      <div className={styles.panelHeading}>
                        <span>03</span>
                        <div>
                          <small>Проверяемая опора</small>
                          <h2 id="evidence-title" tabIndex={-1} ref={evidenceHeadingRef}>
                            Доказательство
                          </h2>
                        </div>
                      </div>
                      {selectedContribution ? (
                        <div className={styles.evidenceBody} data-state={selectedContribution.evidence.state}>
                          <div className={styles.evidenceStage}>
                            {STAGE_META[selectedContribution.stage].label}
                          </div>
                          <h3>{selectedContribution.evidence.label}</h3>
                          <p className={styles.rationale}>{selectedContribution.rationale}</p>
                          <blockquote>{selectedContribution.evidence.excerpt}</blockquote>
                          <dl>
                            <div>
                              <dt>Состояние источника</dt>
                              <dd>
                                {selectedContribution.evidence.state === "live"
                                  ? "Доступен в текущей версии курса"
                                  : selectedContribution.evidence.state === "manual"
                                    ? "Комментарий автора карты"
                                    : "Требует повторной привязки"}
                              </dd>
                            </div>
                            <div>
                              <dt>Надёжность</dt>
                              <dd>
                                {confidenceCopy(
                                  selectedContribution.evidence.confidence,
                                  selectedContribution.evidence.state
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>Статус проверки</dt>
                              <dd>{reviewStatusCopy(selectedContribution.evidence.review_status)}</dd>
                            </div>
                          </dl>
                          <small className={styles.evidenceBoundary}>
                            Карта показывает заявленную связь. Это не автоматическая оценка
                            качества курса или преподавателя.
                          </small>
                        </div>
                      ) : (
                        <div className={styles.evidenceEmpty}>
                          <div className={styles.emptyEvidenceMark}>Опора</div>
                          <p>
                            Выберите связанный курс в маршруте, чтобы открыть основание этой
                            связи. Пустая ячейка не создаёт вымышленного доказательства.
                          </p>
                        </div>
                      )}
                    </aside>
                  </div>
                </>
              ) : null}
            </>
          )}
        </main>
      </div>
    </>
  );
}
