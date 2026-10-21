// Pure view logic for the department page. No Dexie or React imports, so Vitest can run it.
import type { Course, Department, Lecturer } from '../api/types';
import { emptyMessage } from './academicsView';

const ORDER = new Intl.Collator('en', { sensitivity: 'base', numeric: true });

export const COURSES_EMPTY = 'Courses for this department have not been added yet.';
export const LECTURERS_EMPTY = 'Lecturers for this department have not been added yet.';
export const DEPARTMENT_NOT_FOUND = 'This department is not saved on this device.';

/** Drops soft-deleted rows. Synced rows normally arrive without them, so this is a safety net. */
export function liveRows<T extends object>(rows: readonly T[]): T[] {
  return rows.filter((row) => !('deleted_at' in row && (row as { deleted_at?: unknown }).deleted_at));
}

export interface LevelGroup {
  level: number;
  courses: Course[];
}

/** Courses grouped by level, lowest level first. Each group is sorted by course code. */
export function groupCoursesByLevel(courses: readonly Course[]): LevelGroup[] {
  const byLevel = new Map<number, Course[]>();
  for (const course of liveRows(courses)) {
    const group = byLevel.get(course.level) ?? [];
    group.push(course);
    byLevel.set(course.level, group);
  }
  return [...byLevel.entries()]
    .sort(([a], [b]) => a - b)
    .map(([level, group]) => ({
      level,
      courses: group.sort((a, b) => ORDER.compare(a.code, b.code) || a.id.localeCompare(b.id)),
    }));
}

export function levelHeading(level: number): string {
  return `${level} Level`;
}

export function unitsText(units: number): string {
  return `${units} ${units === 1 ? 'unit' : 'units'}`;
}

/** Lecturers, live only, sorted by name. */
export function sortLecturers(lecturers: readonly Lecturer[]): Lecturer[] {
  return liveRows(lecturers).sort(
    (a, b) => ORDER.compare(a.full_name, b.full_name) || a.id.localeCompare(b.id),
  );
}

/** A lecturer's name with the title in front, when there is one. */
export function lecturerDisplayName(lecturer: Pick<Lecturer, 'title' | 'full_name'>): string {
  return [lecturer.title, lecturer.full_name].filter(Boolean).join(' ');
}

/**
 * The department to show, or null when it is not in the cache, is deleted, or belongs to
 * another school than the one in the URL.
 */
export function resolveDepartment(
  department: Department | undefined,
  facultyId: string,
): Department | null {
  if (!department) return null;
  if (department.faculty_id !== facultyId) return null;
  return liveRows([department])[0] ?? null;
}

/** What an empty section says. A sync in progress takes priority, as on the other screens. */
export function sectionEmptyMessage(
  progress: { running: boolean; firstRun: boolean },
  text: string,
): string {
  return emptyMessage(progress, text);
}
