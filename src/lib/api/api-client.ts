export const BACKEND_URL =
  (typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8001"
    : process.env.BACKEND_URL || "http://127.0.0.1:8001"
  ).replace(/\/+$/, "");

/** @deprecated Use BACKEND_URL instead. */
export const BASE_URL = BACKEND_URL;

export type ApiError = {
  status: number;
  message: string;
  data?: unknown;
};

function formatError(status: number, body: unknown): ApiError {
  if (body && typeof body === "object") {
    const detail = (body as Record<string, unknown>).detail;
    if (typeof detail === "string") return { status, message: detail, data: body };
  }
  return { status, message: `HTTP ${status}`, data: body };
}

async function request<T>(
  path: string,
  options: RequestInit & { params?: Record<string, string> } = {},
): Promise<T> {
  let url = `${BACKEND_URL}${path}`;
  if (options.params) {
    const qs = new URLSearchParams(options.params).toString();
    if (qs) url += `?${qs}`;
  }

  const { params: _params, ...fetchOptions } = options;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(fetchOptions.headers as Record<string, string>),
    },
    ...fetchOptions,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw formatError(res.status, body);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string, params?: Record<string, string>) =>
    request<T>(path, { method: "GET", params }),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "DELETE",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
};

/** Simple JSON fetch — returns null on error. */
export async function fetchJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** Raw fetch with BACKEND_URL prefix. */
export async function apiFetch(path: string, options?: RequestInit): Promise<Response> {
  return fetch(`${BACKEND_URL}${path}`, options);
}
