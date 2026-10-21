import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import type { Department, Faculty, User, UserRole } from '../api/types';
import {
  adminGate,
  ADMIN_ROLES,
  buildAnnouncement,
  charCount,
  expiryToIso,
  publishError,
  scopesForRole,
  targetPicker,
  validateAnnouncement,
  type ComposerValues,
} from './composerView';

const verification = { status: 'unverified' as const };
const faculty = (id: string, name: string): Faculty => ({
  id,
  name,
  verification,
  updated_at: '2026-01-01T00:00:00Z',
});
const department = (id: string, name: string, faculty_id: string): Department => ({
  id,
  name,
  faculty_id,
  verification,
  updated_at: '2026-01-01T00:00:00Z',
});

const F1 = '00000000-0000-4000-8000-000000000001';
const F2 = '00000000-0000-4000-8000-000000000002';
const D1 = '00000000-0000-4000-8000-000000000011';
const D2 = '00000000-0000-4000-8000-000000000012';
const D3 = '00000000-0000-4000-8000-000000000013';

const faculties = [faculty(F2, 'Engineering'), faculty(F1, 'Science')];
const departments = [
  department(D3, 'Physics', F1),
  department(D1, 'Biology', F1),
  department(D2, 'Civil', F2),
];

function user(role: UserRole, extra: Partial<User> = {}): User {
  return { id: 'u1', full_name: 'A', email: 'a@b.co', role, ...extra };
}

const NOW = Date.parse('2026-06-01T12:00:00Z');
const valid: ComposerValues = {
  title: 'Exam timetable',
  body: 'The timetable is out.',
  scope: 'university',
  targetId: '',
  expires: '',
};

describe('which roles may open the composer', () => {
  it('lists exactly the four admin roles', () => {
    expect([...ADMIN_ROLES].sort()).toEqual(
      ['department_admin', 'faculty_admin', 'sug', 'super_admin'].sort(),
    );
  });

  it('is signed-out, forbidden or allowed from the auth state alone', () => {
    expect(adminGate('loading', null)).toBe('loading');
    expect(adminGate('signed-out', null)).toBe('signed-out');
    expect(adminGate('signed-in', null)).toBe('no-profile');
    expect(adminGate('signed-in', user('student'))).toBe('forbidden');
    expect(adminGate('signed-in', user('class_rep'))).toBe('forbidden');
    for (const role of ADMIN_ROLES) expect(adminGate('signed-in', user(role))).toBe('allowed');
  });
});

describe('scopesForRole', () => {
  it('matches what each role may publish', () => {
    expect(scopesForRole('super_admin')).toEqual(['university', 'sug', 'faculty', 'department']);
    expect(scopesForRole('sug')).toEqual(['sug']);
    expect(scopesForRole('faculty_admin')).toEqual(['faculty', 'department']);
    expect(scopesForRole('department_admin')).toEqual(['department']);
  });

  it('gives students and class reps nothing', () => {
    expect(scopesForRole('student')).toEqual([]);
    expect(scopesForRole('class_rep')).toEqual([]);
  });
});

describe('targetPicker', () => {
  it('has no picker for university or SUG', () => {
    expect(targetPicker(user('super_admin'), 'university', faculties, departments)).toBeNull();
    expect(targetPicker(user('sug'), 'sug', faculties, departments)).toBeNull();
  });

  it('lets a super admin choose from every cached faculty and department, A to Z', () => {
    const f = targetPicker(user('super_admin'), 'faculty', faculties, departments)!;
    expect(f.locked).toBe(false);
    expect(f.options.map((o) => o.name)).toEqual(['Engineering', 'Science']);
    const d = targetPicker(user('super_admin'), 'department', faculties, departments)!;
    expect(d.options.map((o) => o.name)).toEqual(['Biology', 'Civil', 'Physics']);
  });

  it('locks a faculty admin to their own faculty', () => {
    const picker = targetPicker(user('faculty_admin', { faculty_id: F1 }), 'faculty', faculties, departments)!;
    expect(picker).toMatchObject({ field: 'faculty_id', locked: true, selectedId: F1 });
    expect(picker.options).toEqual([{ id: F1, name: 'Science' }]);
  });

  it('shows a faculty admin only departments of their own faculty', () => {
    const picker = targetPicker(user('faculty_admin', { faculty_id: F1 }), 'department', faculties, departments)!;
    expect(picker.locked).toBe(false);
    expect(picker.options.map((o) => o.id)).toEqual([D1, D3]);
  });

  it('locks a department admin to their own department', () => {
    const picker = targetPicker(user('department_admin', { department_id: D2 }), 'department', faculties, departments)!;
    expect(picker).toMatchObject({ field: 'department_id', locked: true, selectedId: D2 });
    expect(picker.options).toEqual([{ id: D2, name: 'Civil' }]);
  });

  it('still locks to the own id when the name is not in the cache', () => {
    const picker = targetPicker(user('department_admin', { department_id: D2 }), 'department', [], [])!;
    expect(picker.selectedId).toBe(D2);
    expect(picker.options[0].name).toContain('not saved on this device');
  });

  it('reports a problem when a scoped account has no faculty or department', () => {
    expect(targetPicker(user('faculty_admin'), 'faculty', faculties, departments)!.problem).toBeTruthy();
    expect(targetPicker(user('faculty_admin'), 'department', faculties, departments)!.problem).toBeTruthy();
    expect(targetPicker(user('department_admin'), 'department', faculties, departments)!.problem).toBeTruthy();
  });
});

describe('charCount', () => {
  it('counts code points after trimming, like the server', () => {
    expect(charCount('  abc  ')).toBe(3);
    expect(charCount('😀😀')).toBe(2);
  });
});

describe('expiryToIso', () => {
  it('returns an ISO time with a UTC offset for the same moment', () => {
    const iso = expiryToIso('2026-11-02T09:30')!;
    expect(iso).toMatch(/^2026-11-02T09:30:00[+-]\d{2}:\d{2}$/);
    expect(Date.parse(iso)).toBe(new Date('2026-11-02T09:30').getTime());
  });

  it('returns null for empty or unreal input', () => {
    expect(expiryToIso('')).toBeNull();
    expect(expiryToIso('not a date')).toBeNull();
  });
});

describe('validateAnnouncement', () => {
  it('accepts a valid university announcement from a super admin', () => {
    expect(validateAnnouncement(valid, 'super_admin', NOW)).toEqual({});
  });

  it('checks the title length, 3 to 200', () => {
    expect(validateAnnouncement({ ...valid, title: 'ab' }, 'super_admin', NOW).title).toBeTruthy();
    expect(validateAnnouncement({ ...valid, title: '  ab  ' }, 'super_admin', NOW).title).toBeTruthy();
    expect(validateAnnouncement({ ...valid, title: 'abc' }, 'super_admin', NOW).title).toBeUndefined();
    expect(validateAnnouncement({ ...valid, title: 'a'.repeat(200) }, 'super_admin', NOW).title).toBeUndefined();
    expect(validateAnnouncement({ ...valid, title: 'a'.repeat(201) }, 'super_admin', NOW).title).toBeTruthy();
  });

  it('checks the body length, 1 to 4000', () => {
    expect(validateAnnouncement({ ...valid, body: '   ' }, 'super_admin', NOW).body).toBeTruthy();
    expect(validateAnnouncement({ ...valid, body: 'a'.repeat(4000) }, 'super_admin', NOW).body).toBeUndefined();
    expect(validateAnnouncement({ ...valid, body: 'a'.repeat(4001) }, 'super_admin', NOW).body).toBeTruthy();
  });

  it('refuses a scope the role cannot publish', () => {
    expect(validateAnnouncement({ ...valid, scope: 'university' }, 'sug', NOW).scope).toBeTruthy();
    expect(validateAnnouncement({ ...valid, scope: 'sug' }, 'sug', NOW).scope).toBeUndefined();
    expect(validateAnnouncement({ ...valid, scope: 'faculty', targetId: F1 }, 'department_admin', NOW).scope).toBeTruthy();
  });

  it('needs a faculty or department for those scopes', () => {
    expect(validateAnnouncement({ ...valid, scope: 'faculty' }, 'super_admin', NOW).target).toBeTruthy();
    expect(validateAnnouncement({ ...valid, scope: 'department' }, 'super_admin', NOW).target).toBeTruthy();
    expect(validateAnnouncement({ ...valid, scope: 'department', targetId: D1 }, 'super_admin', NOW).target).toBeUndefined();
  });

  it('needs an expiry in the future', () => {
    const past = validateAnnouncement({ ...valid, expires: '2000-01-01T00:00' }, 'super_admin', NOW);
    expect(past.expires).toBeTruthy();
    const future = validateAnnouncement({ ...valid, expires: '2999-01-01T00:00' }, 'super_admin', NOW);
    expect(future.expires).toBeUndefined();
    const junk = validateAnnouncement({ ...valid, expires: 'soon' }, 'super_admin', NOW);
    expect(junk.expires).toBeTruthy();
  });
});

describe('buildAnnouncement', () => {
  it('trims, and leaves out ids and expiry that do not apply', () => {
    expect(buildAnnouncement({ ...valid, title: ' Exam timetable ', targetId: F1 })).toEqual({
      title: 'Exam timetable',
      body: 'The timetable is out.',
      scope: 'university',
    });
  });

  it('sends only the id that matches the scope', () => {
    expect(buildAnnouncement({ ...valid, scope: 'faculty', targetId: F1 })).toMatchObject({
      scope: 'faculty',
      faculty_id: F1,
    });
    const department = buildAnnouncement({ ...valid, scope: 'department', targetId: D1 });
    expect(department).toMatchObject({ scope: 'department', department_id: D1 });
    expect(department).not.toHaveProperty('faculty_id');
  });

  it('sends the expiry as an ISO time with a time zone', () => {
    const sent = buildAnnouncement({ ...valid, expires: '2999-01-01T08:00' });
    expect(sent.expires_at).toMatch(/T08:00:00([+-]\d{2}:\d{2})$/);
  });
});

describe('publishError', () => {
  it('maps 401, 403, 422 and 503', () => {
    expect(publishError(new ApiError(401, 'x'), true)).toMatch(/Log in again/);
    expect(publishError(new ApiError(403, 'You cannot publish for this scope'), true)).toBe(
      'You cannot publish for this scope.',
    );
    expect(publishError(new ApiError(422, 'x'), true)).toMatch(/not valid/);
    expect(publishError(new ApiError(503, 'x', 5), true)).toMatch(/5 seconds/);
    expect(publishError(new ApiError(503, 'x'), true)).toMatch(/busy/);
  });

  it('says offline when offline, whatever the error', () => {
    expect(publishError(new ApiError(403, 'x'), false)).toMatch(/offline/);
  });

  it('handles a network failure and an unknown error', () => {
    expect(publishError(new TypeError('Failed to fetch'), true)).toMatch(/Could not reach/);
    expect(publishError(new ApiError(500, 'boom'), true)).toBe('Something went wrong. Try again.');
  });
});
