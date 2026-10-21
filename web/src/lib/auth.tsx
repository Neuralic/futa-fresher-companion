// The signed-in state for the whole app. Login is optional: nothing else depends on it.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { apiPost, onUnauthorized, request } from '../api/client';
import type { TokenResponse, User } from '../api/types';
import { tokenStore } from './session';

export type AuthStatus = 'loading' | 'signed-in' | 'signed-out';

interface AuthValue {
  status: AuthStatus;
  /** The current user from /auth/me. Null while loading, or if that call failed. */
  user: User | null;
  signIn(email: string, password: string): Promise<void>;
  signOut(): void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus>(() =>
    tokenStore.get() ? 'loading' : 'signed-out',
  );
  const [user, setUser] = useState<User | null>(null);

  // A saved token: ask the server who it belongs to. The server decides the role, not the token.
  useEffect(() => {
    if (!tokenStore.get()) return;
    let active = true;
    request<User>('GET', '/auth/me', { auth: true }).then(
      (me) => {
        if (!active) return;
        setUser(me);
        setStatus('signed-in');
      },
      () => {
        // A 401 has already signed the user out through onUnauthorized. Other errors keep
        // the token, so an offline visit does not log anyone out.
        if (active) setStatus(tokenStore.get() ? 'signed-in' : 'signed-out');
      },
    );
    return () => {
      active = false;
    };
  }, []);

  // Any authenticated call that gets a 401 signs the user out and sends them to log in.
  useEffect(
    () =>
      onUnauthorized(() => {
        setUser(null);
        setStatus('signed-out');
        navigate('/login');
      }),
    [navigate],
  );

  const signIn = useCallback(async (email: string, password: string) => {
    const token = await apiPost<TokenResponse>('/auth/login', { email, password });
    tokenStore.set(token.access_token);
    setStatus('signed-in');
    try {
      setUser(await request<User>('GET', '/auth/me', { auth: true }));
    } catch {
      // Logged in, but the profile could not be loaded now. It is retried on the next visit.
      setUser(null);
    }
  }, []);

  const signOut = useCallback(() => {
    // There is no logout endpoint. Clearing the token ends the session on this device.
    tokenStore.clear();
    setUser(null);
    setStatus('signed-out');
  }, []);

  const value = useMemo(() => ({ status, user, signIn, signOut }), [status, user, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
