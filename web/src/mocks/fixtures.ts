// Sample data ONLY for building the UI before the backend exists. Not real FUTA data.
import type {
  Announcement,
  Building,
  Course,
  Department,
  Faculty,
  Lecturer,
  TimetableEntry,
} from '../api/types';

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

export const departments: Department[] = [
  {
    id: '00000000-0000-4000-8000-000000000011',
    faculty_id: '00000000-0000-4000-8000-000000000001',
    name: 'Sample Department of Biology',
    short_name: 'SBIO',
    hod_name: 'Prof. Sample Head',
    office_location: 'Sample Block A, Room 2',
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000012',
    faculty_id: '00000000-0000-4000-8000-000000000001',
    name: 'Sample Department of Chemistry',
    short_name: null,
    hod_name: null,
    office_location: null,
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000013',
    faculty_id: '00000000-0000-4000-8000-000000000002',
    name: 'Sample Department of Electrical Engineering',
    short_name: 'SEEE',
    hod_name: null,
    office_location: null,
    verification: unverified,
    updated_at: now,
  },
];

export const lecturers: Lecturer[] = [
  {
    id: '00000000-0000-4000-8000-000000000021',
    department_id: '00000000-0000-4000-8000-000000000011',
    full_name: 'Sample Lecturer Two',
    title: 'Dr.',
    rank: 'Senior Lecturer',
    email: null,
    office_location: 'Sample Block A, Room 5',
    specialization: null,
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000020',
    department_id: '00000000-0000-4000-8000-000000000011',
    full_name: 'Sample Lecturer One',
    title: null,
    rank: null,
    email: 'sample.one@example.edu.ng',
    office_location: null,
    specialization: null,
    verification: unverified,
    updated_at: now,
  },
];

export const courses: Course[] = [
  {
    id: '00000000-0000-4000-8000-000000000031',
    department_id: '00000000-0000-4000-8000-000000000011',
    code: 'SBI 201',
    title: 'Sample Cell Biology',
    units: 3,
    level: 200,
    semester: 1,
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000030',
    department_id: '00000000-0000-4000-8000-000000000011',
    code: 'SBI 101',
    title: 'Sample Introduction to Biology',
    units: 2,
    level: 100,
    semester: 1,
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000032',
    department_id: '00000000-0000-4000-8000-000000000011',
    code: 'SBI 110',
    title: 'Sample Laboratory Practice',
    units: 1,
    level: 100,
    semester: 2,
    verification: unverified,
    updated_at: now,
  },
];

export const timetableEntries: TimetableEntry[] = [
  {
    id: '00000000-0000-4000-8000-000000000041',
    department_id: '00000000-0000-4000-8000-000000000011',
    level: 100,
    semester: 1,
    course_id: '00000000-0000-4000-8000-000000000030',
    day_of_week: 1,
    start_time: '08:00',
    end_time: '10:00',
    venue_building_id: '00000000-0000-4000-8000-000000000101',
    venue_note: null,
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000042',
    department_id: '00000000-0000-4000-8000-000000000011',
    level: 100,
    semester: 2,
    course_id: '00000000-0000-4000-8000-000000000032',
    day_of_week: 3,
    start_time: '14:00',
    end_time: '16:00',
    venue_building_id: null,
    venue_note: 'Sample Lab 2, ground floor',
    verification: unverified,
    updated_at: now,
  },
  {
    id: '00000000-0000-4000-8000-000000000043',
    department_id: '00000000-0000-4000-8000-000000000011',
    level: 200,
    semester: 1,
    course_id: '00000000-0000-4000-8000-000000000031',
    day_of_week: 2,
    start_time: '10:00',
    end_time: '12:00',
    venue_building_id: null,
    venue_note: null,
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
