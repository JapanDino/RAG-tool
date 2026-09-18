import type { GetServerSideProps } from "next";

type CanvasSimulatorProps = {
  ltiLaunchUrl?: string | null;
  simulatorActor?: SimulatorActor;
  simulatorLaunchState?: "ready" | "unavailable" | "preview";
};

type SimulatorActor = "learner" | "instructor";

const FIXTURE_IDS = new Set(["demo-ai", "demo-review"]);
const SIMULATOR_ACTORS = new Set<SimulatorActor>(["learner", "instructor"]);
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1"]);

function simulatorBase() {
  const rawBase = process.env.CANVAS_SIMULATOR_LTI_BASE_URL || "http://localhost:8000";
  try {
    const base = new URL(rawBase);
    if (
      base.protocol !== "http:"
      || base.username
      || base.password
      || !LOOPBACK_HOSTS.has(base.hostname)
      || !["", "/"].includes(base.pathname)
      || base.search
      || base.hash
    ) return null;
    return base.origin;
  } catch {
    return null;
  }
}

function exactResolvedLaunch(value: unknown, base: string) {
  if (typeof value !== "string" || value.length > 2000) return null;
  try {
    const launch = new URL(value);
    if (
      launch.origin !== base
      || launch.pathname !== "/integrations/lti/development/start"
      || launch.username
      || launch.password
      || launch.hash
      || !launch.searchParams.get("registration_id")
      || !launch.searchParams.get("subject")
    ) return null;
    return launch.toString();
  } catch {
    return null;
  }
}

async function launchUrlForCourse(courseId: string | undefined, actor: SimulatorActor) {
  if (!courseId || !FIXTURE_IDS.has(courseId)) {
    return { url: null, state: "unavailable" as const };
  }
  const base = simulatorBase();
  if (!base) return { url: null, state: "unavailable" as const };
  try {
    const response = await fetch(
      `${base}/integrations/lti/development/simulator/${encodeURIComponent(courseId)}?actor=${actor}`,
      {
        headers: { Accept: "application/json" },
        signal: AbortSignal.timeout(2500),
      }
    );
    if (!response.ok) return { url: null, state: "unavailable" as const };
    const payload = await response.json() as { launch_url?: unknown };
    const url = exactResolvedLaunch(payload.launch_url, base);
    return url
      ? { url, state: "ready" as const }
      : { url: null, state: "unavailable" as const };
  } catch {
    return { url: null, state: "unavailable" as const };
  }
}

export const canvasSimulatorServerProps: GetServerSideProps<CanvasSimulatorProps> = async (context) => {
  const enabled = process.env.CANVAS_SIMULATOR_ENABLED === "true";
  const syntheticOnly = process.env.CANVAS_SIMULATOR_DATA_MODE === "synthetic";
  const safeEnvironment = process.env.APP_ENV !== "production";

  if (!enabled || !syntheticOnly || !safeEnvironment) {
    return { notFound: true };
  }

  const rawCourseId = context.params?.courseId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;
  const rawActor = context.query.actor;
  const actorValue = Array.isArray(rawActor) ? rawActor[0] : rawActor;
  if (actorValue && !SIMULATOR_ACTORS.has(actorValue as SimulatorActor)) {
    return { notFound: true };
  }
  const simulatorActor = (actorValue || "learner") as SimulatorActor;
  const rawPreview = context.query.preview;
  const previewValue = Array.isArray(rawPreview) ? rawPreview[0] : rawPreview;
  const resolution = previewValue === "1" && simulatorActor === "learner"
    ? { url: null, state: "preview" as const }
    : await launchUrlForCourse(courseId, simulatorActor);
  return {
    props: {
      ltiLaunchUrl: resolution.url,
      simulatorActor,
      simulatorLaunchState: resolution.state,
    },
  };
};
