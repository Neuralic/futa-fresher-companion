import { lazy, Suspense, useEffect } from 'react';
import { Link, Route, Routes } from 'react-router-dom';
import FirstSyncScreen from './components/FirstSyncScreen';
import OfflineBanner from './components/OfflineBanner';
import SyncNotice from './components/SyncNotice';
import { dismissFirstSync, showFirstSyncScreen, useSyncView } from './lib/syncStatus';
import Announcements from './pages/Announcements';
import Home from './pages/Home';
import Login from './pages/Login';

// Heavy / rarely used screens are lazy-loaded to protect the first-load budget.
// The Academics screens read the offline cache (Dexie), so they load on demand too.
const MapPage = lazy(() => import('./pages/MapPage'));
const Admin = lazy(() => import('./pages/Admin'));
const Academics = lazy(() => import('./pages/Academics'));
const FacultyDepartments = lazy(() => import('./pages/FacultyDepartments'));

// The offline store (Dexie) is loaded on demand, so it stays out of the first load.
function retrySync() {
  import('./lib/offline')
    .then((m) => m.syncReferenceData())
    .catch(() => {});
}

export default function App() {
  const sync = useSyncView();
  const firstSync = showFirstSyncScreen(sync);

  useEffect(() => {
    // Prime the offline cache in the background. Fails silently when offline / API not ready.
    if (navigator.onLine) retrySync();
    // Retry when the connection comes back, so a failed sync does not wait for a reload.
    window.addEventListener('online', retrySync);
    return () => window.removeEventListener('online', retrySync);
  }, []);

  return (
    <>
      <OfflineBanner />
      <nav>
        <Link to="/">Home</Link>
        <Link to="/map">Map</Link>
        <Link to="/academics">Academics</Link>
        <Link to="/announcements">Announcements</Link>
        <Link to="/login">Login</Link>
      </nav>
      <SyncNotice onRetry={retrySync} />
      <main>
        {firstSync ? (
          <FirstSyncScreen progress={sync.progress} onContinue={dismissFirstSync} />
        ) : (
          <Suspense fallback={<p className="muted">Loading…</p>}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/map" element={<MapPage />} />
              <Route path="/academics" element={<Academics />} />
              <Route path="/academics/:facultyId" element={<FacultyDepartments />} />
              <Route path="/announcements" element={<Announcements />} />
              <Route path="/login" element={<Login />} />
              <Route path="/admin" element={<Admin />} />
            </Routes>
          </Suspense>
        )}
      </main>
    </>
  );
}
