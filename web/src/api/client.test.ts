import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type ClientModule = typeof import('./client');
type SessionModule = typeof import('../lib/session');

// Load fresh copies with mock mode off, so every request goes through fetch (which is stubbed).
async function load(): Promise<{ client: ClientModule; session: SessionModule }> {
  vi.resetModules();
  vi.stubEnv('VITE_USE_MOCKS', 'false');
  const client = await import('./client');
  const session = await import('../lib/session');
  return { client, session };
}

function mapStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
    key: () => null,
    get length() {
      return data.size;
    },
  } as Storage;
}

interface Sent {
  url: string;
  headers: Record<string, string>;
}

let sent: Sent[] = [];

function stubFetch(respond: () => Response) {
  sent = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    sent.push({ url, headers: { ...((init.headers as Record<string, string>) ?? {}) } });
    return respond();
  });
}

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

beforeEach(() => {
  vi.stubGlobal('localStorage', mapStorage());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('the Authorization header', () => {
  it('is not sent on public requests, even when a token is stored', async () => {
    const { client, session } = await load();
    session.tokenStore.set('stored-token');
    stubFetch(() => json(200, []));

    await client.apiGet('/faculties');
    await client.apiPost('/auth/register', { email: 'a@b.co' });

    expect(sent.every((r) => !('Authorization' in r.headers))).toBe(true);
  });

  it('is sent as a Bearer token on requests that ask for it', async () => {
    const { client, session } = await load();
    session.tokenStore.set('stored-token');
    stubFetch(() => json(200, { id: 'u1' }));

    await client.request('GET', '/auth/me', { auth: true });

    expect(sent[0].headers.Authorization).toBe('Bearer stored-token');
  });

  it('is never put in the URL', async () => {
    const { client, session } = await load();
    session.tokenStore.set('stored-token');
    stubFetch(() => json(200, { id: 'u1' }));

    await client.request('GET', '/auth/me', { auth: true, query: { limit: 1 } });

    expect(sent[0].url).not.toContain('stored-token');
  });

  it('is not sent when the request does not ask for it and no token is needed', async () => {
    const { client } = await load();
    stubFetch(() => json(200, { access_token: 'x', token_type: 'bearer', expires_in: 1 }));

    await client.apiPost('/auth/login', { email: 'a@b.co', password: 'pw' });

    expect(sent[0].headers.Authorization).toBeUndefined();
  });

  it('still works when storage is blocked, because the token is kept in memory', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new DOMException('blocked', 'SecurityError');
      },
      setItem: () => {
        throw new DOMException('blocked', 'SecurityError');
      },
      removeItem: () => {
        throw new DOMException('blocked', 'SecurityError');
      },
    });
    const { client, session } = await load();
    session.tokenStore.set('memory-token');
    stubFetch(() => json(200, { id: 'u1' }));

    await client.request('GET', '/auth/me', { auth: true });

    expect(sent[0].headers.Authorization).toBe('Bearer memory-token');
  });
});

describe('401 responses', () => {
  it('clears the token and tells listeners when an authenticated call gets a 401', async () => {
    const { client, session } = await load();
    session.tokenStore.set('expired-token');
    stubFetch(() => json(401, { detail: 'Invalid or expired token' }));
    const listener = vi.fn();
    client.onUnauthorized(listener);

    await expect(client.request('GET', '/auth/me', { auth: true })).rejects.toMatchObject({
      status: 401,
    });

    expect(session.tokenStore.get()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('keeps the token and tells nobody when a login with a wrong password is refused', async () => {
    const { client, session } = await load();
    session.tokenStore.set('existing-token');
    stubFetch(() => json(401, { detail: 'Invalid email or password' }));
    const listener = vi.fn();
    client.onUnauthorized(listener);

    await expect(
      client.apiPost('/auth/login', { email: 'a@b.co', password: 'wrong' }),
    ).rejects.toMatchObject({ status: 401, message: 'Invalid email or password' });

    expect(session.tokenStore.get()).toBe('existing-token');
    expect(listener).not.toHaveBeenCalled();
  });

  it('stops telling a listener once it has unsubscribed', async () => {
    const { client, session } = await load();
    session.tokenStore.set('t');
    stubFetch(() => json(401, { detail: 'nope' }));
    const listener = vi.fn();
    const stop = client.onUnauthorized(listener);
    stop();

    await expect(client.request('GET', '/auth/me', { auth: true })).rejects.toBeDefined();

    expect(listener).not.toHaveBeenCalled();
  });
});

describe('error details from the server', () => {
  it('uses the server message for a 409', async () => {
    const { client } = await load();
    stubFetch(() =>
      json(409, { detail: 'An account with this email or matric number already exists' }),
    );

    await expect(client.apiPost('/auth/register', {})).rejects.toMatchObject({
      status: 409,
      message: 'An account with this email or matric number already exists',
    });
  });

  it('reads Retry-After from a 503', async () => {
    const { client } = await load();
    stubFetch(() => json(503, { detail: 'Service temporarily unavailable' }, { 'Retry-After': '7' }));

    // A POST, because a GET would now wait and retry (see "the 503 retry" below).
    await expect(client.apiPost('/auth/register', {})).rejects.toMatchObject({
      status: 503,
      retryAfter: 7,
    });
  });

  it('leaves retryAfter empty when the header is missing or not a number', async () => {
    const { client } = await load();
    stubFetch(() => json(503, { detail: 'busy' }, { 'Retry-After': 'soon' }));

    const error = await client.apiGet('/faculties').catch((caught: unknown) => caught);

    expect((error as { retryAfter?: number }).retryAfter).toBeUndefined();
  });
});

describe('the 503 retry', () => {
  // Answers each call from the list in turn and counts the calls.
  function stubSequence(responses: Response[]) {
    sent = [];
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      sent.push({ url, headers: { ...((init.headers as Record<string, string>) ?? {}) } });
      return responses[Math.min(sent.length - 1, responses.length - 1)].clone();
    });
  }
  const busy = (retryAfter?: string) =>
    json(503, { detail: 'busy' }, retryAfter ? { 'Retry-After': retryAfter } : {});

  afterEach(() => {
    vi.useRealTimers();
  });

  it('retries a GET once, after the Retry-After seconds', async () => {
    vi.useFakeTimers();
    const { client } = await load();
    stubSequence([busy('3'), json(200, [{ id: 'f1' }])]);

    const result = client.apiGet('/faculties');
    await vi.advanceTimersByTimeAsync(2900);
    expect(sent).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(200);

    expect(await result).toEqual([{ id: 'f1' }]);
    expect(sent).toHaveLength(2);
  });

  it('waits at most 6 seconds', async () => {
    vi.useFakeTimers();
    const { client } = await load();
    stubSequence([busy('120'), json(200, [])]);

    const result = client.apiGet('/faculties');
    await vi.advanceTimersByTimeAsync(5900);
    expect(sent).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(200);

    await result;
    expect(sent).toHaveLength(2);
  });

  it('retries only once, then gives the 503 to the caller', async () => {
    vi.useFakeTimers();
    const { client } = await load();
    stubSequence([busy('1')]);

    const result = client.apiGet('/faculties').catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(await result).toMatchObject({ status: 503, retryAfter: 1 });
    expect(sent).toHaveLength(2);
  });

  it('does not retry a 503 that has no Retry-After', async () => {
    const { client } = await load();
    stubSequence([busy()]);

    await expect(client.apiGet('/faculties')).rejects.toMatchObject({ status: 503 });
    expect(sent).toHaveLength(1);
  });

  it('does not retry other errors', async () => {
    const { client } = await load();
    stubSequence([json(500, { detail: 'boom' }, { 'Retry-After': '1' })]);

    await expect(client.apiGet('/faculties')).rejects.toMatchObject({ status: 500 });
    expect(sent).toHaveLength(1);
  });

  it('never retries a POST by itself', async () => {
    vi.useFakeTimers();
    const { client, session } = await load();
    session.tokenStore.set('t');
    stubSequence([busy('1'), json(201, { id: 'a1' })]);

    const result = client
      .apiPost('/announcements', { title: 'x' }, { auth: true })
      .catch((caught: unknown) => caught);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(await result).toMatchObject({ status: 503, retryAfter: 1 });
    expect(sent).toHaveLength(1);
  });

  it('stops waiting when the request is aborted', async () => {
    vi.useFakeTimers();
    const { client } = await load();
    stubSequence([busy('5'), json(200, [])]);
    const controller = new AbortController();

    const result = client.apiGet('/faculties', undefined, controller.signal).catch((c: unknown) => c);
    await vi.advanceTimersByTimeAsync(1000);
    controller.abort();
    await vi.advanceTimersByTimeAsync(10);

    expect(await result).toMatchObject({ name: 'AbortError' });
    expect(sent).toHaveLength(1);
  });
});
