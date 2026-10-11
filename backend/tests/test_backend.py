from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update, delete, func
from api import create_app
from service import Service, Policy, digest
from schema import users, academies, inquiries, questions, calls, events, results, answers, worker_receipts
from worker import MockWorker, make_result
from local_runtime import test_engine as local_engine

KEY='mock-test-internal'
INTERNAL={'X-Internal-Key':KEY}
@pytest.fixture
def env():
    engine=local_engine()
    clock=[datetime(2026,10,5,5,0,tzinfo=timezone.utc)] # Monday 14:00 KST
    service=Service(engine,Policy(),lambda:clock[0]); service.initialize()
    owners=[str(uuid4()),str(uuid4())]; tokens=[str(uuid4()),str(uuid4())]; acid=str(uuid4())
    with engine.begin() as c:
        for owner,token in zip(owners,tokens): c.execute(users.insert().values(id=owner,token_hash=digest(token)))
        c.execute(academies.insert().values(id=acid,name='가상 학원',region='대구 북구 침산동',phone=None,
            is_mock=True,hours=[dict(weekday=i,start_minute=540,end_minute=1080) for i in range(5)]))
    worker=MockWorker(engine,KEY)
    client=TestClient(create_app(engine,KEY,service,worker))
    body=dict(inquirer_id=owners[0],academy_id=acid,
        student=dict(grade='M2',subject='MATH',level='MID',region='대구 북구 침산동'),
        question_codes=['shuttle','vacancy','class_time'])
    headers={'Authorization':'Bearer '+tokens[0],'Idempotency-Key':str(uuid4())}
    yield dict(engine=engine,clock=clock,s=service,w=worker,c=client,body=body,h=headers,owners=owners,tokens=tokens,acid=acid)
    client.close(); worker.close()
    # Retain audit rows. Release only this fixture's queue slots without DELETE privileges.
    with engine.begin() as c:
        ids=list(c.execute(select(inquiries.c.id).where(inquiries.c.inquirer_id.in_(owners))).scalars())
        c.execute(update(calls).where(calls.c.inquiry_id.in_(ids),
            calls.c.status.not_in(['finished','timeout'])).values(status='timeout'))
        c.execute(update(inquiries).where(inquiries.c.id.in_(ids),
            inquiries.c.status.not_in(['completed','failed'])).values(status='failed',failure_reason='test_fixture_closed'))
    engine.dispose()

def create(e,**change):
    r=e['c'].post('/api/inquiries',headers=e['h'],json={**e['body'],**change})
    assert r.status_code==201,r.text
    return r.json()['inquiry_id']
def tick(e):
    r=e['c'].post('/internal/mock/tick',headers=INTERNAL); assert r.status_code==200,r.text
    return r.json()
def get(e,iid): return e['c'].get('/api/inquiries/'+iid,headers=e['h']).json()
def payload(e,cid):
    with e['engine'].connect() as c:
        return c.execute(select(calls.c.dispatch_payload).where(calls.c.id==cid)).scalar_one()
def send(e,cid,body): return e['c'].post('/internal/calls/'+cid+'/result',headers=INTERNAL,json=body)
def event(e,cid,kind,when=None,eid=None):
    return e['c'].post('/internal/calls/'+cid+'/events',headers=INTERNAL,
        json=dict(event_id=eid or str(uuid4()),type=kind,occurred_at=(when or e['clock'][0]).isoformat()))
def count(e,table):
    with e['engine'].connect() as c: return c.execute(select(func.count()).select_from(table)).scalar_one()

def test_mult_question_storage_and_owner(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]; p=payload(e,cid)
    body=make_result(p,unanswered=['vacancy'],negative=['shuttle'])
    assert send(e,cid,body).status_code==200
    data=get(e,iid); assert data['status']=='completed'
    a=data['result']['answers']; assert a[0]['answered'] is True and a[0]['yes_no'] is False
    assert a[1]['answered'] is False and a[1]['yes_no'] is None
    assert a[2]['yes_no'] is None and a[2]['detail']=='화목 19:00'
    assert 'transcript' not in data['result'] and 'recording_url' not in data['result']
    assert 'inquirer_id' not in p and 'token' not in p and p['to'] is None
    other={'Authorization':'Bearer '+e['tokens'][1]}
    assert e['c'].get('/api/inquiries/'+iid,headers=other).status_code==404
    assert e['c'].get('/api/inquiries',headers=other).json()==[]
    assert e['c'].get('/api/inquiries?inquirer_id='+e['owners'][0],headers=other).status_code==403
    assert e['c'].get('/api/inquiries/'+iid).status_code==401
    assert e['c'].post('/api/inquiries',headers=e['h'],json={**e['body'],'inquirer_id':e['owners'][1]}).status_code==403

def test_concurrent_inquiry_idempotency(env):
    e=env
    with ThreadPoolExecutor(4) as pool: ids=list(pool.map(lambda _:create(e),range(4)))
    assert len(set(ids))==1
    assert e['c'].post('/api/inquiries',headers=e['h'],json={**e['body'],'question_codes':['pickup']}).status_code==409
    assert len(get(e,ids[0])['questions'])==3

@pytest.mark.parametrize('change',[
    {'question_codes':[]},{'question_codes':['shuttle','shuttle']},{'question_codes':['price']},
    {'student':dict(grade='M4',subject='MATH',level='MID',region='대구 북구 침산동')},
    {'student':dict(grade='M2',subject='math',level='MID',region='대구 북구 침산동')},
    {'student':dict(grade='M2',subject='MATH',level='MID',region='임의 자유 입력')},
    {'extra':'unexpected'}])
def test_invalid_inquiry(env,change):
    e=env; before=count(e,inquiries)
    assert e['c'].post('/api/inquiries',headers=e['h'],json={**e['body'],**change}).status_code==422
    assert count(e,inquiries)==before

def test_business_hours(env):
    e=env; iid=create(e)
    e['clock'][0]=datetime(2026,10,5,9,0,tzinfo=timezone.utc) # 18:00 excluded
    assert tick(e)['reserved']==[]
    e['clock'][0]=datetime(2026,10,10,5,0,tzinfo=timezone.utc) # Saturday
    assert tick(e)['reserved']==[]
    e['clock'][0]=datetime(2026,10,12,0,0,tzinfo=timezone.utc) # Next Monday 09:00 included
    assert len(tick(e)['reserved'])==1 and get(e,iid)['status']=='calling'

def test_concurrency_and_priority(env):
    e=env; ids=[]
    for _ in range(4): e['h']['Idempotency-Key']=str(uuid4()); ids.append(create(e))
    with e['engine'].begin() as c:
        c.execute(update(inquiries).where(inquiries.c.id==ids[-1]).values(priority=10))
    with ThreadPoolExecutor(4) as pool: ticks=list(pool.map(lambda _:tick(e),range(4)))
    reserved=[cid for t in ticks for cid in t['reserved']]
    assert len(reserved)==2
    assert get(e,ids[-1])['status']=='calling'
    assert sum(get(e,i)['status']=='calling' for i in ids)==2

def test_result_atomic_validation_and_conflicts(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]; body=make_result(payload(e,cid))
    before=count(e,answers)
    bad={**body,'answers':body['answers'][:-1]}
    assert send(e,cid,bad).status_code==422 and count(e,answers)==before
    assert get(e,iid)['status']=='calling'
    bad={**body,'answers':[{**body['answers'][0],'question_id':'foreign'},*body['answers'][1:]]}
    assert send(e,cid,bad).status_code==422
    with ThreadPoolExecutor(4) as pool: responses=list(pool.map(lambda _:send(e,cid,body),range(4)))
    assert all(r.status_code==200 for r in responses)
    assert sum(not r.json()['duplicate'] for r in responses)==1
    assert count(e,answers)==before+3
    assert send(e,cid,{**body,'summary_text':'changed'}).status_code==409

def test_event_order_dedup_and_result_wait(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    eid=str(uuid4())
    assert event(e,cid,'answered',eid=eid).json()['applied'] is True
    assert event(e,cid,'answered',eid=eid).json()['duplicate'] is True
    assert event(e,cid,'ringing',e['clock'][0]+timedelta(seconds=1)).json()['applied'] is False
    assert event(e,cid,'completed',e['clock'][0]+timedelta(seconds=2)).json()['applied'] is True
    assert get(e,iid)['status']=='calling' # Completed event alone is not a saved result.
    assert send(e,cid,make_result(payload(e,cid))).status_code==200
    assert event(e,cid,'initiated',e['clock'][0]+timedelta(seconds=3)).json()['applied'] is False
    assert get(e,iid)['status']=='completed'
    assert event(e,cid,'busy',eid=eid).status_code==409

@pytest.mark.parametrize('outcome,retry',[('no_answer',True),('busy',True),('machine',True),('invalid_number',False),('rejected',False)])
def test_failure_policy(env,outcome,retry):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    assert send(e,cid,make_result(payload(e,cid),outcome)).status_code==200
    assert get(e,iid)['status']==('retry_wait' if retry else 'failed')
    assert tick(e)['reserved']==[]
    if retry:
        e['clock'][0]+=timedelta(seconds=300)
        cid2=tick(e)['reserved'][0]; assert cid2!=cid
        assert payload(e,cid2)['attempt_no']==2
        assert send(e,cid2,make_result(payload(e,cid2))).status_code==200
        assert get(e,iid)['status']=='completed'

def test_retry_limit_and_late_result(env):
    e=env; iid=create(e); first=None
    for i in range(3):
        cid=tick(e)['reserved'][0]
        if first is None: first=cid
        assert event(e,cid,'busy').status_code==200
        if i==1:
            late=make_result(payload(e,first),'busy')
            assert send(e,first,late).json()['applied'] is False
            assert get(e,iid)['status']=='retry_wait'
        e['clock'][0]+=timedelta(seconds=300)
    assert tick(e)['reserved']==[]
    assert get(e,iid)['status']=='failed' and get(e,iid)['fallback_required'] is True
    assert len(get(e,iid)['attempts'])==3

def test_delivery_timeout_same_call_no_duplicate(env):
    e=env; iid=create(e)
    class LostResponse:
        def accept(self,p): e['w'].accept(p); raise TimeoutError('Lost 202 response')
    tick1=e['s'].tick(LostResponse()); cid=tick1['reserved'][0]
    assert tick1['delivered'][0]['accepted'] is False
    restarted=MockWorker(e['engine'],KEY)
    tick2=e['s'].tick(restarted); restarted.close()
    assert tick2['reserved']==[] and tick2['delivered'][0]['call_id']==cid
    assert tick2['delivered'][0]['accepted'] is True
    with e['engine'].connect() as c:
        assert c.execute(select(func.count()).select_from(worker_receipts).where(worker_receipts.c.call_id==cid)).scalar_one()==1
    assert len(get(e,iid)['attempts'])==1

def test_missing_result_times_out_without_redial(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    assert event(e,cid,'answered').status_code==200
    e['clock'][0]+=timedelta(seconds=601)
    assert tick(e)['expired']==[cid]
    assert get(e,iid)['status']=='failed'
    assert send(e,cid,make_result(payload(e,cid))).json()['applied'] is False
    assert tick(e)['reserved']==[] and get(e,iid)['status']=='failed'

def test_callback(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    body=make_result(payload(e,cid)); body.update(callback_requested=True,
        callback_at=(e['clock'][0]+timedelta(minutes=30)).isoformat())
    assert send(e,cid,body).status_code==200
    assert get(e,iid)['status']=='retry_wait' and tick(e)['reserved']==[]
    e['clock'][0]+=timedelta(minutes=30)
    assert len(tick(e)['reserved'])==1

def test_disclosure_failure_preserved(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    body=make_result(payload(e,cid)); body['disclosure_played']=False
    assert send(e,cid,body).status_code==200
    assert get(e,iid)['failure_reason']=='disclosure_missing'
    assert get(e,iid)['result']['disclosure_played'] is False

def test_restart_preserves_results(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    assert send(e,cid,make_result(payload(e,cid))).status_code==200
    e['engine'].dispose()
    fresh=local_engine(); svc=Service(fresh)
    assert svc.get(iid,e['tokens'][0])['status']=='completed'
    assert len(svc.get(iid,e['tokens'][0])['result']['answers'])==3
    fresh.dispose()

def test_internal_auth_and_cors(env):
    e=env
    assert e['c'].post('/internal/mock/tick').status_code==401
    assert e['c'].post('/internal/calls/missing/events',headers=INTERNAL,
        json=dict(event_id='x',type='answered',occurred_at='2026-10-05T14:00:00')).status_code==422
    good=e['c'].options('/api/inquiries',headers={'Origin':'http://localhost:5173',
        'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Authorization,Idempotency-Key'})
    assert good.status_code==200
    bad=e['c'].options('/api/inquiries',headers={'Origin':'https://unapproved.example',
        'Access-Control-Request-Method':'POST'})
    assert bad.status_code==400

@pytest.mark.parametrize('change',[
    {'unresolved':['not-in-request']},
    {'answers':[]},
    {'consult_accepted':False},
    {'callback_at':'2026-10-05T15:00:00+09:00'},
    {'latency':{'mean_ms':-1,'p95_ms':100,'turns':5}},
    {'disclosure_played':'true'},
])
def test_inconsistent_results_are_rejected(env,change):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]; body=make_result(payload(e,cid))
    assert send(e,cid,{**body,**change}).status_code==422
    assert get(e,iid)['status']=='calling'

def test_failed_event_does_not_extend_retry_time(env):
    e=env; iid=create(e); cid=tick(e)['reserved'][0]
    assert event(e,cid,'no_answer').status_code==200
    e['clock'][0]+=timedelta(seconds=299)
    assert send(e,cid,make_result(payload(e,cid),'no_answer')).status_code==200
    e['clock'][0]+=timedelta(seconds=1)
    assert len(tick(e)['reserved'])==1

def test_worker_immutable_acceptance(env):
    e=env; create(e); cid=tick(e)['reserved'][0]; p=payload(e,cid)
    assert e['w'].client.post('/internal/calls',json={**p,'academy_name':'changed'},headers=INTERNAL).status_code==409
    assert e['w'].client.post('/internal/calls',json={**p,'call_id':str(uuid4()),'is_mock':False},headers=INTERNAL).status_code==422
