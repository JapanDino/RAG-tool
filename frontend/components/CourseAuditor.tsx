import React, { useCallback, useEffect, useMemo, useState } from "react";

import styles from "../styles/course-auditor.module.css";


type Course = {
  id: number;
  dataset_id: number;
  title: string;
  description: string;
  source_type: "manual" | "file_upload" | "canvas";
  modules?: CourseModule[];
};

type CourseModule = { id: number; title: string; position: number };
type CourseDocument = { id: number; title: string; status: string; source_metadata: Record<string, unknown> };
type AuditRun = { id: number; status: string; config?: Record<string, any>; metrics: Record<string, any>; error?: string | null };
type Objective = { id: number; text: string; top_bloom_levels: string[]; confidence: number; document_id?: number | null };
type Assessment = { id: number; text: string; top_bloom_levels: string[]; confidence: number; document_id?: number | null };
type Alignment = { id: number; source_id: number; target_id: number; target_type: string; relation_type: string; score: number; evidence: any[] };
type Finding = {
  id: number;
  finding_type: string;
  severity: "info" | "low" | "medium" | "high";
  title: string;
  description: string;
  recommendation: string;
  confidence: number;
  evidence: any[];
  uncertainty_reasons: string[];
  status: "new" | "confirmed" | "rejected" | "resolved" | "ignored";
};
type CopilotCitation = {
  source_id: string;
  chunk_id: number;
  document_id: number;
  document_title: string;
  module_id?: number | null;
  module_title?: string | null;
  quote: string;
  source_url?: string | null;
  score: number;
};
type CopilotSuggestion = {
  id: number;
  finding_id: number;
  action_type: "create_material" | "create_assessment" | "revise_assessment";
  title: string;
  draft: string;
  target_bloom_level: string;
  rationale: string;
  citations: CopilotCitation[];
  confidence: number;
  retrieval_method: string;
  generation_provider: string;
  generation_model?: string | null;
  insufficient_context: boolean;
  status: "draft" | "accepted" | "rejected";
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
};
type AuditReport = { copilot_suggestions: CopilotSuggestion[] };
type AuditComparison = {
  available: boolean;
  before?: { audit_run_id: number; summary: Record<string, number>; finding_types: Record<string, number> } | null;
  after?: { audit_run_id: number; summary: Record<string, number>; finding_types: Record<string, number> } | null;
  delta: Record<string, number>;
  new_findings: number;
  removed_findings: number;
  persisted_findings: number;
};
type CanvasAlignmentPair = {
  outcome_external_id: string;
  assignment_external_id: string;
  outcome_text?: string | null;
  assignment_title?: string | null;
};
type CanvasAlignmentEvaluation = {
  available: boolean;
  explicit_pairs: number;
  inferred_pairs: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  precision?: number | null;
  recall?: number | null;
  f1?: number | null;
  mapping_coverage: number;
  matched: CanvasAlignmentPair[];
  missing_in_inference: CanvasAlignmentPair[];
  inferred_only: CanvasAlignmentPair[];
  unmapped_explicit: CanvasAlignmentPair[];
};
type ThresholdMetric = {
  threshold: number;
  inferred_pairs: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  precision: number;
  recall: number;
  f1: number;
};
type CanvasAlignmentCalibration = {
  available: boolean;
  reason?: string | null;
  current_threshold?: number | null;
  current?: ThresholdMetric | null;
  recommended_threshold?: number | null;
  recommended?: ThresholdMetric | null;
  top_k: number;
  labeled_positive_pairs: number;
  comparable_candidates: number;
  mapping_coverage: number;
  reliable: boolean;
  caveat: string;
  curve: ThresholdMetric[];
};
type CourseAnswer = {
  id: number;
  course_id: number;
  question: string;
  answer: string;
  citations: CopilotCitation[];
  confidence: number;
  retrieval_method: string;
  generation_provider: string;
  generation_model?: string | null;
  insufficient_context: boolean;
  feedback_status: "unreviewed" | "helpful" | "unhelpful";
  feedback_comment?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
};
type MlFeedbackSummary = {
  course_id: number;
  total_examples: number;
  positive_examples: number;
  negative_examples: number;
  by_type: Record<string, number>;
  warnings: string[];
};
type EvaluationCheck = {
  check_id: string;
  label: string;
  value?: number | null;
  threshold?: number | null;
  operator: string;
  passed?: boolean | null;
  required: boolean;
  notes: string;
};
type EvaluationProtocol = {
  id: number;
  course_id: number;
  status: "passed" | "failed" | "error";
  protocol_version: string;
  dataset_name: string;
  dataset_hash: string;
  metrics: Record<string, any>;
  checks: EvaluationCheck[];
  methodology: string[];
  duration_ms: number;
  error?: string | null;
  created_at?: string | null;
};
type EvidencePackPreview = {
  course_id: number;
  completeness_score: number;
  ready_for_submission: boolean;
  latest_audit_id?: number | null;
  latest_protocol_id?: number | null;
  artifacts: { name: string; included: boolean; description: string }[];
  missing: string[];
  warnings: string[];
};
type CanvasChangeItem = {
  suggestion_id: number;
  operation: "create_page" | "create_assignment" | "update_assignment";
  api_method: "POST" | "PUT";
  api_path: string;
  ready_for_canvas: boolean;
  module_title?: string | null;
  target_url?: string | null;
  title: string;
  confidence: number;
  warning?: string | null;
};
type CanvasChangeSet = {
  available: boolean;
  reason?: string | null;
  accepted_suggestions: number;
  ready_items: number;
  items: CanvasChangeItem[];
  warnings: string[];
};

const FINDING_LABELS: Record<string, string> = {
  objective_without_material: "Цель без материала",
  objective_without_assessment: "Цель без задания",
  bloom_mismatch: "Несоответствие Блума",
};
const COPILOT_ACTION_LABELS: Record<CopilotSuggestion["action_type"], string> = {
  create_material: "Черновик материала",
  create_assessment: "Новое задание",
  revise_assessment: "Переработанное задание",
};

async function api<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const writeKey = process.env.NEXT_PUBLIC_API_WRITE_KEY || "";
  if (writeKey && init?.method && init.method !== "GET") headers.set("X-API-Key", writeKey);
  if (typeof window !== "undefined") {
    const identity = window.localStorage.getItem("rag-dev-user") || "";
    if (identity) headers.set("X-Dev-User", identity);
  }
  const response = await fetch(`${base}${path}`, { ...init, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export default function CourseAuditor({ apiBase }: { apiBase: string }) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState<number | null>(null);
  const [course, setCourse] = useState<Course | null>(null);
  const [documents, setDocuments] = useState<CourseDocument[]>([]);
  const [audits, setAudits] = useState<AuditRun[]>([]);
  const [activeAuditId, setActiveAuditId] = useState<number | null>(null);
  const [audit, setAudit] = useState<AuditRun | null>(null);
  const [objectives, setObjectives] = useState<Objective[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [alignment, setAlignment] = useState<Alignment[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [canvasUrl, setCanvasUrl] = useState("");
  const [canvasCourseId, setCanvasCourseId] = useState("");
  const [canvasToken, setCanvasToken] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState("unknown");
  const [moduleId, setModuleId] = useState("");
  const [view, setView] = useState<"overview" | "matrix" | "findings" | "qa">("overview");
  const [severity, setSeverity] = useState("all");
  const [status, setStatus] = useState("all");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copilotSuggestions, setCopilotSuggestions] = useState<Record<number, CopilotSuggestion>>({});
  const [copilotHistory, setCopilotHistory] = useState<Record<number, CopilotSuggestion[]>>({});
  const [copilotBusy, setCopilotBusy] = useState<Record<number, boolean>>({});
  const [auditComparison, setAuditComparison] = useState<AuditComparison | null>(null);
  const [canvasAlignment, setCanvasAlignment] = useState<CanvasAlignmentEvaluation | null>(null);
  const [canvasCalibration, setCanvasCalibration] = useState<CanvasAlignmentCalibration | null>(null);
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaModuleId, setQaModuleId] = useState("");
  const [qaHistory, setQaHistory] = useState<CourseAnswer[]>([]);
  const [qaBusy, setQaBusy] = useState(false);
  const [canvasChangeSet, setCanvasChangeSet] = useState<CanvasChangeSet | null>(null);
  const [mlFeedback, setMlFeedback] = useState<MlFeedbackSummary | null>(null);
  const [evaluationProtocols, setEvaluationProtocols] = useState<EvaluationProtocol[]>([]);
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const [evidencePack, setEvidencePack] = useState<EvidencePackPreview | null>(null);

  const loadCourses = useCallback(async () => {
    const rows = await api<Course[]>(apiBase, "/courses");
    setCourses(rows);
    if (!courseId && rows.length) {
      const requested = typeof window !== "undefined"
        ? Number(new URLSearchParams(window.location.search).get("course"))
        : 0;
      setCourseId(rows.some((item) => item.id === requested) ? requested : rows[0].id);
    }
  }, [apiBase, courseId]);

  const loadAuditResults = useCallback(async (auditId: number) => {
    const [run, objectiveRows, assessmentRows, edgeRows, findingRows, report, canvasEvaluation, calibration] = await Promise.all([
      api<AuditRun>(apiBase, `/audits/${auditId}`),
      api<Objective[]>(apiBase, `/audits/${auditId}/objectives`),
      api<Assessment[]>(apiBase, `/audits/${auditId}/assessments`),
      api<Alignment[]>(apiBase, `/audits/${auditId}/alignment`),
      api<Finding[]>(apiBase, `/audits/${auditId}/findings`),
      api<AuditReport>(apiBase, `/audits/${auditId}/report`),
      api<CanvasAlignmentEvaluation>(apiBase, `/audits/${auditId}/canvas-alignment`),
      api<CanvasAlignmentCalibration>(apiBase, `/audits/${auditId}/canvas-alignment/calibration`),
    ]);
    setAudit(run);
    setObjectives(objectiveRows);
    setAssessments(assessmentRows);
    setAlignment(edgeRows);
    setFindings(findingRows);
    setCanvasAlignment(canvasEvaluation);
    setCanvasCalibration(calibration);
    const histories: Record<number, CopilotSuggestion[]> = {};
    report.copilot_suggestions.forEach((item) => {
      histories[item.finding_id] = [item, ...(histories[item.finding_id] || [])];
    });
    setCopilotHistory(histories);
    setCopilotSuggestions(Object.fromEntries(Object.entries(histories).map(([findingId, items]) => [findingId, items[0]])));
  }, [apiBase]);

  const loadCourse = useCallback(async (id: number) => {
    setError(null);
    const [details, docs, runs, comparison, questions, changeSet, feedback, protocols, evidence] = await Promise.all([
      api<Course>(apiBase, `/courses/${id}`),
      api<CourseDocument[]>(apiBase, `/courses/${id}/documents`),
      api<AuditRun[]>(apiBase, `/courses/${id}/audits`),
      api<AuditComparison>(apiBase, `/courses/${id}/audits/compare`),
      api<CourseAnswer[]>(apiBase, `/courses/${id}/qa`),
      api<CanvasChangeSet>(apiBase, `/courses/${id}/canvas-change-set`),
      api<MlFeedbackSummary>(apiBase, `/courses/${id}/ml-feedback`),
      api<EvaluationProtocol[]>(apiBase, `/courses/${id}/evaluation-protocols`),
      api<EvidencePackPreview>(apiBase, `/courses/${id}/evidence-pack`),
    ]);
    setCourse(details);
    setDocuments(docs);
    setAudits(runs);
    setAuditComparison(comparison);
    setQaHistory(questions);
    setQaQuestion("");
    setQaModuleId("");
    setCanvasChangeSet(changeSet);
    setMlFeedback(feedback);
    setEvaluationProtocols(protocols);
    setEvidencePack(evidence);
    const latest = runs.find((item) => item.status === "done") || runs[0];
    if (latest) {
      setActiveAuditId(latest.id);
      await loadAuditResults(latest.id);
    } else {
      setActiveAuditId(null);
      setAudit(null);
      setObjectives([]);
      setAssessments([]);
      setAlignment([]);
      setFindings([]);
      setCopilotSuggestions({});
      setCopilotHistory({});
      setCanvasAlignment(null);
      setCanvasCalibration(null);
    }
  }, [apiBase, loadAuditResults]);

  const refreshEvidencePreview = useCallback(async (id: number) => {
    setEvidencePack(await api<EvidencePackPreview>(apiBase, `/courses/${id}/evidence-pack`));
  }, [apiBase]);

  useEffect(() => {
    loadCourses().catch((reason) => setError(String(reason)));
  }, [loadCourses]);

  useEffect(() => {
    if (courseId) loadCourse(courseId).catch((reason) => setError(String(reason)));
  }, [courseId, loadCourse]);

  useEffect(() => {
    if (!activeAuditId || !audit || !["queued", "running"].includes(audit.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const current = await api<AuditRun>(apiBase, `/audits/${activeAuditId}`);
        setAudit(current);
        if (["done", "failed"].includes(current.status)) {
          window.clearInterval(timer);
          await loadAuditResults(activeAuditId);
          if (courseId) {
            const runs = await api<AuditRun[]>(apiBase, `/courses/${courseId}/audits`);
            setAudits(runs);
            setAuditComparison(await api<AuditComparison>(apiBase, `/courses/${courseId}/audits/compare`));
            await refreshEvidencePreview(courseId);
          }
        }
      } catch (reason) {
        setError(String(reason));
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [activeAuditId, apiBase, audit, courseId, loadAuditResults, refreshEvidencePreview]);

  async function createCourse(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api<Course>(apiBase, "/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), description: description.trim(), source_type: "manual" }),
      });
      setTitle("");
      setDescription("");
      await loadCourses();
      setCourseId(created.id);
      setMessage("Курс создан. Добавьте материалы и запустите аудит.");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function createDemoCourse() {
    setBusy(true);
    setError(null);
    try {
      const demo = await api<{ course_id: number; audit_run_id: number; created: boolean }>(apiBase, "/courses/demo", {
        method: "POST",
      });
      await loadCourses();
      setCourseId(demo.course_id);
      setActiveAuditId(demo.audit_run_id);
      setMessage(demo.created ? "Демо-курс создан и уже проаудирован." : "Открыт существующий демо-курс.");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(event: React.FormEvent) {
    event.preventDefault();
    if (!courseId || !file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("document_type", documentType);
      if (moduleId) form.append("module_id", moduleId);
      const result = await api<CourseDocument & { duplicate: boolean }>(apiBase, `/courses/${courseId}/documents`, {
        method: "POST",
        body: form,
      });
      setFile(null);
      setMessage(result.duplicate ? "Этот файл уже был импортирован." : "Файл принят в обработку.");
      await loadCourse(courseId);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function importCanvas(event: React.FormEvent) {
    event.preventDefault();
    if (!canvasUrl || !canvasCourseId || !canvasToken) return;
    setBusy(true);
    setError(null);
    try {
      const imported = await api<{ course_id: number; documents_created: number; documents_updated: number; explicit_alignments_imported: number }>(
        apiBase,
        "/integrations/canvas/import",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_url: canvasUrl, canvas_course_id: Number(canvasCourseId), access_token: canvasToken }),
        },
      );
      setCanvasToken("");
      await loadCourses();
      setCourseId(imported.course_id);
      setMessage(`Canvas импортирован: новых документов ${imported.documents_created}, обновлено ${imported.documents_updated}, эталонных связей ${imported.explicit_alignments_imported}.`);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function startAudit() {
    await startAuditWithConfig({ min_relation_score: 0.22, top_k: 5 });
  }

  async function startCalibratedAudit() {
    if (canvasCalibration?.recommended_threshold == null || !activeAuditId) return;
    await startAuditWithConfig({
      min_relation_score: canvasCalibration.recommended_threshold,
      top_k: canvasCalibration.top_k,
      experiment_type: "canvas_threshold_validation",
      calibration_source_audit_id: activeAuditId,
    });
  }

  async function startAuditWithConfig(config: Record<string, unknown>) {
    if (!courseId) return;
    setBusy(true);
    setError(null);
    try {
      const started = await api<{ audit_run_id: number }>(apiBase, `/courses/${courseId}/audits`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      setActiveAuditId(started.audit_run_id);
      setAudit({ id: started.audit_run_id, status: "queued", config, metrics: { progress: 0, stage: "queued" } });
      setMessage("Аудит поставлен в очередь.");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function reviewFinding(findingId: number, nextStatus: Finding["status"]) {
    try {
      await api<Finding>(apiBase, `/findings/${findingId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus, reviewed_by: "teacher" }),
      });
      if (activeAuditId) await loadAuditResults(activeAuditId);
      if (courseId) setMlFeedback(await api<MlFeedbackSummary>(apiBase, `/courses/${courseId}/ml-feedback`));
      if (courseId) await refreshEvidencePreview(courseId);
    } catch (reason) {
      setError(String(reason));
    }
  }

  async function askCourseQuestion(event: React.FormEvent) {
    event.preventDefault();
    if (!courseId || !qaQuestion.trim()) return;
    setQaBusy(true);
    setError(null);
    try {
      const answer = await api<CourseAnswer>(apiBase, `/courses/${courseId}/qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: qaQuestion.trim(),
          language: "ru",
          top_k: 5,
          module_id: qaModuleId ? Number(qaModuleId) : null,
        }),
      });
      setQaHistory((current) => [answer, ...current]);
      setQaQuestion("");
      if (courseId) await refreshEvidencePreview(courseId);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setQaBusy(false);
    }
  }

  async function reviewCourseAnswer(answerId: number, status: "helpful" | "unhelpful") {
    setError(null);
    try {
      const reviewed = await api<CourseAnswer>(apiBase, `/qa/answers/${answerId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, reviewed_by: "teacher" }),
      });
      setQaHistory((current) => current.map((item) => item.id === answerId ? reviewed : item));
      if (courseId) setMlFeedback(await api<MlFeedbackSummary>(apiBase, `/courses/${courseId}/ml-feedback`));
      if (courseId) await refreshEvidencePreview(courseId);
    } catch (reason) {
      setError(String(reason));
    }
  }

  async function requestCopilot(findingId: number) {
    setCopilotBusy((current) => ({ ...current, [findingId]: true }));
    setError(null);
    try {
      const suggestion = await api<CopilotSuggestion>(apiBase, `/findings/${findingId}/copilot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ top_k: 5, language: "ru" }),
      });
      setCopilotSuggestions((current) => ({ ...current, [findingId]: suggestion }));
      setCopilotHistory((current) => ({ ...current, [findingId]: [suggestion, ...(current[findingId] || [])] }));
    } catch (reason) {
      setError(String(reason));
    } finally {
      setCopilotBusy((current) => ({ ...current, [findingId]: false }));
    }
  }

  async function reviewCopilot(suggestion: CopilotSuggestion, nextStatus: "accepted" | "rejected") {
    setCopilotBusy((current) => ({ ...current, [suggestion.finding_id]: true }));
    setError(null);
    try {
      await api<CopilotSuggestion>(apiBase, `/copilot/suggestions/${suggestion.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus, reviewed_by: "teacher" }),
      });
      const history = await api<CopilotSuggestion[]>(apiBase, `/findings/${suggestion.finding_id}/copilot`);
      setCopilotHistory((current) => ({ ...current, [suggestion.finding_id]: history }));
      if (history.length) setCopilotSuggestions((current) => ({ ...current, [suggestion.finding_id]: history[0] }));
      setMessage(nextStatus === "accepted" ? "Черновик Copilot принят преподавателем." : "Черновик Copilot отклонён.");
      if (courseId) setCanvasChangeSet(await api<CanvasChangeSet>(apiBase, `/courses/${courseId}/canvas-change-set`));
      if (courseId) setMlFeedback(await api<MlFeedbackSummary>(apiBase, `/courses/${courseId}/ml-feedback`));
      if (courseId) await refreshEvidencePreview(courseId);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setCopilotBusy((current) => ({ ...current, [suggestion.finding_id]: false }));
    }
  }

  function downloadAuditReport() {
    if (!activeAuditId) return;
    const anchor = document.createElement("a");
    anchor.href = `${apiBase}/audits/${activeAuditId}/report/download`;
    anchor.download = `course-audit-${activeAuditId}.json`;
    anchor.rel = "noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  function downloadCanvasChangeSet(format: "markdown" | "json") {
    if (!courseId) return;
    const anchor = document.createElement("a");
    anchor.href = `${apiBase}/courses/${courseId}/canvas-change-set/download?format=${format}`;
    anchor.download = `canvas-change-set-${courseId}.${format === "json" ? "json" : "md"}`;
    anchor.rel = "noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  function downloadMlFeedback() {
    if (!courseId) return;
    const anchor = document.createElement("a");
    anchor.href = `${apiBase}/courses/${courseId}/ml-feedback/download`;
    anchor.download = `course-ml-feedback-${courseId}.jsonl`;
    anchor.rel = "noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  async function runEvaluationProtocol() {
    if (!courseId) return;
    setEvaluationBusy(true);
    setError(null);
    try {
      const protocol = await api<EvaluationProtocol>(apiBase, `/courses/${courseId}/evaluation-protocols`, {
        method: "POST",
      });
      setEvaluationProtocols((current) => [protocol, ...current]);
      if (courseId) await refreshEvidencePreview(courseId);
      setMessage(protocol.status === "passed" ? "Протокол испытаний: все обязательные проверки пройдены." : "Протокол испытаний обнаружил несоответствия.");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setEvaluationBusy(false);
    }
  }

  function downloadEvaluationProtocol(protocolId: number, format: "markdown" | "json" = "markdown") {
    const anchor = document.createElement("a");
    anchor.href = `${apiBase}/evaluation-protocols/${protocolId}/download?format=${format}`;
    anchor.download = `evaluation-protocol-${protocolId}.${format === "json" ? "json" : "md"}`;
    anchor.rel = "noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  function downloadEvidencePack() {
    if (!courseId) return;
    const anchor = document.createElement("a");
    anchor.href = `${apiBase}/courses/${courseId}/evidence-pack/download`;
    anchor.download = `course-evidence-pack-${courseId}.zip`;
    anchor.rel = "noreferrer";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  function copilotMarkdown(suggestion: CopilotSuggestion) {
    const sources = suggestion.citations.map((item) =>
      `- [${item.source_id}] ${item.document_title}${item.source_url ? ` — ${item.source_url}` : ""}\n  > ${item.quote}`
    ).join("\n");
    return `# ${suggestion.title}\n\n${suggestion.draft}\n\n**Целевой уровень Блума:** ${suggestion.target_bloom_level}\n\n**Обоснование:** ${suggestion.rationale}\n\n## Источники\n${sources || "Контекст курса недостаточен."}`;
  }

  async function copyCopilot(suggestion: CopilotSuggestion) {
    const markdown = copilotMarkdown(suggestion);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(markdown);
      setMessage("Черновик Copilot скопирован в Markdown.");
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = markdown;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      document.body.removeChild(textarea);
      if (copied) setMessage("Черновик Copilot скопирован в Markdown.");
      else setError("Браузер не разрешил доступ к буферу обмена. Используйте скачивание JSON.");
    }
  }

  function downloadCopilot(suggestion: CopilotSuggestion) {
    const blob = new Blob([JSON.stringify(suggestion, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `copilot-finding-${suggestion.finding_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const summary = audit?.metrics?.summary || {};
  const latestEvaluation = evaluationProtocols[0] || null;
  const filteredFindings = findings.filter((item) =>
    (severity === "all" || item.severity === severity) && (status === "all" || item.status === status)
  );
  const assessmentById = useMemo(() => new Map(assessments.map((item) => [item.id, item])), [assessments]);
  const edgesByObjective = useMemo(() => {
    const map = new Map<number, Alignment[]>();
    alignment.forEach((edge) => map.set(edge.source_id, [...(map.get(edge.source_id) || []), edge]));
    return map;
  }, [alignment]);

  return (
    <section className={styles.root}>
      <div className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>COURSE QUALITY AUDITOR</div>
          <h1>Проверка согласованности курса</h1>
          <p>Цели → материалы → задания → доказуемые рекомендации преподавателю.</p>
        </div>
        {course && (
          <button
            className={styles.primary}
            onClick={startAudit}
            disabled={busy || !documents.length || documents.some((item) => item.status !== "ready")}
            title={!documents.length ? "Сначала добавьте материалы курса" : undefined}
          >
            Запустить аудит
          </button>
        )}
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {message && (
        <div className={styles.message} role="status">
          <span>{message}</span>
          <button type="button" onClick={() => setMessage(null)} aria-label="Закрыть уведомление">×</button>
        </div>
      )}

      <div className={styles.workspace}>
        <aside className={styles.sidebar}>
          <form className={styles.createForm} onSubmit={createCourse}>
            <strong>Новый курс</strong>
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Название курса" />
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Краткое описание" rows={2} />
            <button className={styles.secondary} disabled={busy || !title.trim()}>Создать</button>
          </form>
          <button className={styles.demoButton} onClick={createDemoCourse} disabled={busy}>Попробовать демо ✦</button>
          <details className={styles.canvasImport}>
            <summary>Импорт из Canvas</summary>
            <form onSubmit={importCanvas}>
              <input type="url" value={canvasUrl} onChange={(event) => setCanvasUrl(event.target.value)} placeholder="https://canvas.example.edu" />
              <input type="number" min="1" value={canvasCourseId} onChange={(event) => setCanvasCourseId(event.target.value)} placeholder="Canvas course ID" />
              <input type="password" autoComplete="off" value={canvasToken} onChange={(event) => setCanvasToken(event.target.value)} placeholder="Access token (не сохраняется)" />
              <button className={styles.secondary} disabled={busy || !canvasUrl || !canvasCourseId || !canvasToken}>Импортировать</button>
            </form>
          </details>
          <div className={styles.courseList}>
            {courses.map((item) => (
              <button key={item.id} className={courseId === item.id ? styles.courseActive : styles.courseButton} onClick={() => setCourseId(item.id)}>
                <span>{item.title}</span><small>{item.source_type === "manual" ? "Создан вручную" : item.source_type === "canvas" ? "Canvas" : item.source_type}</small>
              </button>
            ))}
          </div>
        </aside>

        <div className={styles.content}>
          {!course ? (
            <div className={styles.empty}>
              <span className={styles.emptyEyebrow}>Быстрый старт</span>
              <h2>Проверьте курс за несколько минут</h2>
              <p>Откройте готовый пример или создайте свой курс в панели слева.</p>
              <button className={styles.primary} onClick={createDemoCourse} disabled={busy}>Открыть демо-курс</button>
            </div>
          ) : (
            <>
              <div className={styles.courseHeader}>
                <div><h2>{course.title}</h2><p>{course.description || "Описание не заполнено"}</p></div>
                <div className={styles.courseActions}>
                  <div className={styles.auditStatus} data-status={audit?.status || "none"}>
                    {audit ? `${audit.status === "done" ? "Аудит завершён" : audit.status === "running" ? "Аудит выполняется" : audit.status === "failed" ? "Ошибка аудита" : "Аудит в очереди"} · ${audit.metrics?.progress || 0}%` : "Аудит ещё не запускался"}
                  </div>
                  {activeAuditId && <button className={styles.secondary} onClick={downloadAuditReport}>Скачать отчёт</button>}
                  {evidencePack && (
                    <button className={styles.evidenceButton} onClick={downloadEvidencePack}>Пакет проекта · {evidencePack.completeness_score}%</button>
                  )}
                </div>
              </div>

              <form className={styles.upload} onSubmit={uploadDocument}>
                <label className={styles.filePicker}>
                  <input type="file" accept=".txt,.md,.pdf,.csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
                  <span>Выбрать файл</span>
                  <small>{file?.name || "TXT, MD, PDF или CSV"}</small>
                </label>
                <select value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
                  <option value="unknown">Определить автоматически</option>
                  <option value="learning_objectives">Учебные цели</option>
                  <option value="lecture_material">Лекция / материал</option>
                  <option value="reading">Чтение</option>
                  <option value="assignment">Задание</option>
                  <option value="quiz">Тест</option>
                  <option value="exam">Экзамен</option>
                </select>
                {course.modules?.length ? (
                  <select value={moduleId} onChange={(event) => setModuleId(event.target.value)}>
                    <option value="">Без модуля</option>
                    {course.modules.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}
                  </select>
                ) : null}
                <button className={styles.secondary} disabled={busy || !file}>Импортировать</button>
              </form>

              <div className={styles.documentStrip}>
                {documents.map((item) => <span key={item.id} data-status={item.status}>{item.title} · {item.status === "ready" ? "готов" : item.status}</span>)}
                {!documents.length && <span>Добавьте цели, материалы и задания курса.</span>}
              </div>

              <div className={styles.tabs} role="tablist" aria-label="Разделы аудита курса">
                {(["overview", "matrix", "findings", "qa"] as const).map((item) => (
                  <button key={item} role="tab" aria-selected={view === item} className={view === item ? styles.tabActive : styles.tab} onClick={() => setView(item)}>
                    {item === "overview" ? "Обзор" : item === "matrix" ? "Матрица" : item === "qa" ? "Вопросы к курсу" : `Проблемы (${findings.length})`}
                  </button>
                ))}
              </div>

              {view === "overview" && (
                <div className={styles.overview}>
                  <div className={styles.kpis}>
                    <Kpi label="Учебные цели" value={summary.objectives_total ?? objectives.length} />
                    <Kpi label="Покрыты материалами" value={`${Math.round((summary.objective_material_coverage || 0) * 100)}%`} />
                    <Kpi label="Проверяются заданиями" value={`${Math.round((summary.objective_assessment_coverage || 0) * 100)}%`} />
                    <Kpi label="Проблемы высокой важности" value={summary.high_severity_findings ?? findings.filter((item) => item.severity === "high").length} tone="danger" />
                  </div>
                  <section className={styles.evaluationProtocol} data-status={latestEvaluation?.status || "not-run"}>
                    <div className={styles.comparisonHead}>
                      <div><span>EVALUATION PROTOCOL</span><h3>Программа и результаты испытаний</h3></div>
                      <small>{latestEvaluation ? `#${latestEvaluation.id} · ${latestEvaluation.status}` : "ещё не запускались"}</small>
                    </div>
                    {!latestEvaluation ? (
                      <div className={styles.evaluationEmpty}>
                        <p>Воспроизводимо проверяет retrieval, отказ на неподдержанные вопросы, assessment guard, опору citations и offline p95.</p>
                        <button onClick={runEvaluationProtocol} disabled={evaluationBusy}>Сформировать первый протокол</button>
                      </div>
                    ) : (
                      <>
                        <div className={styles.evaluationChecks}>
                          {latestEvaluation.checks.map((check) => (
                            <div key={check.check_id} data-status={check.passed === true ? "passed" : check.passed === false ? "failed" : "not-run"}>
                              <span>{check.label}</span>
                              <strong>{check.value == null ? "—" : typeof check.value === "number" && check.value <= 1 ? `${Math.round(check.value * 100)}%` : check.value}</strong>
                              <small>{check.passed === true ? "PASS" : check.passed === false ? "FAIL" : "NOT RUN"} · {check.operator} {check.threshold}</small>
                            </div>
                          ))}
                        </div>
                        <div className={styles.evaluationMeta}>
                          <span>{latestEvaluation.dataset_name}</span>
                          <code>sha256:{latestEvaluation.dataset_hash.slice(0, 12)}…</code>
                          <span>{Math.round(latestEvaluation.duration_ms)} ms</span>
                        </div>
                        {latestEvaluation.error && <p className={styles.evaluationError}>{latestEvaluation.error}</p>}
                        <div className={styles.changeSetActions}>
                          <button onClick={() => downloadEvaluationProtocol(latestEvaluation.id, "markdown")}>Скачать протокол Markdown</button>
                          <button onClick={() => downloadEvaluationProtocol(latestEvaluation.id, "json")}>JSON</button>
                          <button onClick={runEvaluationProtocol} disabled={evaluationBusy}>Повторить испытания</button>
                        </div>
                      </>
                    )}
                  </section>
                  {evidencePack && (
                    <section className={styles.evidencePack} data-ready={evidencePack.ready_for_submission}>
                      <div className={styles.comparisonHead}>
                        <div><span>SUBMISSION READINESS</span><h3>Пакет доказательств проекта</h3></div>
                        <strong>{evidencePack.completeness_score}%</strong>
                      </div>
                      <div className={styles.evidenceProgress}><i style={{ width: `${evidencePack.completeness_score}%` }} /></div>
                      <div className={styles.evidenceArtifacts}>
                        {evidencePack.artifacts.map((artifact) => (
                          <div key={artifact.name} data-included={artifact.included}>
                            <span>{artifact.included ? "✓" : "○"}</span>
                            <div><strong>{artifact.name}</strong><small>{artifact.description}</small></div>
                          </div>
                        ))}
                      </div>
                      {evidencePack.missing.length > 0 && (
                        <details className={styles.evidenceMissing}>
                          <summary>Что ещё повысит готовность ({evidencePack.missing.length})</summary>
                          {evidencePack.missing.map((item) => <p key={item}>{item}</p>)}
                        </details>
                      )}
                      {evidencePack.warnings.map((warning) => <p className={styles.evidenceWarning} key={warning}>{warning}</p>)}
                      <div className={styles.evidenceActions}>
                        <button onClick={downloadEvidencePack}>Скачать Evidence Pack ZIP</button>
                        <span>{evidencePack.ready_for_submission ? "Основные продуктовые доказательства собраны" : "Пакет доступен, но содержит пробелы"}</span>
                      </div>
                    </section>
                  )}
                  <div className={styles.auditHistory}>
                    <h3>История аудитов</h3>
                    {audits.map((item) => (
                      <button key={item.id} onClick={() => { setActiveAuditId(item.id); loadAuditResults(item.id).catch((reason) => setError(String(reason))); }}>
                        <span>Audit #{item.id}{item.config?.experiment_type === "canvas_threshold_validation" ? " · threshold validation" : ""}</span>
                        <span>{item.status} · t={Number(item.config?.min_relation_score ?? 0.22).toFixed(2)}</span>
                      </button>
                    ))}
                  </div>
                  {auditComparison?.available && auditComparison.before && auditComparison.after && (
                    <section className={styles.auditComparison}>
                      <div className={styles.comparisonHead}>
                        <div><span>CONTINUOUS IMPROVEMENT</span><h3>Изменения после правок</h3></div>
                        <small>Audit #{auditComparison.before.audit_run_id} → #{auditComparison.after.audit_run_id}</small>
                      </div>
                      <div className={styles.comparisonGrid}>
                        <ComparisonMetric label="Покрытие материалами" value={auditComparison.delta.objective_material_coverage || 0} percentage positiveIsGood />
                        <ComparisonMetric label="Покрытие заданиями" value={auditComparison.delta.objective_assessment_coverage || 0} percentage positiveIsGood />
                        <ComparisonMetric label="Всего findings" value={auditComparison.delta.findings_total || 0} />
                        <ComparisonMetric label="High severity" value={auditComparison.delta.high_severity_findings || 0} />
                      </div>
                      <div className={styles.findingChurn}>
                        <span>Исправлено: <strong>{auditComparison.removed_findings}</strong></span>
                        <span>Новых: <strong>{auditComparison.new_findings}</strong></span>
                        <span>Сохранилось: <strong>{auditComparison.persisted_findings}</strong></span>
                      </div>
                    </section>
                  )}
                  {canvasAlignment?.available && (
                    <section className={styles.canvasEvaluation}>
                      <div className={styles.comparisonHead}>
                        <div><span>CANVAS GROUND TRUTH</span><h3>Совпадение ML-связей с разметкой преподавателя</h3></div>
                        <small>{canvasAlignment.true_positives} совпало из {canvasAlignment.explicit_pairs}</small>
                      </div>
                      <div className={styles.comparisonGrid}>
                        <Kpi label="F1" value={`${Math.round((canvasAlignment.f1 || 0) * 100)}%`} />
                        <Kpi label="Precision" value={`${Math.round((canvasAlignment.precision || 0) * 100)}%`} />
                        <Kpi label="Recall" value={`${Math.round((canvasAlignment.recall || 0) * 100)}%`} />
                        <Kpi label="Покрытие сопоставления" value={`${Math.round(canvasAlignment.mapping_coverage * 100)}%`} />
                      </div>
                      <div className={styles.findingChurn}>
                        <span>Canvas: <strong>{canvasAlignment.explicit_pairs}</strong></span>
                        <span>ML: <strong>{canvasAlignment.inferred_pairs}</strong></span>
                        <span>Пропущено ML: <strong>{canvasAlignment.false_negatives}</strong></span>
                        <span>Лишних ML-связей: <strong>{canvasAlignment.false_positives}</strong></span>
                      </div>
                      {(canvasAlignment.missing_in_inference.length > 0 || canvasAlignment.inferred_only.length > 0 || canvasAlignment.unmapped_explicit.length > 0) && (
                        <details className={styles.canvasDiscrepancies}>
                          <summary>Разобрать расхождения</summary>
                          {canvasAlignment.missing_in_inference.map((item) => <p key={`missing-${item.outcome_external_id}-${item.assignment_external_id}`}><strong>ML не нашла:</strong> {item.outcome_text || `Outcome ${item.outcome_external_id}`} → {item.assignment_title || `Assignment ${item.assignment_external_id}`}</p>)}
                          {canvasAlignment.inferred_only.map((item) => <p key={`extra-${item.outcome_external_id}-${item.assignment_external_id}`}><strong>Только ML:</strong> {item.outcome_text || `Outcome ${item.outcome_external_id}`} → {item.assignment_title || `Assignment ${item.assignment_external_id}`}</p>)}
                          {canvasAlignment.unmapped_explicit.map((item) => <p key={`unmapped-${item.outcome_external_id}-${item.assignment_external_id}`}><strong>Не извлечено:</strong> Canvas Outcome {item.outcome_external_id} → Assignment {item.assignment_external_id}</p>)}
                        </details>
                      )}
                      {canvasCalibration?.available && canvasCalibration.current && (
                        <section className={styles.thresholdCalibration}>
                          <div className={styles.calibrationSummary}>
                            <div>
                              <span>Текущий порог</span>
                              <strong>{canvasCalibration.current_threshold?.toFixed(2)}</strong>
                              <small>F1 {Math.round(canvasCalibration.current.f1 * 100)}%</small>
                            </div>
                            <div data-recommended="true">
                              <span>Диагностический порог</span>
                              <strong>{canvasCalibration.recommended_threshold?.toFixed(2) ?? "—"}</strong>
                              <small>F1 {Math.round((canvasCalibration.recommended?.f1 || 0) * 100)}%</small>
                            </div>
                            <div>
                              <span>Размеченных связей</span>
                              <strong>{canvasCalibration.labeled_positive_pairs}</strong>
                              <small>{canvasCalibration.comparable_candidates} кандидатов</small>
                            </div>
                          </div>
                          <div className={styles.thresholdCurve} aria-label="F1 по порогам">
                            {canvasCalibration.curve.map((point) => (
                              <div key={point.threshold} title={`Порог ${point.threshold.toFixed(2)} · F1 ${Math.round(point.f1 * 100)}%`}>
                                <i style={{ height: `${Math.max(3, point.f1 * 64)}px` }} data-best={point.threshold === canvasCalibration.recommended_threshold} />
                                <small>{Math.round(point.threshold * 100) % 25 === 0 ? point.threshold.toFixed(2) : ""}</small>
                              </div>
                            ))}
                          </div>
                          <p className={styles.calibrationCaveat} data-reliable={canvasCalibration.reliable}>{canvasCalibration.caveat}</p>
                          {canvasCalibration.recommended_threshold != null && (
                            <button className={styles.calibrationButton} onClick={startCalibratedAudit} disabled={busy}>
                              Запустить A/B-аудит с порогом {canvasCalibration.recommended_threshold.toFixed(2)}
                            </button>
                          )}
                        </section>
                      )}
                    </section>
                  )}
                  {canvasChangeSet?.available && canvasChangeSet.accepted_suggestions > 0 && (
                    <section className={styles.changeSet}>
                      <div className={styles.comparisonHead}>
                        <div><span>CANVAS HANDOFF</span><h3>Принятые исправления готовы к переносу</h3></div>
                        <small>{canvasChangeSet.ready_items} из {canvasChangeSet.accepted_suggestions} готовы</small>
                      </div>
                      <div className={styles.changeSetItems}>
                        {canvasChangeSet.items.map((item) => (
                          <article key={item.suggestion_id} data-ready={item.ready_for_canvas}>
                            <div><strong>{item.title}</strong><span>{item.api_method} · {item.operation}</span></div>
                            <code>{item.api_path}</code>
                            <small>{item.module_title || "Модуль не указан"} · confidence {Math.round(item.confidence * 100)}%</small>
                            {item.warning && <p>{item.warning}</p>}
                          </article>
                        ))}
                      </div>
                      <div className={styles.changeSetActions}>
                        <button onClick={() => downloadCanvasChangeSet("markdown")}>Скачать пакет для преподавателя</button>
                        <button onClick={() => downloadCanvasChangeSet("json")}>Экспорт JSON</button>
                        <small>Read-only preview: сервис не изменяет Canvas.</small>
                      </div>
                    </section>
                  )}
                  {mlFeedback && mlFeedback.total_examples > 0 && (
                    <section className={styles.mlFeedback}>
                      <div className={styles.comparisonHead}>
                        <div><span>HUMAN-IN-THE-LOOP</span><h3>Размеченные примеры для улучшения ML</h3></div>
                        <small>{mlFeedback.total_examples} examples</small>
                      </div>
                      <div className={styles.feedbackMetrics}>
                        <div><strong>{mlFeedback.positive_examples}</strong><span>положительных</span></div>
                        <div><strong>{mlFeedback.negative_examples}</strong><span>отрицательных</span></div>
                        {Object.entries(mlFeedback.by_type).map(([type, count]) => <div key={type}><strong>{count}</strong><span>{type}</span></div>)}
                      </div>
                      {mlFeedback.warnings.map((warning) => <p key={warning}>{warning}</p>)}
                      <button className={styles.feedbackExport} onClick={downloadMlFeedback}>Скачать обезличенный JSONL</button>
                    </section>
                  )}
                </div>
              )}

              {view === "matrix" && (
                <div className={styles.matrix}>
                  <div className={styles.matrixHead}><span>Учебная цель</span><span>Материалы</span><span>Задания</span></div>
                  {objectives.map((objective) => {
                    const edges = edgesByObjective.get(objective.id) || [];
                    const materialEdges = edges.filter((edge) => edge.relation_type === "teaches");
                    const assessmentEdges = edges.filter((edge) => edge.relation_type === "assesses");
                    return (
                      <div className={styles.matrixRow} key={objective.id}>
                        <div><strong>{objective.text}</strong><small>{objective.top_bloom_levels.join(" + ")} · {Math.round(objective.confidence * 100)}%</small></div>
                        <div>{materialEdges.length ? materialEdges.map((edge) => <span className={styles.edge} key={edge.id}>{Math.round(edge.score * 100)}%</span>) : <span className={styles.gap}>Нет покрытия</span>}</div>
                        <div>{assessmentEdges.length ? assessmentEdges.map((edge) => <span className={styles.edge} key={edge.id}>{assessmentById.get(edge.target_id)?.text || `Задание #${edge.target_id}`} · {Math.round(edge.score * 100)}%</span>) : <span className={styles.gap}>Не проверяется</span>}</div>
                      </div>
                    );
                  })}
                  {!objectives.length && <div className={styles.empty}>После аудита здесь появится alignment matrix.</div>}
                </div>
              )}

              {view === "qa" && (
                <div className={styles.courseQa}>
                  <div className={styles.qaIntro}>
                    <div><span>COURSE RAG</span><h3>Спросите по материалам курса</h3></div>
                    <p>Ответ строится только по импортированным документам. Любое утверждение сопровождается проверяемым источником.</p>
                  </div>
                  <form className={styles.qaForm} onSubmit={askCourseQuestion}>
                    <textarea value={qaQuestion} onChange={(event) => setQaQuestion(event.target.value)} rows={3} maxLength={1000} placeholder="Например: где объясняется временная сложность quicksort?" />
                    <div>
                      <select value={qaModuleId} onChange={(event) => setQaModuleId(event.target.value)}>
                        <option value="">Весь курс</option>
                        {course.modules?.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                      </select>
                      <button className={styles.primary} disabled={qaBusy || !qaQuestion.trim()}>{qaBusy ? "Ищу источники…" : "Спросить"}</button>
                    </div>
                  </form>
                  {!qaHistory.length && <div className={styles.qaEmpty}>История вопросов пока пуста.</div>}
                  <div className={styles.qaHistory}>
                    {qaHistory.map((item) => (
                      <article key={item.id} data-empty={item.insufficient_context}>
                        <header><strong>{item.question}</strong><span>{Math.round(item.confidence * 100)}% · {item.generation_provider}</span></header>
                        <p>{item.answer}</p>
                        {item.citations.length > 0 && (
                          <details open>
                            <summary>Источники ({item.citations.length})</summary>
                            {item.citations.map((citation) => (
                              <div className={styles.qaSource} key={`${item.id}-${citation.source_id}`}>
                                <div><strong>[{citation.source_id}] {citation.document_title}</strong><small>{citation.module_title || "Без модуля"} · {Math.round(citation.score * 100)}%</small></div>
                                <blockquote>{citation.quote}</blockquote>
                                {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Открыть источник в Canvas ↗</a>}
                              </div>
                            ))}
                          </details>
                        )}
                        {item.insufficient_context && <small className={styles.qaWarning}>Ответ не сгенерирован: retrieval не нашёл достаточного подтверждения.</small>}
                        <footer className={styles.qaFeedback}>
                          <span data-status={item.feedback_status}>{item.feedback_status === "unreviewed" ? "Оцените ответ" : item.feedback_status === "helpful" ? "Полезный ответ" : "Нужна доработка"}</span>
                          <button onClick={() => reviewCourseAnswer(item.id, "helpful")} disabled={item.feedback_status === "helpful"}>Полезно</button>
                          <button onClick={() => reviewCourseAnswer(item.id, "unhelpful")} disabled={item.feedback_status === "unhelpful"}>Не полезно</button>
                        </footer>
                      </article>
                    ))}
                  </div>
                </div>
              )}

              {view === "findings" && (
                <div>
                  <div className={styles.filters}>
                    <select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">Все уровни</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
                    <select value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">Все статусы</option><option value="new">Новые</option><option value="confirmed">Подтверждённые</option><option value="rejected">Отклонённые</option><option value="resolved">Исправленные</option></select>
                  </div>
                  <div className={styles.findings}>
                    {filteredFindings.map((item) => {
                      const copilot = copilotSuggestions[item.id];
                      const history = copilotHistory[item.id] || [];
                      return (
                      <article className={styles.finding} key={item.id} data-severity={item.severity}>
                        <header><span>{FINDING_LABELS[item.finding_type] || item.finding_type}</span><span>{item.severity} · {Math.round(item.confidence * 100)}%</span></header>
                        <h3>{item.title}</h3><p>{item.description}</p>
                        <details><summary>Доказательства ({item.evidence.length})</summary>{item.evidence.map((evidence, index) => <blockquote key={index}>{evidence.quote || JSON.stringify(evidence)}</blockquote>)}</details>
                        <div className={styles.recommendation}><strong>Рекомендация:</strong> {item.recommendation}</div>
                        <section className={styles.copilot}>
                          <div className={styles.copilotHead}>
                            <div><span className={styles.copilotEyebrow}>RAG COPILOT</span><strong>Исправление на основе материалов курса</strong></div>
                            <button
                              className={styles.copilotButton}
                              onClick={() => requestCopilot(item.id)}
                              disabled={copilotBusy[item.id] || item.status !== "confirmed"}
                              title={item.status === "confirmed" ? undefined : "Сначала подтвердите finding"}
                            >
                              {item.status !== "confirmed"
                                ? "Сначала подтвердите"
                                : copilotBusy[item.id]
                                  ? "Ищу контекст…"
                                  : copilot
                                    ? "Сгенерировать заново"
                                    : "Предложить исправление"}
                            </button>
                          </div>
                          {copilot && (
                            <div className={styles.copilotResult} data-empty={copilot.insufficient_context || undefined}>
                              <div className={styles.copilotMeta}>
                                <span>{COPILOT_ACTION_LABELS[copilot.action_type]}</span>
                                <span>Bloom: {copilot.target_bloom_level}</span>
                                <span>{Math.round(copilot.confidence * 100)}%</span>
                                <span data-status={copilot.status}>{copilot.status === "accepted" ? "Принято" : copilot.status === "rejected" ? "Отклонено" : "Черновик"}</span>
                              </div>
                              <h4>{copilot.title}</h4>
                              <div className={styles.copilotDraft}>{copilot.draft}</div>
                              <p><strong>Почему:</strong> {copilot.rationale}</p>
                              {!!copilot.citations.length && (
                                <details className={styles.copilotSources} open>
                                  <summary>Источники курса ({copilot.citations.length})</summary>
                                  {copilot.citations.map((citation) => (
                                    <article key={citation.source_id}>
                                      <div><strong>[{citation.source_id}] {citation.document_title}</strong><span>{Math.round(citation.score * 100)}%</span></div>
                                      {citation.module_title && <small>{citation.module_title}</small>}
                                      <blockquote>{citation.quote}</blockquote>
                                      {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Открыть источник в Canvas ↗</a>}
                                    </article>
                                  ))}
                                </details>
                              )}
                              <div className={styles.copilotActions}>
                                <button onClick={() => copyCopilot(copilot)} disabled={copilot.insufficient_context}>Скопировать Markdown</button>
                                <button onClick={() => downloadCopilot(copilot)}>Скачать JSON</button>
                                {copilot.status !== "accepted" && <button onClick={() => reviewCopilot(copilot, "accepted")} disabled={copilot.insufficient_context || copilotBusy[item.id]}>Принять</button>}
                                {copilot.status !== "rejected" && <button onClick={() => reviewCopilot(copilot, "rejected")} disabled={copilotBusy[item.id]}>Отклонить</button>}
                                <small>{copilot.generation_provider}{copilot.generation_model ? ` · ${copilot.generation_model}` : ""}</small>
                              </div>
                              {history.length > 1 && (
                                <details className={styles.copilotHistory}>
                                  <summary>История Copilot ({history.length})</summary>
                                  {history.map((entry) => <div key={entry.id}><span>#{entry.id} · {entry.status}</span><small>{entry.created_at ? new Date(entry.created_at).toLocaleString("ru-RU") : ""}</small></div>)}
                                </details>
                              )}
                              <div className={styles.copilotWarning}>Черновик сформирован ИИ и требует проверки преподавателем.</div>
                            </div>
                          )}
                        </section>
                        <footer><span className={styles.status}>{item.status}</span>{item.status === "new" && <><button onClick={() => reviewFinding(item.id, "confirmed")}>Подтвердить</button><button onClick={() => reviewFinding(item.id, "rejected")}>Отклонить</button></>}{item.status === "confirmed" && <button onClick={() => reviewFinding(item.id, "resolved")}>Отметить исправленным</button>}</footer>
                      </article>
                    )})}
                    {!filteredFindings.length && <div className={styles.empty}>Нет findings с выбранными фильтрами.</div>}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Kpi({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return <div className={styles.kpi} data-tone={tone}><strong>{value}</strong><span>{label}</span></div>;
}

function ComparisonMetric({ label, value, percentage, positiveIsGood = false }: { label: string; value: number; percentage?: boolean; positiveIsGood?: boolean }) {
  const good = positiveIsGood ? value > 0 : value < 0;
  const bad = positiveIsGood ? value < 0 : value > 0;
  const rendered = `${value > 0 ? "+" : ""}${percentage ? `${Math.round(value * 100)} п.п.` : value}`;
  return <div className={styles.comparisonMetric} data-tone={good ? "good" : bad ? "bad" : "neutral"}><strong>{rendered}</strong><span>{label}</span></div>;
}
