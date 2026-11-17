"""Deleting terminal work must not break a delayed delivery return or Redis consumer."""
from datetime import timedelta
from uuid import uuid4
import importlib.util
from pathlib import Path
from sqlalchemy import select, update
import pytest

from admin_management import AdminManagement, DeleteConfirmation, DELETE_TABLES
from contracts import ResultInput
from redis_queue import RedisQueue
import schema as s
from worker import make_result
from test_admin_management import managed, inquiry, preview, remove


def test_delayed_worker_return_after_terminal_cleanup_does_not_recreate_work(managed):
    e=managed;iid=inquiry(e)
    # Seed only this synthetic attempt; never reserve another test's queued work.
    cid=str(uuid4())
    with e['engine'].begin() as c:
        qs=c.execute(select(s.questions).where(s.questions.c.inquiry_id==iid)).mappings().all()
        payload=dict(call_id=cid,inquiry_id=iid,is_mock=True,questions=[dict(question_id=q['id'],question_code=q['code']) for q in qs])
        c.execute(update(s.inquiries).where(s.inquiries.c.id==iid).values(status='calling'))
        c.execute(s.calls.insert().values(id=cid,inquiry_id=iid,attempt_no=1,status='reserved',created_at=e['service'].now(),
            deadline=e['service'].now()+timedelta(seconds=600),dispatch_payload=payload,delivery_count=0))
    class DelayedWorker:
        def accept(self, payload):
            assert payload['call_id']==cid
            e['service'].result(cid,ResultInput.model_validate(make_result(payload)))
            with e['engine'].begin() as c:
                c.execute(update(s.delivery_leases).where(s.delivery_leases.c.call_id==cid).values(lease_until=e['service'].now()-timedelta(seconds=1)))
            assert remove(e,'inquiries',iid).status_code==200
            return dict(call_id=cid,accepted=True)
    report=e['service'].deliver(DelayedWorker(),[cid])
    assert report==[dict(call_id=cid,accepted=True,deleted=True)]
    with e['engine'].connect() as c:assert c.execute(select(s.calls.c.id).where(s.calls.c.id==cid)).first() is None


def test_redis_message_acknowledged_when_terminal_row_deleted_during_processing(managed, monkeypatch):
    e=managed;iid=inquiry(e)
    from test_admin_management import completed
    cid,_=completed(e,iid)
    from service import uid
    oid=uid()
    with e['engine'].begin() as c:c.execute(s.outbox.insert().values(id=oid,call_id=cid,created_at=e['service'].now()))
    class RedisStub:
        acknowledged=[]
        def xack(self,stream,group,message):self.acknowledged.append(message)
    redis=RedisStub()
    def deleted(*args):assert remove(e,'inquiries',iid).status_code==200
    monkeypatch.setattr(e['service'],'deliver',deleted)
    q=RedisQueue(e['service'],redis)
    report=q.process([('1-0',dict(call_id=cid,outbox_id=oid))],None)
    assert redis.acknowledged==['1-0'] and report[0]['acknowledged'] is True and report[0]['status'] is None


def test_permission_preparation_is_limited_and_rejects_wrong_database_or_identity():
    path=Path(__file__).resolve().parents[2]/'infra/admin-management-permissions.py'
    spec=importlib.util.spec_from_file_location('management_permissions',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert set(module.TABLES)==set(DELETE_TABLES)
    statements=module.grant_statements('team8_app','%','team8_dev')
    assert all('GRANT DELETE ON `team8_dev`.`' in sql and '.*' not in sql for sql in statements)
    assert all(not any(name in sql for name in ['w6_accounts','w6_sessions','w5_inquirers']) for sql in statements)
    for args in [('root','%','team8_dev'),('team8_app','%','other_db'),("app' OR 1=1",'%','team8_dev')]:
        with pytest.raises(ValueError):module.grant_statements(*args)


def test_trusted_admin_bootstrap_uses_current_registration_contract(managed, monkeypatch, capsys):
    import manage_admin6
    e=managed
    login_name='bootstrap_'+uuid4().hex[:12]
    monkeypatch.setattr('sys.argv',['manage_admin6.py',login_name,'--terms-agreed'])
    monkeypatch.setattr(manage_admin6,'require_mock_mode',lambda:None)
    monkeypatch.setattr(manage_admin6,'local_engine',lambda:e['engine'])
    monkeypatch.setattr(manage_admin6.getpass,'getpass',lambda label:'Synthetic_Bootstrap123!')
    manage_admin6.main()
    with e['engine'].connect() as c:
        assert c.execute(select(s.accounts.c.role).where(s.accounts.c.login_name==login_name)).scalar_one()=='admin'
    assert 'Synthetic_Bootstrap123!' not in capsys.readouterr().out
