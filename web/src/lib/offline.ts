// Offline cache (IndexedDB via Dexie). Loaded lazily from App.tsx to keep the first load small.
import Dexie, { type Table } from 'dexie';
import { apiGet } from '../api/client';
import type { SyncResponse } from '../api/types';

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

const COLLECTIONS = [
  'faculties',
  'departments',
  'lecturers',
  'courses',
  'class_reps',
  'buildings',
  'timetable_entries',
  'announcements',
] as const;

/** Pull everything changed since the last sync and merge it into IndexedDB. */
export async function syncReferenceData(): Promise<void> {
  const last = await db.meta.get('last_sync');
  const data = await apiGet<SyncResponse>('/sync', { since: last?.value });

  await db.transaction('rw', [...COLLECTIONS.map((c) => db[c]), db.meta], async () => {
    for (const name of COLLECTIONS) {
      if (data.full) await db[name].clear();
      await db[name].bulkPut(data[name] as Row[]);
      const gone = data.deleted[name];
      if (gone?.length) await db[name].bulkDelete(gone);
    }
    await db.meta.put({ key: 'last_sync', value: data.server_time });
  });
}
