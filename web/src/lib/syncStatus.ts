// Sync state for the UI. A tiny module, so App can import it without loading Dexie.
import { useSyncExternalStore } from 'react';
import type { SyncProgress } from './sync';

const DISMISS_KEY = 'futa-first-sync-dismissed';

export interface SyncView {
  progress: SyncProgress;
  /** The user chose "Continue without saving" in this browser session. */
  dismissed: boolean;
}

const IDLE: SyncProgress = { running: false, failed: false, firstRun: false, pages: 0, rows: 0 };
let view: SyncView = { progress: IDLE, dismissed: readDismissed() };
const listeners = new Set<() => void>();

function readDismissed(): boolean {
  try {
    return sessionStorage.getItem(DISMISS_KEY) === 'yes';
  } catch {
    // Storage can be blocked (for example in private mode). The choice then lasts until reload.
    return false;
  }
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

export function setSyncProgress(progress: SyncProgress): void {
  view = { ...view, progress };
  notify();
}

/** Hides the first-run screen for this session. The sync itself keeps running. */
export function dismissFirstSync(): void {
  view = { ...view, dismissed: true };
  try {
    sessionStorage.setItem(DISMISS_KEY, 'yes');
  } catch {
    // Not stored: the screen stays hidden until the page reloads.
  }
  notify();
}

/** The blocking first-run screen shows only during a first sync the user has not dismissed. */
export function showFirstSyncScreen(state: SyncView): boolean {
  return state.progress.running && state.progress.firstRun && !state.dismissed;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getSyncView(): SyncView {
  return view;
}

export function useSyncView(): SyncView {
  return useSyncExternalStore(subscribe, () => view);
}
