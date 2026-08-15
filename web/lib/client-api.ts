export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type ValidationIssue = {loc?: Array<string | number>; msg?: string};

function errorMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue: ValidationIssue) => {
        if (!issue?.msg) return null;
        const field = issue.loc?.at(-1);
        return field ? `${field}: ${issue.msg}` : issue.msg;
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return "Yêu cầu không thành công";
}

let refreshRequest: Promise<boolean> | null = null;

function refreshSession() {
  if (!refreshRequest) {
    refreshRequest = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "include",
      signal: AbortSignal.timeout(10_000),
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshRequest = null;
      });
  }
  return refreshRequest;
}

function mayRefresh(path: string) {
  return ![
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
  ].includes(path);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers:
      init.body instanceof FormData
        ? init.headers
        : {"Content-Type": "application/json", ...init.headers},
    signal: init.signal ?? AbortSignal.timeout(20_000),
  });
  if (response.status === 401 && retry && mayRefresh(path)) {
    if (await refreshSession()) return apiFetch<T>(path, init, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as {detail?: unknown} | null;
    throw new ApiError(response.status, errorMessage(body?.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
