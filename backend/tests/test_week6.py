from datetime import timedelta
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import copy
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,update,func
from test_backend import env,create,tick,get,payload,send,event
from test_extensions import queue
from schema import accounts,sessions,inquiries,calls,results,fallback_tasks,review_holds,review_actions,provider_calls,provider_inbox
from contracts import CorrectionInput,ResultInput
from contracts6 import Credentials,CallbackReview,FallbackReview
from auth6 import AuthStore
from api import create_app
from worker import make_result
from provider6 import VapiBridge
from service import Service
from ops6 import Operations

def test_unknown_callback_holds_without_guessing_time(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];body=make_result(payload(e,cid))
    body['callback_requested']=True
    assert send(e,cid,body).status_code==200
    view=get(e,iid)
    assert view['status']=='retry_wait' and view['review_reason']=='callback_time_unknown'
    assert view['result']['callback_at'] is None
    e['clock'][0]+=timedelta(hours=1)
    assert tick(e)['reserved']==[] and len(get(e,iid)['attempts'])==1
    review=CallbackReview(action='schedule',callback_at=e['clock'][0]+timedelta(minutes=30),reason='확인된 가상 재통화 시간')
    e['s'].review_callback(iid,review,'local-test-reviewer')
    assert not get(e,iid)['review_required'] and tick(e)['reserved']==[]
    e['clock'][0]+=timedelta(minutes=30)
    second=tick(e)['reserved'][0]
    assert second!=cid and len(get(e,iid)['attempts'])==2
    body2=make_result(payload(e,second));body2['callback_requested']=True
    assert send(e,second,body2).status_code==200 # A second unknown time updates the existing hold.
    e['s'].review_callback(iid,CallbackReview(action='cancel',reason='추가 연락 불필요 확인'),'local-test-reviewer')
    assert get(e,iid)['status']=='completed' and tick(e)['reserved']==[]

def test_callback_review_requires_current_hold_and_future(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];b=make_result(payload(e,cid));b['callback_requested']=True
    send(e,cid,b)
    with pytest.raises(HTTPException) as error:
        e['s'].review_callback(iid,CallbackReview(action='schedule',callback_at=e['clock'][0],reason='검증'),'reviewer')
    assert error.value.status_code==422 and get(e,iid)['review_required']
    e['s'].review_callback(iid,CallbackReview(action='cancel',reason='검증'),'reviewer')
    with pytest.raises(HTTPException) as error:
        e['s'].review_callback(iid,CallbackReview(action='cancel',reason='검증'),'reviewer')
    assert error.value.status_code==409

def test_callback_review_parallel_applies_once(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];b=make_result(payload(e,cid));b['callback_requested']=True;send(e,cid,b)
    def apply():
        try:return e['s'].review_callback(iid,CallbackReview(action='cancel',reason='중복 시험'),'reviewer')['status']
        except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(lambda _:apply(),range(2)))
    assert sorted(out,key=str)==sorted(['completed',409],key=str)

def test_fallback_persist_review_and_dry_run(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];event(e,cid,'invalid_number')
    assert get(e,iid)['fallback_status']=='needs_review'
    with pytest.raises(HTTPException):e['s'].dry_run_fallback(iid)
    e['s'].review_fallback(iid,FallbackReview(action='prepare',reason='개발 문구 검토',message='가상 문의는 연결되지 않았습니다.'),'test-admin')
    first=e['s'].dry_run_fallback(iid);second=e['s'].dry_run_fallback(iid)
    assert first['receipt']['sent'] is False and second['duplicate'] is True
    assert first['receipt']==second['receipt'] and get(e,iid)['fallback_status']=='dry_run_complete'
    e['engine'].dispose()
    with e['engine'].connect() as c:
        task=c.execute(select(fallback_tasks).where(fallback_tasks.c.inquiry_id==iid)).mappings().one()
        assert task['reviewer']=='test-admin' and task['status']=='dry_run_complete'

@pytest.mark.parametrize('failure',['rejected','disclosure_missing'])
def test_rejected_or_no_disclosure_not_fallback(env,failure):
    e=env;iid=create(e);cid=tick(e)['reserved'][0]
    if failure=='rejected':event(e,cid,'rejected')
    else:
        b=make_result(payload(e,cid));b['disclosure_played']=False;send(e,cid,b)
    assert get(e,iid)['fallback_required'] is False and get(e,iid)['fallback_status'] is None

def test_fallback_dismissal_does_not_send(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];event(e,cid,'invalid_number')
    e['s'].review_fallback(iid,FallbackReview(action='dismiss',reason='가상 번호 수정 확인'),'test-admin')
    with pytest.raises(HTTPException):e['s'].dry_run_fallback(iid)
    assert get(e,iid)['fallback_status']=='dismissed'

def test_auth_password_hash_session_expiry_revocation_and_owner(env):
    e=env;store=AuthStore(e['s'],session_seconds=60)
    credentials=Credentials(login_name='u'+uuid4().hex[:20],password='local_only_fixture_password_123')
    registered=store.register(credentials);issued=store.login(credentials);token=issued['access_token']
    with e['engine'].connect() as c:
        account=c.execute(select(accounts).where(accounts.c.user_id==registered['inquirer_id'])).mappings().one()
        session=c.execute(select(sessions).where(sessions.c.user_id==registered['inquirer_id'])).mappings().one()
        assert account['password_hash'].startswith('$argon2') and session['token_hash']!=token
    identity=store.identity(token);assert identity['role']=='member' and 'password_hash' not in identity
    e['s'].allow_legacy_tokens=False
    with pytest.raises(HTTPException):e['s'].get(create_without_legacy(e),e['tokens'][0])
    store.logout(token)
    with pytest.raises(HTTPException):store.identity(token)
    fresh=store.login(credentials)['access_token'];e['clock'][0]+=timedelta(seconds=60)
    with pytest.raises(HTTPException):store.identity(fresh)
def create_without_legacy(e):
    # Create the inquiry before the legacy compatibility switch, then restore strict mode.
    e['s'].allow_legacy_tokens=True
    try:return create(e)
    finally:e['s'].allow_legacy_tokens=False

def test_auth_failed_attempts_commit_lock_and_recover(env):
    e=env;store=AuthStore(e['s']);name='u'+uuid4().hex[:20]
    right=Credentials(login_name=name,password='local_only_fixture_password_123');store.register(right)
    wrong=Credentials(login_name=name,password='wrong_local_fixture_password_123')
    for _ in range(5):
        with pytest.raises(HTTPException) as error:store.login(wrong)
        assert error.value.status_code==401
    with pytest.raises(HTTPException) as error:store.login(right)
    assert error.value.status_code==429
    e['clock'][0]+=timedelta(seconds=300)
    assert store.identity(store.login(right)['access_token'])['login_name']==name

def test_disabled_account_and_duplicate_registration(env):
    e=env;store=AuthStore(e['s']);body=Credentials(login_name='u'+uuid4().hex[:20],password='local_only_fixture_password_123')
    user=store.register(body)['inquirer_id'];token=store.login(body)['access_token']
    with pytest.raises(HTTPException) as error:store.register(body)
    assert error.value.status_code==409
    with e['engine'].begin() as c:c.execute(update(accounts).where(accounts.c.user_id==user).values(enabled=False))
    with pytest.raises(HTTPException):store.identity(token)
    with pytest.raises(HTTPException):store.login(body)

@pytest.fixture
def auth_client(env):
    client=TestClient(create_app(env['engine'],'week6-mock-internal',env['s'],with_auth=True))
    yield client
    client.close()
def login(client):
    body=dict(login_name='u'+uuid4().hex[:20],password='local_only_fixture_password_123')
    registered=client.post('/auth/register',json=body);assert registered.status_code==201
    signed=client.post('/auth/login',json=body);assert signed.status_code==200
    return {'Authorization':'Bearer '+signed.json()['access_token']},registered.json()['inquirer_id']

def test_http_auth_and_admin_separation(env,auth_client):
    e=env;client=auth_client;h,user=login(client)
    assert client.get('/auth/me',headers=h).json()['inquirer_id']==user
    assert client.get('/ops/overview',headers=h).status_code==403
    assert client.get('/ops/overview',headers={'X-Internal-Key':'week6-mock-internal'}).status_code==401
    with e['engine'].begin() as c:c.execute(update(accounts).where(accounts.c.user_id==user).values(role='admin'))
    assert client.get('/ops/overview',headers=h).status_code==200
    h['Idempotency-Key']=str(uuid4())
    created=client.post('/api/inquiries',headers=h,json={**e['body'],'inquirer_id':user});assert created.status_code==201
    other,_=login(client)
    assert client.get('/api/inquiries/'+created.json()['inquiry_id'],headers=other).status_code==404
    # Close the extra auth user's fixture work explicitly; env cleanup owns only its original users.
    with e['engine'].begin() as c:c.execute(update(inquiries).where(inquiries.c.id==created.json()['inquiry_id']).values(status='failed',failure_reason='auth_fixture_closed'))
    assert client.post('/auth/logout',headers=h).status_code==200
    assert client.get('/auth/me',headers=h).status_code==401

def test_validation_error_does_not_echo_password_or_unknown_fields(auth_client):
    marker='do_not_echo_fixture_marker'
    reply=auth_client.post('/auth/register',json=dict(login_name='BadName',password=marker,role='admin'))
    assert reply.status_code==422 and marker not in reply.text
    assert all('input' not in item for item in reply.json()['detail'])

def test_readiness_db_and_redis(env,queue):
    assert Operations(env['s'],queue.client).readiness()['ready'] is True
    class Offline:
        def ping(self):raise ConnectionError('synthetic failure with private text')
    data=Operations(env['s'],Offline()).readiness()
    assert data['ready'] is False and 'private' not in str(data)

def test_vapi_provider_mapping_idempotent_and_conflicting(env):
    e=env;create(e);cid=tick(e)['reserved'][0];bridge=VapiBridge(e['s']);external='vapi-'+str(uuid4())
    assert not bridge.bind(cid,external)['duplicate'] and bridge.bind(cid,external)['duplicate']
    with pytest.raises(HTTPException) as error:bridge.bind(cid,'different-id')
    assert error.value.status_code==409

def vapi_message(external,kind='status-update',**extra):
    return dict(message=dict(type=kind,call={'id':external},timestamp='2026-10-05T14:00:00+09:00',**extra))

def test_provider_ended_waits_for_result_and_duplicate_inbox(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];bridge=VapiBridge(e['s']);external='vapi-'+str(uuid4());bridge.bind(cid,external)
    raw=vapi_message(external,status='ended');stored=bridge.receive(raw)
    assert bridge.receive(raw)['duplicate']
    assert bridge.process(stored['inbox_id'])['status']=='processed'
    assert get(e,iid)['status']=='calling'
    result=make_result(payload(e,cid))
    report=vapi_message(external,'end-of-call-report',artifact={'structuredOutputs':{'team8-result-v1':{'result':result}}})
    stored=bridge.receive(report);assert bridge.process(stored['inbox_id'])['status']=='processed'
    assert get(e,iid)['status']=='completed'
    assert bridge.process(stored['inbox_id'])['duplicate']

@pytest.mark.parametrize('bad',['missing','no_disclosure_field','wrong_question','outcome_conflict'])
def test_provider_missing_or_inconsistent_output_quarantined(env,bad):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];b=VapiBridge(e['s']);external='vapi-'+str(uuid4());b.bind(cid,external)
    output=make_result(payload(e,cid))
    if bad=='no_disclosure_field':output.pop('disclosure_played')
    if bad=='wrong_question':output['answers'][0]['question_id']='other-inquiry-question'
    if bad=='outcome_conflict':event(e,cid,'no_answer')
    artifact={} if bad=='missing' else {'structuredOutputs':{'team8-result-v1':{'result':output}}}
    raw=vapi_message(external,'end-of-call-report',artifact=artifact)
    raw['message']['artifact']['transcript']='raw transcript must not be retained by inbox'
    item=b.receive(raw);processed=b.process(item['inbox_id'])
    assert processed['status']=='quarantined'
    with e['engine'].connect() as c:
        normalized=c.execute(select(provider_inbox.c.normalized).where(provider_inbox.c.id==item['inbox_id'])).scalar_one()
    assert 'raw transcript must not' not in str(normalized)
    assert get(e,iid)['status']!='completed'

def test_provider_unknown_call_never_creates_new_mapping(env):
    bridge=VapiBridge(env['s'])
    with pytest.raises(HTTPException) as error:bridge.receive(vapi_message('unmapped',status='ringing'))
    assert error.value.status_code==404

def test_provider_inbox_survives_processor_restart(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];b=VapiBridge(e['s']);external='vapi-'+str(uuid4());b.bind(cid,external)
    report=vapi_message(external,'end-of-call-report',artifact={'structuredOutputs':{'team8-result-v1':{'result':make_result(payload(e,cid))}}})
    item=b.receive(report);e['engine'].dispose()
    assert VapiBridge(e['s']).process(item['inbox_id'])['status']=='processed'
    assert get(e,iid)['status']=='completed'

def test_http_worker_lost_202_looks_up_persisted_acceptance():
    import httpx
    from http_worker6 import WorkerHttpAdapter
    seen=[];cid=str(uuid4())
    def handler(request):
        seen.append(request.method)
        if request.method=='POST':raise httpx.ReadTimeout('synthetic response loss',request=request)
        return httpx.Response(200,json=dict(call_id=cid,accepted=True))
    worker=WorkerHttpAdapter('https://mock-worker.invalid','synthetic-internal-only',httpx.MockTransport(handler))
    try:assert worker.accept(dict(call_id=cid,is_mock=True))['accepted']
    finally:worker.close()
    assert seen==['POST','GET']

def test_http_worker_unknown_stays_unknown_and_real_disabled():
    import httpx
    from http_worker6 import WorkerHttpAdapter
    worker=WorkerHttpAdapter('https://mock-worker.invalid','synthetic-internal-only',
        httpx.MockTransport(lambda r:httpx.Response(404)))
    try:
        with pytest.raises(ConnectionError):worker.accept(dict(call_id=str(uuid4()),is_mock=True))
        with pytest.raises(ValueError):worker.accept(dict(call_id=str(uuid4()),is_mock=False))
    finally:worker.close()
    with pytest.raises(ValueError):WorkerHttpAdapter('http://external.invalid','synthetic-internal-only')
    # A 200 lookup with JSON null/list is still uncertain, not an accepted receipt.
    for malformed in [None,[],{'accepted':True,'call_id':'different'}]:
        worker=WorkerHttpAdapter('https://mock-worker.invalid','synthetic-internal-only',
            httpx.MockTransport(lambda request,reply=malformed:httpx.Response(200,json=reply)))
        try:
            with pytest.raises(ConnectionError):worker.accept(dict(call_id=str(uuid4()),is_mock=True))
        finally:worker.close()

def test_auth_admin_review_and_authenticated_correction_author(env,auth_client):
    e=env;client=auth_client;h,user=login(client)
    with e['engine'].begin() as c:c.execute(update(accounts).where(accounts.c.user_id==user).values(role='admin'))
    h['Idempotency-Key']=str(uuid4())
    response=client.post('/api/inquiries',headers=h,json={**e['body'],'inquirer_id':user})
    iid=response.json()['inquiry_id'];cid=e['s'].tick(e['w'])['reserved'][0]
    b=make_result(payload(e,cid));e['s'].result(cid,ResultInput.model_validate(b))
    b['summary_text']='인증된 검토자가 교정한 가상 요약'
    reply=client.post('/ops/calls/'+cid+'/corrections',headers=h,json=dict(
        base_revision=0,reviewer='spoofed-reviewer',reason='검토한 요약',payload=b))
    assert reply.status_code==200
    from schema import corrections
    with e['engine'].connect() as c:
        reviewer=c.execute(select(corrections.c.reviewer).where(corrections.c.call_id==cid)).scalar_one()
    assert reviewer==user and reviewer!='spoofed-reviewer'
    assert client.get('/api/inquiries/'+iid,headers=h).json()['result']['review_revision']==1
