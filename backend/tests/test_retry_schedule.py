"""Retry timing on an isolated SQLite database; no telephone or external service."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select

from contracts import EventInput, InquiryInput, ResultInput
from schema import academies, calls, inquiries, users
from service import Policy, Service, digest
from worker import make_result


@pytest.fixture
def schedule(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'retry.sqlite'))
    clock = [datetime(2026, 10, 5, 5, tzinfo=timezone.utc)]
    service = Service(engine, clock=lambda: clock[0])
    service.initialize()
    with engine.begin() as c:
        c.execute(users.insert().values(id='owner', token_hash=digest('test-token')))
        c.execute(academies.insert().values(id='academy', name='synthetic',
            region='대구 북구 침산동', phone=None, is_mock=True,
            hours=[dict(weekday=i, start_minute=0, end_minute=1440) for i in range(7)]))
    inquiry = service.create(InquiryInput(inquirer_id='owner', academy_id='academy',
        student=dict(grade='M2', subject='MATH', level='MID', region='대구 북구 침산동'),
        question_codes=['shuttle']), 'test-token', 'request')['inquiry_id']
    yield service, engine, clock, inquiry
    engine.dispose()


def dispatch_payload(engine, cid):
    with engine.connect() as c:
        return c.execute(select(calls.c.dispatch_payload).where(calls.c.id == cid)).scalar_one()


@pytest.mark.parametrize('outcome', ['no_answer', 'busy', 'machine', 'rejected'])
def test_retry_5_10_30_minutes_not_before_due_and_stops_at_limit(schedule, outcome):
    service, engine, clock, iid = schedule
    cid = service.reserve()[0]
    for attempt_no, delay in enumerate((300, 600, 1800), start=1):
        failed_at = clock[0]
        service.event(cid, EventInput(event_id=f'event_{attempt_no}', type=outcome, occurred_at=failed_at))
        with engine.connect() as c:
            due = c.execute(select(inquiries.c.next_at).where(inquiries.c.id == iid)).scalar_one()
        assert due == (failed_at + timedelta(seconds=delay)).replace(tzinfo=None)
        # A late copy of the same failure report cannot postpone the retry.
        clock[0] += timedelta(seconds=1)
        service.result(cid, ResultInput.model_validate(make_result(dispatch_payload(engine, cid), outcome)))
        with engine.connect() as c:
            assert c.execute(select(inquiries.c.next_at).where(inquiries.c.id == iid)).scalar_one() == due
        clock[0] = failed_at + timedelta(seconds=delay-1)
        assert service.reserve() == []
        clock[0] += timedelta(seconds=1)
        cid = service.reserve()[0]
        assert dispatch_payload(engine, cid)['attempt_no'] == attempt_no + 1
    service.event(cid, EventInput(event_id='final_failure', type=outcome, occurred_at=clock[0]))
    assert service.reserve() == []
    with engine.connect() as c:
        row = c.execute(select(inquiries).where(inquiries.c.id == iid)).mappings().one()
        assert row['status'] == 'failed'
        assert row['fallback_required'] is (outcome != 'rejected')
        assert len(c.execute(select(calls).where(calls.c.inquiry_id == iid)).all()) == 4


def test_explicit_callback_time_takes_precedence_over_retry_delay(schedule):
    service, engine, clock, iid = schedule
    cid = service.reserve()[0]
    callback_at = clock[0] + timedelta(minutes=17)
    body = make_result(dispatch_payload(engine, cid))
    body.update(callback_requested=True, callback_at=callback_at.isoformat())
    service.result(cid, ResultInput.model_validate(body))
    with engine.connect() as c:
        assert c.execute(select(inquiries.c.next_at).where(inquiries.c.id == iid)).scalar_one() == callback_at.replace(tzinfo=None)
    clock[0] = callback_at - timedelta(seconds=1)
    assert service.reserve() == []
    clock[0] = callback_at
    assert len(service.reserve()) == 1


@pytest.mark.parametrize('outcome', ['invalid_number'])
def test_non_retryable_outcomes_do_not_schedule_a_call(schedule, outcome):
    service, engine, clock, iid = schedule
    cid = service.reserve()[0]
    service.event(cid, EventInput(event_id='terminal_event', type=outcome, occurred_at=clock[0]))
    clock[0] += timedelta(hours=1)
    assert service.reserve() == []
    with engine.connect() as c:
        assert c.execute(select(inquiries.c.status).where(inquiries.c.id == iid)).scalar_one() == 'failed'


@pytest.mark.parametrize('event_first', [False, True])
@pytest.mark.parametrize('reason', [None, 'unknown', 'temporary', 'permanent'])
def test_rejection_result_retries_unless_explicit_permanent_refusal(schedule, event_first, reason):
    service, engine, clock, iid = schedule
    cid = service.reserve()[0]
    if event_first:
        service.event(cid, EventInput(event_id='declined', type='rejected', occurred_at=clock[0]))
    body = make_result(dispatch_payload(engine, cid), 'rejected')
    if reason is not None:
        body['rejection_reason'] = reason
    result = ResultInput.model_validate(body)
    assert service.result(cid, result)['applied'] is True
    assert service.result(cid, result)['duplicate'] is True
    with engine.connect() as c:
        row = c.execute(select(inquiries).where(inquiries.c.id == iid)).mappings().one()
        assert row['status'] == ('failed' if reason == 'permanent' else 'retry_wait')
        assert row['fallback_required'] is False
    clock[0] += timedelta(seconds=300)
    assert len(service.reserve()) == (0 if reason == 'permanent' else 1)


def test_old_permanent_rejection_result_does_not_cancel_new_attempt(schedule):
    service, engine, clock, iid = schedule
    first = service.reserve()[0]
    service.event(first, EventInput(event_id='declined', type='rejected', occurred_at=clock[0]))
    clock[0] += timedelta(seconds=300)
    second = service.reserve()[0]
    body = make_result(dispatch_payload(engine, first), 'rejected')
    body['rejection_reason'] = 'permanent'
    assert service.result(first, ResultInput.model_validate(body))['applied'] is False
    with engine.connect() as c:
        assert c.execute(select(inquiries.c.status).where(inquiries.c.id == iid)).scalar_one() == 'calling'
        assert c.execute(select(calls.c.status).where(calls.c.id == second)).scalar_one() == 'reserved'


@pytest.mark.parametrize('delays', [(), (0,), (-1, 300)])
def test_retry_delays_must_be_positive(delays):
    with pytest.raises(ValueError, match='Retry delays'):
        Policy(retry_delays_seconds=delays)
