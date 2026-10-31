"""Real-dispatch boundaries on MySQL; fake HTTP transport never places calls."""
import copy
from datetime import timedelta
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import update
from test_backend import env,create,get,payload,event,send
from schema import academies,accounts
from real_test import RealTestPolicy
from http_worker6 import WorkerHttpAdapter
from worker import make_result

@pytest.fixture
def real_env(env):
    e=env
    with e['engine'].begin() as c:
        c.execute(update(academies).where(academies.c.id==e['acid']).values(is_mock=False,phone='+821000000001'))
        c.execute(accounts.insert().values(user_id=e['owners'][0],login_name='t_'+uuid4().hex[:24],
            password_hash='unused-test-fixture',enabled=True,terms_agreed_at=e['s'].now()))
    e['s'].real_test=RealTestPolicy(True,e['acid'],'+821000000001',e['owners'][0])
    return e

@pytest.mark.parametrize('field,value',[('enabled',False),('academy_id','other'),
    ('allowed_to','+821000000002'),('inquirer_id','other')])
def test_real_gate_rejects_mismatched_config(real_env,field,value):
    e=real_env;values=vars(e['s'].real_test).copy();values[field]=value
    e['s'].real_test=RealTestPolicy(**values)
    assert e['c'].post('/api/inquiries',headers=e['h'],json=e['body']).status_code==409
    assert e['s'].reserve()==[]

def test_real_exact_dispatch_and_duplicate_result(real_env):
    e=real_env;iid=create(e);cid=e['s'].reserve()[0];seen=[]
    def handle(request):
        seen.append(request.read());return httpx.Response(202,json={'call_id':cid,'accepted':True})
    adapter=WorkerHttpAdapter('http://localhost:18780','fixture',httpx.MockTransport(handle),
        authorize_real=e['s'].authorize_real_dispatch)
    try:
        assert e['s'].deliver(adapter,[cid])[0]['accepted']
        assert len(seen)==1 and not e['s'].deliver(adapter,[cid])
        body=make_result(payload(e,cid),negative=['shuttle'])
        assert send(e,cid,body).json()['applied']
        assert send(e,cid,body).json()['duplicate']
        assert get(e,iid)['status']=='completed' and get(e,iid)['academy']['max_attempts']==1
    finally:adapter.close()

@pytest.mark.parametrize('change',['destination','body','academy','account','disabled'])
def test_real_rechecks_persisted_state_before_http(real_env,change):
    e=real_env;create(e);cid=e['s'].reserve()[0];p=copy.deepcopy(payload(e,cid));seen=[]
    if change=='destination':p['to']='+821000000002'
    if change=='body':p['policy']['max_seconds']=999
    if change=='academy':
        with e['engine'].begin() as c:c.execute(update(academies).where(academies.c.id==e['acid']).values(phone='+821000000002'))
    if change=='account':
        with e['engine'].begin() as c:c.execute(update(accounts).where(accounts.c.user_id==e['owners'][0]).values(enabled=False))
    if change=='disabled':e['s'].real_test=RealTestPolicy()
    adapter=WorkerHttpAdapter('http://localhost:18780','fixture',httpx.MockTransport(lambda r:seen.append(r)),
        authorize_real=e['s'].authorize_real_dispatch)
    try:
        from worker_errors import WorkerRejected
        with pytest.raises(WorkerRejected):adapter.accept(p)
        assert seen==[]
    finally:adapter.close()

@pytest.mark.parametrize('outcome',['no_answer','busy','machine','rejected'])
def test_real_failure_has_no_second_attempt(real_env,outcome):
    e=real_env;iid=create(e);cid=e['s'].reserve()[0]
    assert event(e,cid,outcome).status_code==200
    e['clock'][0]+=timedelta(seconds=301)
    assert get(e,iid)['status']=='failed' and e['s'].reserve()==[]
    assert len(get(e,iid)['attempts'])==1

@pytest.mark.parametrize('known',[False,True])
def test_real_callback_request_never_schedules_redial(real_env,known):
    e=real_env;iid=create(e);cid=e['s'].reserve()[0];body=make_result(payload(e,cid))
    body['callback_requested']=True
    if known:body['callback_at']=(e['clock'][0]+timedelta(seconds=300)).isoformat()
    assert send(e,cid,body).json()['applied']
    assert get(e,iid)['status']=='completed'
    e['clock'][0]+=timedelta(seconds=301)
    assert e['s'].reserve()==[]

def test_disable_cancels_unreserved_real_work(real_env):
    e=real_env;iid=create(e);e['s'].real_test=RealTestPolicy()
    assert e['s'].reserve()==[]
    assert get(e,iid)['failure_reason']=='real_test_disabled'
