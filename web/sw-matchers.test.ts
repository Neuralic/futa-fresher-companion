import { describe, expect, it } from 'vitest';
import { isAnnouncementsRequest, isCacheablePublicApi } from './sw-matchers';

// Workbox writes each matcher into dist/sw.js as text. Rebuilding it with new Function gives
// the same text in an empty scope, so any outer variable it uses is undefined here, exactly
// as it would be in the service worker.
function detached<F extends (...args: never[]) => boolean>(matcher: F): F {
  return new Function(`return (${matcher.toString()});`)() as F;
}

const announcements = detached(isAnnouncementsRequest);
const publicApi = detached(isCacheablePublicApi);

function at(path: string): { url: URL } {
  return { url: new URL(path, 'https://app.test') };
}

describe('service worker matchers (run in an empty scope, like dist/sw.js)', () => {
  it('matches announcements, and only announcements', () => {
    expect(announcements(at('/api/v1/announcements'))).toBe(true);
    expect(announcements(at('/api/v1/announcements?limit=20'))).toBe(true);
    expect(announcements(at('/api/v1/faculties'))).toBe(false);
    expect(announcements(at('/api/v1/auth/login'))).toBe(false);
    expect(announcements(at('/academics'))).toBe(false);
  });

  it('caches public API reads, including announcements', () => {
    expect(publicApi(at('/api/v1/faculties'))).toBe(true);
    expect(publicApi(at('/api/v1/departments?faculty_id=abc'))).toBe(true);
    expect(publicApi(at('/api/v1/departments/1/lecturers'))).toBe(true);
    expect(publicApi(at('/api/v1/campus/buildings'))).toBe(true);
    expect(publicApi(at('/api/v1/announcements'))).toBe(true);
  });

  it('never caches auth, admin or sync', () => {
    expect(publicApi(at('/api/v1/auth/login'))).toBe(false);
    expect(publicApi(at('/api/v1/auth/me'))).toBe(false);
    expect(publicApi(at('/api/v1/admin/verify'))).toBe(false);
    expect(publicApi(at('/api/v1/sync?limit=500'))).toBe(false);
  });

  it('ignores paths outside the API', () => {
    expect(publicApi(at('/academics'))).toBe(false);
    expect(publicApi(at('/map'))).toBe(false);
    expect(publicApi(at('/api-docs/faculties'))).toBe(false);
  });

  it('gives the same answers as the imported functions', () => {
    const samples = [
      '/api/v1/faculties',
      '/api/v1/auth/login',
      '/api/v1/sync',
      '/api/v1/announcements',
      '/academics',
    ];
    for (const path of samples) {
      expect(announcements(at(path))).toBe(isAnnouncementsRequest(at(path)));
      expect(publicApi(at(path))).toBe(isCacheablePublicApi(at(path)));
    }
  });
});
