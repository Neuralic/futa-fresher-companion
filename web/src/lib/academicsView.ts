// Pure helpers for the Academics screens. No Dexie or React imports, so Vitest can run them.

/** How a row's verification status reads on screen. Text carries the meaning; the symbol is extra. */
const STATUS_LABELS: Record<string, { text: string; symbol: string }> = {
  verified: { text: 'Verified', symbol: '✓' },
  unverified: { text: 'Unverified', symbol: '○' },
  outdated: { text: 'May be outdated', symbol: '!' },
};

export function verificationLabel(status: string): { text: string; symbol: string } {
  return STATUS_LABELS[status] ?? { text: 'Status unknown', symbol: '?' };
}

// Nigerian local time, so an update late in the evening does not show as the next day.
const UPDATED_DATE = new Intl.DateTimeFormat('en-NG', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'Africa/Lagos',
});

/** "21 Oct 2026" in Nigerian local time, or null when the value is not a date. */
export function formatDay(iso: string): string | null {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? null : UPDATED_DATE.format(when);
}

export function formatUpdated(iso: string): string {
  const day = formatDay(iso);
  return day ? `Updated ${day}` : 'Updated date unknown';
}

const NAME_ORDER = new Intl.Collator('en', { sensitivity: 'base', numeric: true });

/** A copy sorted A to Z by name. Case and accents do not change the order; numbers sort naturally. */
export function sortByName<T extends { name: string }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => NAME_ORDER.compare(a.name, b.name));
}

export const SAVING_MESSAGE = 'Saving campus data, this list will appear shortly';

/**
 * What an empty list says. While the first full sync is running, the list is still filling
 * in, so say so. Otherwise say what is missing.
 */
export function emptyMessage(progress: { running: boolean; firstRun: boolean }, notSaved: string) {
  return progress.running && progress.firstRun ? SAVING_MESSAGE : notSaved;
}
