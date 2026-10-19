// Minimal typed fetch wrapper around the FastAPI backend.

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const TOKEN_KEY = "answerwise.token"; // storage key kept so existing sessions stay signed in

export class ApiError extends Error {
  status: number;
  code: string;
  fieldErrors: { field: string; message: string }[];

  constructor(status: number, message: string, code = "error", fieldErrors: { field: string; message: string }[] = []) {
    super(message);
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string | null) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage unavailable (private mode) - session lasts until reload */
    }
  },
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

type Params = Record<string, string | number | boolean | undefined>;

async function request<T>(method: Method, path: string, body?: unknown, params?: Params, signal?: AbortSignal): Promise<T> {
  const url = new URL(BASE_URL + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) if (v !== undefined) url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(BASE_URL ? url.toString() : url.pathname + url.search, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    // A cancelled request is not a failure: callers ignore it (e.g. a draft for an outdated question).
    if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) throw err;
    throw new ApiError(0, "Cannot reach the server. Check that the backend is running and try again.", "network_error");
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized?.();
    const message = (data && typeof data.detail === "string" && data.detail) || `Request failed (${res.status})`;
    throw new ApiError(res.status, message, data?.code ?? "error", data?.errors ?? []);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: Params) => request<T>("GET", path, undefined, params),
  post: <T>(path: string, body?: unknown, params?: Params, signal?: AbortSignal) => request<T>("POST", path, body ?? {}, params, signal),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException ? err.name === "AbortError" : err instanceof Error && err.name === "AbortError";
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "The request could not be completed. Try again.";
}
