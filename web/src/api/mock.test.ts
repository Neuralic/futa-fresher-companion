import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  announcements,
  buildings,
  courses,
  departments,
  faculties,
  lecturers,
} from '../mocks/fixtures';
import type { SyncResponse } from './types';
import { runSync, type PageStore, type PageWrite, type SyncQuery } from '../lib/sync';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function loadMock(pageSize: string) {
  vi.stubEnv('VITE_MOCK_SYNC_PAGE_SIZE', pageSize);
  vi.resetModules();
  return import('./mock');
}

// Records what the engine writes, so the test can count the rows it received.
function recordingStore() {
  const meta = new Map<string, string>();
  const writes: PageWrite[] = [];
  const store: PageStore = {
    async getMeta(key) {
      return meta.get(key);
    },
    async deleteMeta(key) {
      meta.delete(key);
    },
    async applyPage(write) {
      writes.push(write);
      if (write.cursor) meta.set('sync_cursor', write.cursor);
      else meta.delete('sync_cursor');
      if (write.lastSync) meta.set('last_sync', write.lastSync);
    },
  };
  return { store, meta, writes };
}

describe('mock /sync', () => {
  it('returns one page when no page size is set', async () => {
    const { mockRequest } = await loadMock('');

    const page = (await mockRequest('GET', '/sync', {})) as SyncResponse;

    expect(page.next_cursor).toBeNull();
    expect(page.full).toBe(true);
    expect(page.faculties).toHaveLength(faculties.length);
  });

  it('pages through every row with the engine and sends full only on the first page', async () => {
    const { mockRequest } = await loadMock('2');
    const { store, writes } = recordingStore();
    const fetchPage = (query: SyncQuery) =>
      mockRequest('GET', '/sync', query) as Promise<SyncResponse>;

    await runSync({ store, fetchPage });

    const totalRows =
      faculties.length +
      departments.length +
      lecturers.length +
      courses.length +
      buildings.length +
      announcements.length;
    const received = writes.reduce(
      (sum, w) =>
        sum + [
            'faculties',
            'departments',
            'lecturers',
            'courses',
            'buildings',
            'announcements',
          ].reduce(
          (n, name) => n + w.page[name as 'faculties'].length,
          0,
        ),
      0,
    );
    expect(writes.length).toBeGreaterThan(1);
    expect(received).toBe(totalRows);
    expect(writes.map((w) => w.clear)[0]).toBe(true);
    expect(writes.slice(1).every((w) => !w.clear)).toBe(true);
    expect(writes.at(-1)?.lastSync).toBeDefined();
  });
});
