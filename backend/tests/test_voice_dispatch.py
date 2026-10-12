"""Regression coverage for definitive refusal versus uncertain delivery."""
import copy
from datetime import timedelta
import pytest,httpx
from sqlalchemy import select,func
from test_backend import env,create,get,payload,send,event
from http_worker6 import WorkerHttpAdapter
from worker_errors import WorkerRejected,WorkerProtocolError
from schema import calls,results,fallback_tasks
from worker import make_result
from redis_queue import RedisQueue
from test_extensions import queue
from run_queue import parse_args,build_worker

@pytest.mark.parametrize('status',[400,401,403,404,409,422])
def test_definite_refusal_never_looks_up(status):
    seen=[]
    def handler(r):
        seen.append(r.method)
        return httpx.Response(status,json={'accepted':True,'call_id':'fixture'})
    w=WorkerHttpAdapter('http://localhost:18780','test',httpx.MockTransport(handler))
    try:
        with pytest.raises(WorkerRejected) as e:w.accept(dict(call_id='fixture',is_mock=True))
        assert e.value.status_code==status and seen==['POST']
    finally:w.close()

@pytest.mark.parametrize('status',[429,500,501,502,503,504,599])
def test_temporary_response_retries_without_lookup(status):
    seen=[]
    w=WorkerHttpAdapter('http://localhost:18780','test',httpx.MockTransport(
        lambda r:(seen.append(r.method) or httpx.Response(status))))
    try:
        with pytest.raises(ConnectionError):w.accept(dict(call_id='fixture',is_mock=True))
        assert seen==['POST']
    finally:w.close()

@pytest.mark.parametrize('status,body',[(200,{}),(302,{}),(202,None),(202,[]),(202,{'call_id':'wrong','accepted':True})])
def test_protocol_error_never_looks_up(status,body):
    seen=[]
    w=WorkerHttpAdapter('http://localhost:18780','test',httpx.MockTransport(
        lambda r:(seen.append(r.method) or httpx.Response(status,json=body))))
    try:
        with pytest.raises(WorkerProtocolError):w.accept(dict(call_id='fixture',is_mock=True))
        assert seen==['POST']
    finally:w.close()

@pytest.mark.parametrize('status',[401,404,409,422])
def test_queue_refusal_is_acknowledged_and_reviewed(env,queue,status):
    e=env;iid=create(e);cid=e['s'].reserve()[0]
    class Refused:
        def accept(self,p):raise WorkerRejected(status)
    queue.publish();r=queue.consume(Refused())[0]
    assert r['acknowledged'] and r['status']=='finished'
    view=get(e,iid)
    assert view['status']=='failed' and view['review_required']
    assert view['failure_reason']==f'worker_http_{status}' and not view['fallback_required']
    assert e['s'].deliver(Refused(),[cid])==[] and queue.publish()==[]
    assert e['s'].reserve()==[]

def test_queue_protocol_failure_requires_review(env,queue):
    iid=create(env);env['s'].reserve();queue.publish()
    class Bad:
        def accept(self,p):raise WorkerProtocolError('synthetic')
    assert queue.consume(Bad())[0]['acknowledged']
    assert get(env,iid)['review_reason']=='worker_protocol_error'

def test_uncertain_delivery_keeps_identical_payload(env):
    iid=create(env);cid=env['s'].reserve()[0];seen=[]
    class Offline:
        def accept(self,p):seen.append(copy.deepcopy(p));raise ConnectionError('fixture')
    for _ in range(3):assert not env['s'].deliver(Offline(),[cid])[0]['accepted']
    assert seen[0]==seen[1]==seen[2] and env['s'].deliver(Offline(),[cid])==[]
    assert get(env,iid)['status']=='calling'

@pytest.mark.parametrize('scheduler_first',[False,True])
def test_late_result_stored_unapplied_with_or_without_scheduler(env,scheduler_first):
    e=env;iid=create(e);cid=e['s'].reserve()[0];body=make_result(payload(e,cid))
    e['clock'][0]+=timedelta(seconds=600)
    if scheduler_first:e['s'].expire()
    r=send(e,cid,body)
    assert r.status_code==200 and r.json()=={'duplicate':False,'applied':False}
    assert get(e,iid)['status']=='failed' and get(e,iid)['result'] is None
    assert send(e,cid,body).json()=={'duplicate':True,'applied':False}
    changed=copy.deepcopy(body);changed['notes']='different'
    assert send(e,cid,changed).status_code==409

def test_late_callback_kept_for_audit(env):
    iid=create(env);cid=env['s'].reserve()[0];body=make_result(payload(env,cid))
    body['callback_requested']=True;body['callback_at']=(env['clock'][0]+timedelta(seconds=300)).isoformat()
    env['clock'][0]+=timedelta(seconds=601)
    assert send(env,cid,body).json()['applied'] is False

def test_before_deadline_applies(env):
    iid=create(env);cid=env['s'].reserve()[0];body=make_result(payload(env,cid))
    env['clock'][0]+=timedelta(seconds=599)
    assert send(env,cid,body).json()['applied'] is True and get(env,iid)['status']=='completed'

def test_late_no_answer_report_does_not_cancel_scheduled_retry(env):
    iid=create(env);cid=env['s'].reserve()[0]
    assert event(env,cid,'no_answer').status_code==200
    body=make_result(payload(env,cid),outcome='no_answer')
    env['clock'][0]+=timedelta(seconds=601)
    r=send(env,cid,body)
    assert r.status_code==200 and r.json()['applied'] is False
    assert get(env,iid)['status']=='retry_wait'

def test_cli_external_cannot_simulate():
    with pytest.raises(SystemExit) as e:parse_args(['--worker-url','http://localhost:18780','--simulate-results'])
    assert e.value.code==2
    assert parse_args(['--worker-url','http://localhost:18780','--once']).worker_url
