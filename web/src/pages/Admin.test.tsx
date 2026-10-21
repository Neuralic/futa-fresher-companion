import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User, UserRole } from '../api/types';
import type { AuthStatus } from '../lib/auth';

// The page is rendered once, as the server would, so only what shows first is checked.
// Auth is faked, and the offline cache is replaced with a fixed answer.
const auth: { status: AuthStatus; user: User | null } = { status: 'signed-out', user: null };
vi.mock('../lib/auth', () => ({ useAuth: () => auth }));
vi.mock('../lib/offline', () => ({ readComposerChoices: async () => ({}) }));
vi.mock('../lib/useCachedRows', () => ({
  useCachedRows: () => ({
    result: {
      state: 'ready',
      value: {
        faculties: [{ id: 'f1', name: 'Science' }],
        departments: [{ id: 'd1', faculty_id: 'f1', name: 'Biology' }],
      },
    },
    retry: () => {},
    progress: {},
  }),
}));

import Admin from './Admin';

function page(): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <Admin />
    </MemoryRouter>,
  );
}

function signedInAs(role: UserRole, extra: Partial<User> = {}) {
  auth.status = 'signed-in';
  auth.user = { id: 'u1', full_name: 'A', email: 'a@b.co', role, ...extra };
}

beforeEach(() => {
  auth.status = 'signed-out';
  auth.user = null;
});

describe('the Admin page gate', () => {
  it('asks a signed-out visitor to log in, with a link, and shows no form', () => {
    const html = page();
    expect(html).toContain('Log in to continue');
    expect(html).toContain('href="/login"');
    expect(html).not.toContain('<form');
  });

  it('says "Admins only" to a student and shows no form', () => {
    signedInAs('student');
    const html = page();
    expect(html).toContain('Admins only');
    expect(html).not.toContain('<form');
  });

  it('says "Admins only" to a class rep', () => {
    signedInAs('class_rep');
    expect(page()).toContain('Admins only');
  });

  it('shows nothing to act on while the profile is loading or missing', () => {
    auth.status = 'loading';
    expect(page()).not.toContain('<form');
    auth.status = 'signed-in';
    expect(page()).not.toContain('<form');
  });
});

describe('the composer for admins', () => {
  it('gives a super admin all four scopes', () => {
    signedInAs('super_admin');
    const html = page();
    expect(html).toContain('<form');
    for (const label of ['Whole university', 'SUG', 'One faculty', 'One department']) {
      expect(html).toContain(`>${label}</option>`);
    }
  });

  it('gives SUG only the SUG scope', () => {
    signedInAs('sug');
    const html = page();
    expect(html).toContain('>SUG</option>');
    expect(html).not.toContain('Whole university');
    expect(html).not.toContain('One faculty');
    expect(html).not.toContain('ann-target');
  });

  it('locks a department admin to their own department', () => {
    signedInAs('department_admin', { department_id: 'd1' });
    const html = page();
    expect(html).not.toContain('One faculty');
    expect(html).toMatch(/<select id="ann-target"[^>]*disabled/);
    expect(html).toContain('>Biology</option>');
  });

  it('shows a live character count for title and body', () => {
    signedInAs('super_admin');
    const html = page();
    expect(html).toContain('0 / 200 characters');
    expect(html).toContain('0 / 4000 characters');
  });
});
