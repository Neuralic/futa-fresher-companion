// Offline cache (IndexedDB via Dexie). Loaded lazily from App.tsx to keep the first load small.
import Dexie, { type Table } from 'dexie';
import { apiGet } from '../api/client';
import type { Announcement, SyncResponse } from '../api/types';
import { COLLECTIONS, CURSOR_KEY, LAST_SYNC_KEY, runSync, type PageStore } from './sync';
import { setSyncProgress } from './syncStatus';
import { notExpired } from './visibility';

type Row = { id: string };
type Meta = { key: string; value: string };

class CompanionDB extends Dexie {
  faculties!: Table<Row, string>;
  departments!: Table<Row, string>;
  lecturers!: Table<Row, string>;
  courses!: Table<Row, string>;
  class_reps!: Table<Row, string>;
  buildings!: Table<Row, string>;
  timetable_entries!: Table<Row, string>;
  announcements!: Table<Row, string>;
  meta!: Table<Meta, string>;

  constructor() {
    super('futa-companion');
    this.version(1).stores({
      faculties: 'id',
      departments: 'id, faculty_id',
      lecturers: 'id, department_id, full_name',
      courses: 'id, department_id, level',
      class_reps: 'id, department_id, level',
      buildings: 'id, name, type',
      timetable_entries: 'id, department_id, level',
      announcements: 'id, scope, published_at',
      meta: 'key',
    });
  }
}

export const db = new CompanionDB();

// Each page is one transaction: its clears, rows, tombstones and cursor commit together,
// so a crash mid-page leaves the cache as it was before that page.
const dexieStore: PageStore = {
  async getMeta(key) {
    return (await db.meta.get(key))?.value;
  },

  async deleteMeta(key) {
    await db.meta.delete(key);
  },

  async applyPage({ page, clear, cursor, lastSync }) {
    await db.transaction('rw', [...COLLECTIONS.map((c) => db[c]), db.meta], async () => {
      for (const name of COLLECTIONS) {
        if (clear) await db[name].clear();
        await db[name].bulkPut(page[name] as Row[]);
        const gone = page.deleted[name];
        if (gone?.length) await db[name].bulkDelete(gone);
      }
      if (cursor) await db.meta.put({ key: CURSOR_KEY, value: cursor });
      else await db.meta.delete(CURSOR_KEY);
      if (lastSync) await db.meta.put({ key: LAST_SYNC_KEY, value: lastSync });
    });
  },
};

/** Pull everything changed since the last sync, page by page, into IndexedDB. */
export function syncReferenceData(): Promise<void> {
  return runSync({
    store: dexieStore,
    fetchPage: (query) => apiGet<SyncResponse>('/sync', query),
    onProgress: setSyncProgress,
  });
}

/** Cached announcements that have not expired on this device. Expired rows stay stored. */
export async function readCachedAnnouncements(): Promise<Announcement[]> {
  const rows = (await db.announcements.toArray()) as Announcement[];
  return notExpired(rows, Date.now());
}
