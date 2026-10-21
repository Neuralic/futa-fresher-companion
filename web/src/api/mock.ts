import { announcements, buildings, departments, faculties } from '../mocks/fixtures';
import type { Query } from './client';

// Rows per /sync page in mock mode. 0 (the default) returns everything in one page.
// Set VITE_MOCK_SYNC_PAGE_SIZE to a small number to test paging without the backend.
const MOCK_SYNC_PAGE_SIZE = Number(import.meta.env.VITE_MOCK_SYNC_PAGE_SIZE ?? 0);
const SYNC_COLLECTIONS = [
  'faculties',
  'departments',
  'lecturers',
  'courses',
  'class_reps',
  'buildings',
  'timetable_entries',
  'announcements',
] as const;

// Add a case here whenever the UI needs a new endpoint before the backend has it.
export async function mockRequest(method: string, path: string, query?: Query): Promise<unknown> {
  await new Promise((r) => setTimeout(r, 150)); // feel like a real network
  const key = `${method} ${path}`;

  switch (key) {
    case 'GET /faculties':
      return faculties;
    case 'GET /campus/buildings':
      return buildings;
    case 'GET /announcements':
      return announcements;
    case 'GET /sync':
      return mockSync(query);
    default:
      throw new Error(`No mock for ${key}. Add it in src/api/mock.ts`);
  }
}

// Same rules as the API: rows in collection order, then in list order, cut into pages.
// The cursor is only an offset here, which is enough for mock data.
function mockSync(query: Query | undefined) {
  const data: Record<string, unknown[]> = {
    faculties,
    departments,
    lecturers: [],
    courses: [],
    class_reps: [],
    buildings,
    timetable_entries: [],
    announcements,
  };
  const items = SYNC_COLLECTIONS.flatMap((name) => data[name].map((row) => [name, row] as const));
  const start = query?.cursor ? Number(String(query.cursor).replace('mock:', '')) : 0;
  const size = MOCK_SYNC_PAGE_SIZE > 0 ? MOCK_SYNC_PAGE_SIZE : items.length;
  const end = start + size;

  const page: Record<string, unknown[]> = Object.fromEntries(
    SYNC_COLLECTIONS.map((name) => [name, []]),
  );
  for (const [name, row] of items.slice(start, end)) page[name].push(row);

  return {
    server_time: new Date().toISOString(),
    full: !query?.since && !query?.cursor,
    next_cursor: end < items.length ? `mock:${end}` : null,
    ...page,
    deleted: {},
  };
}
