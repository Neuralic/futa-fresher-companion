// Pure view logic for the timetable. No Dexie or React imports, so Vitest can run it.
import type { Building, Course, TimetableEntry } from '../api/types';
import { emptyMessage } from './academicsView';
import { liveRows } from './departmentView';

// day_of_week in the schema: 1 = Monday ... 7 = Sunday.
const DAY_NAMES: Record<number, string> = {
  1: 'Monday',
  2: 'Tuesday',
  3: 'Wednesday',
  4: 'Thursday',
  5: 'Friday',
  6: 'Saturday',
  7: 'Sunday',
};
const SHORT_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const LEVEL_KEY = 'futa-timetable-level';
export const TIMETABLE_EMPTY = 'The timetable for this department has not been added yet.';
export const LEVEL_EMPTY = 'No timetable entries for this level yet.';
export const COURSE_MISSING = 'Course details are not saved on this device.';
export const VENUE_MISSING = 'Venue not given yet.';
export const BUILDING_MISSING = 'Building not saved on this device';

/** Levels that have at least one live entry, lowest first. Only these are offered in the picker. */
export function levelsWithEntries(entries: readonly TimetableEntry[]): number[] {
  return [...new Set(liveRows(entries).map((entry) => entry.level))].sort((a, b) => a - b);
}

/** The remembered level if it still has entries, otherwise the lowest level, or null if none. */
export function chooseLevel(levels: readonly number[], remembered: number | null): number | null {
  if (remembered !== null && levels.includes(remembered)) return remembered;
  return levels[0] ?? null;
}

export function entriesForLevel(entries: readonly TimetableEntry[], level: number): TimetableEntry[] {
  return liveRows(entries).filter((entry) => entry.level === level);
}

// Storage can be missing or blocked (private mode). Every access is guarded.
export function loadRememberedLevel(storage: Pick<Storage, 'getItem'> | undefined): number | null {
  try {
    const raw = storage?.getItem(LEVEL_KEY);
    if (raw === null || raw === undefined) return null;
    const level = Number(raw);
    return Number.isInteger(level) ? level : null;
  } catch {
    return null;
  }
}

export function rememberLevel(storage: Pick<Storage, 'setItem'> | undefined, level: number): void {
  try {
    storage?.setItem(LEVEL_KEY, String(level));
  } catch {
    // Not stored: the choice lasts until the page is left.
  }
}

/** The browser's local storage, or undefined if the browser blocks it. */
export function browserLocalStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}

function startsBefore(a: TimetableEntry, b: TimetableEntry): number {
  return a.start_time.localeCompare(b.start_time) || a.id.localeCompare(b.id);
}

export interface DayGroup {
  day: number;
  label: string;
  entries: TimetableEntry[];
}

/** Entries grouped by day, Monday first, each day sorted by start time. Sunday only if it has entries. */
export function groupByDay(entries: readonly TimetableEntry[]): DayGroup[] {
  const byDay = new Map<number, TimetableEntry[]>();
  for (const entry of liveRows(entries)) {
    const group = byDay.get(entry.day_of_week) ?? [];
    group.push(entry);
    byDay.set(entry.day_of_week, group);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([day, group]) => ({
      day,
      label: DAY_NAMES[day] ?? 'Unknown day',
      entries: group.sort(startsBefore),
    }));
}

export function timeRange(entry: Pick<TimetableEntry, 'start_time' | 'end_time'>): string {
  return `${entry.start_time}–${entry.end_time}`;
}

/** Course code and title from the cache, or a plain message when the course is not saved. */
export function courseText(course: Course | undefined): { code: string; title: string } | null {
  if (!course) return null;
  return { code: course.code, title: course.title };
}

/** Venue text. A building name from the cache when linked, else the note, else a plain message. */
export function venueText(
  entry: Pick<TimetableEntry, 'venue_building_id' | 'venue_note'>,
  buildings: ReadonlyMap<string, Pick<Building, 'name'>>,
): string {
  const note = entry.venue_note?.trim() || null;
  if (entry.venue_building_id) {
    const building = buildings.get(entry.venue_building_id);
    const name = building ? building.name : BUILDING_MISSING;
    return note ? `${name} · ${note}` : name;
  }
  return note ?? VENUE_MISSING;
}

export function buildingsById(
  buildings: readonly Pick<Building, 'id' | 'name'>[],
): Map<string, Pick<Building, 'id' | 'name'>> {
  return new Map(buildings.map((building) => [building.id, building]));
}

/**
 * Day of week, 1 = Monday ... 7 = Sunday, for an instant in a time zone. Without a zone it uses
 * the device's own, so nothing is hardcoded. Returns 0 if the browser gives an unexpected name.
 */
export function todayDayNumber(now: Date, timeZone?: string): number {
  const name = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone }).format(now);
  const index = SHORT_DAYS.indexOf(name);
  return index === -1 ? 0 : index + 1;
}

export function isToday(group: Pick<DayGroup, 'day'>, now: Date, timeZone?: string): boolean {
  return group.day === todayDayNumber(now, timeZone);
}

/** What an empty timetable says. A sync in progress takes priority, as on the other screens. */
export function timetableEmptyMessage(
  progress: { running: boolean; firstRun: boolean },
  text: string,
): string {
  return emptyMessage(progress, text);
}
