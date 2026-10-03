import { lazy, Suspense, useEffect } from 'react';
import { Link, Route, Routes } from 'react-router-dom';
import OfflineBanner from './components/OfflineBanner';
import Academics from './pages/Academics';
import Announcements from './pages/Announcements';
import Home from './pages/Home';
import Login from './pages/Login';

// Heavy / rarely used screens are lazy-loaded to protect the first-load budget.
const MapPage = lazy(() => import('./pages/MapPage'));
const Admin = lazy(() => import('./pages/Admin'));

export default function App() {
  useEffect(() => {
    // Prime the offline cache in the background. Fails silently when offline / API not ready.
    if (navigator.onLine) {
      import('./lib/offline').then((m) => m.syncReferenceData()).catch(() => {});
    }
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
      <main>
        <Suspense fallback={<p className="muted">Loading…</p>}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/academics" element={<Academics />} />
            <Route path="/announcements" element={<Announcements />} />
            <Route path="/login" element={<Login />} />
            <Route path="/admin" element={<Admin />} />
          </Routes>
        </Suspense>
      </main>
    </>
  );
}
