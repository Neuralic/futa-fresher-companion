// Pure helpers for the Announcements screen. No Dexie or React imports, so Vitest can run them.
import type { Announcement } from '../api/types';
import { formatDay, SAVING_MESSAGE } from './academicsView';
import { notExpired } from './visibility';

/** Rows the device should show now: not expired, newest first. Expired rows stay in the cache. */
export function announcementsForDisplay(rows: readonly Announcement[], now: number): Announcement[] {
  return sortNewestFirst(notExpired(rows, now));
}

function publishedTime(row: Announcement): number {
  const time = Date.parse(row.published_at);
  return Number.isNaN(time) ? 0 : time;
}

/** Newest published first. Equal times put the larger id first, the same order as the API. */
export function sortNewestFirst(rows: readonly Announcement[]): Announcement[] {
  return [...rows].sort((a, b) => {
    const byTime = publishedTime(b) - publishedTime(a);
    if (byTime !== 0) return byTime;
    return b.id.localeCompare(a.id);
  });
}

/** Maps id to name, for looking up a school or department name from the cache. */
export function namesById(rows: readonly { id: string; name: string }[]): Map<string, string> {
  return new Map(rows.map((row) => [row.id, row.name]));
}

const NAME_UNKNOWN = 'name not available on this device';

/** Scope label as shown on each item. Names come from the cache; a missing one says so. */
export function scopeLabel(
  announcement: Announcement,
  faculties: ReadonlyMap<string, string>,
  departments: ReadonlyMap<string, string>,
): string {
  switch (announcement.scope) {
    case 'university':
      return 'University';
    case 'sug':
      return 'SUG';
    case 'faculty':
      return `Faculty · ${faculties.get(announcement.faculty_id ?? '') ?? NAME_UNKNOWN}`;
    case 'department':
      return `Department · ${departments.get(announcement.department_id ?? '') ?? NAME_UNKNOWN}`;
    default:
      return 'Announcement';
  }
}

export function formatPublished(iso: string): string {
  const day = formatDay(iso);
  return day ? `Published ${day}` : 'Published date unknown';
}

/** The first part of a body, for the collapsed item. Counts characters, not UTF-16 units. */
export function previewText(body: string, maxChars = 140): string {
  const chars = Array.from(body);
  if (chars.length <= maxChars) return body;
  return `${chars.slice(0, maxChars).join('').trimEnd()}…`;
}

export const OFFLINE_EMPTY_MESSAGE =
  "You're offline and no announcements are saved on this device yet. They will appear after you are online and the app has synced.";
export const NO_ANNOUNCEMENTS_MESSAGE = 'No announcements right now.';

/** What an empty Announcements list says, depending on sync and connection. */
export function announcementsEmptyMessage(
  progress: { running: boolean; firstRun: boolean },
  online: boolean,
): string {
  if (progress.running && progress.firstRun) return SAVING_MESSAGE;
  if (!online) return OFFLINE_EMPTY_MESSAGE;
  return NO_ANNOUNCEMENTS_MESSAGE;
}
