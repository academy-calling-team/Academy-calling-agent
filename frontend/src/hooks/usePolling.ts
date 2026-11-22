import { useEffect, useRef } from 'react';
import { active } from '../lib/inquiry-model';

export function usePolling({
  enabled,
  intervalMs = 5000,
  errorIntervalMs = 15000,
  hasError,
  onTick,
}: {
  enabled: boolean;
  intervalMs?: number;
  errorIntervalMs?: number;
  hasError?: boolean;
  onTick: () => void | Promise<void>;
}) {
  const tickRef = useRef(onTick);
  tickRef.current = onTick;

  useEffect(() => {
    if (!enabled) return;
    let timer = 0;
    let cancelled = false;
    const schedule = () => {
      if (cancelled) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(async () => {
        if (cancelled) return;
        if (document.hidden) {
          schedule();
          return;
        }
        await tickRef.current();
        schedule();
      }, hasError ? errorIntervalMs : intervalMs);
    };
    schedule();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, intervalMs, errorIntervalMs, hasError]);
}

export function shouldPollList(statuses: string[]) {
  return statuses.some(active);
}

export function shouldPollDetail(status?: string) {
  return status ? active(status) : false;
}
