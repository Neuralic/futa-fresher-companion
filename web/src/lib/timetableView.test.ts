import { describe, expect, it } from 'vitest';
import type { Building, Course, TimetableEntry } from '../api/types';
import {
  BUILDING_MISSING,
  buildingsById,
  chooseLevel,
  courseText,
  entriesForLevel,
  groupByDay,
  isToday,
  LEVEL_KEY,
  levelsWithEntries,
  loadRememberedLevel,
  rememberLevel,
  timeRange,
  timetableEmptyMessage,
  todayDayNumber,
  VENUE_MISSING,
  venueText,
} from './timetableView';
import { SAVING_MESSAGE } from './academicsView';

const DEPT = '33333333-3333-4333-8333-333333333333';
const COURSE = '44444444-4444-4444-8444-444444444444';
const BUILDING = '55555555-5555-4555-8555-555555555555';
const STAMP = '2026-10-20T09:00:00.000Z';
const VERIFICATION = { status: 'verified' as const, source: 'Timetable notice' };

function entry(overrides: Partial<TimetableEntry> & { id: string }): TimetableEntry {
  return {
    department_id: DEPT,
    level: 100,
    semester: 1,
    course_id: COURSE,
    day_of_week: 1,
    start_time: '08:00',
    end_time: '10:00',
    venue_building_id: null,
    venue_note: null,
    verification: VERIFICATION,
    updated_at: STAMP,
    ...overrides,
  };
}

function course(overrides: Partial<Course> & { id: string }): Course {
  return {
    department_id: DEPT,
    code: 'CSC 101',
    title: 'Introduction to Computing',
    units: 3,
    level: 100,
    semester: 1,
    verification: VERIFICATION,
    updated_at: STAMP,
    ...overrides,
  };
}

function building(overrides: Partial<Building> = {}): Building {
  return {
    id: BUILDING,
    name: 'Lecture Theatre 2',
    type: 'lecture_hall',
    description: null,
    lat: 7.296,
    lng: 5.145,
    verification: VERIFICATION,
    updated_at: STAMP,
    ...overrides,
  };
}

describe('groupByDay', () => {
  it('groups by day, Monday first', () => {
    const groups = groupByDay([
      entry({ id: 'wed', day_of_week: 3 }),
      entry({ id: 'mon', day_of_week: 1 }),
      entry({ id: 'fri', day_of_week: 5 }),
    ]);

    expect(groups.map((g) => g.label)).toEqual(['Monday', 'Wednesday', 'Friday']);
    expect(groups.map((g) => g.entries.length)).toEqual([1, 1, 1]);
  });

  it('shows Sunday only when there are Sunday entries', () => {
    const without = groupByDay([entry({ id: 'mon', day_of_week: 1 })]);
    const withSunday = groupByDay([
      entry({ id: 'mon', day_of_week: 1 }),
      entry({ id: 'sun', day_of_week: 7 }),
    ]);

    expect(without.map((g) => g.label)).toEqual(['Monday']);
    expect(withSunday.map((g) => g.label)).toEqual(['Monday', 'Sunday']);
  });

  it('names an unexpected day number plainly', () => {
    const groups = groupByDay([entry({ id: 'odd', day_of_week: 9 })]);

    expect(groups[0].label).toBe('Unknown day');
  });

  it('gives no groups for no entries', () => {
    expect(groupByDay([])).toEqual([]);
  });
});

describe('sorting by time', () => {
  it('sorts entries inside a day by start time', () => {
    const groups = groupByDay([
      entry({ id: 'late', start_time: '14:00', end_time: '16:00' }),
      entry({ id: 'early', start_time: '08:00', end_time: '10:00' }),
      entry({ id: 'mid', start_time: '11:00', end_time: '12:00' }),
    ]);

    expect(groups[0].entries.map((e) => e.start_time)).toEqual(['08:00', '11:00', '14:00']);
  });

  it('breaks equal start times by id', () => {
    const groups = groupByDay([
      entry({ id: 'b', start_time: '08:00' }),
      entry({ id: 'a', start_time: '08:00' }),
    ]);

    expect(groups[0].entries.map((e) => e.id)).toEqual(['a', 'b']);
  });

  it('formats the time range', () => {
    expect(timeRange({ start_time: '08:00', end_time: '10:00' })).toBe('08:00–10:00');
  });
});

describe('level filter and the remembered level', () => {
  const entries = [
    entry({ id: 'a', level: 200 }),
    entry({ id: 'b', level: 100 }),
    entry({ id: 'c', level: 200 }),
  ];

  it('lists only levels that have entries, lowest first, once each', () => {
    expect(levelsWithEntries(entries)).toEqual([100, 200]);
  });

  it('keeps only the entries of the chosen level', () => {
    expect(entriesForLevel(entries, 200).map((e) => e.id)).toEqual(['a', 'c']);
  });

  it('uses the remembered level when it still has entries', () => {
    expect(chooseLevel([100, 200], 200)).toBe(200);
  });

  it('falls back to the lowest level when the remembered one has no entries', () => {
    expect(chooseLevel([100, 200], 500)).toBe(100);
    expect(chooseLevel([100, 200], null)).toBe(100);
  });

  it('has no level when there are no entries', () => {
    expect(chooseLevel([], 100)).toBeNull();
  });

  it('reads a remembered level from storage, and ignores anything else', () => {
    expect(loadRememberedLevel({ getItem: () => '300' })).toBe(300);
    expect(loadRememberedLevel({ getItem: () => 'abc' })).toBeNull();
    expect(loadRememberedLevel({ getItem: () => null })).toBeNull();
    expect(loadRememberedLevel(undefined)).toBeNull();
  });

  it('treats blocked storage as no remembered level, without throwing', () => {
    const blocked = {
      getItem: () => {
        throw new DOMException('blocked', 'SecurityError');
      },
    };

    expect(loadRememberedLevel(blocked)).toBeNull();
  });

  it('writes the chosen level, and does not throw when storage is blocked', () => {
    const written: Record<string, string> = {};
    rememberLevel({ setItem: (key, value) => (written[key] = value) }, 300);

    expect(written[LEVEL_KEY]).toBe('300');
    expect(() =>
      rememberLevel(
        {
          setItem: () => {
            throw new DOMException('full', 'QuotaExceededError');
          },
        },
        200,
      ),
    ).not.toThrow();
  });
});

describe('course and venue fallbacks', () => {
  it('shows the course code and title from the cache', () => {
    expect(courseText(course({ id: COURSE, code: 'CSC 101', title: 'Intro' }))).toEqual({
      code: 'CSC 101',
      title: 'Intro',
    });
  });

  it('gives nothing when the course is not in the cache', () => {
    expect(courseText(undefined)).toBeNull();
  });

  it('shows the building name when it is linked and cached', () => {
    const buildings = buildingsById([building()]);

    expect(venueText(entry({ id: 'x', venue_building_id: BUILDING }), buildings)).toBe(
      'Lecture Theatre 2',
    );
  });

  it('adds the venue note after the building name', () => {
    const buildings = buildingsById([building()]);
    const item = entry({ id: 'x', venue_building_id: BUILDING, venue_note: 'Ground floor' });

    expect(venueText(item, buildings)).toBe('Lecture Theatre 2 · Ground floor');
  });

  it('says so when a linked building is not in the cache', () => {
    expect(venueText(entry({ id: 'x', venue_building_id: BUILDING }), buildingsById([]))).toBe(
      BUILDING_MISSING,
    );
  });

  it('uses the venue note when there is no building', () => {
    expect(venueText(entry({ id: 'x', venue_note: 'Room 4, Block C' }), buildingsById([]))).toBe(
      'Room 4, Block C',
    );
  });

  it('says the venue is not given when neither is set', () => {
    expect(venueText(entry({ id: 'x' }), buildingsById([]))).toBe(VENUE_MISSING);
  });
});

describe('deleted rows', () => {
  it('hides soft-deleted entries from the days, the levels and the level filter', () => {
    const entries = [
      entry({ id: 'live', level: 100, day_of_week: 1 }),
      { ...entry({ id: 'gone', level: 300, day_of_week: 2 }), deleted_at: STAMP } as TimetableEntry,
    ];

    expect(levelsWithEntries(entries)).toEqual([100]);
    expect(groupByDay(entries).map((g) => g.entries.map((e) => e.id))).toEqual([['live']]);
    expect(entriesForLevel(entries, 300)).toEqual([]);
  });
});

describe('today highlight', () => {
  // 2026-10-21 is a Wednesday. 2026-10-25 is a Sunday.
  it('gives the day number, Monday = 1 ... Sunday = 7', () => {
    expect(todayDayNumber(new Date('2026-10-21T10:00:00Z'), 'UTC')).toBe(3);
    expect(todayDayNumber(new Date('2026-10-25T10:00:00Z'), 'UTC')).toBe(7);
  });

  it('depends on the time zone: the same instant can be a different day', () => {
    // 23:30 UTC on Tuesday 20 October is 00:30 on Wednesday 21 October in Lagos (UTC+1).
    const instant = new Date('2026-10-20T23:30:00Z');

    expect(todayDayNumber(instant, 'UTC')).toBe(2);
    expect(todayDayNumber(instant, 'Africa/Lagos')).toBe(3);
  });

  it('highlights only the group for the current day', () => {
    const wednesday = { day: 3 };
    const monday = { day: 1 };
    const now = new Date('2026-10-21T10:00:00Z');

    expect(isToday(wednesday, now, 'UTC')).toBe(true);
    expect(isToday(monday, now, 'UTC')).toBe(false);
  });
});

describe('timetable empty state', () => {
  it('says the list is coming while the first sync runs', () => {
    expect(timetableEmptyMessage({ running: true, firstRun: true }, 'x')).toBe(SAVING_MESSAGE);
  });

  it('otherwise says what is missing', () => {
    expect(
      timetableEmptyMessage({ running: false, firstRun: false }, 'The timetable has not been added yet.'),
    ).toBe('The timetable has not been added yet.');
  });
});
