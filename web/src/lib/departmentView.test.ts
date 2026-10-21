import { describe, expect, it } from 'vitest';
import type { Course, Department, Lecturer } from '../api/types';
import {
  COURSES_EMPTY,
  DEPARTMENT_NOT_FOUND,
  groupCoursesByLevel,
  LECTURERS_EMPTY,
  lecturerDisplayName,
  levelHeading,
  liveRows,
  resolveDepartment,
  sectionEmptyMessage,
  sortLecturers,
  unitsText,
} from './departmentView';
import { SAVING_MESSAGE } from './academicsView';

const FACULTY = '11111111-1111-4111-8111-111111111111';
const OTHER_FACULTY = '22222222-2222-4222-8222-222222222222';
const DEPT = '33333333-3333-4333-8333-333333333333';
const STAMP = '2026-10-20T09:00:00.000Z';
const VERIFICATION = { status: 'verified' as const, source: 'Department notice board' };

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

function lecturer(overrides: Partial<Lecturer> & { id: string }): Lecturer {
  return {
    department_id: DEPT,
    full_name: 'Adaeze Okafor',
    title: null,
    rank: null,
    email: null,
    office_location: null,
    specialization: null,
    verification: VERIFICATION,
    updated_at: STAMP,
    ...overrides,
  };
}

function department(overrides: Partial<Department> = {}): Department {
  return {
    id: DEPT,
    faculty_id: FACULTY,
    name: 'Computer Science',
    short_name: 'CSC',
    hod_name: null,
    office_location: null,
    verification: VERIFICATION,
    updated_at: STAMP,
    ...overrides,
  };
}

describe('groupCoursesByLevel', () => {
  it('groups by level, lowest level first', () => {
    const groups = groupCoursesByLevel([
      course({ id: 'c3', code: 'CSC 301', level: 300 }),
      course({ id: 'c1', code: 'CSC 101', level: 100 }),
      course({ id: 'c2', code: 'CSC 201', level: 200 }),
    ]);

    expect(groups.map((g) => g.level)).toEqual([100, 200, 300]);
    expect(groups.map((g) => g.courses.length)).toEqual([1, 1, 1]);
  });

  it('keeps every course in the group for its own level', () => {
    const groups = groupCoursesByLevel([
      course({ id: 'a', code: 'CSC 101', level: 100 }),
      course({ id: 'b', code: 'CSC 102', level: 100 }),
      course({ id: 'c', code: 'CSC 201', level: 200 }),
    ]);

    expect(groups[0].courses.map((c) => c.id)).toEqual(['a', 'b']);
    expect(groups[1].courses.map((c) => c.id)).toEqual(['c']);
  });

  it('gives no groups for an empty list', () => {
    expect(groupCoursesByLevel([])).toEqual([]);
  });

  it('sorts courses inside a level by code, with numbers in order', () => {
    const groups = groupCoursesByLevel([
      course({ id: 'ten', code: 'CSC 110', level: 100 }),
      course({ id: 'two', code: 'CSC 102', level: 100 }),
      course({ id: 'one', code: 'CSC 101', level: 100 }),
    ]);

    expect(groups[0].courses.map((c) => c.code)).toEqual(['CSC 101', 'CSC 102', 'CSC 110']);
  });

  it('does not change the input order', () => {
    const input = [course({ id: 'b', code: 'CSC 102' }), course({ id: 'a', code: 'CSC 101' })];

    groupCoursesByLevel(input);

    expect(input.map((c) => c.code)).toEqual(['CSC 102', 'CSC 101']);
  });

  it('hides soft-deleted courses', () => {
    const groups = groupCoursesByLevel([
      course({ id: 'live', code: 'CSC 101' }),
      { ...course({ id: 'gone', code: 'CSC 102' }), deleted_at: STAMP } as Course,
    ]);

    expect(groups[0].courses.map((c) => c.id)).toEqual(['live']);
  });
});

describe('level and units text', () => {
  it('names each level', () => {
    expect(levelHeading(100)).toBe('100 Level');
    expect(levelHeading(500)).toBe('500 Level');
  });

  it('uses the right word for the number of units', () => {
    expect(unitsText(1)).toBe('1 unit');
    expect(unitsText(3)).toBe('3 units');
    expect(unitsText(0)).toBe('0 units');
  });
});

describe('sortLecturers and names', () => {
  it('sorts lecturers by name, ignoring case', () => {
    const sorted = sortLecturers([
      lecturer({ id: 'z', full_name: 'Zainab Musa' }),
      lecturer({ id: 'a', full_name: 'adaeze okafor' }),
      lecturer({ id: 'm', full_name: 'Mohammed Bello' }),
    ]);

    expect(sorted.map((l) => l.full_name)).toEqual([
      'adaeze okafor',
      'Mohammed Bello',
      'Zainab Musa',
    ]);
  });

  it('hides soft-deleted lecturers', () => {
    const sorted = sortLecturers([
      lecturer({ id: 'live', full_name: 'Live Person' }),
      { ...lecturer({ id: 'gone', full_name: 'Gone Person' }), deleted_at: STAMP } as Lecturer,
    ]);

    expect(sorted.map((l) => l.id)).toEqual(['live']);
  });

  it('puts the title in front of the name when there is one', () => {
    expect(lecturerDisplayName({ title: 'Dr.', full_name: 'Adaeze Okafor' })).toBe(
      'Dr. Adaeze Okafor',
    );
    expect(lecturerDisplayName({ title: null, full_name: 'Adaeze Okafor' })).toBe(
      'Adaeze Okafor',
    );
  });
});

describe('liveRows', () => {
  it('drops any row whose deleted_at is set, and keeps the rest', () => {
    const rows = [
      { id: 'a', deleted_at: null },
      { id: 'b' },
      { id: 'c', deleted_at: STAMP },
    ];

    expect(liveRows(rows).map((r) => r.id)).toEqual(['a', 'b']);
  });
});

describe('empty states', () => {
  it('says courses have not been added when nothing is cached', () => {
    expect(sectionEmptyMessage({ running: false, firstRun: false }, COURSES_EMPTY)).toBe(
      'Courses for this department have not been added yet.',
    );
  });

  it('says lecturers have not been added when nothing is cached', () => {
    expect(sectionEmptyMessage({ running: false, firstRun: false }, LECTURERS_EMPTY)).toBe(
      'Lecturers for this department have not been added yet.',
    );
  });

  it('says the list is coming while the first sync runs', () => {
    expect(sectionEmptyMessage({ running: true, firstRun: true }, COURSES_EMPTY)).toBe(
      SAVING_MESSAGE,
    );
  });
});

describe('not found', () => {
  it('is not found when the department is not in the cache', () => {
    expect(resolveDepartment(undefined, FACULTY)).toBeNull();
    expect(sectionEmptyMessage({ running: false, firstRun: false }, DEPARTMENT_NOT_FOUND)).toBe(
      'This department is not saved on this device.',
    );
  });

  it('is not found when the department belongs to another school', () => {
    expect(resolveDepartment(department({ faculty_id: OTHER_FACULTY }), FACULTY)).toBeNull();
  });

  it('is not found when the department is soft-deleted', () => {
    const gone = { ...department(), deleted_at: STAMP } as Department;

    expect(resolveDepartment(gone, FACULTY)).toBeNull();
  });

  it('returns the department when it is live and in the right school', () => {
    expect(resolveDepartment(department(), FACULTY)?.name).toBe('Computer Science');
  });
});
