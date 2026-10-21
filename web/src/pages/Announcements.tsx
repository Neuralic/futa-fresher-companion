import { useEffect, useMemo, useState } from 'react';
import VerificationNote from '../components/VerificationNote';
import {
  announcementsEmptyMessage,
  announcementsForDisplay,
  formatPublished,
  namesById,
  previewText,
  scopeLabel,
} from '../lib/announcementsView';
import { readAnnouncementsScreen } from '../lib/offline';
import { useCachedRows } from '../lib/useCachedRows';

function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);
  return online;
}

// Reads only the offline cache. Text is rendered as text: no HTML is ever interpreted.
export default function Announcements() {
  const { result, retry, progress } = useCachedRows(readAnnouncementsScreen);
  const online = useOnline();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());

  const view = useMemo(() => {
    if (result.state !== 'ready') return null;
    const { announcements, faculties, departments } = result.value;
    return {
      items: announcementsForDisplay(announcements, Date.now()),
      facultyNames: namesById(faculties),
      departmentNames: namesById(departments),
    };
  }, [result]);

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <>
      <h1>Announcements</h1>

      {result.state === 'loading' && (
        <p role="status" className="muted">
          Loading announcements…
        </p>
      )}

      {result.state === 'error' && (
        <div role="alert">
          <p>Could not read the saved announcements on this device.</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      )}

      {view && view.items.length === 0 && (
        <p className="muted" role="status">
          {announcementsEmptyMessage(progress, online)}
        </p>
      )}

      {view && view.items.length > 0 && (
        <ul className="items">
          {view.items.map((item) => {
            const isOpen = expanded.has(item.id);
            const bodyId = `announcement-body-${item.id}`;
            return (
              <li key={item.id}>
                <h2 className="announcement-title">
                  <button
                    type="button"
                    className="announcement-toggle"
                    aria-expanded={isOpen}
                    aria-controls={bodyId}
                    onClick={() => toggle(item.id)}
                  >
                    {item.title}
                  </button>
                </h2>
                <p className="muted">
                  {scopeLabel(item, view.facultyNames, view.departmentNames)} ·{' '}
                  {formatPublished(item.published_at)}
                </p>
                <p id={bodyId} className="announcement-body">
                  {isOpen ? item.body : previewText(item.body)}
                </p>
                <VerificationNote verification={item.verification} updatedAt={item.updated_at} />
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
