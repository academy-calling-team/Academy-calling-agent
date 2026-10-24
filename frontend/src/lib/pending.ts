import type { SubmissionKey } from './inquiry-model';

const PENDING_KEY = 'hakwon:pending-inquiry';

export interface PendingInquiry {
  owner: string;
  mode: 'mock' | 'backend';
  fingerprint: string;
  key: string;
}

export function clearPending() {
  try {
    sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* ignore */
  }
}

export function readPending(owner: string | undefined, mode: 'mock' | 'backend'): PendingInquiry | null {
  if (!owner) return null;
  try {
    const stored = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null') as PendingInquiry | null;
    if (stored?.owner === owner && stored.mode === mode) return stored;
  } catch {
    /* ignore */
  }
  return null;
}

export function writePending(owner: string, mode: 'mock' | 'backend', submission: SubmissionKey) {
  const entry: PendingInquiry = {
    owner,
    mode,
    fingerprint: submission.fingerprint,
    key: submission.key,
  };
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify(entry));
  } catch {
    /* ignore */
  }
}
