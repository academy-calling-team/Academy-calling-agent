import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { handleApi } from '../server/api.ts';

const originalFetch = globalThis.fetch;
let calls;
beforeEach(() => {
  calls = [];
  process.env.ACADEMY_BACKEND_URL = 'https://backend.invalid/shared';
  process.env.FRONTEND_ORIGIN = 'http://127.0.0.1:5173';
  globalThis.fetch = async (url, init) => {
    calls.push({ url, ...init });
    if (url.endsWith('/auth/me')) return Response.json({ inquirer_id: 'fixture-owner', login_name: 'fixture' });
    if (url.endsWith('/auth/login')) return Response.json({ access_token: 'fixture-token', expires_at: new Date(Date.now() + 3600000).toISOString() });
    return Response.json({ registered: true, inquiry_id: 'fixture-inquiry' });
  };
});
afterEach(() => { globalThis.fetch = originalFetch; });
function post(path, body, headers = {}) {
  return handleApi(new Request('http://127.0.0.1:5173/api/' + path, {
    method: 'POST', headers: { origin: 'http://127.0.0.1:5173', 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  }));
}
const account = { login_name: 'fixture', password: 'fixture-password-123' };
for (const consent of [undefined, false, 'true']) {
  test(`registration rejects consent ${String(consent)} before upstream`, async () => {
    assert.equal((await post('auth/register', { ...account, terms_agreed: consent })).status, 422);
    assert.equal(calls.length, 0);
  });
}
test('registration forwards explicit boolean consent', async () => {
  assert.equal((await post('auth/register', { ...account, terms_agreed: true })).status, 201);
  assert.deepEqual(JSON.parse(calls[0].body), { ...account, terms_agreed: true });
});
test('login stores token in HttpOnly cookie without sending consent', async () => {
  const r = await post('auth/login', account);
  assert.equal(r.status, 200);
  assert.match(r.headers.get('set-cookie'), /HttpOnly; SameSite=Lax/);
  assert.deepEqual(JSON.parse(calls[0].body), account);
  assert.equal((await r.text()).includes('fixture-token'), false);
});
test('cross-origin registration is rejected', async () => {
  assert.equal((await post('auth/register', { ...account, terms_agreed: true }, { origin: 'https://outside.invalid' })).status, 403);
  assert.equal(calls.length, 0);
});
test('inquiry owner comes from authenticated session and key is forwarded', async () => {
  const r = await post('inquiries', { inquirer_id: 'forged', academy_id: 'fixture-academy', student: {}, question_codes: ['shuttle'] }, {
    cookie: 'hakwon_backend_session=fixture-token', 'Idempotency-Key': 'fixture-key',
  });
  assert.equal(r.status, 200);
  assert.equal(JSON.parse(calls[1].body).inquirer_id, 'fixture-owner');
  assert.equal(calls[1].headers['Idempotency-Key'], 'fixture-key');
});
