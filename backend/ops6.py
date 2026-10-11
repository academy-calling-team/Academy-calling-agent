"""Backend operations data, not a frontend dashboard."""
from sqlalchemy import select,func,text
from schema import inquiries,calls,review_holds,fallback_tasks,provider_inbox
from service import aware

class Operations:
    def __init__(self,service,queue_client=None):self.service,self.queue_client=service,queue_client
    def readiness(self):
        database=queue=False
        try:
            with self.service.engine.connect() as c:c.execute(text('SELECT 1'))
            database=True
        except Exception:pass
        if self.queue_client is not None:
            try:queue=self.queue_client.ping() is True
            except Exception:pass
        return dict(ready=database and queue,database='ok' if database else 'unavailable',
            queue='ok' if queue else 'unavailable',mode='development')
    def overview(self):
        with self.service.engine.connect() as c:
            grouped=lambda table:dict(c.execute(select(table.c.status,func.count()).group_by(table.c.status)).all())
            active=c.execute(select(func.count()).select_from(calls).where(calls.c.status.not_in(['finished','timeout']))).scalar_one()
            holds=c.execute(select(func.count()).select_from(review_holds).where(review_holds.c.open==True)).scalar_one()
            oldest=c.execute(select(func.min(inquiries.c.created_at)).where(inquiries.c.status=='queued')).scalar_one()
            return aware(dict(scope='local_development_database',inquiries=grouped(inquiries),
                active_calls=active,concurrency_limit=self.service.policy.max_concurrent,
                open_reviews=holds,fallback=grouped(fallback_tasks),provider_inbox=grouped(provider_inbox),
                oldest_queued_at=oldest))
    def reviews(self,limit=50,offset=0):
        with self.service.engine.connect() as c:
            rows=c.execute(select(review_holds).where(review_holds.c.open==True)
                .order_by(review_holds.c.created_at,review_holds.c.inquiry_id).limit(limit).offset(offset)).mappings()
            fallback=c.execute(select(fallback_tasks.c.inquiry_id,fallback_tasks.c.status,
                fallback_tasks.c.failure_reason,fallback_tasks.c.created_at)
                .where(fallback_tasks.c.status=='needs_review').order_by(fallback_tasks.c.created_at,
                    fallback_tasks.c.inquiry_id).limit(limit).offset(offset)).mappings()
            return aware(dict(callbacks=[dict(r) for r in rows],fallback=[dict(r) for r in fallback]))
