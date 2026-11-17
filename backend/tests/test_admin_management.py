"""Admin-only edits and destructive cleanup, including MySQL FK and stale-request checks."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, update

import schema as s
from api import create_app
from contracts import ResultInput
from service import Service
from worker import make_result
from test_portable_smoke import login


@pytest.fixture(params=['sqlite', 'mysql'])
def managed(request, tmp_path):
    if request.param == 'mysql':
        if not os.getenv('TEST_MYSQL_HOST'):
            pytest.skip('Disposable MySQL is configured in CI')
        from local_runtime import test_engine
        engine = test_engine()
    else:
        engine = create_engine('sqlite:///' + str(tmp_path / 'admin.sqlite'))
        @event.listens_for(engine, 'connect')
        def foreign_keys(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
    service = Service(engine, clock=lambda: datetime(2026, 10, 5, 5, tzinfo=timezone.utc), allow_legacy_tokens=False)
    service.initialize()
    client = TestClient(create_app(engine, 'synthetic-admin-key', service, with_auth=True))
    identity, admin = login(client)
    with engine.begin() as c:
        c.execute(update(s.accounts).where(s.accounts.c.user_id == identity['inquirer_id']).values(role='admin'))
    parent, member = login(client)
    acid = str(uuid4())
    with engine.begin() as c:
        c.execute(s.academies.insert().values(id=acid, name='관리 합성 학원', phone=None, is_mock=True,
            region='대구 북구 침산동', hours=[dict(weekday=i,start_minute=0,end_minute=1440) for i in range(7)]))
    env = dict(engine=engine, service=service, client=client, admin=admin, member=member, parent=parent,
               actor=identity['inquirer_id'], acid=acid)
    yield env
    # Scope to this fixture's academy only; leave unrelated CI audit data intact.
    with engine.begin() as c:
        iids = select(s.inquiries.c.id).where(s.inquiries.c.academy_id == acid)
        c.execute(update(s.calls).where(s.calls.c.inquiry_id.in_(iids)).values(status='timeout'))
        c.execute(update(s.inquiries).where(s.inquiries.c.academy_id == acid).values(status='failed'))
    client.close()
    engine.dispose()


def inquiry(e):
    response = e['client'].post('/api/inquiries', headers={**e['member'], 'Idempotency-Key':str(uuid4())}, json=dict(
        inquirer_id=e['parent']['inquirer_id'],academy_id=e['acid'],
        student=dict(grade='M2',subject='MATH',level='MID',region='대구 북구 침산동'),question_codes=['shuttle']))
    assert response.status_code == 201, response.text
    return response.json()['inquiry_id']


def preview(e, kind, target):
    response = e['client'].get('/ops/'+kind+'/'+target+'/delete-preview', headers=e['admin'])
    assert response.status_code == 200, response.text
    return response.json()


def remove(e, kind, target, check=None):
    check = check or preview(e,kind,target)
    return e['client'].request('DELETE','/ops/'+kind+'/'+target,headers=e['admin'],
        json=dict(confirm_id=target,preview_token=check['preview_token']))


@pytest.mark.parametrize('route,method', [
    ('/ops/academies','GET'),('/ops/academies/example','GET'),('/ops/academies/example','PATCH'),
    ('/ops/academies/example/delete-preview','GET'),('/ops/academies/example','DELETE'),
    ('/ops/inquiries','GET'),('/ops/inquiries/example/delete-preview','GET'),('/ops/inquiries/example','DELETE')])
def test_every_management_route_requires_actual_admin(managed, route, method):
    e=managed
    body={'version':0,'name':'수정'} if method=='PATCH' else dict(confirm_id='example',preview_token='0'*64)
    kwargs={'json':body} if method in ['PATCH','DELETE'] else {}
    assert e['client'].request(method,route,**kwargs).status_code==401
    assert e['client'].request(method,route,headers=e['member'],**kwargs).status_code==403


def test_signup_cannot_select_admin_role_and_academy_account_is_not_admin(managed):
    e=managed
    body=dict(login_name='owner_'+uuid4().hex[:12],password='Synthetic_Owner123!',terms_agreed=True,account_type='academy')
    assert e['client'].post('/auth/register',json={**body,'role':'admin'}).status_code==422
    registered=e['client'].post('/auth/register',json=body)
    assert registered.status_code==201 and registered.json()['role']=='member'
    token=e['client'].post('/auth/login',json={k:body[k] for k in ['login_name','password']}).json()['access_token']
    assert e['client'].get('/ops/academies',headers={'Authorization':'Bearer '+token}).status_code==403


@pytest.mark.parametrize('change', ['revoked','expired','disabled','demoted'])
def test_admin_session_and_current_role_are_checked(managed, change):
    e=managed
    with e['engine'].begin() as c:
        if change in ['revoked','expired']:
            values={'revoked':True} if change=='revoked' else {'expires_at':e['service'].now()-timedelta(seconds=1)}
            c.execute(update(s.sessions).where(s.sessions.c.user_id==e['actor']).values(**values))
        else:
            c.execute(update(s.accounts).where(s.accounts.c.user_id==e['actor']).values(**({'enabled':False} if change=='disabled' else {'role':'member'})))
    assert e['client'].get('/ops/academies',headers=e['admin']).status_code==(403 if change=='demoted' else 401)


def test_partial_edit_preserves_omitted_fields_and_stale_owner_edit_conflicts(managed):
    e=managed;path='/ops/academies/'+e['acid']
    first=e['client'].get(path,headers=e['admin']).json()
    assert first['version']==0 and first['phone'] is None
    edited=e['client'].patch(path,headers=e['admin'],json=dict(version=0,name='바뀐 학원'))
    assert edited.status_code==200,edited.text
    value=edited.json()
    assert value['version']==1 and value['region']==first['region'] and value['phone'] is None
    assert e['client'].patch(path,headers=e['admin'],json=dict(version=0,name='덮어쓰기')).status_code==409
    assert e['client'].get(path,headers=e['admin']).json()['name']=='바뀐 학원'


@pytest.mark.parametrize('fields', [dict(is_mock=False),dict(role='admin'),dict(name=None),dict(name='  '),
    dict(phone='abc1234'),dict(region='없는 지역'),dict(call_hours=[]),
    dict(call_hours=[dict(day_of_week=0,start_time='18:00',end_time='14:00')]),
    dict(call_hours=[dict(day_of_week=0,start_time='14:00',end_time='16:00'),dict(day_of_week=0,start_time='15:00',end_time='17:00')])])
def test_edit_rejects_invalid_or_privileged_fields(managed, fields):
    e=managed
    response=e['client'].patch('/ops/academies/'+e['acid'],headers=e['admin'],json={'version':0,**fields})
    assert response.status_code==422,response.text


def test_operational_fields_edit_and_failed_address_edit_roll_back(managed):
    e=managed;path='/ops/academies/'+e['acid']
    response=e['client'].patch(path,headers=e['admin'],json=dict(version=0,phone='010-0000-0001',
        classes=[dict(grade_code='M2',subject_code='MATH',level_code='MID')],
        call_hours=[dict(day_of_week=0,start_time='14:00',end_time='18:00')]))
    assert response.status_code==200,response.text
    value=response.json();assert value['classes'][0]['grade_code']=='M2' and value['call_hours'][0]['start_time']=='14:00:00'
    failed=e['client'].patch(path,headers=e['admin'],json=dict(version=1,name='롤백 대상',address='소유자 없음'))
    assert failed.status_code==409
    current=e['client'].get(path,headers=e['admin']).json()
    assert current['name']=='관리 합성 학원' and current['version']==1


def test_delete_queued_inquiry_then_academy_preserves_accounts_and_unrelated_rows(managed):
    e=managed;iid=inquiry(e)
    acid=e['acid'];a=preview(e,'academies',acid)
    assert not a['can_delete'] and a['linked_inquiries']==1
    assert remove(e,'academies',acid,a).status_code==409
    before=e['client'].get('/auth/me',headers=e['member']).json()
    p=preview(e,'inquiries',iid)
    assert p['can_delete'] and p['counts']['w5_questions']==1
    assert remove(e,'inquiries',iid,p).status_code==200
    assert e['client'].get('/api/inquiries/'+iid,headers=e['member']).status_code==404
    assert e['client'].get('/auth/me',headers=e['member']).json()==before
    assert remove(e,'academies',acid).status_code==200
    assert e['client'].get('/ops/academies/'+acid,headers=e['admin']).status_code==404


def test_delete_preview_stale_or_wrong_target_cannot_delete(managed):
    e=managed;iid=inquiry(e);p=preview(e,'inquiries',iid)
    response=e['client'].request('DELETE','/ops/inquiries/'+iid,headers=e['admin'],
        json=dict(confirm_id=str(uuid4()),preview_token=p['preview_token']))
    assert response.status_code==422
    with e['engine'].begin() as c:c.execute(update(s.inquiries).where(s.inquiries.c.id==iid).values(priority=9))
    assert remove(e,'inquiries',iid,p).status_code==409
    assert e['client'].get('/api/inquiries/'+iid,headers=e['member']).status_code==200


def completed(e, iid):
    # Insert a single synthetic attempt without dispatching or reserving unrelated CI inquiries.
    cid=str(uuid4())
    with e['engine'].begin() as c:
        qs=c.execute(select(s.questions).where(s.questions.c.inquiry_id==iid)).mappings().all()
        payload=dict(call_id=cid,inquiry_id=iid,is_mock=True,questions=[dict(question_id=q['id'],question_code=q['code']) for q in qs])
        c.execute(update(s.inquiries).where(s.inquiries.c.id==iid).values(status='calling'))
        c.execute(s.calls.insert().values(id=cid,inquiry_id=iid,attempt_no=1,status='answered',created_at=e['service'].now(),
            deadline=e['service'].now()+timedelta(seconds=600),dispatch_payload=payload,delivery_count=1))
    body=make_result(payload)
    assert e['service'].result(cid,ResultInput.model_validate(body))['applied']
    return cid,body


def test_completed_result_children_delete_on_real_foreign_keys(managed):
    e=managed;iid=inquiry(e);cid,body=completed(e,iid)
    with e['engine'].begin() as c:
        c.execute(s.corrections.insert().values(id=str(uuid4()),call_id=cid,revision=1,reviewer=e['actor'],reason='합성 교정',payload=body,created_at=e['service'].now()))
        c.execute(s.review_holds.insert().values(inquiry_id=iid,call_id=cid,reason='합성 검토',open=False,created_at=e['service'].now()))
        c.execute(s.outbox.insert().values(id=str(uuid4()),call_id=cid,created_at=e['service'].now()))
    assert remove(e,'inquiries',iid).status_code==200
    with e['engine'].connect() as c:
        assert c.execute(select(func.count()).select_from(s.results).where(s.results.c.call_id==cid)).scalar_one()==0
        assert c.execute(select(func.count()).select_from(s.corrections).where(s.corrections.c.call_id==cid)).scalar_one()==0
        assert c.execute(select(func.count()).select_from(s.accounts).where(s.accounts.c.user_id==e['parent']['inquirer_id'])).scalar_one()==1


@pytest.mark.parametrize('blocker', ['call','lease','recording'])
def test_active_or_recorded_work_is_not_deleted(managed, blocker):
    e=managed;iid=inquiry(e);cid,body=completed(e,iid)
    with e['engine'].begin() as c:
        if blocker=='call':c.execute(update(s.calls).where(s.calls.c.id==cid).values(status='accepted'))
        elif blocker=='lease':c.execute(s.delivery_leases.insert().values(call_id=cid,claim_id=str(uuid4()),lease_until=e['service'].now()+timedelta(seconds=10)))
        else:c.execute(update(s.results).where(s.results.c.call_id==cid).values(payload={**body,'recording_url':'https://example.invalid/synthetic-recording'}))
    p=preview(e,'inquiries',iid);assert not p['can_delete']
    assert remove(e,'inquiries',iid,p).status_code==409
    assert e['client'].get('/api/inquiries/'+iid,headers=e['member']).status_code==200


def test_admin_lists_filter_and_do_not_expose_passwords_or_sessions(managed):
    e=managed;iid=inquiry(e)
    response=e['client'].get('/ops/inquiries',headers=e['admin'],params=dict(academy_id=e['acid'],inquirer_id=e['parent']['inquirer_id'],limit=1))
    assert response.status_code==200 and response.json()['total']==1
    assert response.json()['items'][0]['inquiry_id']==iid
    assert 'password' not in response.text and 'token' not in response.text
    assert e['client'].get('/ops/academies',headers=e['admin'],params=dict(q='管理%')).json()['total']==0


def test_delete_permission_failure_rolls_back_all_children(managed):
    from sqlalchemy.exc import OperationalError
    e=managed;iid=inquiry(e);p=preview(e,'inquiries',iid)
    def deny(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith('DELETE FROM w5_inquiries'):
            raise OperationalError(statement,parameters,Exception(1142,'synthetic DELETE denied'))
    event.listen(e['engine'],'before_cursor_execute',deny)
    try:
        response=remove(e,'inquiries',iid,p)
    finally:
        event.remove(e['engine'],'before_cursor_execute',deny)
    assert response.status_code==503 and 'DELETE denied' not in response.text
    after=preview(e,'inquiries',iid)
    assert after['counts']==p['counts'] and after['preview_token']==p['preview_token']


def test_registered_owner_edit_observes_admin_version_and_academy_delete_preserves_owner(managed):
    e=managed
    credentials=dict(login_name='profile_'+uuid4().hex[:12],password='Synthetic_Owner123!',terms_agreed=True,account_type='academy')
    owner=e['client'].post('/auth/register',json=credentials).json()
    token=e['client'].post('/auth/login',json={k:credentials[k] for k in ['login_name','password']}).json()['access_token']
    auth={'Authorization':'Bearer '+token}
    profile=dict(name='등록 학원',phone='010-0000-0001',region='대구 북구 침산동',address='초기 주소',classes=[],
        call_hours=[dict(day_of_week=0,start_time='14:00',end_time='18:00')])
    registered=e['client'].post('/api/my-academy',headers=auth,json=profile)
    assert registered.status_code==201,registered.text
    academy=registered.json();path='/ops/academies/'+academy['academy_id']
    edited=e['client'].patch(path,headers=e['admin'],json=dict(version=academy['version'],address='관리자 수정 주소'))
    assert edited.status_code==200 and edited.json()['version']==academy['version']+1
    assert e['client'].put('/api/my-academy',headers=auth,json={**profile,'version':academy['version']}).status_code==409
    assert e['client'].get('/api/my-academy',headers=auth).json()['address']=='관리자 수정 주소'
    assert remove(e,'academies',academy['academy_id']).status_code==200
    identity=e['client'].get('/auth/me',headers=auth).json()
    assert identity['inquirer_id']==owner['inquirer_id'] and identity['academy_registration_status']=='unregistered'
