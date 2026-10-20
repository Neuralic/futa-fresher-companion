import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import type { SyncResponse } from '../api/types';
import {
  COLLECTIONS,
  CURSOR_KEY,
  LAST_SYNC_KEY,
  runSync,
  type PageStore,
  type PageWrite,
  type SyncProgress,
  type SyncQuery,
} from './sync';

const SERVER_TIME = '2026-10-20T10:00:00.000Z';
const OLD_SYNC = '2026-10-19T10:00:00.000Z';

type Faculty = SyncResponse['faculties'][number];

function faculty(id: string): Faculty {
  return {
    id,
    name: `Faculty ${id}`,
    short_name: null,
    verification: { status: 'verified' },
    updated_at: SERVER_TIME,
  } as Faculty;
}

function makePage(overrides: Partial<SyncResponse> = {}): SyncResponse {
  return {
    server_time: SERVER_TIME,
    full: false,
    next_cursor: null,
    faculties: [],
    departments: [],
    lecturers: [],
    courses: [],
    class_reps: [],
    buildings: [],
    timetable_entries: [],
    announcements: [],
    deleted: {},
    ...overrides,
  };
}

// In-memory store with the same contract as the Dexie store: a page is written as one unit.
function memoryStore(meta: Record<string, string> = {}, faculties: Faculty[] = []) {
  const metaMap = new Map(Object.entries(meta));
  const tables: Record<string, Map<string, { id: string }>> = {};
  for (const name of COLLECTIONS) tables[name] = new Map();
  for (const row of faculties) tables.faculties.set(row.id, row);
  const writes: PageWrite[] = [];

  const store: PageStore = {
    async getMeta(key) {
      return metaMap.get(key);
    },
    async deleteMeta(key) {
      metaMap.delete(key);
    },
    async applyPage(write) {
      writes.push(write);
      for (const name of COLLECTIONS) {
        const table = tables[name];
        if (write.clear) table.clear();
        for (const row of write.page[name] as { id: string }[]) table.set(row.id, row);
        for (const id of write.page.deleted[name] ?? []) table.delete(id);
      }
      if (write.cursor) metaMap.set(CURSOR_KEY, write.cursor);
      else metaMap.delete(CURSOR_KEY);
      if (write.lastSync) metaMap.set(LAST_SYNC_KEY, write.lastSync);
    },
  };

  return { store, meta: metaMap, tables, writes };
}

// Fake server: the first request gets pages[0], and cursor "c<n>" gets pages[n].
function fakeServer(pages: SyncResponse[], failOn?: (query: SyncQuery) => Error | undefined) {
  const requests: SyncQuery[] = [];
  const fetchPage = async (query: SyncQuery): Promise<SyncResponse> => {
    requests.push(query);
    const failure = failOn?.(query);
    if (failure) throw failure;
    const index = query.cursor ? Number(query.cursor.slice(1)) : 0;
    const page = pages[index];
    if (!page) throw new Error(`no page for ${JSON.stringify(query)}`);
    return page;
  };
  return { requests, fetchPage };
}

describe('runSync', () => {
  it('applies every page of a multi-page sync', async () => {
    const mem = memoryStore();
    const server = fakeServer([
      makePage({ full: true, next_cursor: 'c1', faculties: [faculty('f1'), faculty('f2')] }),
      makePage({ next_cursor: 'c2', faculties: [faculty('f3'), faculty('f4')] }),
      makePage({ faculties: [faculty('f5')] }),
    ]);

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect(server.requests).toEqual([{}, { cursor: 'c1' }, { cursor: 'c2' }]);
    expect([...mem.tables.faculties.keys()].sort()).toEqual(['f1', 'f2', 'f3', 'f4', 'f5']);
  });

  it('clears a collection only on the first page of a full sync', async () => {
    const mem = memoryStore({}, [faculty('stale')]);
    const server = fakeServer([
      makePage({ full: true, next_cursor: 'c1', faculties: [faculty('f1')] }),
      makePage({ full: false, next_cursor: 'c2', faculties: [faculty('f2')] }),
      makePage({ full: false, faculties: [faculty('f3')] }),
    ]);

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect(mem.writes.map((w) => w.clear)).toEqual([true, false, false]);
    expect([...mem.tables.faculties.keys()].sort()).toEqual(['f1', 'f2', 'f3']);
  });

  it('stores last_sync only with the last page, never earlier', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC });
    const seenBeforeEachRequest: (string | undefined)[] = [];
    const server = fakeServer([
      makePage({ next_cursor: 'c1', faculties: [faculty('f1')] }),
      makePage({ next_cursor: 'c2', faculties: [faculty('f2')] }),
      makePage({ faculties: [faculty('f3')] }),
    ]);
    const watching: typeof server.fetchPage = async (query) => {
      seenBeforeEachRequest.push(mem.meta.get(LAST_SYNC_KEY));
      return server.fetchPage(query);
    };

    await runSync({ store: mem.store, fetchPage: watching });

    expect(seenBeforeEachRequest).toEqual([OLD_SYNC, OLD_SYNC, OLD_SYNC]);
    expect(mem.writes.map((w) => w.lastSync)).toEqual([undefined, undefined, SERVER_TIME]);
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(SERVER_TIME);
  });

  it('a failed page leaves last_sync unchanged and keeps the cursor of the last applied page', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC });
    const server = fakeServer(
      [
        makePage({ next_cursor: 'c1', faculties: [faculty('f1')] }),
        makePage({ faculties: [faculty('f2')] }),
      ],
      (query) => (query.cursor === 'c1' ? new TypeError('network down') : undefined),
    );

    await expect(runSync({ store: mem.store, fetchPage: server.fetchPage })).rejects.toThrow(
      'network down',
    );

    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(OLD_SYNC);
    expect(mem.meta.get(CURSOR_KEY)).toBe('c1');
    expect(mem.tables.faculties.has('f1')).toBe(true);
    expect(mem.tables.faculties.has('f2')).toBe(false);
  });

  it('resumes from a saved cursor instead of since', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC, [CURSOR_KEY]: 'c1' });
    const server = fakeServer([makePage({ faculties: [faculty('f0')] }), makePage({ faculties: [faculty('f1')] })]);

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect(server.requests).toEqual([{ cursor: 'c1' }]);
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(SERVER_TIME);
    expect(mem.meta.has(CURSOR_KEY)).toBe(false);
  });

  it('a 422 on a saved cursor restarts from the stored last_sync', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC, [CURSOR_KEY]: 'old' });
    const server = fakeServer(
      [makePage({ faculties: [faculty('f1')] })],
      (query) => (query.cursor === 'old' ? new ApiError(422, 'Cursor expired') : undefined),
    );

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect(server.requests).toEqual([{ cursor: 'old' }, { since: OLD_SYNC }]);
    expect(mem.meta.has(CURSOR_KEY)).toBe(false);
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(SERVER_TIME);
    expect(mem.writes.map((w) => w.clear)).toEqual([false]);
  });

  it('a 422 with no stored last_sync restarts as a full sync', async () => {
    const mem = memoryStore({ [CURSOR_KEY]: 'old' }, [faculty('stale')]);
    const server = fakeServer(
      [makePage({ full: true, faculties: [faculty('f1')] })],
      (query) => (query.cursor === 'old' ? new ApiError(422, 'Cursor expired') : undefined),
    );

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect(server.requests).toEqual([{ cursor: 'old' }, {}]);
    expect(mem.writes.map((w) => w.clear)).toEqual([true]);
    expect([...mem.tables.faculties.keys()]).toEqual(['f1']);
  });

  it('a second 422 is not retried forever', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC, [CURSOR_KEY]: 'old' });
    const server = fakeServer([], () => new ApiError(422, 'Invalid cursor'));

    await expect(runSync({ store: mem.store, fetchPage: server.fetchPage })).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(server.requests).toEqual([{ cursor: 'old' }, { since: OLD_SYNC }]);
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(OLD_SYNC);
  });

  it.each([
    ['no next_cursor', undefined],
    ['null next_cursor', null],
    ['empty next_cursor', ''],
  ])('an unpaged response with %s works as the last page', async (_label, value) => {
    const mem = memoryStore();
    const page = makePage({ full: true, faculties: [faculty('f1')] });
    if (value === undefined) delete (page as { next_cursor?: string | null }).next_cursor;
    else page.next_cursor = value;
    const server = fakeServer([page]);

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect(server.requests).toEqual([{}]);
    expect(mem.writes).toHaveLength(1);
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(SERVER_TIME);
    expect(mem.meta.has(CURSOR_KEY)).toBe(false);
  });

  it('applies tombstones as deletions', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC }, [faculty('gone'), faculty('kept')]);
    const server = fakeServer([makePage({ deleted: { faculties: ['gone'] } })]);

    await runSync({ store: mem.store, fetchPage: server.fetchPage });

    expect([...mem.tables.faculties.keys()]).toEqual(['kept']);
  });

  it('reports progress, and reports running false at the end', async () => {
    const mem = memoryStore();
    const updates: SyncProgress[] = [];
    const server = fakeServer([
      makePage({ full: true, next_cursor: 'c1', faculties: [faculty('f1'), faculty('f2')] }),
      makePage({ faculties: [faculty('f3')], deleted: { faculties: ['x'] } }),
    ]);

    await runSync({
      store: mem.store,
      fetchPage: server.fetchPage,
      onProgress: (progress) => updates.push(progress),
    });

    expect(updates[0]).toEqual({ running: true, failed: false, firstRun: true, pages: 0, rows: 0 });
    expect(updates.at(-1)).toEqual({
      running: false,
      failed: false,
      firstRun: true,
      pages: 2,
      rows: 4,
    });
  });

  it('a timed-out page leaves the cursor and last_sync unchanged', async () => {
    const mem = memoryStore({ [LAST_SYNC_KEY]: OLD_SYNC, [CURSOR_KEY]: 'c1' });
    const updates: SyncProgress[] = [];
    let signalSeen: AbortSignal | undefined;
    // The request for c1 never answers and ignores its signal. The engine must still give up.
    const stalled = (query: SyncQuery, signal: AbortSignal) => {
      if (query.cursor !== 'c1') return Promise.resolve(makePage());
      signalSeen = signal;
      return new Promise<SyncResponse>(() => {});
    };

    const error = await runSync({
      store: mem.store,
      fetchPage: stalled,
      pageTimeoutMs: 20,
      onProgress: (progress) => updates.push(progress),
    }).catch((caught: unknown) => caught);

    expect((error as Error).name).toBe('TimeoutError');
    expect(signalSeen?.aborted).toBe(true);
    expect(mem.meta.get(CURSOR_KEY)).toBe('c1');
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(OLD_SYNC);
    expect(mem.writes).toHaveLength(0);
    expect(updates.at(-1)).toMatchObject({ running: false, failed: true });
  });

  it('a retry after a timed-out page resumes from the saved cursor', async () => {
    const mem = memoryStore();
    const server = fakeServer([
      makePage({ full: true, next_cursor: 'c1', faculties: [faculty('f1')] }),
      makePage({ faculties: [faculty('f2')] }),
    ]);
    let firstTry = true;
    // The first attempt at c1 stalls. Later attempts answer normally.
    const flaky = (query: SyncQuery) => {
      if (query.cursor === 'c1' && firstTry) {
        firstTry = false;
        return new Promise<SyncResponse>(() => {});
      }
      return server.fetchPage(query);
    };

    await runSync({ store: mem.store, fetchPage: flaky, pageTimeoutMs: 20 }).catch(() => {});
    expect(mem.meta.get(CURSOR_KEY)).toBe('c1');

    const updates: SyncProgress[] = [];
    await runSync({
      store: mem.store,
      fetchPage: flaky,
      onProgress: (progress) => updates.push(progress),
    });

    // The retry asks for c1 and not a full sync from the start.
    expect(server.requests).toEqual([{}, { cursor: 'c1' }]);
    expect(updates[0]).toMatchObject({ failed: false, firstRun: true });
    expect(mem.writes.map((w) => w.clear)).toEqual([true, false]);
    expect([...mem.tables.faculties.keys()].sort()).toEqual(['f1', 'f2']);
    expect(mem.meta.get(LAST_SYNC_KEY)).toBe(SERVER_TIME);
    expect(mem.meta.has(CURSOR_KEY)).toBe(false);
  });

  it('a non-422 error on a fresh sync is thrown and changes nothing', async () => {
    const mem = memoryStore();
    const server = fakeServer([], () => new ApiError(500, 'Server error'));

    await expect(runSync({ store: mem.store, fetchPage: server.fetchPage })).rejects.toBeInstanceOf(
      ApiError,
    );

    expect(mem.writes).toHaveLength(0);
    expect(mem.meta.size).toBe(0);
  });
});
