// Paged /sync client. The storage is passed in, so this file has no IndexedDB dependency and
// can be tested in Node. offline.ts supplies the Dexie store.
import { ApiError } from '../api/client';
import type { SyncResponse } from '../api/types';

export const COLLECTIONS = [
  'faculties',
  'departments',
  'lecturers',
  'courses',
  'class_reps',
  'buildings',
  'timetable_entries',
  'announcements',
] as const;

export const LAST_SYNC_KEY = 'last_sync';
export const CURSOR_KEY = 'sync_cursor';

/** One page, written in a single transaction by the store. */
export interface PageWrite {
  page: SyncResponse;
  /** True only on the first page of a full sync: clear each collection before writing. */
  clear: boolean;
  /** The cursor to resume from next time, or null to remove the saved cursor. */
  cursor: string | null;
  /** Set only on the last page: the value to send as `since` next time. */
  lastSync?: string;
}

export interface PageStore {
  getMeta(key: string): Promise<string | undefined>;
  applyPage(write: PageWrite): Promise<void>;
  deleteMeta(key: string): Promise<void>;
}

// A type alias (not an interface) so it can be passed as apiGet's query record.
export type SyncQuery = {
  since?: string;
  cursor?: string;
};

export interface SyncProgress {
  running: boolean;
  /** True when no last_sync is stored yet: this is the first sync on this device. */
  firstRun: boolean;
  pages: number;
  rows: number;
}

export interface SyncOptions {
  store: PageStore;
  fetchPage: (query: SyncQuery) => Promise<SyncResponse>;
  onProgress?: (progress: SyncProgress) => void;
}

/**
 * Pull pages until the server has no next_cursor. Each page is written in one store
 * transaction together with its cursor. last_sync is written only with the last page.
 */
export async function runSync({
  store,
  fetchPage,
  onProgress = () => {},
}: SyncOptions): Promise<void> {
  const lastSync = await store.getMeta(LAST_SYNC_KEY);
  let cursor = await store.getMeta(CURSOR_KEY);
  const progress: SyncProgress = {
    running: true,
    firstRun: lastSync === undefined,
    pages: 0,
    rows: 0,
  };
  onProgress({ ...progress });
  let restarted = false;

  try {
    for (;;) {
      let page: SyncResponse;
      try {
        page = await fetchPage(cursor ? { cursor } : lastSync ? { since: lastSync } : {});
      } catch (error) {
        if (cursor && !restarted && isCursorRejected(error)) {
          // The saved cursor expired or is malformed. Start again from the stored last_sync,
          // or from a full sync if there is none. Once only, so a second 422 surfaces.
          restarted = true;
          cursor = undefined;
          await store.deleteMeta(CURSOR_KEY);
          continue;
        }
        throw error;
      }

      const next = page.next_cursor;
      await store.applyPage({
        page,
        // The server sends full: true only on the first page of a full sync.
        clear: page.full === true,
        cursor: next || null,
        lastSync: next ? undefined : page.server_time,
      });

      progress.pages += 1;
      progress.rows += countRows(page);
      onProgress({ ...progress });

      if (!next) return;
      cursor = next;
    }
  } finally {
    onProgress({ ...progress, running: false });
  }
}

function isCursorRejected(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422;
}

function countRows(page: SyncResponse): number {
  const rows = COLLECTIONS.reduce((sum, name) => sum + page[name].length, 0);
  const deleted = Object.values(page.deleted).reduce((sum, ids) => sum + ids.length, 0);
  return rows + deleted;
}
