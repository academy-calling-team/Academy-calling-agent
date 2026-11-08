"""Durable MySQL development queue with a replaceable mock voice worker."""
import hashlib
import json
from collections import deque
from datetime import datetime, time, timezone, timedelta
from dataclasses import dataclass
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from schema import accounts,sessions,review_holds,review_actions,fallback_tasks
from schema import (metadata, users, academies, inquiries, questions, calls, events, results, answers, control,
                    outbox, delivery_leases, corrections, academy_policies,
                    academy_classes, academy_call_hours, academy_setting_states)
from worker_errors import WorkerRejected, WorkerProtocolError
from real_test import RealTestPolicy, phone
from contracts import QUESTION_LABELS, CALL_STATUS_LABELS_KR, CALL_OUTCOME_LABELS_KR

def uid(): return str(uuid4())
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def fingerprint(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':')))
def utc(value): return value.astimezone(timezone.utc).replace(tzinfo=None)

def queue_order(row):
    return -row['priority'], row['created_at'], row['id']

def clock_seconds(value):
    return value.hour * 3600 + value.minute * 60 + value.second

def daily_windows(windows):
    days = [[] for _ in range(7)]
    for day, start, end in windows:
        if start < end:
            days[day].append((start, end))
        elif end < start:
            days[day].append((start, 86400))
            if end:
                days[(day + 1) % 7].append((0, end))
    merged_days = []
    for ranges in days:
        merged = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        merged_days.append(merged)
    return merged_days

def academy_windows(academy, call_hours):
    operating = daily_windows((w['weekday'], w['start_minute'] * 60, w['end_minute'] * 60)
                              for w in academy['hours'])
    if not call_hours:
        return operating
    response = daily_windows((w['day_of_week'], clock_seconds(w['start_time']), clock_seconds(w['end_time']))
                             for w in call_hours)
    return [
        [(max(start, first), min(end, last)) for start, end in operating_day
         for first, last in response_day if max(start, first) < min(end, last)]
        for operating_day, response_day in zip(operating, response)
    ]

def within_hours(local, windows):
    second = clock_seconds(local)
    return any(start <= second < end for start, end in windows[local.weekday()])

def waiting_cutoffs(local_now, earliest, windows, closed_dates, targets):
    # Find each waiting threshold once per academy, walking back through open hours.
    cutoffs = {}
    elapsed = timedelta()
    targets = iter(sorted(set(targets)))
    target = next(targets, None)
    day = local_now.date()
    while target is not None and day >= earliest.date():
        if day.isoformat() not in closed_dates:
            midnight = datetime.combine(day, time.min, tzinfo=local_now.tzinfo)
            for start, end in reversed(windows[day.weekday()]):
                start_at = max(earliest, midnight + timedelta(seconds=start))
                end_at = min(local_now, midnight + timedelta(seconds=end))
                duration = end_at - start_at
                if duration <= timedelta():
                    continue
                while target is not None and elapsed + duration >= timedelta(minutes=target):
                    cutoffs[target] = utc(end_at - (timedelta(minutes=target) - elapsed))
                    target = next(targets, None)
                if target is None:
                    break
                elapsed += duration
        day -= timedelta(days=1)
    return cutoffs

def eligible_since(row):
    return max(row['created_at'], row['next_at'])

def aware(value):
    if isinstance(value, datetime): return value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, dict): return {k:aware(v) for k,v in value.items()}
    if isinstance(value, list): return [aware(v) for v in value]
    return value

@dataclass(frozen=True)
class Policy:
    # Retry schedule confirmed by the project owner; other limits are development defaults.
    max_concurrent: int = 2
    max_attempts: int = 4
    retry_delays_seconds: tuple[int, ...] = (300, 600, 1800)
    result_timeout_seconds: int = 600
    max_delivery_attempts: int = 3
    max_seconds: int = 180
    delivery_lease_seconds: int = 30
    disclosure_text: str = '개발용 예시: AI가 진행하는 녹음 통화입니다. 상담 가능하신가요?'
    # Development defaults for ordering eligible inquiries within an academy.
    priority_aging_minutes: int = 60
    priority_overdue_minutes: int = 240
    def __post_init__(self):
        if min(self.max_concurrent,self.max_attempts,
               self.result_timeout_seconds,self.max_delivery_attempts,self.max_seconds,
               self.delivery_lease_seconds) < 1:
            raise ValueError('Policy limits must be positive')
        if min(self.priority_aging_minutes, self.priority_overdue_minutes) < 1:
            raise ValueError('Priority waiting limits must be positive')
        if not self.retry_delays_seconds or any(delay < 1 for delay in self.retry_delays_seconds):
            raise ValueError('Retry delays must be positive')
    def retry_delay(self, attempt_no):
        # A failed first call waits 5 minutes; later failures wait 10, then 30.
        return self.retry_delays_seconds[min(attempt_no-1,len(self.retry_delays_seconds)-1)]

class Service:
    def __init__(self, engine, policy=None, clock=None,allow_legacy_tokens=True,real_test=None):
        self.engine, self.policy = engine, policy or Policy()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.allow_legacy_tokens=allow_legacy_tokens
        self.real_test=real_test or RealTestPolicy()
    def attempt_limit(self,c,academy_id):
        mock=c.execute(select(academies.c.is_mock).where(academies.c.id==academy_id)).scalar_one()
        return self.policy.max_attempts if mock else 1
    def authorize_real_dispatch(self,payload):
        # Resolve the academy and owner from persisted state, never caller claims.
        with self.engine.connect() as c:
            call=c.execute(select(calls).where(calls.c.id==payload.get('call_id'))).mappings().first()
            if not call or call['status'] not in ['reserved','delivery_unknown']:return False
            row=c.execute(select(inquiries).where(inquiries.c.id==call['inquiry_id'])).mappings().one()
            ac=c.execute(select(academies).where(academies.c.id==row['academy_id'])).mappings().one()
            account=c.execute(select(accounts.c.enabled).where(accounts.c.user_id==row['inquirer_id'])).scalar()
            return bool(account and self.real_test.permits(ac,row['inquirer_id'])
                and call['attempt_no']==1 and payload.get('is_mock') is False
                and phone(payload.get('to'))==phone(ac['phone'])
                and fingerprint(payload)==fingerprint(call['dispatch_payload']))
    def now(self): return utc(self.clock())
    def initialize(self):
        metadata.create_all(self.engine)
        try:
            with self.engine.begin() as c: c.execute(control.insert().values(id='scheduler'))
        except IntegrityError: pass
    def lock(self, c):
        # One database row serializes orchestration across processes, not just threads.
        c.execute(select(control).where(control.c.id=='scheduler').with_for_update()).first()
    def owner(self, c, token):
        if not token: raise HTTPException(401,'Bearer token required')
        session=c.execute(select(sessions.c.user_id,sessions.c.expires_at,sessions.c.revoked,
            accounts.c.enabled).join(accounts,sessions.c.user_id==accounts.c.user_id)
            .where(sessions.c.token_hash==digest(token))).mappings().first()
        if session:
            if session['revoked'] or session['expires_at']<=self.now() or not session['enabled']:
                raise HTTPException(401,'Session expired or revoked')
            return session['user_id']
        if not self.allow_legacy_tokens: raise HTTPException(401,'Invalid session')
        row=c.execute(select(users.c.id).where(users.c.token_hash==digest(token))).first()
        if row is None: raise HTTPException(401,'Invalid token')
        return row.id
    def create(self, body, token, key):
        payload=body.model_dump(mode='json')
        with self.engine.begin() as c:
            self.lock(c)
            owner=self.owner(c,token)
            if body.inquirer_id != owner: raise HTTPException(403,'inquirer_id must match authenticated identity')
            prev=c.execute(select(inquiries).where(inquiries.c.inquirer_id==owner,
                           inquiries.c.request_key==key).with_for_update()).mappings().first()
            if prev:
                if prev['payload_hash']!=fingerprint(payload): raise HTTPException(409,'Idempotency key conflict')
                return dict(inquiry_id=prev['id'],status=prev['status'],duplicate=True)
            ac=c.execute(select(academies).where(academies.c.id==body.academy_id)).mappings().first()
            if ac is None:
                raise HTTPException(404,'Academy not found')
            if not ac['is_mock'] and not self.real_test.permits(ac,owner):
                raise HTTPException(409,'실통화 시험은 서버 설정과 지정 시험 계정 확인 후 접수할 수 있습니다.')
            iid=uid()
            c.execute(inquiries.insert().values(id=iid,inquirer_id=owner,academy_id=body.academy_id,
                request_key=key,payload_hash=fingerprint(payload),student=payload['student'],status='queued',
                created_at=self.now(),next_at=self.now(),priority=0,fallback_required=False))
            for pos,code in enumerate(body.question_codes):
                c.execute(questions.insert().values(id=uid(),inquiry_id=iid,code=code,position=pos))
            return dict(inquiry_id=iid,status='queued',duplicate=False)
    def list_owned(self, token, owner_filter=None, limit=50, offset=0):
        with self.engine.connect() as c:
            owner=self.owner(c,token)
            if owner_filter and owner_filter!=owner: raise HTTPException(403,'Other owner forbidden')
            rows=c.execute(select(inquiries.c.id,inquiries.c.status,inquiries.c.created_at)
                .where(inquiries.c.inquirer_id==owner).order_by(inquiries.c.created_at.desc(),inquiries.c.id)
                .limit(limit).offset(offset)).mappings()
            return aware([dict(inquiry_id=r['id'],status=r['status'],created_at=r['created_at']) for r in rows])
    def get(self, iid, token):
        with self.engine.connect() as c:
            owner=self.owner(c,token)
            row=c.execute(select(inquiries).where(inquiries.c.id==iid,inquiries.c.inquirer_id==owner)).mappings().first()
            if not row: raise HTTPException(404,'Inquiry not found')
            ac=c.execute(select(academies).where(academies.c.id==row['academy_id'])).mappings().one()
            qs=c.execute(select(questions).where(questions.c.inquiry_id==iid).order_by(questions.c.position)).mappings().all()
            history=[]; final=None
            hold=c.execute(select(review_holds).where(review_holds.c.inquiry_id==iid,
                review_holds.c.open==True)).mappings().first()
            fallback=c.execute(select(fallback_tasks.c.status).where(fallback_tasks.c.inquiry_id==iid)).first()
            for call in c.execute(select(calls).where(calls.c.inquiry_id==iid).order_by(calls.c.attempt_no)).mappings():
                history.append(dict(call_id=call['id'],attempt_no=call['attempt_no'],status=call['status'],
                    status_label_kr=CALL_STATUS_LABELS_KR.get(call['status'],call['status']),
                    started_at=call['created_at'],outcome=call['outcome'],
                    outcome_label_kr=CALL_OUTCOME_LABELS_KR.get(call['outcome'],call['outcome'])))
                res=c.execute(select(results).where(results.c.call_id==call['id'],results.c.applied==True)).mappings().first()
                if res:
                    review=c.execute(select(corrections).where(corrections.c.call_id==call['id'])
                        .order_by(corrections.c.revision.desc()).limit(1)).mappings().first()
                    effective=review['payload'] if review else res['payload']
                    # Raw transcripts, recording URLs and internal delivery metadata stay internal.
                    final={k:v for k,v in effective.items() if k not in
                           ('transcript','recording_url','result_id','rejection_reason')}
                    final['review_revision']=review['revision'] if review else 0
            return aware(dict(inquiry_id=iid,inquirer_id=owner,status=row['status'],student=row['student'],
                academy={'academy_id':ac['id'],'name':ac['name'],'is_mock':ac['is_mock'],
                         **self.real_test.public(ac)},
                questions=[dict(question_id=q['id'],question_code=q['code'],
                    question_label_kr=QUESTION_LABELS.get(q['code'],q['code'])) for q in qs],
                attempts=history,result=final,failure_reason=row['failure_reason'],
                fallback_required=row['fallback_required'],fallback_status=fallback.status if fallback else None,
                review_required=hold is not None,review_reason=hold['reason'] if hold else None))
    def opened(self, academy):
        local = self.clock().astimezone(ZoneInfo('Asia/Seoul'))
        return within_hours(local, academy_windows(academy, ()))
    def set_academy_policy(self,acid,body):
        """Validated local configuration. No public scheduler-policy mutation endpoint."""
        values=body.model_dump(mode='json');hours=values.pop('hours')
        with self.engine.begin() as c:
            self.lock(c)
            if c.execute(select(academies.c.id).where(academies.c.id==acid)).first() is None:
                raise HTTPException(404,'Academy not found')
            existing=c.execute(select(academy_policies).where(academy_policies.c.academy_id==acid)).first()
            if existing: c.execute(update(academy_policies).where(academy_policies.c.academy_id==acid).values(**values))
            else:c.execute(academy_policies.insert().values(academy_id=acid,**values))
            c.execute(update(academies).where(academies.c.id==acid).values(hours=hours))
    def academy_queue_order(self, row, classes, cutoffs):
        student = row['student']
        fields = (('grade_code', 'grade'), ('subject_code', 'subject'), ('level_code', 'level'))
        match_score = max(
            (sum(rule[setting] is not None and rule[setting] == student.get(answer)
                 for setting, answer in fields) for rule in classes),
            default=0,
        )
        since = eligible_since(row)
        overdue_cutoff = cutoffs.get(self.policy.priority_overdue_minutes)
        overdue = overdue_cutoff is not None and since <= overdue_cutoff
        steps = (self.policy.priority_aging_minutes, self.policy.priority_aging_minutes * 2)
        aging_score = sum(since <= cutoffs[step] for step in steps if step in cutoffs)
        # Four points per match keeps the two ordinary waiting points below a single match.
        score = match_score * 4 + aging_score
        # Keep explicitly assigned priority tiers ahead of automatic preferences.
        return (-row['priority'], not overdue, 0 if overdue else -score,
                since if overdue else row['created_at'], row['created_at'], row['id'])

    def academy_slots(self, c, academy_id, available, now, rule):
        if not rule:
            return available
        academy_calls = calls.join(inquiries)
        belongs_to_academy = inquiries.c.academy_id == academy_id
        active = c.execute(select(func.count()).select_from(academy_calls).where(
            belongs_to_academy, calls.c.status.not_in(['finished', 'timeout']))).scalar_one()
        slots = min(available, rule['max_concurrent'] - active)
        if slots <= 0 or not rule['cooldown_seconds']:
            return slots
        latest_start = c.execute(select(func.max(calls.c.created_at)).select_from(academy_calls)
                                 .where(belongs_to_academy)).scalar_one()
        cooldown = timedelta(seconds=rule['cooldown_seconds'])
        return 1 if latest_start is None or latest_start + cooldown <= now else 0

    def eligible_academies(self, c, rows, available, now, local):
        pending = {}
        for row in rows:
            pending.setdefault(row['academy_id'], []).append(row)

        groups = {}
        local_date = local.date().isoformat()
        for academy_id, candidates in pending.items():
            academy = c.execute(select(academies).where(
                academies.c.id == academy_id)).mappings().one()
            permitted = []
            for row in candidates:
                if not academy['is_mock'] and not self.real_test.permits(academy, row['inquirer_id']):
                    self.fail(c, row['id'], 'real_test_disabled')
                else:
                    permitted.append(row)
            if not permitted:
                continue
            call_hours = c.execute(select(academy_call_hours).where(
                academy_call_hours.c.academy_id == academy_id)).mappings().all()
            windows = academy_windows(academy, call_hours)
            if not within_hours(local, windows):
                continue
            rule = c.execute(select(academy_policies).where(
                academy_policies.c.academy_id == academy_id)).mappings().first()
            closed_dates = set(rule['closed_dates']) if rule else set()
            if (rule and not rule['enabled']) or local_date in closed_dates:
                continue
            slots = self.academy_slots(c, academy_id, available, now, rule)
            if slots <= 0:
                continue
            limit = self.attempt_limit(c, academy_id)
            eligible = []
            for row in permitted:
                if row['attempt_count'] >= limit:
                    self.fail(c, row['id'], 'retry_exhausted')
                else:
                    eligible.append(row)
            if not eligible:
                continue
            classes = c.execute(select(academy_classes).where(
                academy_classes.c.academy_id == academy_id)).mappings().all()
            if classes:
                earliest = min(eligible_since(row) for row in eligible).replace(tzinfo=timezone.utc)
                step = self.policy.priority_aging_minutes
                cutoffs = waiting_cutoffs(local, earliest.astimezone(local.tzinfo), windows, closed_dates,
                                          (step, step * 2, self.policy.priority_overdue_minutes))
                eligible.sort(key=lambda row: self.academy_queue_order(row, classes, cutoffs))
            groups[academy_id] = (academy, deque(eligible), slots)
        return groups

    def get_academy_settings(self, acid):
        with self.engine.connect() as c:
            if c.execute(select(academies.c.id).where(academies.c.id == acid)).first() is None:
                raise HTTPException(404, 'Academy not found')
            
            classes = c.execute(select(academy_classes).where(academy_classes.c.academy_id == acid)).mappings().all()
            hours = c.execute(select(academy_call_hours).where(academy_call_hours.c.academy_id == acid)).mappings().all()
            
            return dict(
                classes=[dict(c) for c in classes],
                call_hours=[dict(h) for h in hours]
            )

    def update_academy_settings(self, acid, body):
        payload = body.model_dump(mode='json')
        with self.engine.begin() as c:
            self.lock(c)
            if c.execute(select(academies.c.id).where(academies.c.id == acid)).first() is None:
                raise HTTPException(404, 'Academy not found')

            # 반/시간 전체 삭제 후 재삽입 (트랜잭션)
            c.execute(academy_classes.delete().where(academy_classes.c.academy_id == acid))
            c.execute(academy_call_hours.delete().where(academy_call_hours.c.academy_id == acid))
            
            now_time = self.now()
            for cls in payload['classes']:
                c.execute(academy_classes.insert().values(id=uid(), academy_id=acid, created_at=now_time, updated_at=now_time, **cls))
            for hr in payload['call_hours']:
                c.execute(academy_call_hours.insert().values(
                    academy_id=acid, created_at=now_time, day_of_week=hr['day_of_week'],
                    start_time=time.fromisoformat(hr['start_time']), end_time=time.fromisoformat(hr['end_time'])))
                
            # 설정 상태 업데이트 (버전 및 수정시각)
            state = c.execute(select(academy_setting_states).where(academy_setting_states.c.academy_id == acid)).first()
            if state:
                c.execute(update(academy_setting_states).where(academy_setting_states.c.academy_id == acid).values(
                    is_class_configured=True, is_call_hours_configured=True, last_modified_at=now_time, version=state.version+1))
            else:
                c.execute(academy_setting_states.insert().values(academy_id=acid, 
                    is_class_configured=True, is_call_hours_configured=True, last_modified_at=now_time, version=1))
        return dict(status='updated')
    
    def reserve(self):
        with self.engine.begin() as c:
            self.lock(c)
            active = c.execute(select(func.count()).select_from(calls).where(
                calls.c.status.not_in(['finished', 'timeout']))).scalar_one()
            available = self.policy.max_concurrent - active
            if available <= 0:
                return []
            instant = self.clock()
            now = utc(instant)
            local = instant.astimezone(ZoneInfo('Asia/Seoul'))
            attempt_count = select(func.count()).where(calls.c.inquiry_id == inquiries.c.id).scalar_subquery()
            has_review_hold = select(review_holds.c.inquiry_id).where(
                review_holds.c.inquiry_id == inquiries.c.id, review_holds.c.open.is_(True)).exists()
            rows = c.execute(select(inquiries, attempt_count.label('attempt_count')).where(
                inquiries.c.status.in_(['queued', 'retry_wait']), inquiries.c.next_at <= now,
                ~has_review_hold).order_by(inquiries.c.priority.desc(), inquiries.c.created_at,
                                          inquiries.c.id).with_for_update()).mappings().all()
            groups = self.eligible_academies(c, rows, available, now, local)
            reserved = []
            while groups and len(reserved) < available:
                academy_id = min(groups, key=lambda key: queue_order(groups[key][1][0]))
                ac, candidates, slots = groups[academy_id]
                row = candidates.popleft()
                if candidates and slots > 1:
                    groups[academy_id] = (ac, candidates, slots - 1)
                else:
                    del groups[academy_id]
                attempt = row['attempt_count'] + 1
                cid=uid()
                qs=c.execute(select(questions).where(questions.c.inquiry_id==row['id']).order_by(questions.c.position)).mappings()
                payload=dict(call_id=cid,inquiry_id=row['id'],attempt_no=attempt,to=ac['phone'],
                    academy_name=ac['name'],student=row['student'],
                    questions=[dict(question_id=q['id'],question_code=q['code']) for q in qs],
                    fixed_checks=['consult_accepted','available_times'],disclosure_text=self.policy.disclosure_text,
                    policy=dict(max_reask=1,max_seconds=self.policy.max_seconds,is_retry=attempt>1),
                    is_mock=ac['is_mock'])
                c.execute(calls.insert().values(id=cid,inquiry_id=row['id'],attempt_no=attempt,status='reserved',
                    created_at=self.now(),deadline=self.now()+timedelta(seconds=self.policy.result_timeout_seconds),
                    dispatch_payload=payload,delivery_count=0))
                c.execute(outbox.insert().values(id=uid(),call_id=cid,created_at=self.now()))
                c.execute(update(inquiries).where(inquiries.c.id==row['id']).values(status='calling'))
                reserved.append(cid)
            return reserved
    def deliver(self, worker, call_ids=None):
        # Commit reservation before I/O. On unknown delivery, resend the SAME call_id.
        # The mock/real worker must persist idempotent acceptance of that ID.
        with self.engine.connect() as c:
            query=select(calls.c.id).where(calls.c.status.in_(['reserved','delivery_unknown']))
            if call_ids is not None: query=query.where(calls.c.id.in_(call_ids))
            ids=list(c.execute(query).scalars())
        sent=[]
        for cid in ids:
            with self.engine.begin() as c:
                self.lock(c)
                row=c.execute(select(calls).where(calls.c.id==cid)).mappings().one()
                lease=c.execute(select(delivery_leases).where(delivery_leases.c.call_id==cid)).mappings().first()
                if row['status'] not in ['reserved','delivery_unknown'] or row['delivery_count']>=self.policy.max_delivery_attempts:
                    continue
                if row['deadline']<=self.now() or (lease and lease['lease_until']>self.now()): continue
                claim=uid(); values=dict(claim_id=claim,lease_until=self.now()+timedelta(seconds=self.policy.delivery_lease_seconds))
                if lease: c.execute(update(delivery_leases).where(delivery_leases.c.call_id==cid).values(**values))
                else: c.execute(delivery_leases.insert().values(call_id=cid,**values))
                c.execute(update(calls).where(calls.c.id==cid).values(delivery_count=row['delivery_count']+1))
                payload=row['dispatch_payload']
            # No DB transaction or scheduler lock spans network I/O. A callback can commit here.
            rejection=None
            try:
                reply=worker.accept(payload)
                ok=reply.get('call_id')==cid and reply.get('accepted') is True
            except WorkerRejected as error:
                ok=False; rejection=f'worker_http_{error.status_code}'
            except WorkerProtocolError:
                ok=False; rejection='worker_protocol_error'
            except (TimeoutError,ConnectionError): ok=False
            with self.engine.begin() as c:
                self.lock(c)
                lease=c.execute(select(delivery_leases).where(delivery_leases.c.call_id==cid)).mappings().one()
                if lease['claim_id']==claim:
                    current=c.execute(select(calls).where(calls.c.id==cid)).mappings().one()
                    if current['status'] in ['reserved','delivery_unknown']:
                        if rejection:
                            # A declined dispatch never becomes an automatic redial or SMS fallback.
                            c.execute(update(calls).where(calls.c.id==cid).values(status='finished'))
                            c.execute(update(inquiries).where(inquiries.c.id==current['inquiry_id']).values(
                                status='failed',failure_reason=rejection,fallback_required=False))
                            values=dict(call_id=cid,reason=rejection,open=True,created_at=self.now())
                            if c.execute(select(review_holds).where(review_holds.c.inquiry_id==current['inquiry_id'])).first():
                                c.execute(update(review_holds).where(review_holds.c.inquiry_id==current['inquiry_id']).values(**values))
                            else:c.execute(review_holds.insert().values(inquiry_id=current['inquiry_id'],**values))
                        else:
                            c.execute(update(calls).where(calls.c.id==cid).values(status='accepted' if ok else 'delivery_unknown'))
                    c.execute(update(delivery_leases).where(delivery_leases.c.call_id==cid).values(lease_until=self.now()))
            sent.append(dict(call_id=cid,accepted=ok,**({'rejection':rejection} if rejection else {})))
        return sent
    def correct_result(self,cid,body):
        """Local reviewer service only. Never changes a worker's original report or call state."""
        payload=body.payload.model_dump(mode='json')
        with self.engine.begin() as c:
            self.lock(c)
            original=c.execute(select(results).where(results.c.call_id==cid)).mappings().first()
            if not original or not original['applied']: raise HTTPException(409,'Only applied results can be reviewed')
            previous=c.execute(select(corrections).where(corrections.c.call_id==cid)
                .order_by(corrections.c.revision.desc()).limit(1)).mappings().first()
            revision=previous['revision'] if previous else 0
            if body.base_revision!=revision: raise HTTPException(409,'Review revision conflict; reload before editing')
            editable={'answers','unresolved','summary_text','notes'}
            if any(payload[k]!=original['payload'][k] for k in payload.keys()-editable):
                raise HTTPException(422,'Operational fields cannot be corrected')
            expected={a['question_id']:a['question_code'] for a in original['payload']['answers']}
            if {a['question_id']:a['question_code'] for a in payload['answers']}!=expected:
                raise HTTPException(422,'Question identities cannot be corrected')
            current=previous['payload'] if previous else original['payload']
            if payload==current: raise HTTPException(422,'Review contains no changes')
            c.execute(corrections.insert().values(id=uid(),call_id=cid,revision=revision+1,
                reviewer=body.reviewer,reason=body.reason,payload=payload,created_at=self.now()))
            return dict(call_id=cid,revision=revision+1)
    def fail(self,c,iid,reason):
        needs_fallback=reason not in ['rejected','disclosure_missing']
        c.execute(update(inquiries).where(inquiries.c.id==iid).values(status='failed',
            failure_reason=reason,fallback_required=needs_fallback))
        if needs_fallback and not c.execute(select(fallback_tasks.c.inquiry_id).where(
            fallback_tasks.c.inquiry_id==iid)).first():
            c.execute(fallback_tasks.insert().values(inquiry_id=iid,status='needs_review',
                failure_reason=reason,created_at=self.now()))
    def finish(self,c,call,outcome,callback_at=None,permanent=False,callback_requested=False):
        c.execute(update(calls).where(calls.c.id==call['id']).values(status='finished',outcome=outcome))
        latest=c.execute(select(func.max(calls.c.attempt_no)).where(calls.c.inquiry_id==call['inquiry_id'])).scalar_one()
        state=c.execute(select(inquiries.c.status).where(inquiries.c.id==call['inquiry_id'])).scalar_one()
        if call['attempt_no']!=latest or state in ['completed','failed']: return False
        academy_id=c.execute(select(inquiries.c.academy_id).where(inquiries.c.id==call['inquiry_id'])).scalar_one()
        attempt_limit=self.attempt_limit(c,academy_id)
        is_mock=c.execute(select(academies.c.is_mock).where(academies.c.id==academy_id)).scalar_one()
        if not is_mock and outcome=='answered':
            # Record the answer, including callback metadata, without scheduling another call.
            c.execute(update(inquiries).where(inquiries.c.id==call['inquiry_id']).values(status='completed'))
            return True
        if outcome=='answered' and callback_requested and callback_at is None:
            c.execute(update(inquiries).where(inquiries.c.id==call['inquiry_id']).values(status='retry_wait'))
            hold_values=dict(call_id=call['id'],reason='callback_time_unknown',open=True,created_at=self.now())
            if c.execute(select(review_holds.c.inquiry_id).where(review_holds.c.inquiry_id==call['inquiry_id'])).first():
                c.execute(update(review_holds).where(review_holds.c.inquiry_id==call['inquiry_id']).values(**hold_values))
            else:c.execute(review_holds.insert().values(inquiry_id=call['inquiry_id'],**hold_values))
            return True
        retry=outcome in ['no_answer','busy','machine','rejected'] or callback_at is not None
        if outcome=='answered' and callback_at is None:
            c.execute(update(inquiries).where(inquiries.c.id==call['inquiry_id']).values(status='completed'))
        elif retry and not permanent and call['attempt_no']<attempt_limit:
            at=utc(callback_at) if callback_at else self.now()+timedelta(seconds=self.policy.retry_delay(call['attempt_no']))
            c.execute(update(inquiries).where(inquiries.c.id==call['inquiry_id']).values(status='retry_wait',next_at=at))
        else:
            # Keep rejection fallback handling unchanged; its policy is a separate task.
            self.fail(c,call['inquiry_id'],outcome if permanent or outcome=='rejected'
                else ('retry_exhausted' if retry else outcome))
        return True
    def event(self,cid,body):
        payload=body.model_dump(mode='json'); fp=fingerprint(payload)
        with self.engine.begin() as c:
            self.lock(c)
            old=c.execute(select(events).where(events.c.id==body.event_id)).mappings().first()
            if old:
                if old['call_id']!=cid or old['payload_hash']!=fp: raise HTTPException(409,'Event ID conflict')
                return dict(duplicate=True,applied=old['applied'])
            call=c.execute(select(calls).where(calls.c.id==cid).with_for_update()).mappings().first()
            if not call: raise HTTPException(404,'Call not found')
            when=utc(body.occurred_at)
            applied=call['status'] not in ['finished','timeout','ended'] and (
                call['last_event_at'] is None or when>=call['last_event_at'])
            rank={'reserved':0,'delivery_unknown':0,'accepted':0,'initiated':1,'ringing':2,'answered':3}
            if body.type in rank and rank[body.type]<rank.get(call['status'],0): applied=False
            if body.type=='barge_in': applied=False
            if applied:
                if body.type in ['no_answer','busy','machine','rejected','invalid_number']:
                    self.finish(c,call,body.type)
                else:
                    c.execute(update(calls).where(calls.c.id==cid).values(
                        status='ended' if body.type=='completed' else body.type,
                        # Duplicate/progressive status events must not keep a lost call alive forever.
                        deadline=call['deadline']))
                c.execute(update(calls).where(calls.c.id==cid).values(last_event_at=when))
            c.execute(events.insert().values(id=body.event_id,call_id=cid,type=body.type,occurred_at=when,
                received_at=self.now(),payload_hash=fp,applied=applied))
            return dict(duplicate=False,applied=applied)
    def result(self,cid,body):
        payload=body.model_dump(mode='json'); fp=fingerprint(payload)
        with self.engine.begin() as c:
            self.lock(c)
            call=c.execute(select(calls).where(calls.c.id==cid).with_for_update()).mappings().first()
            if not call: raise HTTPException(404,'Call not found')
            prior=c.execute(select(results).where((results.c.call_id==cid)|(results.c.result_id==body.result_id))).mappings().first()
            if prior:
                if prior['call_id']!=cid or prior['payload_hash']!=fp: raise HTTPException(409,'Immutable result conflict')
                return dict(duplicate=True,applied=prior['applied'])
            expected={q['id']:q['code'] for q in c.execute(select(questions).where(
                questions.c.inquiry_id==call['inquiry_id'])).mappings()}
            if {a.question_id:a.question_code for a in body.answers}!=expected:
                raise HTTPException(422,'Result must include every requested question with matching ID/code')
            expired=call['deadline']<=self.now()
            if body.callback_at is not None and utc(body.callback_at)<=self.now() and not (expired or call['status']=='timeout'):
                raise HTTPException(422,'Callback time must be in the future')
            if call['outcome'] is not None and call['outcome']!=body.outcome:
                raise HTTPException(409,'Result outcome conflicts with terminal event')
            latest=c.execute(select(func.max(calls.c.attempt_no)).where(calls.c.inquiry_id==call['inquiry_id'])).scalar_one()
            state=c.execute(select(inquiries.c.status).where(inquiries.c.id==call['inquiry_id'])).scalar_one()
            if expired and call['status'] not in ['finished','timeout']:
                c.execute(update(calls).where(calls.c.id==cid).values(status='timeout'))
                if call['attempt_no']==latest and state not in ['completed','failed']:
                    self.fail(c,call['inquiry_id'],'delivery_or_result_timeout')
            applied=not expired and call['attempt_no']==latest and call['status']!='timeout' and state not in ['completed','failed']
            if applied:
                if body.outcome=='answered' and body.disclosure_played is not True:
                    c.execute(update(calls).where(calls.c.id==cid).values(status='finished',outcome=body.outcome))
                    self.fail(c,call['inquiry_id'],'disclosure_missing')
                elif body.outcome=='rejected' and body.rejection_reason=='permanent':
                    # A final refusal can arrive after the event scheduled a retry.
                    self.finish(c,call,body.outcome,permanent=True)
                elif call['status']=='finished':
                    # Failure event already scheduled retry; receiving its report must not move due time.
                    pass
                else:
                    self.finish(c,call,body.outcome,body.callback_at,body.rejection_reason=='permanent',body.callback_requested)
            c.execute(results.insert().values(call_id=cid,result_id=body.result_id,payload_hash=fp,
                payload=payload,received_at=self.now(),applied=applied))
            for a in body.answers:
                c.execute(answers.insert().values(call_id=cid,question_id=a.question_id,asked=a.asked,
                    answered=a.answered,yes_no=a.yes_no,reason=a.reason,detail=a.detail))
            return dict(duplicate=False,applied=applied)
    def expire(self):
        with self.engine.begin() as c:
            self.lock(c)
            rows=c.execute(select(calls).where(calls.c.status.not_in(['finished','timeout']),
                calls.c.deadline<=self.now()).with_for_update()).mappings().all()
            for row in rows:
                c.execute(update(calls).where(calls.c.id==row['id']).values(status='timeout'))
                self.fail(c,row['inquiry_id'],'delivery_or_result_timeout')
            return [r['id'] for r in rows]
    def tick(self,worker):
        expired=self.expire(); reserved=self.reserve(); delivered=self.deliver(worker)
        return dict(expired=expired,reserved=reserved,delivered=delivered)

    def review_callback(self,iid,body,actor):
        with self.engine.begin() as c:
            self.lock(c)
            hold=c.execute(select(review_holds).where(review_holds.c.inquiry_id==iid,
                review_holds.c.open==True)).mappings().first()
            if not hold:raise HTTPException(409,'No open callback review')
            inquiry=c.execute(select(inquiries).where(inquiries.c.id==iid)).mappings().one()
            if inquiry['status']!='retry_wait':raise HTTPException(409,'Inquiry no longer awaiting callback review')
            if body.action=='schedule':
                if utc(body.callback_at)<=self.now():raise HTTPException(422,'Callback must be in the future')
                attempts=c.execute(select(func.count()).select_from(calls).where(calls.c.inquiry_id==iid)).scalar_one()
                if attempts>=self.attempt_limit(c,inquiry['academy_id']):raise HTTPException(409,'Call attempt limit reached')
                c.execute(update(inquiries).where(inquiries.c.id==iid).values(next_at=utc(body.callback_at)))
            else:
                c.execute(update(inquiries).where(inquiries.c.id==iid).values(status='completed'))
            c.execute(update(review_holds).where(review_holds.c.inquiry_id==iid).values(open=False))
            c.execute(review_actions.insert().values(id=uid(),inquiry_id=iid,actor=actor,action=body.action,
                reason=body.reason,payload=body.model_dump(mode='json'),created_at=self.now()))
            return dict(inquiry_id=iid,status='retry_wait' if body.action=='schedule' else 'completed')

    def review_fallback(self,iid,body,actor):
        with self.engine.begin() as c:
            self.lock(c)
            task=c.execute(select(fallback_tasks).where(fallback_tasks.c.inquiry_id==iid)).mappings().first()
            if not task:raise HTTPException(404,'Fallback task not found')
            if task['status']!='needs_review':raise HTTPException(409,'Fallback already reviewed')
            c.execute(update(fallback_tasks).where(fallback_tasks.c.inquiry_id==iid).values(
                status='prepared' if body.action=='prepare' else 'dismissed',message=body.message,
                reviewed_at=self.now(),reviewer=actor,review_reason=body.reason))
            c.execute(review_actions.insert().values(id=uid(),inquiry_id=iid,actor=actor,action='fallback_'+body.action,
                reason=body.reason,payload=body.model_dump(mode='json'),created_at=self.now()))
            return dict(inquiry_id=iid,status='prepared' if body.action=='prepare' else 'dismissed')
    def dry_run_fallback(self,iid):
        with self.engine.begin() as c:
            self.lock(c)
            task=c.execute(select(fallback_tasks).where(fallback_tasks.c.inquiry_id==iid)).mappings().first()
            if not task:raise HTTPException(404,'Fallback task not found')
            if task['status']=='dry_run_complete':return dict(duplicate=True,receipt=task['dry_run_receipt'])
            if task['status']!='prepared':raise HTTPException(409,'Reviewed message required')
            receipt=dict(receipt_id=uid(),channel='mock_notification',sent=False,
                message_sha256=digest(task['message']),inquiry_id=iid)
            c.execute(update(fallback_tasks).where(fallback_tasks.c.inquiry_id==iid).values(
                status='dry_run_complete',dry_run_receipt=receipt))
            return dict(duplicate=False,receipt=receipt)
