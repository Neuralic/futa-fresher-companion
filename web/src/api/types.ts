// Types come from docs/openapi.yaml via `npm run gen:api` (src/api/schema.d.ts).
// Do not hand-write API shapes.
import type { components } from './schema';

type S = components['schemas'];

export type Faculty = S['Faculty'];
export type Department = S['Department'];
export type Lecturer = S['Lecturer'];
export type Course = S['Course'];
export type ClassRep = S['ClassRep'];
export type Building = S['Building'];
export type TimetableEntry = S['TimetableEntry'];
export type Announcement = S['Announcement'];
export type User = S['User'];
export type SyncResponse = S['SyncResponse'];
