from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import copy
import pytest
import redis
from settings import redis_url
from redis.exceptions import ConnectionError as RedisConnectionError
from fastapi import HTTPException
from sqlalchemy import select,update,func
from test_backend import env,create,get,payload,send,tick
from contracts import ResultInput,CorrectionInput
from contracts import AcademyPolicyInput
from service import Service
from redis_queue import RedisQueue
from schema import calls,outbox,delivery_leases,worker_receipts,results,corrections,academy_policies,academies
from worker import make_result

@pytest.fixture
def queue(env):
    client=redis.Redis.from_url(redis_url(test=True),decode_responses=True,
        socket_connect_timeout=2,socket_timeout=3)
    client.ping() # An actual Redis server is mandatory; absence must fail rather than skip.
    stream='team8:w5:test:'+str(uuid4())
    q=RedisQueue(env['s'],client,stream=stream)
    yield q
    client.delete(stream) # Only this fixture's unique Redis stream, never FLUSHDB.
    client.close()

def row(e,table,cid):
    with e['engine'].connect() as c:
        column=table.c.id if table is calls else table.c.call_id
        return c.execute(select(table).where(column==cid)).mappings().one()

def test_callback_during_worker_accept_no_lock_or_regression(env):
    e=env;iid=create(e);cid=e['s'].reserve()[0]
    class CallbackWorker:
        def accept(self,p):
            # Different connection/thread must be able to commit before acceptance returns.
            with ThreadPoolExecutor(max_workers=1) as pool:
                reply=pool.submit(e['s'].result,cid,ResultInput.model_validate(make_result(p))).result(timeout=4)
                assert reply['applied'] is True
            return dict(call_id=p['call_id'],accepted=True)
    assert e['s'].deliver(CallbackWorker(),[cid])[0]['accepted']
    assert row(e,calls,cid)['status']=='finished' and get(e,iid)['status']=='completed'

def test_delivery_claim_prevents_parallel_send(env):
    import threading
    e=env;create(e);cid=e['s'].reserve()[0];entered=threading.Event();release=threading.Event()
    class SlowWorker:
        def accept(self,p):
            entered.set();assert release.wait(4);return e['w'].accept(p)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(e['s'].deliver,SlowWorker(),[cid]);assert entered.wait(3)
        assert pool.submit(e['s'].deliver,e['w'],[cid]).result(timeout=3)==[]
        release.set();assert first.result(timeout=3)[0]['accepted']
    assert row(e,calls,cid)['delivery_count']==1

def test_outbox_atomic_and_redis_outage(env):
    e=env;iid=create(e);cid=e['s'].reserve()[0]
    class Offline:
        def xgroup_create(self,*a,**k): raise RedisConnectionError('offline')
    with pytest.raises(RedisConnectionError): RedisQueue(e['s'],Offline()).publish()
    assert row(e,outbox,cid)['last_published_at'] is None
    assert row(e,calls,cid)['status']=='reserved'
    assert get(e,iid)['status']=='calling'
    with e['engine'].connect() as c:
        assert c.execute(select(func.count()).select_from(worker_receipts).where(worker_receipts.c.call_id==cid)).scalar_one()==0

def test_real_redis_roundtrip_duplicates_and_restart(env,queue):
    e=env;iid=create(e);cid=e['s'].reserve()[0];q=queue
    published=q.publish();assert len(published)==1
    oid=row(e,outbox,cid)['id']
    q.client.xadd(q.stream,dict(call_id=cid,outbox_id=oid))
    replies=q.consume(e['w']);assert len(replies)==2 and all(x['acknowledged'] for x in replies)
    assert row(e,calls,cid)['delivery_count']==1
    e['engine'].dispose()
    assert send(e,cid,make_result(payload(e,cid))).status_code==200
    assert get(e,iid)['status']=='completed'
    assert q.client.xpending(q.stream,q.group)['pending']==0

def test_xautoclaim_after_consumer_dies(env,queue):
    e=env;create(e);cid=e['s'].reserve()[0];q=queue;q.publish()
    q.client.xreadgroup(q.group,'dead-consumer',{q.stream:'>'},count=10)
    assert q.client.xpending(q.stream,q.group)['pending']==1
    recovered=RedisQueue(e['s'],q.client,q.stream,consumer='replacement').recover(e['w'],min_idle_ms=0)
    assert recovered[0]['acknowledged'] and row(e,calls,cid)['status']=='accepted'

def test_worker_crash_after_acceptance_reclaims_same_call(env,queue):
    e=env;create(e);cid=e['s'].reserve()[0];q=queue;q.publish()
    class Crash:
        def accept(self,p):
            e['w'].accept(p)
            raise RuntimeError('simulate process death after receipt commit')
    with pytest.raises(RuntimeError): q.consume(Crash())
    assert row(e,calls,cid)['status']=='reserved'
    assert e['s'].deliver(e['w'],[cid])==[] # Lease still belongs to the dead process.
    e['clock'][0]+=timedelta(seconds=31)
    assert q.recover(e['w'],min_idle_ms=0)[0]['acknowledged']
    assert row(e,calls,cid)['delivery_count']==2
    with e['engine'].connect() as c:
        assert c.execute(select(func.count()).select_from(worker_receipts).where(worker_receipts.c.call_id==cid)).scalar_one()==1

def test_unknown_delivery_stays_pending_no_new_call(env,queue):
    e=env;iid=create(e);cid=e['s'].reserve()[0];q=queue;q.publish()
    class LostResponse:
        def accept(self,p):
            e['w'].accept(p);raise TimeoutError()
    assert not q.consume(LostResponse())[0]['acknowledged']
    assert e['s'].reserve()==[]
    e['clock'][0]+=timedelta(seconds=31)
    assert q.recover(e['w'],min_idle_ms=0)[0]['acknowledged']
    assert len(get(e,iid)['attempts'])==1

def test_redis_data_loss_republishes_mysql_outbox(env,queue):
    e=env;create(e);cid=e['s'].reserve()[0];q=queue;q.publish()
    q.client.delete(q.stream) # Loss restricted to the fixture stream.
    e['clock'][0]+=timedelta(seconds=61)
    assert q.publish()[0]['call_id']==cid
    assert q.consume(e['w'])[0]['acknowledged']

def test_publish_ack_lost_retries_without_new_call(env,queue):
    e=env;create(e);cid=e['s'].reserve()[0];q=queue
    class LostPublishReply:
        def xgroup_create(self,*a,**k): return q.client.xgroup_create(*a,**k)
        def xadd(self,*a,**k):
            q.client.xadd(*a,**k);raise RedisConnectionError('lost reply')
    with pytest.raises(RedisConnectionError): RedisQueue(e['s'],LostPublishReply(),q.stream).publish()
    assert row(e,outbox,cid)['last_published_at'] is None
    q.publish();replies=q.consume(e['w'])
    assert len(replies)==2 and row(e,calls,cid)['delivery_count']==1

def test_invalid_stream_message_cannot_dispatch(env,queue):
    e=env;create(e);cid=e['s'].reserve()[0];q=queue;q.ensure_group()
    q.client.xadd(q.stream,dict(call_id=cid,outbox_id='wrong-outbox'))
    assert q.consume(e['w'])[0]['disposition']=='invalid_ignored'
    assert row(e,calls,cid)['delivery_count']==0

def test_correction_preserves_original_and_detects_conflict(env):
    e=env;iid=create(e);cid=tick(e)['reserved'][0];original=make_result(payload(e,cid))
    assert send(e,cid,original).status_code==200
    changed=copy.deepcopy(original);changed['summary_text']='교정한 가상 상담 요약'
    body=CorrectionInput(base_revision=0,reviewer='개발 검토자',reason='가상 결과 요약 오기 교정',payload=ResultInput.model_validate(changed))
    assert e['s'].correct_result(cid,body)['revision']==1
    assert get(e,iid)['result']['summary_text']==changed['summary_text']
    assert get(e,iid)['result']['review_revision']==1
    assert row(e,results,cid)['payload']['summary_text']==original['summary_text']
    with pytest.raises(HTTPException) as error: e['s'].correct_result(cid,body)
    assert error.value.status_code==409
    assert send(e,cid,original).json()['duplicate'] is True
    changed['duration_sec']+=1
    body=CorrectionInput(base_revision=1,reviewer='개발 검토자',reason='금지 필드 시험',payload=ResultInput.model_validate(changed))
    with pytest.raises(HTTPException) as error: e['s'].correct_result(cid,body)
    assert error.value.status_code==422

def test_academy_closure_cooldown_and_limit(env):
    e=env;create(e)
    with e['engine'].begin() as c:
        c.execute(academy_policies.insert().values(academy_id=e['acid'],enabled=True,
            max_concurrent=1,cooldown_seconds=300,closed_dates=['2026-10-05']))
    assert e['s'].reserve()==[]
    with e['engine'].begin() as c:
        c.execute(update(academy_policies).where(academy_policies.c.academy_id==e['acid']).values(closed_dates=[]))
    cid=tick(e)['reserved'][0]
    e['h']['Idempotency-Key']=str(uuid4());create(e)
    assert e['s'].reserve()==[]
    assert send(e,cid,make_result(payload(e,cid))).status_code==200
    assert e['s'].reserve()==[] # Finished, but cooldown still applies.
    e['clock'][0]+=timedelta(seconds=300)
    assert len(e['s'].reserve())==1

def test_overnight_hours_boundary(env):
    e=env;ac=dict(hours=[dict(weekday=0,start_minute=1320,end_minute=120)])
    e['clock'][0]=e['clock'][0].replace(hour=13) # Monday 22:00 KST
    assert e['s'].opened(ac)
    e['clock'][0]+=timedelta(hours=3) # Tuesday 01:00 KST
    assert e['s'].opened(ac)
    e['clock'][0]+=timedelta(hours=1) # 02:00 exact closing
    assert not e['s'].opened(ac)

def test_event_cannot_extend_result_deadline(env):
    from test_backend import event
    e=env;iid=create(e);cid=tick(e)['reserved'][0]
    original=row(e,calls,cid)['deadline']
    e['clock'][0]+=timedelta(seconds=590)
    assert event(e,cid,'answered').status_code==200
    assert row(e,calls,cid)['deadline']==original
    e['clock'][0]+=timedelta(seconds=10)
    assert e['s'].expire()==[cid] and get(e,iid)['status']=='failed'

def test_policy_validation_and_disabled_academy(env):
    from pydantic import ValidationError
    e=env;create(e)
    body=dict(enabled=False,max_concurrent=1,cooldown_seconds=300,closed_dates=[],
        hours=[dict(weekday=0,start_minute=540,end_minute=1080)])
    e['s'].set_academy_policy(e['acid'],AcademyPolicyInput.model_validate(body))
    assert e['s'].reserve()==[]
    for invalid in [dict(max_concurrent=0),dict(closed_dates=['2026-02-30']),
                    dict(hours=[dict(weekday=0,start_minute=540,end_minute=540)])]:
        with pytest.raises(ValidationError): AcademyPolicyInput.model_validate({**body,**invalid})
