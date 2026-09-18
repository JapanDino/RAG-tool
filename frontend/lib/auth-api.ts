export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

type SessionContext = { csrf_token: string };

export const SESSION_ENDED_EVENT = "rag:lti-session-ended";

let sessionCsrf: string | null = null;
let sessionCsrfRequest: Promise<string> | null = null;

function signalSessionEnded() {
  clearSessionCsrf();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SESSION_ENDED_EVENT));
  }
}

function isUnsafe(method: string) {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

async function responseMessage(response: Response) {
  let message = `Не удалось выполнить запрос (${response.status}).`;
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string") message = detail;
    if (typeof detail?.message === "string") message = detail.message;
    if (typeof payload?.error?.message === "string") message = payload.error.message;
  } catch {
    // Keep the safe status-based message for non-JSON responses.
  }
  return message;
}

async function loadSessionCsrf(apiBase: string) {
  if (sessionCsrf) return sessionCsrf;
  if (!sessionCsrfRequest) {
    sessionCsrfRequest = fetch(`${apiBase}/identity/session`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        if (!response.ok) {
          if (response.status === 401) signalSessionEnded();
          throw new ApiRequestError(await responseMessage(response), response.status);
        }
        const context = (await response.json()) as SessionContext;
        sessionCsrf = context.csrf_token;
        return context.csrf_token;
      })
      .finally(() => {
        sessionCsrfRequest = null;
      });
  }
  return sessionCsrfRequest;
}

export function clearSessionCsrf() {
  sessionCsrf = null;
  sessionCsrfRequest = null;
}

export async function authenticatedJson<T>(
  apiBase: string,
  path: string,
  identity: string,
  init?: RequestInit
): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (identity) headers.set("X-Dev-User", identity);
  if (init?.body) headers.set("Content-Type", "application/json");
  const writeKey = process.env.NEXT_PUBLIC_API_WRITE_KEY || "";
  if (writeKey && isUnsafe(method)) headers.set("X-API-Key", writeKey);
  if (!identity && isUnsafe(method)) {
    headers.set("X-CSRF-Token", await loadSessionCsrf(apiBase));
  }

  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    if (response.status === 401 && !identity) signalSessionEnded();
    throw new ApiRequestError(await responseMessage(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
