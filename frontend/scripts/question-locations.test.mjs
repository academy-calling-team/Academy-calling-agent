import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleApi } from '../server/api.ts';
import { inquiryPayload, submissionKey } from '../src/lib/inquiry-model.ts';

const form = { academy_id: 'fixture-academy', grade: 'M2', subject: 'MATH', level: 'MID',
  region: '대구 북구 침산동', question_codes: ['shuttle', 'pickup'] };

test('location metadata is part of duplicate prevention, while old forms keep their payload', () => {
  const old = inquiryPayload(form);
  assert.equal('locations' in old, false);
  const next = inquiryPayload({ ...form, locations: {
    shuttle: { kind: '학교', name: ' 침산초등학교 ' }, pickup: { kind: '집 근처', name: '침산네거리' },
  } });
  assert.equal(next.locations.shuttle.name, '침산초등학교');
  const key = submissionKey(null, next, () => 'first-key');
  assert.equal(submissionKey(key, next, () => 'wrong').key, 'first-key');
  const changed = inquiryPayload({ ...form, locations: { shuttle: { kind: '학교', name: '다른초등학교' } } });
  assert.equal(submissionKey(key, changed, () => 'new-key').key, 'new-key');
  assert.equal('locations' in inquiryPayload({ ...form, question_codes: ['vacancy'], locations: next.locations }), false);
});

test('authenticated web requests forward question locations and keep owner injection', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  process.env.ACADEMY_BACKEND_URL = 'http://backend.invalid';
  process.env.FRONTEND_ORIGIN = 'http://127.0.0.1:5173';
  globalThis.fetch = async (url, init) => {
    if (url.endsWith('/auth/me')) return Response.json({ inquirer_id: 'fixture-owner', login_name: 'fixture' });
    calls.push(JSON.parse(init.body));
    return Response.json({ inquiry_id: 'fixture-inquiry', status: 'queued' }, { status: 201 });
  };
  try {
    const payload = inquiryPayload({ ...form, locations: { shuttle: { kind: '학교', name: '침산초등학교' } } });
    const response = await handleApi(new Request('http://127.0.0.1:5173/api/inquiries', {
      method: 'POST', headers: { origin: 'http://127.0.0.1:5173', 'content-type': 'application/json',
        cookie: 'hakwon_backend_session=fixture-token', 'Idempotency-Key': 'fixture-key' },
      body: JSON.stringify({ ...payload, inquirer_id: 'cannot-impersonate' }),
    }));
    assert.equal(response.status, 201);
    assert.deepEqual(calls[0].locations, payload.locations);
    assert.equal(calls[0].inquirer_id, 'fixture-owner');
  } finally { globalThis.fetch = originalFetch; }
});
