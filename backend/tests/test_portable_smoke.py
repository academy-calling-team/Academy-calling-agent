"""Serial portability checks only; MySQL row-lock/Redis coverage lives in integration tests."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from api import create_app
from schema import academies, calls, metadata
from service import Service
from worker import MockWorker, make_result
from http_worker6 import WorkerHttpAdapter
import settings


@pytest.fixture
def portable(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'serial.sqlite'))
    service = Service(engine, clock=lambda: datetime(2026, 10, 5, 5, tzinfo=timezone.utc),
                      allow_legacy_tokens=False)
    service.initialize()
    with engine.begin() as c:
        c.execute(academies.insert().values(id='demo-academy', name='가상 시험 학원',
            region='대구 북구 침산동', phone=None, is_mock=True,
            hours=[dict(weekday=i,start_minute=0,end_minute=1440) for i in range(7)]))
    worker = MockWorker(engine, 'synthetic-test-key')
    client = TestClient(create_app(engine, 'synthetic-test-key', service, worker=worker, with_auth=True))
    yield engine, service, client
    client.close()
    worker.close()
    engine.dispose()


def login(client):
    credentials = {'login_name':'demo_' + uuid4().hex[:12], 'password':'Synthetic_Test_Pass123!'}
    registered = client.post('/auth/register', json=credentials)
    assert registered.status_code == 201, registered.text
    logged = client.post('/auth/login', json=credentials)
    assert logged.status_code == 200, logged.text
    data = logged.json()
    return data, {'Authorization':'Bearer ' + data['access_token']}


def test_login_inquiry_result_duplicate_and_ownership(portable):
    engine, service, client = portable
    identity, headers = login(client)
    request = dict(inquirer_id=identity['inquirer_id'], academy_id='demo-academy',
        student=dict(grade='M2', subject='MATH', level='MID', region='대구 북구 침산동'),
        question_codes=['shuttle','vacancy','class_time'])
    headers['Idempotency-Key'] = str(uuid4())
    response = client.post('/api/inquiries', json=request, headers=headers)
    assert response.status_code == 201, response.text
    iid = response.json()['inquiry_id']
    duplicate = client.post('/api/inquiries', json=request, headers=headers)
    assert duplicate.status_code == 201 and duplicate.json()['inquiry_id'] == iid
    other, other_headers = login(client)
    assert client.get('/api/inquiries/' + iid, headers=other_headers).status_code == 404
    tick = client.post('/internal/mock/tick', headers={'X-Internal-Key':'synthetic-test-key'})
    assert tick.status_code == 200, tick.text
    cid = tick.json()['reserved'][0]
    with engine.connect() as c:
        payload = c.execute(select(calls.c.dispatch_payload).where(calls.c.id==cid)).scalar_one()
    result = make_result(payload, unanswered=['vacancy'], negative=['shuttle'])
    for _ in range(2):
        sent = client.post('/internal/calls/' + cid + '/result', json=result,
                           headers={'X-Internal-Key':'synthetic-test-key'})
        assert sent.status_code == 200, sent.text
    view = client.get('/api/inquiries/' + iid, headers=headers).json()
    assert view['status'] == 'completed'
    assert view['result']['answers'][0]['yes_no'] is False
    assert view['result']['answers'][1]['answered'] is False
    assert view['result']['answers'][1]['yes_no'] is None
    assert 'transcript' not in view['result'] and 'recording_url' not in view['result']
    assert client.post('/auth/logout', headers=headers).status_code == 200
    assert client.get('/api/inquiries/' + iid, headers=headers).status_code == 401


def test_password_validation_does_not_echo_password(portable):
    _, _, client = portable
    response = client.post('/auth/register', json={'login_name':'demo', 'password':'short'})
    assert response.status_code == 422
    assert 'short' not in response.text


def test_schema_shape():
    assert len(metadata.tables) == 21
    assert sum(len(t.columns) for t in metadata.tables.values()) == 125
    assert sum(len(t.foreign_keys) for t in metadata.tables.values()) == 20


def test_database_configuration_has_no_original_pc_dependency(monkeypatch):
    values = dict(MYSQL_HOST='127.0.0.1', MYSQL_PORT='13306', MYSQL_USER='example-user',
                  MYSQL_PASSWORD='synthetic_password_#@', MYSQL_DATABASE='team8_dev')
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    url = settings.database_url()
    assert url.port == 13306 and url.password == values['MYSQL_PASSWORD']
    assert url.database == 'team8_dev'
    monkeypatch.delenv('MYSQL_PASSWORD')
    with pytest.raises(ValueError, match='MYSQL_PASSWORD'):
        settings.database_url()


@pytest.mark.parametrize('host,database', [('3.35.222.227','team8_test'),('localhost','team8_dev')])
def test_integration_database_rejects_shared_or_non_test_target(monkeypatch, host, database):
    monkeypatch.setenv('TEST_MYSQL_HOST', host)
    monkeypatch.setenv('TEST_MYSQL_DATABASE', database)
    with pytest.raises(ValueError, match='local MySQL'):
        settings.database_url(test=True)


@pytest.mark.parametrize('url', ['redis://example.invalid:6379/1','redis://localhost:6379/0'])
def test_integration_redis_rejects_shared_or_default_database(monkeypatch, url):
    monkeypatch.setenv('TEST_REDIS_URL', url)
    with pytest.raises(ValueError, match='local Redis'):
        settings.redis_url(test=True)


def test_settings_fail_closed_and_internal_key_is_not_generated(monkeypatch):
    monkeypatch.setenv('APP_MODE', 'production')
    with pytest.raises(ValueError, match='development_mock'):
        settings.require_mock_mode()
    monkeypatch.setenv('INTERNAL_API_KEY', '')
    with pytest.raises(ValueError, match='INTERNAL_API_KEY'):
        settings.internal_key()
    monkeypatch.setenv('CORS_ORIGINS', '*')
    with pytest.raises(ValueError, match='explicit'):
        settings.cors_origins()


def test_real_dialing_still_disabled_without_network_call():
    adapter = WorkerHttpAdapter('http://localhost:18888', 'synthetic-test-key')
    try:
        with pytest.raises(ValueError, match='Real dialing is disabled'):
            adapter.accept({'call_id':'synthetic-call','is_mock':False})
    finally:
        adapter.close()


def test_server_factory_uses_repository_settings_without_connecting_to_db(monkeypatch):
    from serve6 import build
    values = dict(APP_MODE='development_mock', MYSQL_HOST='127.0.0.1', MYSQL_PORT='13306',
                  MYSQL_USER='synthetic-user', MYSQL_PASSWORD='synthetic-password',
                  MYSQL_DATABASE='team8_dev', REDIS_URL='redis://127.0.0.1:16389/0',
                  INTERNAL_API_KEY='synthetic-internal-key-for-test-only-123456',
                  CORS_ORIGINS='http://localhost:5173')
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with TestClient(build()) as client:
        assert client.get('/api/options').status_code == 200
        assert client.get('/openapi.json').json()['info']['version'] == '0.4.0'
        assert client.get('/api/inquiries').status_code == 401
