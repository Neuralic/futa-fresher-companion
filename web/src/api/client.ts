import { tokenStore } from '../lib/session';

const BASE = (import.meta.env.VITE_API_URL ?? '') + '/api/v1';
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Seconds to wait before trying again, from the Retry-After header, when the server sent one. */
    public retryAfter?: number,
  ) {
    super(message);
  }
}

export type Query = Record<string, string | number | boolean | undefined>;

export interface RequestOptions {
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
  /** Send the signed-in user's token. Only for endpoints that need one. Off by default. */
  auth?: boolean;
}

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

/** Called when an authenticated request gets a 401. The token has already been cleared. */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

function parseRetryAfter(value: string | null): number | undefined {
  return value && /^\d+$/.test(value) ? Number(value) : undefined;
}

/** The longest we wait before the one retry of a busy (503) read. */
const MAX_RETRY_WAIT_SECONDS = 6;

function pause(seconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'));
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, seconds * 1000);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

export async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  if (USE_MOCKS) {
    const { mockRequest } = await import('./mock');
    return (await mockRequest(method, path, opts.query, opts.body)) as T;
  }

  try {
    return await send<T>(method, path, opts);
  } catch (error) {
    // A busy server (503 with Retry-After) gets one more try, for reads only. A write is never
    // repeated by itself: if the first one did get through, a retry would post it twice.
    if (
      method.toUpperCase() === 'GET' &&
      error instanceof ApiError &&
      error.status === 503 &&
      error.retryAfter !== undefined
    ) {
      await pause(Math.min(error.retryAfter, MAX_RETRY_WAIT_SECONDS), opts.signal);
      return send<T>(method, path, opts);
    }
    throw error;
  }
}

async function send<T>(method: string, path: string, opts: RequestOptions): Promise<T> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined) params.set(k, String(v));
  }
  const qs = params.toString();

  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  if (opts.auth) {
    const token = tokenStore.get();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`, {
    method,
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });

  if (!res.ok) {
    if (res.status === 401 && opts.auth) {
      // The token is no longer valid (expired, deactivated or revoked).
      tokenStore.clear();
      unauthorizedListeners.forEach((listener) => listener());
    }
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === 'string') detail = data.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail, parseRetryAfter(res.headers.get('Retry-After')));
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// Public by default: these never send a token.
export const apiGet = <T>(path: string, query?: Query, signal?: AbortSignal) =>
  request<T>('GET', path, { query, signal });

export const apiPost = <T>(path: string, body?: unknown, opts: { auth?: boolean } = {}) =>
  request<T>('POST', path, { body, auth: opts.auth });
