// Sample data ONLY for building the UI before the backend exists. Not real FUTA data.
import type { Announcement, Building, Faculty } from '../api/types';

const now = new Date().toISOString();
const unverified = { status: 'unverified' as const, source: 'sample data' };

export const faculties: Faculty[] = [
  {
    id: '00000000-0000-4000-8000-000000000001',
    name: 'Sample Faculty of Science',
    short_name: 'SOS',
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000002',
    name: 'Sample Faculty of Engineering',
    short_name: 'SEET',
    verification: unverified,
    updated_at: now,
  },
];

export const buildings: Building[] = [
  {
    id: '00000000-0000-4000-8000-000000000101',
    name: 'Sample Main Gate',
    type: 'gate',
    description: null,
    lat: 7.3011,
    lng: 5.1366,
    verification: unverified,
    updated_at: now,
  },
];

export const announcements: Announcement[] = [
  {
    id: '00000000-0000-4000-8000-000000000201',
    title: 'Welcome, freshers (sample)',
    body: 'This is placeholder content from src/mocks/fixtures.ts.',
    scope: 'university',
    author_id: '00000000-0000-4000-8000-000000000301',
    published_at: now,
    verification: { status: 'verified', source: 'sample data' },
    updated_at: now,
  },
];
