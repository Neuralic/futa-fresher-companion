import { Link } from 'react-router-dom';
import VerificationNote from '../components/VerificationNote';
import { emptyMessage } from '../lib/academicsView';
import { readFaculties } from '../lib/offline';
import { useCachedRows } from '../lib/useCachedRows';

// Reads only the offline cache, so this list works without a connection.
export default function Academics() {
  const { result, retry, progress } = useCachedRows(readFaculties);

  return (
    <>
      <h1>Academics</h1>
      <p className="muted">Schools at FUTA. Choose one to see its departments.</p>

      {result.state === 'loading' && (
        <p role="status" className="muted">
          Loading schools…
        </p>
      )}

      {result.state === 'error' && (
        <div role="alert">
          <p>Could not read the saved schools on this device.</p>
          <button type="button" onClick={retry}>
            Try again
          </button>
        </div>
      )}

      {result.state === 'ready' && result.value.length === 0 && (
        <p className="muted" role="status">
          {emptyMessage(progress, 'No schools saved yet')}
        </p>
      )}

      {result.state === 'ready' && result.value.length > 0 && (
        <ul className="items">
          {result.value.map((faculty) => (
            <li key={faculty.id}>
              <Link to={`/academics/${faculty.id}`}>{faculty.name}</Link>
              {faculty.short_name && <span className="muted"> ({faculty.short_name})</span>}
              <VerificationNote
                verification={faculty.verification}
                updatedAt={faculty.updated_at}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
