export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export type MockFault = 'normal' | 'loading' | 'error';

let mockMode = false;
let mockFault: MockFault = 'normal';
let mockHandler: ((path: string, init?: RequestInit & { headers?: Record<string, string> }, fault?: MockFault) => Promise<unknown>) | null = null;
let sessionEpoch = 0;

export function getMockMode() {
  return mockMode;
}

export function setMockMode(enabled: boolean, handler?: typeof mockHandler) {
  mockMode = enabled;
  mockHandler = handler || null;
}

export function setMockFault(fault: MockFault) {
  mockFault = fault;
}

export function getMockFault() {
  return mockFault;
}

export function bumpSessionEpoch() {
  sessionEpoch += 1;
}

export function getSessionEpoch() {
  return sessionEpoch;
}

export async function api<T = unknown>(url: string, init: RequestInit & { headers?: Record<string, string> } = {}): Promise<T> {
  if (mockMode && mockHandler) {
    return mockHandler(url, init, mockFault) as Promise<T>;
  }
  const requestEpoch = sessionEpoch;
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      cache: 'no-store',
      signal: AbortSignal.timeout(12000),
    });
  } catch {
    throw new ApiError(
      '상담 서비스 응답이 지연되거나 연결이 끊겼습니다. 다시 시도해 주세요.',
      0,
    );
  }
  const data = (await response.json().catch(() => ({
    message: '응답 내용을 확인할 수 없습니다.',
  }))) as T & { message?: string };

  if (!response.ok) {
    if (response.status === 401 && requestEpoch === sessionEpoch) {
      sessionEpoch += 1;
    }
    throw new ApiError(data.message || '요청을 처리할 수 없습니다.', response.status);
  }
  return data;
}
