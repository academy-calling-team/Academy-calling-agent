"""Account isolation, profile transactions and compatibility for academy registration."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import os

import pytest
from sqlalchemy import select

from schema import academies, academy_profiles
from test_portable_smoke import portable


PROFILE = dict(name='시험 학원', phone='053-123-4567', region='대구 북구 침산동',
               address='시험 주소', classes=[dict(grade_code='M2', subject_code='MATH')],
               call_hours=[dict(day_of_week=0, start_time='14:00', end_time='18:00')])


@pytest.fixture(params=['sqlite', 'mysql'])
def academy_env(request, portable):
    if request.param == 'sqlite':
        yield portable
        return
    if not os.getenv('TEST_MYSQL_HOST'):
        pytest.skip('Disposable MySQL is configured in CI')
    from api import create_app
    from fastapi.testclient import TestClient
    from local_runtime import test_engine
    from service import Service
    engine = test_engine()
    service = Service(engine, allow_legacy_tokens=False)
    service.initialize()
    client = TestClient(create_app(engine, 'synthetic-test-key', service, with_auth=True))
    yield engine, service, client
    client.close()
    engine.dispose()


def account(client, name, account_type='academy'):
    name = name + '_' + uuid4().hex[:6]
    credentials = dict(login_name=name, password='Synthetic_Test_Pass123!')
    response = client.post('/auth/register', json={
        **credentials, 'terms_agreed': True, 'account_type': account_type})
    assert response.status_code == 201, response.text
    token = client.post('/auth/login', json=credentials).json()['access_token']
    return {'Authorization': 'Bearer ' + token}


def test_registration_edit_and_session_identity(academy_env):
    engine, _, client = academy_env
    auth = account(client, 'academy_owner')
    me = client.get('/auth/me', headers=auth).json()
    assert (me['role'], me['account_type'], me['academy_id']) == ('member', 'academy', None)
    assert client.get('/api/my-academy', headers=auth).status_code == 404
    created = client.post('/api/my-academy', headers=auth, json=PROFILE)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body['version'] == 1 and body['address'] == PROFILE['address']
    assert client.get('/auth/me', headers=auth).json()['academy_id'] == body['academy_id']
    assert client.post('/api/my-academy', headers=auth, json=PROFILE).status_code == 409
    assert client.put('/api/my-academy', headers=auth, json={**PROFILE, 'name': '수정 학원', 'version': 1}).status_code == 200
    assert client.put('/api/my-academy', headers=auth, json={**PROFILE, 'version': 1}).status_code == 409
    saved = client.get('/api/my-academy', headers=auth).json()
    assert saved['name'] == '수정 학원' and saved['version'] == 2
    with engine.connect() as connection:
        assert connection.execute(select(academies.c.is_mock).where(academies.c.id == body['academy_id'])).scalar() is False


def test_ownership_and_privilege_boundaries(academy_env):
    _, _, client = academy_env
    owner = account(client, 'academy_one')
    other = account(client, 'academy_two')
    parent = account(client, 'parent_one', 'parent')
    assert client.get('/api/my-academy').status_code == 401
    assert client.post('/api/my-academy', headers=parent, json=PROFILE).status_code == 403
    assert client.post('/api/my-academy', headers=owner, json=PROFILE).status_code == 201
    assert client.get('/api/my-academy', headers=other).status_code == 404
    assert client.put('/api/my-academy', headers=other, json={**PROFILE, 'version': 1}).status_code == 404
    assert client.post('/api/my-academy', headers=other, json={**PROFILE, 'owner_id': 'someone'}).status_code == 422
    assert client.put('/api/academies/demo-academy/settings', headers=owner,
                      json={'classes': [], 'call_hours': []}).status_code == 403
    assert client.post('/auth/register', json=dict(login_name='bad_' + uuid4().hex[:10], password='Synthetic_Test_Pass123!',
                       terms_agreed=True, account_type='admin')).status_code == 422
    credentials = dict(login_name='legacy_' + uuid4().hex[:10], password='Synthetic_Test_Pass123!')
    assert client.post('/auth/register', json={**credentials, 'terms_agreed': True}).json()['account_type'] == 'parent'


@pytest.mark.parametrize('patch', [
    {'name': ' '}, {'phone': 'abc'}, {'region': '없는 지역'}, {'call_hours': []},
    {'classes': PROFILE['classes'] * 2},
    {'call_hours': [dict(day_of_week=0, start_time='18:00', end_time='14:00')]},
    {'call_hours': PROFILE['call_hours'] * 2},
])
def test_invalid_profile_does_not_create_partial_records(academy_env, patch):
    engine, _, client = academy_env
    auth = account(client, 'invalid_academy')
    assert client.post('/api/my-academy', headers=auth, json={**PROFILE, **patch}).status_code == 422
    with engine.connect() as connection:
        owner = client.get('/auth/me', headers=auth).json()['inquirer_id']
        assert connection.execute(select(academy_profiles).where(academy_profiles.c.owner_id == owner)).first() is None


def test_competing_registration_creates_one_academy(academy_env):
    engine, _, client = academy_env
    auth = account(client, 'concurrent_academy')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post('/api/my-academy', headers=auth, json=PROFILE), range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    with engine.connect() as connection:
        owner = client.get('/auth/me', headers=auth).json()['inquirer_id']
        assert len(connection.execute(select(academy_profiles).where(academy_profiles.c.owner_id == owner)).all()) == 1


def test_registration_rolls_back_when_settings_storage_fails(academy_env, monkeypatch):
    engine, service, client = academy_env
    auth = account(client, 'rollback_academy')
    name = 'rollback_' + uuid4().hex[:12]
    original = service.write_academy_settings

    def interrupted(connection, academy_id, body):
        original(connection, academy_id, body)
        raise RuntimeError('simulated storage failure')

    monkeypatch.setattr(service, 'write_academy_settings', interrupted)
    with pytest.raises(RuntimeError, match='simulated storage failure'):
        client.post('/api/my-academy', headers=auth, json={**PROFILE, 'name': name})
    assert client.get('/api/my-academy', headers=auth).status_code == 404
    with engine.connect() as connection:
        assert connection.execute(select(academies.c.id).where(academies.c.name == name)).first() is None


def test_concurrent_mysql_updates_keep_one_version(academy_env):
    engine, _, client = academy_env
    if engine.dialect.name != 'mysql':
        pytest.skip('MySQL row-lock test')
    auth = account(client, 'version_academy')
    assert client.post('/api/my-academy', headers=auth, json=PROFILE).status_code == 201
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda number: client.put('/api/my-academy', headers=auth,
            json={**PROFILE, 'name': '학원 ' + str(number), 'version': 1}), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert client.get('/api/my-academy', headers=auth).json()['version'] == 2
