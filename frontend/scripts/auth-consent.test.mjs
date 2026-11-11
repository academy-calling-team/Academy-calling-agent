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

test('academy registration forwards only the account type, and rejects admin as a type', async () => {
  assert.equal((await post('auth/register', { ...account, terms_agreed: true, account_type: 'academy' })).status, 201);
  assert.equal(JSON.parse(calls[0].body).account_type, 'academy');
  assert.equal((await post('auth/register', { ...account, terms_agreed: true, account_type: 'admin' })).status, 422);
  assert.equal(calls.length, 1);
});

test('my-academy writes require an authenticated cookie and preserve PUT and version', async () => {
  assert.equal((await post('my-academy', {})).status, 401);
  assert.equal(calls.length, 0);
  const response = await handleApi(new Request('http://127.0.0.1:5173/api/my-academy', {
    method: 'PUT',
    headers: { origin: 'http://127.0.0.1:5173', 'content-type': 'application/json',
      cookie: 'hakwon_backend_session=fixture-token' },
    body: JSON.stringify({ version: 3 }),
  }));
  assert.equal(response.status, 200);
  assert.equal(calls[0].method, 'PUT');
  assert.equal(calls[0].headers.Authorization, 'Bearer fixture-token');
  assert.deepEqual(JSON.parse(calls[0].body), { version: 3 });
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
