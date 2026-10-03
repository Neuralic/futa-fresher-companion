import { useEffect, useState } from 'react';
import { apiGet } from '../api/client';
import type { Faculty } from '../api/types';

export default function Academics() {
  const [faculties, setFaculties] = useState<Faculty[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Faculty[]>('/faculties')
      .then(setFaculties)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <>
      <h1>Academics</h1>
      {error && <p className="muted">Could not load: {error}</p>}
      <ul>
        {faculties.map((f) => (
          <li key={f.id}>{f.name}</li>
        ))}
      </ul>
    </>
  );
}
