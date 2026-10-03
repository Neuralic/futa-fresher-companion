const BASE = (import.meta.env.VITE_API_URL ?? '') + '/api/v1';
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';
const TOKEN_KEY = 'futa_token';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export type Query = Record<string, string | number | boolean | undefined>;

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export async function request<T>(
  method: string,
  path: string,
  opts: { query?: Query; body?: unknown } = {},
): Promise<T> {
  if (USE_MOCKS) {
    const { mockRequest } = await import('./mock');
    return (await mockRequest(method, path, opts.query)) as T;
  }

  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined) params.set(k, String(v));
  }
  const qs = params.toString();

  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`, {
    method,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const apiGet = <T>(path: string, query?: Query) => request<T>('GET', path, { query });
export const apiPost = <T>(path: string, body?: unknown) => request<T>('POST', path, { body });
