import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

let server, browser;
const base = 'http://127.0.0.1:5178';
before(async () => {
  server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5178', '--strictPort'], {
    cwd: fileURLToPath(new URL('../', import.meta.url)), stdio: 'ignore',
    env: { ...process.env, ACADEMY_BACKEND_URL: 'https://backend.invalid/shared' },
  });
  for (let n = 0; ; n++) {
    try { if ((await fetch(base)).ok) break; } catch {}
    if (n > 100 || server.exitCode !== null) throw Error('Fixture Vite server did not start');
    await new Promise(r => setTimeout(r, 100));
  }
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
});
after(async () => { await browser?.close(); server?.kill(); });

const student = { grade: 'M2', subject: 'MATH', level: 'MID', region: '대구 북구 침산동' };
async function fixture(path, { canSubmit = true, loggedIn = true } = {}) {
  const page = await browser.newPage();
  const submissions = [];
  await page.route('**/api/**', async route => {
    const req = route.request(), p = new URL(req.url()).pathname;
    await new Promise(r => setTimeout(r, p === '/api/account' ? 150 : 300));
    let data;
    if (p === '/api/account') {
      data = { mode: 'backend', user: loggedIn ? { displayName: 'fixture', registered: true } : null };
    } else if (p === '/api/auth/login') { loggedIn = true; data = { logged_in: true };
    } else if (p === '/api/auth/register') { submissions.push(req.postDataJSON()); data = { registered: true };
    } else if (p === '/api/options') data = { grade: ['M2'], subject: ['MATH'], level: ['MID'], regions: [student.region], question_codes: { shuttle: '통학 차량' } };
    else if (p === '/api/academies') data = [{ academy_id: 'fixture-academy', name: '시험 학원', region: student.region, is_mock: false, is_test: true, can_submit: canSubmit }];
    else if (p === '/api/inquiries' && req.method() === 'POST') { submissions.push(req.postDataJSON()); data = { inquiry_id: 'fixture-inquiry', status: 'queued' }; }
    else if (p === '/api/inquiries') data = [{ inquiry_id: 'fixture-inquiry', status: 'completed', created_at: '2026-10-28T00:00:00Z' }];
    else data = { inquiry_id: 'fixture-inquiry', status: 'completed', student, academy: { name: '시험 학원' }, questions: [], attempts: [], result: { answers: [], consult_accepted: true, available_times: ['수요일 3시'] } };
    await route.fulfill({ status: p === '/api/account' && !loggedIn ? 401 : 200, json: data });
  });
  await page.goto(base + path);
  return { page, submissions };
}
for (const path of ['/', '/tasks', '/detail/fixture-inquiry']) {
  test(`authenticated direct entry and reload finish loading: ${path}`, async () => {
    const { page } = await fixture(path);
    try {
      for (let i = 0; i < 2; i++) {
        await page.getByText('fixture님').waitFor();
        if (path.startsWith('/detail')) await page.getByRole('link', { name: /내 상담/ }).first().waitFor();
        await page.waitForFunction(() => !document.body.innerText.includes('불러오고') && (document.body.innerText.includes('fixture-inquiry') || document.body.innerText.includes('시험 학원')));
        assert.equal(await page.getByText('상담 내역을 불러오고 있어요.').count(), 0);
        if (i === 0) await page.reload();
      }
    } finally { await page.close(); }
  });
}
async function fillInquiry(page) {
  await page.locator('[name=academy_id]').selectOption('fixture-academy');
  for (const k of ['grade', 'subject', 'level', 'region']) await page.locator(`[name=${k}]`).selectOption(student[k]);
  await page.locator('[name=codes]').check();
}
test('registration requires explicit consent and login then loads owned inquiries', async () => {
  const { page, submissions } = await fixture('/register', { loggedIn: false });
  try {
    await page.locator('[name=login_name]').fill('fixture');
    await page.locator('[name=password]').fill('fixture-password-123');
    await page.locator('[name=confirm_password]').fill('fixture-password-123');
    await page.getByRole('button', { name: '회원가입 ↗' }).click();
    assert.equal(submissions.length, 0);
    await page.locator('[name=terms_agreed]').check();
    await page.getByRole('button', { name: '회원가입 ↗' }).click();
    await page.waitForURL('**/login');
    assert.equal(submissions.length, 1);
    assert.equal(submissions[0].terms_agreed, true);
    await page.locator('[name=login_name]').fill('fixture');
    await page.locator('[name=password]').fill('fixture-password-123');
    await page.getByRole('button', { name: '로그인 ↗' }).click();
    await page.waitForURL(base + '/');
    await page.getByRole('heading', { name: 'fixture-inquiry' }).waitFor();
  } finally { await page.close(); }
});
test('real call requires recipient confirmation, ready request submits once', async () => {
  const { page, submissions } = await fixture('/new');
  try {
    await fillInquiry(page);
    await page.getByRole('button', { name: '상담 접수' }).click();
    await page.getByText('수신자 준비와 실제 전화 요청을 확인해 주세요.').waitFor();
    assert.equal(submissions.length, 0);
    await page.locator('[name=real_test_confirm]').check();
    await page.getByRole('button', { name: '상담 접수' }).click();
    await page.waitForURL('**/detail/fixture-inquiry');
    assert.equal(submissions.length, 1);
  } finally { await page.close(); }
});
test('unprepared real academy cannot submit', async () => {
  const { page, submissions } = await fixture('/new', { canSubmit: false });
  try {
    await fillInquiry(page);
    assert.equal(await page.getByRole('button', { name: '상담 접수' }).isDisabled(), true);
    assert.equal(submissions.length, 0);
  } finally { await page.close(); }
});
