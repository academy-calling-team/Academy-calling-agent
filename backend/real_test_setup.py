"""Host operator helper, invoked inside the API container. JSON arrives via stdin.

No account creation, no public mutation endpoint, no phone/key output.
"""
import json
import sys
from sqlalchemy import select, update
from local_runtime import local_engine
from real_test import TEST_ACADEMY_ID, phone
from schema import academies, accounts, inquiries, calls
from service import Service

def main():
    request=json.load(sys.stdin)
    engine=local_engine(); service=Service(engine)
    try:
        with engine.begin() as c:
            service.lock(c)
            action=request['action']
            if action=='status':
                active=c.execute(select(calls.c.id).where(calls.c.status.not_in(['finished','timeout']))).all()
                pending=c.execute(select(inquiries.c.id).where(inquiries.c.status.in_(['queued','retry_wait']))).all()
                row=c.execute(select(academies).where(academies.c.id==TEST_ACADEMY_ID)).mappings().first()
                print(json.dumps(dict(active_calls=len(active),pending_inquiries=len(pending),
                    academy_prepared=row is not None,phone_configured=bool(row and row['phone']))));return
            if action=='owner':
                owner=c.execute(select(accounts.c.user_id).where(accounts.c.login_name==request['login_name'],
                    accounts.c.enabled==True,accounts.c.terms_agreed_at.is_not(None))).scalar_one_or_none()
                if not owner:raise ValueError('Enabled account with terms agreement required')
                print(json.dumps({'owner':owner}));return
            if action not in ['prepare','configure','clear']:raise ValueError('Invalid action')
            number=phone(request.get('phone')) if action=='configure' else None
            if action=='configure' and number is None:raise ValueError('One Korean mobile number required')
            row=c.execute(select(academies).where(academies.c.id==TEST_ACADEMY_ID)).mappings().first()
            if row and row['is_mock']:raise ValueError('Reserved test academy ID already used by mock data')
            if not row:
                c.execute(academies.insert().values(id=TEST_ACADEMY_ID,name='실통화 시험용 학원',
                    region='대구 북구 침산동',phone=number,is_mock=False,
                    hours=[dict(weekday=i,start_minute=0,end_minute=1440) for i in range(7)]))
            elif action!='prepare':
                c.execute(update(academies).where(academies.c.id==TEST_ACADEMY_ID).values(phone=number))
            print(json.dumps({'academy_prepared':True,'phone_configured':bool(number or (row and row['phone'] and action=='prepare'))}))
    finally:engine.dispose()

if __name__=='__main__':main()
