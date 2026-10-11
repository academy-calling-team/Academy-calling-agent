"""MySQL outbox -> Redis Streams -> idempotent worker acceptance.

Redis carries only call/outbox identifiers. MySQL remains the source of truth.
Crash after XADD may duplicate messages; duplicate messages never allocate new calls.
"""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_
from redis.exceptions import ResponseError
from schema import calls, outbox

class RedisQueue:
    def __init__(self,service,client,stream='team8:w5:calls',group='dispatch',consumer=None):
        self.service,self.client,self.stream,self.group=service,client,stream,group
        self.consumer=consumer or str(uuid4())
    def ensure_group(self):
        try: self.client.xgroup_create(self.stream,self.group,id='0-0',mkstream=True)
        except ResponseError as error:
            if 'BUSYGROUP' not in str(error): raise
    def publish(self,recovery_seconds=60):
        self.ensure_group()
        with self.service.engine.connect() as c:
            rows=c.execute(select(outbox).join(calls,calls.c.id==outbox.c.call_id).where(
                calls.c.status.in_(['reserved','delivery_unknown']),
                calls.c.delivery_count<self.service.policy.max_delivery_attempts,
                calls.c.deadline>self.service.now(),
                or_(outbox.c.last_published_at.is_(None),
                    outbox.c.last_published_at<=self.service.now()-timedelta(seconds=recovery_seconds))
            )).mappings().all()
        published=[]
        for row in rows:
            mid=self.client.xadd(self.stream,{'outbox_id':row['id'],'call_id':row['call_id']})
            # This write intentionally follows Redis acceptance; duplicate XADD is safe.
            with self.service.engine.begin() as c:
                c.execute(update(outbox).where(outbox.c.id==row['id']).values(last_published_at=self.service.now()))
            published.append(dict(call_id=row['call_id'],message_id=mid))
        return published
    def process(self,messages,worker):
        handled=[]
        for mid,fields in messages:
            cid=fields.get('call_id'); oid=fields.get('outbox_id')
            with self.service.engine.connect() as c:
                row=c.execute(select(calls.c.status).join(outbox,calls.c.id==outbox.c.call_id)
                    .where(calls.c.id==cid,outbox.c.id==oid)).first()
            if row is None:
                self.client.xack(self.stream,self.group,mid)
                handled.append(dict(message_id=mid,disposition='invalid_ignored')); continue
            self.service.deliver(worker,[cid])
            with self.service.engine.connect() as c:
                status=c.execute(select(calls.c.status).where(calls.c.id==cid)).scalar_one()
            # The worker has persisted acceptance, or the call progressed/terminated.
            # Unknown deliveries stay pending until reclaim or deadline, using the same call_id.
            ack=status not in ['reserved','delivery_unknown']
            if ack: self.client.xack(self.stream,self.group,mid)
            handled.append(dict(call_id=cid,message_id=mid,acknowledged=ack,status=status))
        return handled
    def consume(self,worker,count=10):
        self.ensure_group()
        reply=self.client.xreadgroup(self.group,self.consumer,{self.stream:'>'},count=count)
        return self.process([message for _,messages in reply for message in messages],worker)
    def recover(self,worker,min_idle_ms=30000,count=10):
        self.ensure_group()
        # Scan the entire pending list; a lost process may leave messages far beyond the first page.
        cursor='0-0'; handled=[]
        while True:
            reply=self.client.xautoclaim(self.stream,self.group,self.consumer,min_idle_ms,cursor,count=count)
            cursor,messages=reply[:2]
            handled.extend(self.process(messages,worker))
            if cursor=='0-0': break
        return handled
    def step(self,worker):
        expired=self.service.expire(); reserved=self.service.reserve()
        return dict(expired=expired,reserved=reserved,published=self.publish(),
                    recovered=self.recover(worker),consumed=self.consume(worker))
