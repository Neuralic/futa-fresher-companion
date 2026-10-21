import { describe, expect, it } from 'vitest';
import type { Announcement } from '../api/types';
import {
  announcementsEmptyMessage,
  announcementsForDisplay,
  formatPublished,
  namesById,
  NO_ANNOUNCEMENTS_MESSAGE,
  OFFLINE_EMPTY_MESSAGE,
  previewText,
  scopeLabel,
  sortNewestFirst,
} from './announcementsView';
import { SAVING_MESSAGE } from './academicsView';

const NOW = Date.parse('2026-10-21T12:00:00.000Z');
const HOUR = 60 * 60 * 1000;

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    title: 'Registration opens',
    body: 'Register on the portal.',
    scope: 'university',
    faculty_id: null,
    department_id: null,
    author_id: '00000000-0000-4000-8000-0000000000aa',
    published_at: '2026-10-20T09:00:00.000Z',
    expires_at: null,
    verification: { status: 'verified', source: 'Registrar notice' },
    updated_at: '2026-10-20T09:00:00.000Z',
    ...overrides,
  };
}

describe('announcementsForDisplay: expired items', () => {
  it('hides an announcement whose expiry has passed', () => {
    const expired = announcement({
      id: 'a',
      expires_at: new Date(NOW - HOUR).toISOString(),
    });

    expect(announcementsForDisplay([expired], NOW)).toEqual([]);
  });

  it('keeps an announcement with no expiry, and one that expires later', () => {
    const open = announcement({ id: 'open', expires_at: null });
    const later = announcement({ id: 'later', expires_at: new Date(NOW + HOUR).toISOString() });

    expect(announcementsForDisplay([open, later], NOW).map((a) => a.id).sort()).toEqual([
      'later',
      'open',
    ]);
  });

  it('keeps expired rows in the input (they are hidden, not deleted)', () => {
    const rows = [announcement({ id: 'x', expires_at: new Date(NOW - HOUR).toISOString() })];

    announcementsForDisplay(rows, NOW);

    expect(rows).toHaveLength(1);
  });
});

describe('ordering', () => {
  it('sorts newest published first', () => {
    const older = announcement({ id: 'older', published_at: '2026-10-18T09:00:00.000Z' });
    const newest = announcement({ id: 'newest', published_at: '2026-10-21T08:00:00.000Z' });
    const middle = announcement({ id: 'middle', published_at: '2026-10-19T09:00:00.000Z' });

    expect(sortNewestFirst([older, newest, middle]).map((a) => a.id)).toEqual([
      'newest',
      'middle',
      'older',
    ]);
  });

  it('breaks equal publish times by id, larger first, the same order as the API', () => {
    const low = announcement({ id: '00000000-0000-4000-8000-000000000001' });
    const high = announcement({ id: '00000000-0000-4000-8000-000000000009' });

    expect(sortNewestFirst([low, high]).map((a) => a.id)).toEqual([high.id, low.id]);
  });

  it('does not change the input order', () => {
    const rows = [
      announcement({ id: 'a', published_at: '2026-10-18T00:00:00.000Z' }),
      announcement({ id: 'b', published_at: '2026-10-21T00:00:00.000Z' }),
    ];

    sortNewestFirst(rows);

    expect(rows.map((r) => r.id)).toEqual(['a', 'b']);
  });
});

describe('scopeLabel', () => {
  const faculties = namesById([{ id: 'f-eng', name: 'School of Engineering' }]);
  const departments = namesById([{ id: 'd-csc', name: 'Computer Science' }]);

  it('labels university and SUG announcements', () => {
    expect(scopeLabel(announcement({ scope: 'university' }), faculties, departments)).toBe(
      'University',
    );
    expect(scopeLabel(announcement({ scope: 'sug' }), faculties, departments)).toBe('SUG');
  });

  it('names the faculty from the cache', () => {
    const item = announcement({ scope: 'faculty', faculty_id: 'f-eng' });

    expect(scopeLabel(item, faculties, departments)).toBe('Faculty · School of Engineering');
  });

  it('names the department from the cache', () => {
    const item = announcement({ scope: 'department', department_id: 'd-csc' });

    expect(scopeLabel(item, faculties, departments)).toBe('Department · Computer Science');
  });

  it('says so when the name is not in the cache, instead of showing an id', () => {
    const item = announcement({ scope: 'faculty', faculty_id: 'f-unknown' });

    const label = scopeLabel(item, faculties, departments);
    expect(label).toBe('Faculty · name not available on this device');
    expect(label).not.toContain('f-unknown');
  });
});

describe('formatPublished', () => {
  it('shows the Nigerian date with the word Published', () => {
    expect(formatPublished('2026-10-20T23:30:00Z')).toBe('Published 21 Oct 2026');
  });

  it('does not invent a date for a value that is not a date', () => {
    expect(formatPublished('nope')).toBe('Published date unknown');
  });
});

describe('announcementsEmptyMessage', () => {
  it('says the list is coming while the first sync runs', () => {
    expect(announcementsEmptyMessage({ running: true, firstRun: true }, true)).toBe(
      SAVING_MESSAGE,
    );
  });

  it('explains an empty cache when offline', () => {
    expect(announcementsEmptyMessage({ running: false, firstRun: true }, false)).toBe(
      OFFLINE_EMPTY_MESSAGE,
    );
    expect(OFFLINE_EMPTY_MESSAGE).toContain('offline');
  });

  it('says there is nothing right now when online and nothing is saved', () => {
    expect(announcementsEmptyMessage({ running: false, firstRun: false }, true)).toBe(
      NO_ANNOUNCEMENTS_MESSAGE,
    );
  });
});

describe('previewText', () => {
  it('leaves a short body as it is', () => {
    expect(previewText('Short body.', 140)).toBe('Short body.');
  });

  it('cuts a long body and adds an ellipsis', () => {
    const preview = previewText('a'.repeat(200), 140);

    expect(preview).toBe(`${'a'.repeat(140)}…`);
  });

  it('counts characters, not UTF-16 units, so an emoji is not split', () => {
    const body = '😀'.repeat(10);

    expect(previewText(body, 5)).toBe(`${'😀'.repeat(5)}…`);
  });

  it('keeps HTML as plain text. Nothing here parses it.', () => {
    const body = '<img src=x onerror="alert(1)"><b>bold</b>';

    expect(previewText(body)).toBe(body);
  });
});
