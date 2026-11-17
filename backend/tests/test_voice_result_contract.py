"""Additive result contract, stable legacy replays and same-call evidence references."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from contracts import AnswerInput, ResultInput
from schema import accounts, results
from service import fingerprint, result_payload
from test_portable_smoke import login, portable
from test_voice_answer_fields import INTERNAL, reserved

EXAMPLES = json.loads((Path(__file__).resolve().parents[2] /
                      'docs/api/examples/voice_result_examples.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('example', EXAMPLES, ids=lambda item: item['case'])
def test_documented_full_result_examples(example):
    assert ResultInput.model_validate(example['payload']).result_id.startswith('example-')


@pytest.fixture
def legacy():
    # Frozen pre-addition shape: defaults that already existed are explicitly present.
    return dict(result_id='contract-test', outcome='answered', disclosure_played=True,
                consult_accepted=True, available_times=[],
                answers=[dict(question_id='q1', question_code='shuttle', asked=True,
                              answered=True, yes_no=True, reason=None, detail='가능합니다.')],
                unresolved=[], summary_text='상담 결과', notes='', latency=None,
                duration_sec=30,
                transcript=[dict(speaker='academy', at_ms=1000, text='학교 앞에서 가능합니다.')],
                recording_url=None, callback_requested=False, callback_at=None,
                rejection_reason=None)


@pytest.mark.parametrize('patch', [
    dict(),
    dict(condition='학교 앞에서만 가능'),
    dict(yes_no=False),
    dict(answered=False, yes_no=None, reason='redirect'),
    dict(answered=False, yes_no=None, reason='unknown'),
    dict(answered=False, yes_no=None, reason='uncertain'),
    dict(answered=False, yes_no=None, reason='refused'),
    dict(asked=False, answered=False, yes_no=None, reason='not_asked'),
])
def test_answer_combinations_and_legacy_reasons(legacy, patch):
    answer = {**legacy['answers'][0], **patch, 'reason_text': '공유된 판정 근거'}
    parsed = AnswerInput.model_validate(answer)
    assert parsed.reason == answer['reason']
    assert parsed.reason_text == '공유된 판정 근거'


def test_class_time_preserves_existing_exception(legacy):
    answer = {**legacy['answers'][0], 'question_code': 'class_time', 'yes_no': None,
              'detail': '월요일 오후 수업'}
    assert AnswerInput.model_validate(answer).yes_no is None
    with pytest.raises(ValidationError):
        AnswerInput.model_validate({**answer, 'condition': '테스트 후 시간 확정'})


@pytest.mark.parametrize('patch', [
    dict(condition=''), dict(condition=' '), dict(condition='가' * 201),
    dict(condition='조건', yes_no=False),
    dict(condition='조건', answered=False, yes_no=None, reason='unknown'),
    dict(reason_text=' '), dict(reason_text='가' * 501),
    dict(source_text=' '), dict(source_text='가' * 2001),
    dict(evidence_turns=list(range(11))), dict(evidence_turns=[-1]),
    dict(evidence_turns=[True]), dict(evidence_turns=[1.0]),
    dict(evidence_turns=['0']), dict(evidence_turns=[0, 0]),
    dict(asked=False, answered=False, yes_no=None, reason='not_asked', evidence_turns=[0]),
    dict(certainty='certain'), dict(answer_status='conditional'),
])
def test_invalid_answer_additions_are_rejected(legacy, patch):
    with pytest.raises(ValidationError):
        AnswerInput.model_validate({**legacy['answers'][0], **patch})


@pytest.mark.parametrize('accepted,explanation', [
    (True, dict()),
    (True, dict(condition='문자로 시간 확정', reason_text='조건부 수락')),
    (False, dict(reason_text='이번 문의 기간은 불가')),
    (None, dict(reason='redirect', reason_text='추가 정보 필요')),
    (None, dict(reason='unknown')),
    (None, dict(reason='uncertain')),
    (None, dict(reason='refused')),
    (None, dict(reason='not_asked')),
])
def test_consultation_combinations(legacy, accepted, explanation):
    legacy.update(consult_accepted=accepted, consult=explanation)
    assert ResultInput.model_validate(legacy).consult_accepted is accepted


@pytest.mark.parametrize('accepted,explanation', [
    (True, dict(reason='unknown')), (False, dict(reason='redirect')),
    (False, dict(condition='조건')), (None, dict(condition='조건', reason='unknown')),
    (None, dict()),
    (None, dict(reason='not_asked', source_text='발화')),
])
def test_inconsistent_consultation_is_rejected(legacy, accepted, explanation):
    legacy.update(consult_accepted=accepted, consult=explanation)
    with pytest.raises(ValidationError):
        ResultInput.model_validate(legacy)


def test_same_call_numbered_evidence_without_renumbering(legacy):
    # Numbers are explicit IDs within a call, not offsets in this JSON array.
    legacy['transcript'][0]['turn_no'] = 12
    legacy['answers'][0].update(evidence_turns=[12], source_text='학교 앞에서 가능합니다.')
    legacy['consult'] = dict(evidence_turns=[12])
    parsed = ResultInput.model_validate(legacy)
    assert parsed.answers[0].evidence_turns == parsed.consult.evidence_turns == [12]
    assert result_payload(parsed)['transcript'][0]['turn_no'] == 12


@pytest.mark.parametrize('patch', ['missing', 'array-offset', 'duplicate', 'negative', 'boolean', 'consult-missing'])
def test_invalid_evidence_and_turn_numbering(legacy, patch):
    legacy['transcript'][0]['turn_no'] = 12
    if patch == 'missing':
        legacy['answers'][0]['evidence_turns'] = [13]
    elif patch == 'array-offset':
        legacy['answers'][0]['evidence_turns'] = [0]
    elif patch == 'duplicate':
        legacy['transcript'].append(dict(legacy['transcript'][0]))
    elif patch == 'negative':
        legacy['transcript'][0]['turn_no'] = -1
    elif patch == 'boolean':
        legacy['transcript'][0]['turn_no'] = True
    else:
        legacy['consult'] = dict(evidence_turns=[0])
    with pytest.raises(ValidationError):
        ResultInput.model_validate(legacy)


@pytest.mark.parametrize('at', [None, '2026-11-18T15:00:00+09:00'])
def test_callback_explanations_allow_unknown_or_explicit_time(legacy, at):
    legacy.update(callback_requested=True, callback_at=at,
                  callback_reason_text='수업 중이라 다시 연락 요청',
                  callback_source_text='오후에 다시 전화 주세요.')
    parsed = ResultInput.model_validate(legacy)
    assert parsed.callback_requested and parsed.callback_source_text == '오후에 다시 전화 주세요.'


@pytest.mark.parametrize('patch', [
    dict(callback_reason_text='사유'), dict(callback_source_text='원문'),
    dict(callback_requested=True, callback_reason_text=' '),
    dict(callback_requested=True, callback_source_text='가' * 501),
    dict(callback_requested=True, callback_at='2026-11-18T15:00:00'),
    dict(end_reason='busy'),
])
def test_invalid_callback_and_end_reason(legacy, patch):
    with pytest.raises(ValidationError):
        ResultInput.model_validate({**legacy, **patch})


@pytest.mark.parametrize('addition', [dict(consult={}), dict(end_reason='connection_lost')])
def test_nonhuman_result_cannot_claim_consultation_or_human_ending(legacy, addition):
    legacy.update(outcome='machine', disclosure_played=None, consult_accepted=None,
                  transcript=[], **addition)
    legacy['answers'][0].update(asked=False, answered=False, yes_no=None, reason='not_asked')
    legacy['unresolved'] = ['q1']
    with pytest.raises(ValidationError):
        ResultInput.model_validate(legacy)


def test_missing_null_and_empty_additions_keep_legacy_hash(legacy):
    expected = deepcopy(legacy)
    assert result_payload(ResultInput.model_validate(legacy)) == expected
    legacy.update(consult=None, callback_reason_text=None, callback_source_text=None, end_reason=None)
    legacy['answers'][0].update(condition=None, reason_text=None, source_text=None, evidence_turns=[])
    legacy['transcript'][0]['turn_no'] = None
    assert fingerprint(result_payload(ResultInput.model_validate(legacy))) == fingerprint(expected)


def add_metadata(result):
    excerpt = '학교 앞에서만 가능합니다.'
    result['transcript'] = [dict(speaker='academy', at_ms=1000, text=excerpt, turn_no=12)]
    result['answers'][0].update(condition='학교 앞에서만 가능', reason_text='탑승 장소 제한',
                                source_text=excerpt, evidence_turns=[12])
    result['answers'][1].update(reason='redirect', reason_text='학부모 추가 정보 필요')
    result['consult'] = dict(reason=None, condition='문자로 시간 확정',
                             reason_text='공유된 조건부 가능 기준',
                             source_text=excerpt, evidence_turns=[12])
    result['end_reason'] = 'completed'


def test_new_json_metadata_round_trip_and_duplicate_conflict(reserved):
    engine, client, _, auth, iid, cid, body = reserved
    add_metadata(body)
    url = f'/internal/calls/{cid}/result'
    first = client.post(url, headers=INTERNAL, json=body)
    assert first.status_code == 200, first.text
    assert client.post(url, headers=INTERNAL, json=body).json()['duplicate'] is True
    with engine.connect() as c:
        stored = c.execute(select(results.c.payload).where(results.c.call_id == cid)).scalar_one()
        assert stored['answers'][0]['condition'] == body['answers'][0]['condition']
        assert stored['consult']['evidence_turns'] == [12]
        assert stored['transcript'][0]['turn_no'] == 12
    shown = client.get(f'/api/inquiries/{iid}', headers=auth).json()['result']
    assert shown['consult']['condition'] == '문자로 시간 확정'
    assert shown['answers'][1]['reason'] == 'redirect'
    assert 'transcript' not in shown and 'recording_url' not in shown
    _, other = login(client)
    assert client.get(f'/api/inquiries/{iid}', headers=other).status_code == 404
    changed = deepcopy(body)
    changed['answers'][0]['condition'] = '다른 장소'
    assert client.post(url, headers=INTERNAL, json=changed).status_code == 409


def test_legacy_reviewer_preserves_omitted_additions(reserved):
    engine, client, user, auth, iid, cid, body = reserved
    add_metadata(body)
    body.update(callback_requested=True, callback_reason_text='재연락 요청',
                callback_source_text='나중에 다시 전화 주세요.')
    assert client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body).status_code == 200
    with engine.begin() as c:
        c.execute(update(accounts).where(accounts.c.user_id == user['inquirer_id']).values(role='admin'))
    correction = deepcopy(body)
    for name in ('consult', 'callback_reason_text', 'callback_source_text', 'end_reason'):
        correction.pop(name)
    for answer in correction['answers']:
        for name in ('condition', 'reason_text', 'evidence_turns', 'source_text'):
            answer.pop(name, None)
    for turn in correction['transcript']:
        turn.pop('turn_no')
    correction['summary_text'] = '검토 후 요약 수정'
    reply = client.post(f'/ops/calls/{cid}/corrections', headers=auth,
                        json=dict(base_revision=0, reviewer='test', reason='summary only', payload=correction))
    assert reply.status_code == 200, reply.text
    view = client.get(f'/api/inquiries/{iid}', headers=auth).json()['result']
    assert view['answers'][0]['condition'] == body['answers'][0]['condition']
    assert view['answers'][0]['evidence_turns'] == [12]
    assert view['consult']['condition'] == body['consult']['condition']
    assert view['callback_source_text'] == body['callback_source_text']


@pytest.mark.parametrize('end_reason', ['academy_hung_up', 'connection_lost', 'agent_error'])
def test_end_reason_is_metadata_and_does_not_enable_new_redial(reserved, end_reason):
    _, client, _, auth, iid, cid, body = reserved
    body['end_reason'] = end_reason
    assert client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body).status_code == 200
    view = client.get(f'/api/inquiries/{iid}', headers=auth).json()
    assert view['result']['end_reason'] == end_reason
    assert view['status'] == 'completed' and len(view['attempts']) == 1
