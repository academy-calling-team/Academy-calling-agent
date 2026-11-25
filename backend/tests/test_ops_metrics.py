"""Simulation and verification tests for GET /ops/metrics."""
import json
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select, update
from real_test import RealTestPolicy
from schema import accounts, academies, calls
from test_portable_smoke import login, portable
from worker import make_result

INTERNAL = {'X-Internal-Key': 'synthetic-test-key'}


def make_admin_headers(engine, client):
    identity, headers = login(client)
    with engine.begin() as c:
        c.execute(
            update(accounts)
            .where(accounts.c.user_id == identity['inquirer_id'])
            .values(role='admin')
        )
    return headers


def submit_inquiry(client, parent_id, headers, academy_id, codes):
    req_headers = {**headers, 'Idempotency-Key': str(uuid4())}
    res = client.post(
        '/api/inquiries',
        headers=req_headers,
        json={
            'inquirer_id': parent_id,
            'academy_id': academy_id,
            'student': {'grade': 'M2', 'subject': 'MATH', 'level': 'MID', 'region': '대구 북구 침산동'},
            'question_codes': codes,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()['inquiry_id']


def dispatch_payload_for(engine, call_id):
    with engine.connect() as c:
        return c.execute(select(calls.c.dispatch_payload).where(calls.c.id == call_id)).scalar_one()


def test_ops_metrics_requires_admin(portable):
    _, _, client = portable
    _, parent_headers = login(client)
    assert client.get('/ops/metrics').status_code == 401
    assert client.get('/ops/metrics', headers=parent_headers).status_code == 403


def test_ops_metrics_simulation_scenarios_and_corrections(portable):
    engine, service, client = portable
    admin_headers = make_admin_headers(engine, client)
    parent, parent_headers = login(client)
    pid = parent['inquirer_id']

    # 실발신 학원 1개 추가 (is_mock=False)
    with engine.begin() as c:
        c.execute(
            academies.insert().values(
                id='real-academy-1',
                name='실발신 테스트 학원',
                region='대구 북구 침산동',
                phone='010-1234-5678',
                is_mock=False,
                hours=[dict(weekday=i, start_minute=0, end_minute=1440) for i in range(7)],
            )
        )
    service.real_test = RealTestPolicy(
        enabled=True,
        academy_id='real-academy-1',
        allowed_to='010-1234-5678',
        inquirer_id=pid,
    )

    # 시나리오 A (mock): 정상 연결 + 조건부 가능 + 상담 조건부 수락
    submit_inquiry(client, pid, parent_headers, 'demo-academy', ['shuttle', 'vacancy'])
    cid_a = client.post('/internal/mock/tick', headers=INTERNAL).json()['reserved'][0]
    res_a = make_result(dispatch_payload_for(engine, cid_a))
    res_a['duration_sec'] = 40
    res_a['consult_accepted'] = True
    res_a['consult'] = {'condition': '사전 문자 예약 시 가능'}
    res_a['answers'][0]['condition'] = '침산초 앞 4시 탑승 시 가능'
    assert client.post(f'/internal/calls/{cid_a}/result', headers=INTERNAL, json=res_a).status_code == 200

    # 시나리오 B (mock): 정상 연결 + 직접 확인(redirect) + 시간 부족 미질문(not_asked) + 상담 거절
    submit_inquiry(
        client, pid, parent_headers, 'demo-academy', ['shuttle', 'vacancy', 'level_test']
    )
    cid_b = client.post('/internal/mock/tick', headers=INTERNAL).json()['reserved'][0]
    res_b = make_result(
        dispatch_payload_for(engine, cid_b),
        negative=['shuttle'],
        unanswered=['vacancy', 'level_test'],
    )
    res_b['duration_sec'] = 20
    res_b['consult_accepted'] = False
    res_b['available_times'] = []
    res_b['answers'][1].update(answered=False, yes_no=None, reason='redirect', source_text=None)
    res_b['answers'][2].update(asked=False, answered=False, yes_no=None, reason='not_asked', source_text=None)
    r_b = client.post(f'/internal/calls/{cid_b}/result', headers=INTERNAL, json=res_b)
    assert r_b.status_code == 200, r_b.text

    # 시나리오 C (mock): 통화 거절 최종 실패 (rejected)
    submit_inquiry(client, pid, parent_headers, 'demo-academy', ['shuttle'])
    cid_c = client.post('/internal/mock/tick', headers=INTERNAL).json()['reserved'][0]
    res_c = make_result(dispatch_payload_for(engine, cid_c), outcome='rejected')
    res_c['rejection_reason'] = 'permanent'
    assert client.post(f'/internal/calls/{cid_c}/result', headers=INTERNAL, json=res_c).status_code == 200

    # 시나리오 D (real): 실발신 학원 정상 연결 1건
    submit_inquiry(client, pid, parent_headers, 'real-academy-1', ['shuttle'])
    cid_d = client.post('/internal/mock/tick', headers=INTERNAL).json()['reserved'][0]
    res_d = make_result(dispatch_payload_for(engine, cid_d))
    res_d['duration_sec'] = 30
    res_d['consult_accepted'] = True
    assert client.post(f'/internal/calls/{cid_d}/result', headers=INTERNAL, json=res_d).status_code == 200

    # 운영자 교정 반영 검증: 시나리오 B의 미질문(level_test)을 운영자가 답변 완료로 교정
    edited_b = deepcopy(res_b)
    edited_b['answers'][2].update(asked=True, answered=True, yes_no=True, reason=None, detail='레벨테스트 가능')
    edited_b['unresolved'] = [a['question_id'] for a in edited_b['answers'] if not a['answered']]
    corr = client.post(
        f'/ops/calls/{cid_b}/corrections',
        headers=admin_headers,
        json={
            'base_revision': 0,
            'reviewer': 'admin',
            'reason': '후속 확인 내용 반영',
            'payload': edited_b,
        },
    )
    assert corr.status_code == 200, corr.text

    # 전체(all) 집계 검증
    all_metrics = client.get('/ops/metrics?mode=all', headers=admin_headers).json()
    print('\n[시뮬레이션 산출 결과 - mode=all]\n' + json.dumps(all_metrics, indent=2, ensure_ascii=False))

    assert all_metrics['inquiries']['total'] == 4
    assert all_metrics['inquiries']['completed'] == 3
    assert all_metrics['inquiries']['failed'] == 1
    assert all_metrics['calls']['total_attempts'] == 4
    assert all_metrics['calls']['connected'] == 3
    assert all_metrics['calls']['connection_rate'] == 0.75
    assert all_metrics['questions']['total_questions'] == 6
    assert all_metrics['questions']['answered_count'] == 5  # 교정 반영으로 4 -> 5 증가
    assert all_metrics['consult']['accepted'] == 2
    assert all_metrics['consult']['conditional_accepted'] == 1
    assert all_metrics['timing']['avg_duration_sec'] == 30.0

    # 실발신(real) 필터 분리 검증
    real_metrics = client.get('/ops/metrics?mode=real', headers=admin_headers).json()
    assert real_metrics['inquiries']['total'] == 1
    assert real_metrics['calls']['connected'] == 1
    assert real_metrics['calls']['connection_rate'] == 1.0