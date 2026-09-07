export const publicApiBase = "";

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

export async function apiFetch<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const response = await fetch(`${publicApiBase}${path}`, {
    ...init,
    credentials: "include",
    headers: init.body instanceof FormData ? init.headers : {"Content-Type": "application/json", ...init.headers},
  });
  if (response.status === 401 && retry && path !== "/api/auth/refresh") {
    const refreshed = await fetch(`${publicApiBase}/api/auth/refresh`, {method: "POST", credentials: "include"});
    if (refreshed.ok) return apiFetch<T>(path, init, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as {detail?: unknown} | null;
    throw new ApiError(response.status, errorMessage(body?.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
