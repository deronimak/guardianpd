const TOKEN_KEY = "orbit_admin_token";
const ROLE_KEY = "orbit_admin_role";

let onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRole(): string | null {
  return localStorage.getItem(ROLE_KEY);
}

export function setSession(token: string, role: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface ApiFetchOptions extends RequestInit {
  /** Some endpoints (e.g. change-password) return 401 for a business-logic
   * reason ("current password is incorrect") that has nothing to do with
   * the session token itself — auto-logging-out on those would clear a
   * perfectly valid session just because the user mistyped a field. Only
   * a 401 caused by the token itself (every other endpoint) should trigger
   * the global logout/redirect. */
  skipUnauthorizedHandler?: boolean;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { skipUnauthorizedHandler, ...fetchOptions } = options;
  const token = getToken();
  const headers = new Headers(fetchOptions.headers);
  if (!headers.has("Content-Type") && fetchOptions.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(path, { ...fetchOptions, headers });
  const text = await response.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }

  if (response.status === 401 && !skipUnauthorizedHandler) {
    clearSession();
    onUnauthorized?.();
  }

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(response.status, detail);
  }

  return body as T;
}
