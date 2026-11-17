"""Late-result diagnosis, real callback response examples and additive MySQL DDL."""
from datetime import timedelta
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from schema import accounts, results
from test_portable_smoke import portable
from test_voice_answer_fields import INTERNAL, reserved
from test_voice_result_storage_evidence import register_academy_owner


@pytest.mark.parametrize('viewer', ['admin', 'academy'])
def test_late_transcript_is_available_only_to_authorized_viewers(reserved, portable, viewer):
    engine, client, user, parent_auth, iid, cid, body = reserved
    _, service, _ = portable
    body['transcript'] = [dict(speaker='academy', at_ms=1000, text='늦게 도착한 통화 결과의 근거입니다.', turn_no=0)]
    now = service.clock()
    service.clock = lambda: now + timedelta(seconds=700)
    posted = client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body)
    assert posted.status_code == 200, posted.text
    assert posted.json() == dict(duplicate=False, applied=False)
    inquiry_url = f'/api/inquiries/{iid}'
    parent_view = client.get(inquiry_url, headers=parent_auth).json()
    assert parent_view['result'] is None
    assert client.get(f'/api/calls/{cid}/transcript', headers=parent_auth).status_code == 403
    academy_id = parent_view['academy']['academy_id']
    if viewer == 'admin':
        with engine.begin() as c:
            c.execute(update(accounts).where(accounts.c.user_id == user['inquirer_id']).values(role='admin'))
        auth = parent_auth
    else:
        _, auth = register_academy_owner(client, engine, academy_id, 'late_owner')

    response = client.get(f'/api/calls/{cid}/transcript', headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()['applied'] is False
    assert response.json()['transcript'] == body['transcript']
    assert 'recording_url' not in response.json()
    after_view = client.get(inquiry_url, headers=parent_auth).json()
    assert after_view == parent_view  # Diagnosis must not promote the late result or redial.
    with engine.connect() as c:
        stored = c.execute(select(results.c.applied).where(results.c.call_id == cid)).scalar_one()
        assert stored is False


def test_transcript_result_not_yet_received_remains_404(reserved):
    engine, client, user, auth, _, cid, _ = reserved
    with engine.begin() as c:
        c.execute(update(accounts).where(accounts.c.user_id == user['inquirer_id']).values(role='admin'))
    response = client.get(f'/api/calls/{cid}/transcript', headers=auth)
    assert response.status_code == 404 and response.json()['detail'] == 'Result not found'


@pytest.mark.parametrize('callback,expected', [
    (False, dict(status='completed', review_required=False, review_reason=None)),
    (True, dict(status='retry_wait', review_required=True, review_reason='callback_time_unknown')),
])
def test_callback_state_and_frontend_document_match_real_api(reserved, callback, expected):
    _, client, _, auth, iid, cid, body = reserved
    body.update(callback_requested=callback, callback_at=None,
                end_reason='academy_hung_up' if callback else 'completed')
    if callback:
        body.update(callback_reason_text='시각 미정 재연락 요청', callback_source_text='나중에 다시 전화 주세요.')
    response = client.post(f'/internal/calls/{cid}/result', headers=INTERNAL, json=body)
    assert response.status_code == 200, response.text
    view = client.get(f'/api/inquiries/{iid}', headers=auth).json()
    assert {key: view[key] for key in expected} == expected
    if callback:
        document = (Path(__file__).resolve().parents[2] /
                    'docs/api/frontend_result_response_example.md').read_text(encoding='utf-8')
        example = json.loads(re.search(r'```json\s*\n(.*?)\n```', document, re.S).group(1))
        assert {key: example[key] for key in expected} == expected
        assert example['result']['callback_requested'] is True
        assert example['result']['callback_at'] is None


@pytest.mark.parametrize('partial', [False, True])
def test_mysql_answer_migration_preserves_rows_and_repeats(partial):
    if not os.getenv('TEST_MYSQL_HOST'):
        pytest.skip('Disposable MySQL is configured in CI')
    from local_runtime import test_engine
    engine = test_engine()
    name = 'answer_migration_' + uuid4().hex[:12]
    sql = (Path(__file__).resolve().parents[2] /
           'docs/database/migrations/20261117_voice_result_answers.sql').read_text(encoding='utf-8')
    sql = '\n'.join(line for line in sql.replace('w5_answers', name).splitlines()
                    if not line.lstrip().startswith('--'))
    try:
        with engine.connect() as c:
            c.exec_driver_sql(f'CREATE TABLE {name} (id INT PRIMARY KEY, detail TEXT NOT NULL) ENGINE=InnoDB CHARSET=utf8mb4')
            c.exec_driver_sql(f"INSERT INTO {name} VALUES (1, '기존 답변 원문')")
            c.commit()
            if partial:
                c.exec_driver_sql(f'ALTER TABLE {name} ADD COLUMN `condition` VARCHAR(200) NULL')
                c.exec_driver_sql(f"UPDATE {name} SET `condition`='기존 조건' WHERE id=1")
                c.commit()
            for _ in range(2):
                for statement in sql.split(';'):
                    if statement.strip():
                        c.exec_driver_sql(statement).close()
            row = c.exec_driver_sql(f'SELECT id, detail, `condition`, reason_text, evidence_turns FROM {name}').one()
            assert row == (1, '기존 답변 원문', '기존 조건' if partial else None, None, None)
            # Old releases can still address their original columns after the additive DDL.
            assert c.exec_driver_sql(f'SELECT id, detail FROM {name}').one() == (1, '기존 답변 원문')
            c.exec_driver_sql(f"UPDATE {name} SET reason_text='판정 근거', evidence_turns=JSON_ARRAY(0) WHERE id=1")
            stored = c.exec_driver_sql(f'SELECT reason_text, evidence_turns FROM {name}').one()
            assert stored[0] == '판정 근거' and json.loads(stored[1]) == [0]
            c.commit()
    finally:
        with engine.connect() as c:
            c.exec_driver_sql(f'DROP TABLE IF EXISTS {name}')
        engine.dispose()
