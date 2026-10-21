import { lazy, Suspense, useEffect } from 'react';
import { Link, Route, Routes, useNavigate } from 'react-router-dom';
import FirstSyncScreen from './components/FirstSyncScreen';
import OfflineBanner from './components/OfflineBanner';
import SyncNotice from './components/SyncNotice';
import { dismissFirstSync, showFirstSyncScreen, useSyncView } from './lib/syncStatus';
import Home from './pages/Home';
import { useAuth } from './lib/auth';
import { isAdminRole } from './lib/composerView';

// Heavy / rarely used screens are lazy-loaded to protect the first-load budget.
// The Academics screens read the offline cache (Dexie), so they load on demand too.
const MapPage = lazy(() => import('./pages/MapPage'));
const Admin = lazy(() => import('./pages/Admin'));
const Academics = lazy(() => import('./pages/Academics'));
const FacultyDepartments = lazy(() => import('./pages/FacultyDepartments'));
const DepartmentDetail = lazy(() => import('./pages/DepartmentDetail'));
const Timetable = lazy(() => import('./pages/Timetable'));
// Login and sign-up are optional, so they load only when opened.
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
// Reads the offline cache, so it loads on demand too.
const Announcements = lazy(() => import('./pages/Announcements'));

// The offline store (Dexie) is loaded on demand, so it stays out of the first load.
function retrySync() {
  import('./lib/offline')
    .then((m) => m.syncReferenceData())
    .catch(() => {});
}

export default function App() {
  const sync = useSyncView();
  const firstSync = showFirstSyncScreen(sync);
  const auth = useAuth();
  const navigate = useNavigate();

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
        {isAdminRole(auth.user?.role) && <Link to="/admin">Admin</Link>}
        {auth.status === 'signed-in' ? (
          <button
            type="button"
            className="nav-button"
            onClick={() => {
              auth.signOut();
              navigate('/');
            }}
          >
            Log out
          </button>
        ) : (
          <Link to="/login">Log in</Link>
        )}
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
              <Route
                path="/academics/:facultyId/:departmentId"
                element={<DepartmentDetail />}
              />
              <Route
                path="/academics/:facultyId/:departmentId/timetable"
                element={<Timetable />}
              />
              <Route path="/announcements" element={<Announcements />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/admin" element={<Admin />} />
            </Routes>
          </Suspense>
        )}
      </main>
    </>
  );
}
