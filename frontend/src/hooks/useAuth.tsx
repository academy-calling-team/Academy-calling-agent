import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError, bumpSessionEpoch, setMockMode, type MockFault } from '../lib/api';
import { mockRequest } from '../lib/mock-inquiries';

export interface AccountUser {
  displayName: string;
  registered: boolean;
}

interface AuthState {
  ready: boolean;
  error: boolean;
  user: AccountUser | null;
  mode: 'backend' | 'mock';
  mockMode: boolean;
  mockFault: 'normal' | 'loading' | 'error';
  setMockFault: (f: MockFault) => void;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
  pendingLogin: string;
  setPendingLogin: (v: string) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  const [user, setUser] = useState<AccountUser | null>(null);
  const [mode, setMode] = useState<'backend' | 'mock'>('backend');
  const [mockFault, setMockFaultState] = useState<MockFault>('normal');
  const [pendingLogin, setPendingLogin] = useState('');
  const epochRef = useRef(0);

  const mockMode = useMemo(() => {
    const enabled = new URLSearchParams(window.location.search).get('preview') === 'mock';
    return enabled;
  }, []);

  useEffect(() => {
    if (mockMode) {
      setMockMode(true, mockRequest as never);
      setMode('mock');
    }
  }, [mockMode]);

  const reload = useCallback(async () => {
    bumpSessionEpoch();
    epochRef.current += 1;
    const epoch = epochRef.current;
    setReady(false);
    setError(false);
    setUser(null);
    try {
      if (mockMode) {
        if (epoch !== epochRef.current) return;
        setUser({ displayName: '미리보기 사용자', registered: true });
        setMode('mock');
        setReady(true);
        return;
      }
      const r = await fetch('/api/account', {
        cache: 'no-store',
        signal: AbortSignal.timeout(12000),
      });
      if (epoch !== epochRef.current) return;
      if (r.status !== 401 && !r.ok) throw new ApiError('계정 확인 실패', r.status);
      const data = (await r.json()) as { mode?: string; user: AccountUser | null };
      setMode(data.mode === 'mock' ? 'mock' : 'backend');
      setUser(data.user);
      setReady(true);
    } catch {
      if (epoch !== epochRef.current) return;
      setReady(true);
      setError(true);
    }
  }, [mockMode]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const logout = useCallback(async () => {
    if (mockMode) {
      bumpSessionEpoch();
      setUser(null);
      window.location.href = '/?preview=mock#/overview';
      return;
    }
    const response = await fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const data = (await response.json()) as { message?: string };
    if (!response.ok) throw new Error(data.message || '로그아웃할 수 없어요.');
    bumpSessionEpoch();
    setUser(null);
    window.location.hash = '#/login';
    window.location.reload();
  }, [mockMode]);

  const value: AuthState = {
    ready,
    error,
    user,
    mode,
    mockMode,
    mockFault,
    setMockFault: setMockFaultState,
    reload,
    logout,
    pendingLogin,
    setPendingLogin,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export async function submitBackendAuth(
  action: 'register' | 'login',
  payload: { login_name: string; password: string; terms_agreed?: boolean },
): Promise<void> {
  const response = await fetch('/api/auth/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = (await response.json()) as { message?: string };
  if (!response.ok) throw new Error(data.message || '요청을 처리할 수 없어요.');
}

export type { MockFault };
