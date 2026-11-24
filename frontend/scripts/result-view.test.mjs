import { test } from 'node:test';
import assert from 'node:assert/strict';
import { answerView, questionLabel } from '../src/lib/inquiry-model.ts';

test('skipped questions explain the supplied reason without implying a negative answer', () => {
  for (const question_code of ['vacancy', 'class_time']) {
    const view = answerView({ question_id: question_code, question_code, asked: false,
      answered: false, reason: 'not_asked', detail: '맞는 반이 없다고 해서 묻지 않음' });
    assert.equal(view.kind, 'unknown');
    assert.equal(view.label, '미질문');
    assert.equal(view.reason, '');
    assert.equal(view.detail, '맞는 반이 없다고 해서 묻지 않음');
  }
  assert.equal(answerView({ reason: 'not_asked', detail: ' ' }).reason, '이 질문을 아직 묻지 못했습니다.');
  assert.equal(answerView({ answered: true, yes_no: false }).label, '불가');
});

test('transport labels are consistent with old, missing and new server labels', () => {
  for (const label of [null, '', '셔틀 운행', '통학 차량', '등원 차량']) assert.equal(questionLabel('shuttle', label), '등원 차량');
  for (const label of [null, '픽업', '픽업 가능 여부', '하원 차량']) assert.equal(questionLabel('pickup', label), '하원 차량');
  assert.equal(questionLabel('level_fit', ' 수준에 맞는 반 '), '수준에 맞는 반');
  assert.equal(questionLabel('future_code'), 'future_code');
});

test('demo scenarios remain available with an older preview cache', async () => {
  const previousStorage = globalThis.sessionStorage;
  globalThis.sessionStorage = { getItem: () => JSON.stringify({ rows: [], keys: {} }) };
  try {
    const { mockRequest } = await import('../src/lib/mock-inquiries.ts');
    const evidence = await mockRequest('/api/inquiries/mock-evidence');
    assert.ok(evidence.result.answers.some(answer => answer.evidence_dialogue?.length));
    assert.ok(evidence.result.consult.evidence_dialogue.length);
    const noClass = await mockRequest('/api/inquiries/mock-no-class');
    const skipped = noClass.result.answers.filter(answer => answer.reason === 'not_asked');
    assert.deepEqual(skipped.map(answer => answer.question_code), ['vacancy', 'class_time']);
    assert.ok(skipped.every(answer => !answer.answered && !answer.evidence_dialogue && answer.detail === '맞는 반이 없다고 해서 묻지 않음'));
  } finally {
    if (previousStorage === undefined) delete globalThis.sessionStorage;
    else globalThis.sessionStorage = previousStorage;
  }
});
