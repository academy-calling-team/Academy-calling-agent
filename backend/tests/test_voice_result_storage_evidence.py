"""Storage of additive answer columns, evidence dialogue filtering, transcript RBAC, and consult corrections."""
from copy import deepcopy
from sqlalchemy import select, update
from schema import accounts, answers, academies, academy_profiles, academy_setting_states
from test_portable_smoke import login, portable
from test_voice_answer_fields import INTERNAL, reserved


def register_academy_owner(client, engine, academy_id, login_name='academy_owner_1'):
    reg = client.post('/auth/register', json={
        'login_name': login_name,
        'password': 'AcademyPassword123!',
        'terms_agreed': True,
        'account_type': 'academy',
    })
    assert reg.status_code == 201, reg.text
    owner_id = reg.json()['inquirer_id']
    tok = client.post('/auth/login', json={
        'login_name': login_name,
        'password': 'AcademyPassword123!',
    }).json()['access_token']
    with engine.begin() as c:
        c.execute(academy_profiles.insert().values(
            academy_id=academy_id, owner_id=owner_id, address='대구 북구 침산동'))
        c.execute(academy_setting_states.insert().values(
            academy_id=academy_id, is_class_configured=True, is_call_hours_configured=True,
            last_modified_at=c.execute(select(academies.c.id)).first() and __import__('datetime').datetime.utcnow(),
            version=1))
    return owner_id, {'Authorization': f'Bearer {tok}'}


def test_answer_columns_and_parent_evidence_dialogue_filtering(reserved):
    engine, client, _, parent_auth, iid, cid, body = reserved
    body['transcript'] = [
        {'speaker': 'agent', 'at_ms': 500, 'text': '안녕하세요, 셔틀 문의드립니다.', 'turn_no': 0},
        {'speaker': 'academy', 'at_ms': 1500, 'text': '침산초등학교 앞에서 4시 운행합니다.', 'turn_no': 1},
        {'speaker': 'academy', 'at_ms': 3000, 'text': '내부 사정으로 비공개 메모입니다.', 'turn_no': 2},
        {'speaker': 'academy', 'at_ms': 4200, 'text': '문자로 시간 확정 후 상담 가능합니다.', 'turn_no': 3},
    ]
    body['answers'][0].update(
        condition='침산초등학교 앞 4시 탑승 시 가능',
        reason_text='정류장 및 시간 조건부 운행',
        source_text='침산초등학교 앞에서 4시 운행합니다.',
        evidence_turns=[1],
    )
    body['answers'][1].update(
        answered=False, yes_no=None, reason='redirect',
        reason_text='학원 직접 문의 필요',
    )
    body['consult'] = {
        'condition': '문자로 시간 확정 시 가능',
        'reason_text': '사전 문자 예약 조건부 수락',
        'source_text': '문자로 시간 확정 후 상담 가능합니다.',
        'evidence_turns': [3],
    }

    res = client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body)
    assert res.status_code == 200, res.text

    # 1. w5_answers 정규화 테이블 컬럼 적재 검증
    with engine.connect() as c:
        rows = c.execute(select(answers).where(answers.c.call_id == cid)).mappings().all()
        by_qid = {r['question_id']: r for r in rows}
        first = by_qid[body['answers'][0]['question_id']]
        assert first['condition'] == '침산초등학교 앞 4시 탑승 시 가능'
        assert first['reason_text'] == '정류장 및 시간 조건부 운행'
        assert first['evidence_turns'] == [1]

    # 2. 학부모 상세 조회 시 허용된 근거 발화만 포함되고 전체 transcript는 비공개
    view = client.get(f'/api/inquiries/{iid}', headers=parent_auth).json()['result']
    assert 'transcript' not in view
    assert 'recording_url' not in view
    assert view['answers'][0]['evidence_dialogue'] == [{
        'turn_no': 1,
        'speaker': 'academy',
        'at_ms': 1500,
        'text': '침산초등학교 앞에서 4시 운행합니다.',
    }]
    assert 'evidence_dialogue' not in view['answers'][1]
    assert view['consult']['evidence_dialogue'] == [{
        'turn_no': 3,
        'speaker': 'academy',
        'at_ms': 4200,
        'text': '문자로 시간 확정 후 상담 가능합니다.',
    }]


def test_transcript_access_control_by_role(reserved):
    engine, client, user, parent_auth, iid, cid, body = reserved
    body['transcript'] = [
        {'speaker': 'academy', 'at_ms': 1000, 'text': '전체 전사 테스트 발화입니다.', 'turn_no': 0},
    ]
    assert client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body).status_code == 200

    # 학부모 계정은 전체 전사 조회 차단 (403)
    assert client.get(f'/api/calls/{cid}/transcript', headers=parent_auth).status_code == 403

    # 해당 문의를 받은 학원 소유자 계정은 전체 전사 조회 허용 (200)
    academy_id = client.get(f'/api/inquiries/{iid}', headers=parent_auth).json()['academy']['academy_id']
    _, academy_auth = register_academy_owner(client, engine, academy_id, 'owner_ok')
    tr = client.get(f'/api/calls/{cid}/transcript', headers=academy_auth)
    assert tr.status_code == 200, tr.text
    assert tr.json()['transcript'][0]['text'] == '전체 전사 테스트 발화입니다.'

    # 다른 학원 소유자 계정은 타 학원 통화 전사 조회 차단 (403)
    with engine.begin() as c:
        c.execute(academies.insert().values(
            id='other-acad-1', name='타학원', region='대구 북구 침산동',
            phone='053-000-0000', is_mock=True, hours=[]))
    _, other_academy_auth = register_academy_owner(client, engine, 'other-acad-1', 'owner_other')
    assert client.get(f'/api/calls/{cid}/transcript', headers=other_academy_auth).status_code == 403

    # 운영자(admin) 계정은 전체 전사 조회 허용 (200)
    with engine.begin() as c:
        c.execute(update(accounts).where(accounts.c.user_id == user['inquirer_id']).values(role='admin'))
    assert client.get(f'/api/calls/{cid}/transcript', headers=parent_auth).status_code == 200


def test_admin_can_correct_consult_and_keep_evidence_dialogue(reserved):
    engine, client, user, parent_auth, iid, cid, body = reserved
    body['transcript'] = [
        {'speaker': 'academy', 'at_ms': 1000, 'text': '평일 오후 방문 상담 가능합니다.', 'turn_no': 5},
    ]
    body['consult'] = {
        'condition': '기존 조건',
        'reason_text': '기존 상담 사유',
        'evidence_turns': [5],
    }
    assert client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body).status_code == 200

    with engine.begin() as c:
        c.execute(update(accounts).where(accounts.c.user_id == user['inquirer_id']).values(role='admin'))

    edited = deepcopy(body)
    edited['consult'] = {
        'condition': '평일 오후 방문 예약 시 가능',
        'reason_text': '운영자 검토 후 상담 조건 보완',
        'evidence_turns': [5],
    }
    corr = client.post(f'/ops/calls/{cid}/corrections', headers=parent_auth, json={
        'base_revision': 0,
        'reviewer': 'ignored',
        'reason': '상담 조건 문구 명확화',
        'payload': edited,
    })
    assert corr.status_code == 200, corr.text

    view = client.get(f'/api/inquiries/{iid}', headers=parent_auth).json()['result']
    assert view['consult']['condition'] == '평일 오후 방문 예약 시 가능'
    assert view['consult']['reason_text'] == '운영자 검토 후 상담 조건 보완'
    assert view['consult']['evidence_dialogue'][0]['turn_no'] == 5