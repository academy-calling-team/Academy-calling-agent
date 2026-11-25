"""Question location compatibility, real HTTP worker boundary and additive migration."""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4
import importlib.util
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from test_portable_smoke import portable, login
from schema import calls, inquiries, sessions
from service import fingerprint
from http_worker6 import WorkerHttpAdapter
from contracts import ResultInput
from worker import make_result


def inquiry(client, headers, identity, key, **patch):
    body = dict(inquirer_id=identity['inquirer_id'], academy_id='demo-academy',
                student=dict(grade='M2', subject='MATH', level='MID', region='대구 북구 침산동'),
                question_codes=['shuttle', 'pickup'])
    return client.post('/api/inquiries', json={**body, **patch},
                       headers={**headers, 'Idempotency-Key': key})


@pytest.mark.parametrize('locations', [None, {}])
def test_legacy_hash_and_same_key_retry_are_preserved(portable, locations):
    engine, _, client = portable
    identity, headers = login(client)
    created = inquiry(client, headers, identity, 'legacy')
    assert created.status_code == 201
    old_body = dict(inquirer_id=identity['inquirer_id'], academy_id='demo-academy',
                    student=dict(grade='M2', subject='MATH', level='MID', region='대구 북구 침산동'),
                    question_codes=['shuttle', 'pickup'])
    with engine.connect() as c:
        stored = c.execute(select(inquiries.c.payload_hash).where(
            inquiries.c.id == created.json()['inquiry_id'])).scalar_one()
    assert stored == fingerprint(old_body)
    retried = inquiry(client, headers, identity, 'legacy', locations=locations)
    assert retried.status_code == 201 and retried.json()['duplicate'] is True
    assert retried.json()['inquiry_id'] == created.json()['inquiry_id']
    changed = inquiry(client, headers, identity, 'legacy',
                      locations={'shuttle': {'kind': '학교', 'name': '침산초등학교'}})
    assert changed.status_code == 409


@pytest.mark.parametrize('locations', [
    {'shuttle': {'kind': '기타', 'name': '학교'}},
    {'shuttle': {'kind': '학교', 'name': '  '}},
    {'shuttle': {'kind': '학교', 'name': '가' * 101}},
    {'vacancy': {'kind': '학교', 'name': '침산초등학교'}},
])
def test_invalid_locations_are_rejected(portable, locations):
    _, _, client = portable
    identity, headers = login(client)
    assert inquiry(client, headers, identity, 'bad', locations=locations).status_code == 422


def test_location_change_keeps_conflict_and_whitespace_is_canonical(portable):
    _, _, client = portable
    identity, headers = login(client)
    first = inquiry(client, headers, identity, 'place', locations={'shuttle': {'kind': '학교', 'name': ' 침산초등학교 '}})
    same = inquiry(client, headers, identity, 'place', locations={'shuttle': {'kind': '학교', 'name': '침산초등학교'}})
    changed = inquiry(client, headers, identity, 'place', locations={'shuttle': {'kind': '학교', 'name': '다른초등학교'}})
    assert first.status_code == same.status_code == 201
    assert same.json()['duplicate'] is True and changed.status_code == 409


def test_dispatch_time_uses_dispatch_day_and_persists(portable):
    engine, service, client = portable
    identity, headers = login(client)
    intake = service.clock()
    response = inquiry(client, headers, identity, 'next-day')
    service.clock = lambda: intake + timedelta(days=1)
    with engine.begin() as c:
        c.execute(update(sessions).where(sessions.c.user_id == identity['inquirer_id']).values(
            expires_at=service.now() + timedelta(days=1)))
    cid = service.reserve()[0]
    with engine.connect() as c:
        payload = c.execute(select(calls.c.dispatch_payload).where(calls.c.id == cid)).scalar_one()
    context = payload['time_context']
    assert context == dict(inquiry_created_at=intake.isoformat(),
                           dispatch_requested_at=service.clock().isoformat(), timezone='Asia/Seoul')
    detail = client.get('/api/inquiries/' + response.json()['inquiry_id'], headers=headers).json()
    assert detail['created_at'] == intake.isoformat()
    assert detail['attempts'][0]['time_context'] == context


def test_actual_voice_http_round_trip_accepts_locations_and_missing_region(portable, tmp_path, monkeypatch):
    _, service, client = portable
    identity, headers = login(client)
    question_codes = ['shuttle', 'pickup', 'level_fit', 'vacancy', 'class_time']
    created = inquiry(client, headers, identity, 'http-worker',
                      question_codes=question_codes,
                      student=dict(grade='M2', subject='MATH', level='MID'),
                      locations={'shuttle': {'kind': '학교', 'name': '침산초등학교'},
                                 'pickup': {'kind': '집 근처', 'name': '침산네거리'}})
    assert created.status_code == 201
    voice_dir = Path(__file__).resolve().parents[2] / 'voice/mock_worker'
    monkeypatch.syspath_prepend(str(voice_dir))
    spec = importlib.util.spec_from_file_location('location_voice_app', voice_dir / 'app.py')
    voice = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(voice)

    def callback(request):
        reply = client.request(request.method, request.url.raw_path.decode(),
                               content=request.content, headers=dict(request.headers))
        return httpx.Response(reply.status_code, content=reply.content, headers=dict(reply.headers))

    sender = voice.Sender('http://backend.test', 'synthetic-test-key', delay_sec=0,
                          transport=httpx.MockTransport(callback))
    store = voice.ReceiptStore(tmp_path / 'voice.sqlite')
    with TestClient(voice.create_app('synthetic-test-key', store, sender)) as worker_client:
        def forward(request):
            reply = worker_client.request(request.method, request.url.raw_path.decode(),
                                          content=request.content, headers=dict(request.headers))
            return httpx.Response(reply.status_code, content=reply.content, headers=dict(reply.headers))
        adapter = WorkerHttpAdapter('http://localhost:18780', 'synthetic-test-key', transport=httpx.MockTransport(forward))
        try:
            cid = service.reserve()[0]
            service.deliver(adapter)
            receipt = store.receipt(cid)
            assert receipt.payload['student']['region'] is None
            assert [question['question_code'] for question in receipt.payload['questions']] == question_codes
            ResultInput.model_validate(make_result(receipt.payload))
        finally:
            adapter.close()
    detail = client.get('/api/inquiries/' + created.json()['inquiry_id'], headers=headers).json()
    assert detail['status'] == 'completed'
    assert [question['question_code'] for question in detail['questions']] == question_codes
    assert detail['questions'][0]['location']['name'] == '침산초등학교'
    assert detail['questions'][1]['location']['name'] == '침산네거리'
    assert all('location' not in row for row in detail['result']['answers'])


@pytest.mark.parametrize('partial', [False, True])
def test_mysql_location_migration_preserves_existing_rows_and_repeats(partial):
    if not os.getenv('TEST_MYSQL_HOST'):
        pytest.skip('Disposable MySQL is configured in CI')
    from local_runtime import test_engine
    engine = test_engine()
    name = 'locations_migration_' + uuid4().hex[:10]
    sql = (Path(__file__).resolve().parents[2] / 'docs/database/migrations/20261115_question_locations.sql').read_text(encoding='utf-8')
    sql = sql.replace('w5_questions', name)
    sql = '\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
    try:
        with engine.connect() as c:
            c.exec_driver_sql(f'CREATE TABLE {name} (id VARCHAR(36) PRIMARY KEY, code VARCHAR(30)) ENGINE=InnoDB CHARSET=utf8mb4')
            c.exec_driver_sql(f"INSERT INTO {name} VALUES ('existing-question', 'shuttle')")
            c.commit()
            if partial:
                c.exec_driver_sql(f'ALTER TABLE {name} ADD COLUMN location_kind VARCHAR(20) NULL')
            for _ in range(2):
                for statement in sql.split(';'):
                    if statement.strip():
                        c.exec_driver_sql(statement).close()
            assert c.exec_driver_sql(f'SELECT id, code, location_kind, location_name FROM {name}').one() == ('existing-question', 'shuttle', None, None)
    finally:
        with engine.connect() as c:
            c.exec_driver_sql(f'DROP TABLE IF EXISTS {name}')
        engine.dispose()
