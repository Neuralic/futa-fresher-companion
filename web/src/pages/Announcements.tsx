import { useEffect, useState } from 'react';
import { apiGet } from '../api/client';
import type { Announcement } from '../api/types';

export default function Announcements() {
  const [items, setItems] = useState<Announcement[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Announcement[]>('/announcements', { limit: 20 })
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <>
      <h1>Announcements</h1>
      {error && <p className="muted">Could not load: {error}</p>}
      {items.map((a) => (
        <article key={a.id}>
          <h3>{a.title}</h3>
          <p>{a.body}</p>
          <small className="muted">
            {a.verification.status}
            {a.verification.source ? ` · ${a.verification.source}` : ''}
          </small>
        </article>
      ))}
    </>
  );
}
