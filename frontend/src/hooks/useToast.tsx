import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { api, getSessionEpoch } from '../lib/api';

export interface ToastApi {
  show: (text: string) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [text, setText] = useState('');
  const timer = useRef<number>(0);

  const show = useCallback((message: string) => {
    setText(message);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setText(''), 3500);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div id="toast" role="status" className={text ? 'visible' : ''}>
        {text}
      </div>
    </ToastContext.Provider>
  );
}

export type LoadState = 'idle' | 'loading' | 'ready' | 'error';

export async function fetchWithEpoch<T>(
  fn: () => Promise<T>,
  epoch: number,
): Promise<{ ok: true; data: T } | { ok: false; stale: true } | { ok: false; stale: false; error: Error }> {
  try {
    const data = await fn();
    if (epoch !== getSessionEpoch()) return { ok: false, stale: true };
    return { ok: true, data };
  } catch (error) {
    if (epoch !== getSessionEpoch()) return { ok: false, stale: true };
    return { ok: false, stale: false, error: error as Error };
  }
}

export { api };
