import { env } from 'cloudflare:workers';
import { cookies } from 'next/headers';
import { getChatGPTUser } from './chatgpt-auth';

export const SESSION_COOKIE = 'hakwon_backend_session';
export function backendUrl() {
  const value = (env as unknown as Record<string, unknown>).ACADEMY_BACKEND_URL;
  if (typeof value !== 'string' || !value.trim()) return null;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash)
    throw new Error('Invalid backend URL');
  return url.href.replace(/\/$/, '');
}
export async function sessionToken() { return (await cookies()).get(SESSION_COOKIE)?.value; }
export async function backendRequest(path: '/auth/register' | '/auth/login' | '/auth/logout' | '/auth/me', body?: unknown, token?: string) {
  const base = backendUrl();
  if (!base) throw new Error('Backend unavailable');
  return fetch(`${base}${path}`, {
    method: path === '/auth/me' ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(10000), redirect: 'manual',
  });
}
export async function currentIdentity() {
  if (!backendUrl()) return getChatGPTUser();
  const token = await sessionToken();
  if (!token) return null;
  const response = await backendRequest('/auth/me', undefined, token);
  if (response.status === 401) return null;
  if (!response.ok) throw new Error('Backend identity unavailable');
  const data = await response.json() as { inquirer_id: string; login_name: string; role: string; expires_at: string };
  return { userId: `backend:${data.inquirer_id}`, displayName: data.login_name, email: '', fullName: null,
    role: data.role, expiresAt: data.expires_at };
}
export function sessionCookie(request: Request, token = '', maxAge = 0) {
  return `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}${new URL(request.url).protocol === 'https:' ? '; Secure' : ''}`;
}
