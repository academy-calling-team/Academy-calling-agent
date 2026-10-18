import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const source = readFileSync(new URL('../app/api/auth/[action]/route.ts', import.meta.url), 'utf8');

function handler() {
  const calls = [];
  const exports = {};
  const backend = {
    backendUrl: () => 'https://synthetic.invalid/shared',
    backendRequest: async (path, body) => {
      calls.push({ path, body });
      return new Response(JSON.stringify(path.endsWith('register') ? {} : {
        access_token: 'synthetic-session', expires_at: new Date(Date.now() + 3600000).toISOString(),
      }), { status: path.endsWith('register') ? 201 : 200 });
    },
    sessionToken: async () => undefined,
    sessionCookie: () => 'synthetic=value',
  };
  const security = { writable: () => true, json: (body, status = 200) => Response.json(body, { status }) };
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  } }).outputText, { exports, require: name => name.includes('backend-auth') ? backend : security });
  return { calls, post: (action, body) => exports.POST(new Request('http://localhost/api/auth/' + action, {
    method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
  }), { params: Promise.resolve({ action }) }) };
}

for (const value of [undefined, false, 'true']) {
  test(`registration rejects non-consent ${String(value)} without forwarding`, async () => {
    const h = handler();
    const response = await h.post('register', { login_name: 'synthetic', password: 'Synthetic_Pass123!', terms_agreed: value });
    assert.equal(response.status, 422);
    assert.equal(h.calls.length, 0);
  });
}
test('explicit true is forwarded only on registration', async () => {
  const h = handler();
  const credentials = { login_name: 'synthetic', password: 'Synthetic_Pass123!', terms_agreed: true };
  assert.equal((await h.post('register', credentials)).status, 201);
  assert.equal(h.calls[0].body.terms_agreed, true);
  assert.equal((await h.post('login', credentials)).status, 200);
  assert.equal(Object.hasOwn(h.calls[1].body, 'terms_agreed'), false);
});
test('registration renders required consent without preselecting it', () => {
  const app = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
  const render = app.slice(app.indexOf('function backendAuthPage('), app.indexOf('async function submitBackendAuth('));
  const context = { user: null, pendingLogin: '', esc: x => x };
  vm.createContext(context);
  vm.runInContext(render, context);
  const input = context.backendAuthPage(true).match(/<input[^>]*name="terms_agreed"[^>]*>/)?.[0];
  assert.ok(input);
  assert.match(input, /required/);
  assert.doesNotMatch(input, /checked/);
  assert.doesNotMatch(context.backendAuthPage(false), /name="terms_agreed"/);
});
