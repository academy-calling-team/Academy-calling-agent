"""Offline Vapi message normalization and durable inbox. No provider API calls/webhook listener.

Only mapped call IDs are accepted. Store canonical minimal data, not raw transcripts/recordings.
Unsupported/missing extraction is quarantined; never invent a yes/no, disclosure or latency.
"""
from datetime import datetime,timezone
from pydantic import ValidationError
from sqlalchemy import select,update
from fastapi import HTTPException
from schema import calls,provider_calls,provider_inbox
from service import fingerprint
from contracts import EventInput,ResultInput

class VapiBridge:
    def __init__(self,service,output_id='team8-result-v1'):
        self.service,self.output_id=service,output_id
    def bind(self,cid,external_id):
        if not isinstance(external_id,str) or not 1<=len(external_id)<=100:
            raise HTTPException(422,'Invalid provider call ID')
        with self.service.engine.begin() as c:
            self.service.lock(c)
            if not c.execute(select(calls.c.id).where(calls.c.id==cid)).first():raise HTTPException(404,'Call not found')
            old=c.execute(select(provider_calls).where((provider_calls.c.call_id==cid)|(
                (provider_calls.c.provider=='vapi')&(provider_calls.c.external_id==external_id)))).mappings().first()
            if old:
                if old['call_id']!=cid or old['provider']!='vapi' or old['external_id']!=external_id:
                    raise HTTPException(409,'Provider call mapping conflict')
                return dict(duplicate=True)
            c.execute(provider_calls.insert().values(call_id=cid,provider='vapi',external_id=external_id,
                created_at=self.service.now()))
        return dict(duplicate=False)
    def receive(self,raw):
        message=raw.get('message') if isinstance(raw,dict) else None
        if not isinstance(message,dict) or not isinstance(message.get('call'),dict):
            raise HTTPException(422,'Vapi message/call object required')
        external_id=message['call'].get('id');kind=message.get('type')
        with self.service.engine.connect() as c:
            mapping=c.execute(select(provider_calls).where(provider_calls.c.provider=='vapi',
                provider_calls.c.external_id==external_id)).mappings().first()
        if not mapping:raise HTTPException(404,'Unmapped provider call')
        cid=mapping['call_id'];fp=fingerprint(raw);ident=fingerprint(dict(provider='vapi',payload_hash=fp))
        status='pending';error=None;normalized={}
        try:
            if kind=='status-update':
                event_type={'ringing':'ringing','in-progress':'initiated','ended':'completed'}.get(message.get('status'))
                if not event_type:status='ignored'
                else:
                    stamp=message.get('timestamp')
                    if isinstance(stamp,(int,float)) and not isinstance(stamp,bool):
                        stamp=datetime.fromtimestamp(stamp/1000,timezone.utc)
                    event=EventInput(event_id='vapi_'+ident,type=event_type,occurred_at=stamp)
                    normalized=dict(event=event.model_dump(mode='json'))
            elif kind=='end-of-call-report':
                artifact=message.get('artifact') or message['call'].get('artifact') or {}
                output=artifact.get('structuredOutputs',{}).get(self.output_id)
                extracted=output.get('result') if isinstance(output,dict) else None
                # Configuration explicitly pins the expected output ID/schema; no legacy auto-guessing.
                if extracted is None:raise ValueError('structured_output_missing')
                body=ResultInput.model_validate(extracted)
                normalized=dict(result=body.model_dump(mode='json'))
            else:status='ignored'
        except (ValidationError,ValueError,TypeError,AttributeError,OverflowError):
            status='quarantined';error='invalid_or_missing_canonical_fields'
        with self.service.engine.begin() as c:
            self.service.lock(c)
            old=c.execute(select(provider_inbox).where(provider_inbox.c.id==ident)).mappings().first()
            if old:return dict(inbox_id=ident,duplicate=True,status=old['status'])
            c.execute(provider_inbox.insert().values(id=ident,call_id=cid,type=str(kind)[:60],
                payload_hash=fp,status=status,normalized=normalized,error=error,received_at=self.service.now()))
        return dict(inbox_id=ident,duplicate=False,status=status)
    def process(self,ident):
        with self.service.engine.connect() as c:
            row=c.execute(select(provider_inbox).where(provider_inbox.c.id==ident)).mappings().first()
        if not row:raise HTTPException(404,'Inbox item not found')
        if row['status']!='pending':return dict(inbox_id=ident,status=row['status'],duplicate=True)
        try:
            if 'event' in row['normalized']:
                result=self.service.event(row['call_id'],EventInput.model_validate(row['normalized']['event']))
            else:result=self.service.result(row['call_id'],ResultInput.model_validate(row['normalized']['result']))
            status='processed';error=None
        except HTTPException as failure:
            status='quarantined';error='contract_error_'+str(failure.status_code);result=None
        with self.service.engine.begin() as c:
            c.execute(update(provider_inbox).where(provider_inbox.c.id==ident,provider_inbox.c.status=='pending')
                .values(status=status,error=error,processed_at=self.service.now()))
        return dict(inbox_id=ident,status=status,result=result)
