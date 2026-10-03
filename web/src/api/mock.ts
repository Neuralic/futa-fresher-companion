import { announcements, buildings, faculties } from '../mocks/fixtures';
import type { Query } from './client';

// Add a case here whenever the UI needs a new endpoint before the backend has it.
export async function mockRequest(method: string, path: string, _query?: Query): Promise<unknown> {
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
      return {
        server_time: new Date().toISOString(),
        full: true,
        faculties,
        departments: [],
        lecturers: [],
        courses: [],
        class_reps: [],
        buildings,
        timetable_entries: [],
        announcements,
        deleted: {},
      };
    default:
      throw new Error(`No mock for ${key}. Add it in src/api/mock.ts`);
  }
}
