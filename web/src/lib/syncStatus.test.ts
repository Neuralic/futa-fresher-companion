import { describe, expect, it } from 'vitest';
import type { SyncResponse } from '../api/types';
import { runSync, type PageStore, type SyncProgress, type SyncQuery } from './sync';
import {
  dismissFirstSync,
  getSyncView,
  setSyncProgress,
  showFirstSyncScreen,
  type SyncView,
} from './syncStatus';

const SERVER_TIME = '2026-10-20T10:00:00.000Z';

function makePage(overrides: Partial<SyncResponse> = {}): SyncResponse {
  return {
    server_time: SERVER_TIME,
    full: false,
    next_cursor: null,
    faculties: [],
    departments: [],
    lecturers: [],
    courses: [],
    class_reps: [],
    buildings: [],
    timetable_entries: [],
    announcements: [],
    deleted: {},
    ...overrides,
  };
}

function simpleStore(): PageStore & { lastSync: () => string | undefined } {
  const meta = new Map<string, string>();
  return {
    async getMeta(key) {
      return meta.get(key);
    },
    async deleteMeta(key) {
      meta.delete(key);
    },
    async applyPage(write) {
      if (write.cursor) meta.set('sync_cursor', write.cursor);
      else meta.delete('sync_cursor');
      if (write.lastSync) meta.set('last_sync', write.lastSync);
    },
    lastSync: () => meta.get('last_sync'),
  };
}

function view(progress: Partial<SyncProgress>, dismissed = false): SyncView {
  return {
    progress: { running: false, failed: false, firstRun: false, pages: 0, rows: 0, ...progress },
    dismissed,
  };
}

describe('showFirstSyncScreen', () => {
  it('shows only while a first sync is running and not dismissed', () => {
    expect(showFirstSyncScreen(view({ running: true, firstRun: true }))).toBe(true);
    expect(showFirstSyncScreen(view({ running: true, firstRun: true }, true))).toBe(false);
    expect(showFirstSyncScreen(view({ running: false, firstRun: true }))).toBe(false);
    expect(showFirstSyncScreen(view({ running: true, firstRun: false }))).toBe(false);
  });
});

describe('dismissal', () => {
  it('hides the screen for the session, and the sync keeps running to the end', async () => {
    const store = simpleStore();
    const shownBeforeDismiss: boolean[] = [];
    const fetchPage = async (query: SyncQuery): Promise<SyncResponse> => {
      if (!query.cursor) {
        // The screen is up while the first page is being fetched.
        shownBeforeDismiss.push(showFirstSyncScreen(getSyncView()));
        return makePage({ full: true, next_cursor: 'c1' });
      }
      // The user taps "Continue without saving" while the second page is being fetched.
      dismissFirstSync();
      return makePage();
    };

    await runSync({ store, fetchPage, onProgress: setSyncProgress });

    expect(shownBeforeDismiss).toEqual([true]);
    expect(store.lastSync()).toBe(SERVER_TIME);
    expect(getSyncView().progress).toMatchObject({ running: false, failed: false, pages: 2 });
    expect(getSyncView().dismissed).toBe(true);
    expect(showFirstSyncScreen(getSyncView())).toBe(false);
  });
});
