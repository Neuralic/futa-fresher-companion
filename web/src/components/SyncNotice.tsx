import { useSyncView } from '../lib/syncStatus';

// A small message after a failed sync. It does not block the page. The browser's online
// event also retries the sync, so the button is for when the user wants to retry now.
export default function SyncNotice({ onRetry }: { onRetry: () => void }) {
  const { progress } = useSyncView();
  if (!progress.failed || progress.running) return null;

  return (
    <div className="banner sync-notice" role="status">
      <span>Couldn't finish saving. We'll try again when your connection improves.</span>{' '}
      <button type="button" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
