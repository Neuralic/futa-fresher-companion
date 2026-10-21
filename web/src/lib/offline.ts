// Offline cache (IndexedDB via Dexie). Loaded lazily from App.tsx to keep the first load small.
import Dexie, { type Table } from 'dexie';
import { apiGet } from '../api/client';
import type {
  Announcement,
  Building,
  Course,
  Department,
  Faculty,
  Lecturer,
  SyncResponse,
  TimetableEntry,
} from '../api/types';
import { sortByName } from './academicsView';
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

// Only one sync runs at a time. A retry while one is running joins that run.
let inFlight: Promise<void> | null = null;

/** Pull everything changed since the last sync, page by page, into IndexedDB. */
export function syncReferenceData(): Promise<void> {
  if (!inFlight) {
    inFlight = runSync({
      store: dexieStore,
      fetchPage: (query, signal) => apiGet<SyncResponse>('/sync', query, signal),
      onProgress: setSyncProgress,
    }).finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

/** Saved schools (faculties), A to Z. Reads the cache only, so it works offline. */
export async function readFaculties(): Promise<Faculty[]> {
  return sortByName((await db.faculties.toArray()) as Faculty[]);
}

/** One saved school, or undefined if it is not in the cache on this device. */
export async function readFaculty(id: string): Promise<Faculty | undefined> {
  return (await db.faculties.get(id)) as Faculty | undefined;
}

/** Saved departments of one school, A to Z. */
export async function readDepartments(facultyId: string): Promise<Department[]> {
  const rows = (await db.departments
    .where('faculty_id')
    .equals(facultyId)
    .toArray()) as Department[];
  return sortByName(rows);
}

/** Every saved department, for looking up names. Reads the cache only. */
export async function readAllDepartments(): Promise<Department[]> {
  return (await db.departments.toArray()) as Department[];
}

/** One saved department, or undefined if it is not in the cache. */
export async function readDepartment(id: string): Promise<Department | undefined> {
  return (await db.departments.get(id)) as Department | undefined;
}

/** Saved courses of one department. Sorting is done by the caller. */
export async function readCourses(departmentId: string): Promise<Course[]> {
  return (await db.courses.where('department_id').equals(departmentId).toArray()) as Course[];
}

/** Saved lecturers of one department. Sorting is done by the caller. */
export async function readLecturers(departmentId: string): Promise<Lecturer[]> {
  return (await db.lecturers
    .where('department_id')
    .equals(departmentId)
    .toArray()) as Lecturer[];
}

/** Everything the department page needs, from the cache only. */
export async function readDepartmentScreen(departmentId: string) {
  const [department, courses, lecturers] = await Promise.all([
    readDepartment(departmentId),
    readCourses(departmentId),
    readLecturers(departmentId),
  ]);
  return { department, courses, lecturers };
}

/** Saved timetable entries of one department, all levels. Filtering is done by the caller. */
export async function readTimetable(departmentId: string): Promise<TimetableEntry[]> {
  return (await db.timetable_entries
    .where('department_id')
    .equals(departmentId)
    .toArray()) as TimetableEntry[];
}

/** Everything the timetable page needs, from the cache only. */
export async function readTimetableScreen(departmentId: string) {
  const [department, entries, courses] = await Promise.all([
    readDepartment(departmentId),
    readTimetable(departmentId),
    readCourses(departmentId),
  ]);
  const buildingIds = [
    ...new Set(entries.map((entry) => entry.venue_building_id).filter((id): id is string => !!id)),
  ];
  const buildings = (await db.buildings.bulkGet(buildingIds)).filter(
    (building): building is Building => building !== undefined,
  );
  return { department, entries, courses, buildings };
}

/** Departments for the sign-up picker, A to Z, each with its school name. Cache only. */
export async function readDepartmentChoices(): Promise<{ id: string; name: string; school: string }[]> {
  const [departments, faculties] = await Promise.all([readAllDepartments(), readFaculties()]);
  const schoolNames = new Map(faculties.map((faculty) => [faculty.id, faculty.name]));
  return sortByName(
    departments.map((department) => ({
      id: department.id,
      name: department.name,
      school: schoolNames.get(department.faculty_id) ?? '',
    })),
  );
}

/** Everything the Announcements screen needs, from the cache only. */
export async function readAnnouncementsScreen() {
  const [announcements, faculties, departments] = await Promise.all([
    readCachedAnnouncements(),
    readFaculties(),
    readAllDepartments(),
  ]);
  return { announcements, faculties, departments };
}

/** Cached announcements that have not expired on this device. Expired rows stay stored. */
export async function readCachedAnnouncements(): Promise<Announcement[]> {
  const rows = (await db.announcements.toArray()) as Announcement[];
  return notExpired(rows, Date.now());
}
