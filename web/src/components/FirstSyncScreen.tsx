import type { SyncProgress } from '../lib/sync';

// Shown only while the first full sync runs. The user can continue without waiting.
export default function FirstSyncScreen({
  progress,
  onContinue,
}: {
  progress: SyncProgress;
  onContinue: () => void;
}) {
  return (
    <section className="first-sync" aria-labelledby="first-sync-title">
      <h1 id="first-sync-title">Saving campus data for offline use</h1>
      <p className="muted">
        This happens once. You can keep using the app while it finishes in the background.
      </p>
      {/* No value: the server does not say how many pages a full sync has, so the bar is
          indeterminate. The count below is the real progress. */}
      <progress aria-label="Saving campus data for offline use" />
      <p role="status">{progress.rows} items saved so far</p>
      <button type="button" onClick={onContinue}>
        Continue without saving
      </button>
    </section>
  );
}
