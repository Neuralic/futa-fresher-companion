// Workbox route matchers. Workbox copies each function into dist/sw.js as plain text
// (Function.prototype.toString), so every function here must be self-contained:
// no imports, no variables from outside the function. sw-matchers.test.ts checks this.

/** Announcements: freshness matters most, so they are NetworkFirst. */
export function isAnnouncementsRequest({ url }: { url: URL }): boolean {
  const announcements = '/api/v1/announcements';
  return url.pathname.startsWith(announcements);
}

/**
 * Public API reads (departments, lecturers, buildings...): StaleWhileRevalidate.
 * Auth, admin and sync are never cached.
 */
export function isCacheablePublicApi({ url }: { url: URL }): boolean {
  const api = '/api/v1/';
  return (
    url.pathname.startsWith(api) &&
    !url.pathname.startsWith(api + 'auth') &&
    !url.pathname.startsWith(api + 'admin') &&
    !url.pathname.startsWith(api + 'sync')
  );
}
