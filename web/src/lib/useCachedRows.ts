import { useEffect, useState } from 'react';
import type { SyncProgress } from './sync';
import { useSyncView } from './syncStatus';

export type CacheResult<T> =
  | { state: 'loading' }
  | { state: 'error' }
  | { state: 'ready'; value: T };

/**
 * Reads from the offline cache, and reads again whenever a sync page lands or a sync ends,
 * so a list fills in while the first sync runs. A screen that remounts (use a key per item)
 * starts from loading again.
 */
export function useCachedRows<T>(read: () => Promise<T>): {
  result: CacheResult<T>;
  retry: () => void;
  progress: SyncProgress;
} {
  const { progress } = useSyncView();
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<CacheResult<T>>({ state: 'loading' });

  useEffect(() => {
    let active = true;
    read().then(
      (value) => {
        if (active) setResult({ state: 'ready', value });
      },
      () => {
        if (active) setResult({ state: 'error' });
      },
    );
    return () => {
      active = false;
    };
    // The read is the same for the life of this screen. Re-run on retry and on sync progress
    // only. Callers that change the query remount the screen with a key.
  }, [attempt, progress.running, progress.pages]);

  const retry = () => {
    setResult({ state: 'loading' });
    setAttempt((n) => n + 1);
  };

  return { result, retry, progress };
}
