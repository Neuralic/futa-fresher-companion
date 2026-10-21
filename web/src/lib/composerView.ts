// Pure logic for the admin announcement composer. No React, Dexie or storage imports.
import { ApiError } from '../api/client';
import type {
  AnnouncementCreate,
  AnnouncementScope,
  Department,
  Faculty,
  User,
  UserRole,
} from '../api/types';
import { sortByName } from './academicsView';
import type { AuthStatus } from './auth';
import { friendlyError, type FieldErrors } from './authView';

export const TITLE_MIN = 3;
export const TITLE_MAX = 200;
export const BODY_MIN = 1;
export const BODY_MAX = 4000;

export const ADMIN_ROLES: readonly UserRole[] = [
  'super_admin',
  'sug',
  'faculty_admin',
  'department_admin',
];

export function isAdminRole(role: UserRole | undefined): boolean {
  return role !== undefined && ADMIN_ROLES.includes(role);
}

/** What the page shows for the current sign-in state. The role is the server's, from /auth/me. */
export type AdminGate = 'loading' | 'signed-out' | 'no-profile' | 'forbidden' | 'allowed';

export function adminGate(status: AuthStatus, user: User | null): AdminGate {
  if (status === 'loading') return 'loading';
  if (status === 'signed-out') return 'signed-out';
  // Signed in, but /auth/me has not answered. Without a role we cannot tell, so we do not guess.
  if (!user) return 'no-profile';
  return isAdminRole(user.role) ? 'allowed' : 'forbidden';
}

export const SCOPE_LABELS: Record<AnnouncementScope, string> = {
  university: 'Whole university',
  sug: 'SUG',
  faculty: 'One faculty',
  department: 'One department',
};

// The same rules as the server's publish check. The server still decides; this only keeps
// the form from offering a choice that would be refused.
export function scopesForRole(role: UserRole): AnnouncementScope[] {
  switch (role) {
    case 'super_admin':
      return ['university', 'sug', 'faculty', 'department'];
    case 'sug':
      return ['sug'];
    case 'faculty_admin':
      return ['faculty', 'department'];
    case 'department_admin':
      return ['department'];
    default:
      return [];
  }
}

export interface TargetPicker {
  field: 'faculty_id' | 'department_id';
  label: string;
  options: { id: string; name: string }[];
  /** True when the user cannot change it: it is their own faculty or department. */
  locked: boolean;
  /** The id to start with. Empty when the user has to choose. */
  selectedId: string;
  /** Set when this account cannot publish for the scope at all. */
  problem?: string;
}

const UNSAVED_NAME = 'name not saved on this device';

/**
 * The faculty or department picker for a scope, built from cached rows only.
 * Null when the scope needs no target (university, SUG).
 */
export function targetPicker(
  user: User,
  scope: AnnouncementScope,
  faculties: readonly Faculty[],
  departments: readonly Department[],
): TargetPicker | null {
  if (scope === 'faculty') {
    const base = { field: 'faculty_id' as const, label: 'Faculty' };
    if (user.role === 'super_admin') {
      return { ...base, options: sortByName(faculties), locked: false, selectedId: '' };
    }
    const own = user.faculty_id;
    if (!own) return { ...base, options: [], locked: true, selectedId: '', problem: NO_FACULTY };
    const name = faculties.find((f) => f.id === own)?.name ?? `Your faculty (${UNSAVED_NAME})`;
    return { ...base, options: [{ id: own, name }], locked: true, selectedId: own };
  }

  if (scope === 'department') {
    const base = { field: 'department_id' as const, label: 'Department' };
    if (user.role === 'super_admin') {
      return { ...base, options: sortByName(departments), locked: false, selectedId: '' };
    }
    if (user.role === 'faculty_admin') {
      const own = user.faculty_id;
      if (!own) return { ...base, options: [], locked: true, selectedId: '', problem: NO_FACULTY };
      const options = sortByName(departments.filter((d) => d.faculty_id === own));
      return { ...base, options, locked: false, selectedId: '' };
    }
    const own = user.department_id;
    if (!own) {
      return { ...base, options: [], locked: true, selectedId: '', problem: NO_DEPARTMENT };
    }
    const name = departments.find((d) => d.id === own)?.name ?? `Your department (${UNSAVED_NAME})`;
    return { ...base, options: [{ id: own, name }], locked: true, selectedId: own };
  }

  return null;
}

const NO_FACULTY = 'Your account has no faculty set, so you cannot publish here. Ask a super admin.';
const NO_DEPARTMENT =
  'Your account has no department set, so you cannot publish here. Ask a super admin.';

/** Characters the way the server counts them (code points), so the limits match. */
export function charCount(text: string): number {
  return Array.from(text.trim()).length;
}

/**
 * A datetime-local value ("2026-11-02T09:30", the device's own time) as an ISO time with the
 * device's UTC offset, e.g. "2026-11-02T09:30:00+01:00". Null when it is not a real time.
 */
export function expiryToIso(local: string): string | null {
  const date = new Date(local);
  if (!local || Number.isNaN(date.getTime())) return null;
  const pad = (n: number) => String(Math.trunc(Math.abs(n))).padStart(2, '0');
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
    `${sign}${pad(offset / 60)}:${pad(offset % 60)}`
  );
}

export interface ComposerValues {
  title: string;
  body: string;
  scope: AnnouncementScope;
  /** The chosen faculty or department id. Empty when none is chosen. */
  targetId: string;
  /** A datetime-local value, or empty for no expiry. */
  expires: string;
}

export type ComposerField = 'title' | 'body' | 'scope' | 'target' | 'expires';

export function validateAnnouncement(
  values: ComposerValues,
  role: UserRole,
  now: number,
): FieldErrors<ComposerField> {
  const errors: FieldErrors<ComposerField> = {};

  const titleLength = charCount(values.title);
  if (titleLength < TITLE_MIN) errors.title = `The title needs at least ${TITLE_MIN} characters.`;
  else if (titleLength > TITLE_MAX) errors.title = `The title can be at most ${TITLE_MAX} characters.`;

  const bodyLength = charCount(values.body);
  if (bodyLength < BODY_MIN) errors.body = 'Write the announcement.';
  else if (bodyLength > BODY_MAX) errors.body = `The text can be at most ${BODY_MAX} characters.`;

  if (!scopesForRole(role).includes(values.scope)) {
    errors.scope = 'Your role cannot publish for this scope.';
  } else if (
    (values.scope === 'faculty' || values.scope === 'department') &&
    !values.targetId
  ) {
    errors.target = `Choose a ${values.scope}.`;
  }

  if (values.expires) {
    const iso = expiryToIso(values.expires);
    if (!iso) errors.expires = 'Enter a valid date and time.';
    else if (Date.parse(iso) <= now) errors.expires = 'The expiry must be in the future.';
  }

  return errors;
}

/** The request body. Only the id that matches the scope is sent; blank expiry is left out. */
export function buildAnnouncement(values: ComposerValues): AnnouncementCreate {
  const expiresAt = values.expires ? expiryToIso(values.expires) : null;
  return {
    title: values.title.trim(),
    body: values.body.trim(),
    scope: values.scope,
    ...(values.scope === 'faculty' ? { faculty_id: values.targetId } : {}),
    ...(values.scope === 'department' ? { department_id: values.targetId } : {}),
    ...(expiresAt ? { expires_at: expiresAt } : {}),
  };
}

/**
 * Friendly text for a failed publish. A 401 has already signed the user out (the client does
 * that), so its text is only a fallback. Everything else shares the wording used elsewhere.
 */
export function publishError(error: unknown, online: boolean): string {
  if (online && error instanceof ApiError) {
    if (error.status === 401) return 'Your session has ended. Log in again to publish.';
    if (error.status === 403) return 'You cannot publish for this scope.';
  }
  return friendlyError(error, online);
}
