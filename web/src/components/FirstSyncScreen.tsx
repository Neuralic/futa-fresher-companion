import type { SyncProgress } from '../lib/sync';

// Shown only while the first full sync runs, so a new user knows why the app is busy.
export default function FirstSyncScreen({ progress }: { progress: SyncProgress }) {
  return (
    <section className="first-sync" aria-labelledby="first-sync-title">
      <h1 id="first-sync-title">Saving campus data for offline use</h1>
      <p className="muted">This happens once. Keep this page open until it finishes.</p>
      {/* No value: the server does not say how many pages a full sync has, so the bar is
          indeterminate. The count below is the real progress. */}
      <progress aria-label="Saving campus data for offline use" />
      <p role="status">{progress.rows} items saved so far</p>
    </section>
  );
}
