"""Local fake voice worker. Persists acceptance but never invokes telephony."""
import secrets
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from schema import worker_receipts
from service import fingerprint, datetime, timezone

def create_worker(engine, internal_key):
    app=FastAPI(title='8조 목업 음성 워커',version='0.2.0')
    @app.get('/internal/calls/{call_id}')
    def lookup(call_id:str,x_internal_key:str|None=Header(None)):
        if not x_internal_key or not secrets.compare_digest(x_internal_key,internal_key):
            raise HTTPException(401,'Invalid internal key')
        with engine.connect() as c:
            exists=c.execute(select(worker_receipts.c.call_id).where(worker_receipts.c.call_id==call_id)).first()
        if not exists:raise HTTPException(404,'Call not accepted')
        return dict(call_id=call_id,accepted=True)
    @app.post('/internal/calls',status_code=202)
    def accept(payload:dict,x_internal_key:str|None=Header(None)):
        if not x_internal_key or not secrets.compare_digest(x_internal_key,internal_key):
            raise HTTPException(401,'Invalid internal key')
        cid=payload.get('call_id')
        if not cid or len(cid)>36 or payload.get('is_mock') is not True:
            raise HTTPException(422,'Mock worker accepts mock calls only')
        fp=fingerprint(payload)
        try:
            with engine.begin() as c:
                old=c.execute(select(worker_receipts).where(worker_receipts.c.call_id==cid)).mappings().first()
                if old:
                    if old['payload_hash']!=fp: raise HTTPException(409,'Call ID reused with different payload')
                    return dict(call_id=cid,accepted=True,duplicate=True)
                c.execute(worker_receipts.insert().values(call_id=cid,payload_hash=fp,payload=payload,
                    received_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        except IntegrityError:
            with engine.connect() as c:
                old=c.execute(select(worker_receipts).where(worker_receipts.c.call_id==cid)).mappings().one()
                if old['payload_hash']!=fp: raise HTTPException(409,'Call ID conflict')
            return dict(call_id=cid,accepted=True,duplicate=True)
        return dict(call_id=cid,accepted=True,duplicate=False)
    return app

class MockWorker:
    def __init__(self,engine,key):
        self.client=TestClient(create_worker(engine,key)); self.key=key
    def accept(self,payload):
        reply=self.client.post('/internal/calls',json=payload,headers={'X-Internal-Key':self.key})
        if reply.status_code!=202: raise ConnectionError('Mock worker did not accept')
        return reply.json()
    def close(self): self.client.close()

def make_result(payload,outcome='answered',unanswered=None,negative=None):
    """Deterministic fake output and explicit labels for backend tests."""
    unanswered,negative=set(unanswered or []),set(negative or [])
    ans=[]
    for q in payload['questions']:
        ok=outcome=='answered' and q['question_code'] not in unanswered
        ans.append(dict(**q,asked=outcome=='answered',answered=ok,
            yes_no=(q['question_code'] not in negative) if ok and q['question_code']!='class_time' else None,
            reason=None if ok else ('unknown' if outcome=='answered' else 'not_asked'),
            detail=('화목 19:00' if q['question_code']=='class_time' else '목업 정답') if ok else '미확인'))
    return dict(result_id='result_'+payload['call_id'],outcome=outcome,
        disclosure_played=True if outcome=='answered' else None,
        consult_accepted=True if outcome=='answered' else None,
        available_times=['평일 14:00-16:00'] if outcome=='answered' else [],answers=ans,
        unresolved=[a['question_id'] for a in ans if not a['answered']],summary_text='가상 통화 결과',
        notes='실제 전화 아님',latency=None,duration_sec=0,transcript=[])
