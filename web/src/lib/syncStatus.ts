// Sync progress for the UI. A tiny module, so App can import it without loading Dexie.
import { useSyncExternalStore } from 'react';
import type { SyncProgress } from './sync';

const IDLE: SyncProgress = { running: false, firstRun: false, pages: 0, rows: 0 };
let current: SyncProgress = IDLE;
const listeners = new Set<() => void>();

export function setSyncProgress(next: SyncProgress): void {
  current = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useSyncProgress(): SyncProgress {
  return useSyncExternalStore(subscribe, () => current);
}
