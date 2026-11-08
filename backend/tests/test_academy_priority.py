"""Academy settings and the boundaries of academy-local ordering."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from contracts import AcademyPolicyInput, AcademySettingsInput
from schema import academies, accounts, calls, inquiries
from service import academy_windows, utc, waiting_cutoffs
from test_portable_smoke import login, portable


ACADEMY = 'demo-academy'
OTHER_ACADEMY = 'other-academy'
SETTINGS = {
    'classes': [{'grade_code': 'M2', 'subject_code': 'MATH'}],
    'call_hours': [],
}


@pytest.fixture
def priority_setup(portable):
    engine, service, client = portable
    member, auth = login(client)
    with engine.begin() as c:
        c.execute(update(accounts).where(accounts.c.user_id == member['inquirer_id']).values(role='admin'))
        academy = dict(c.execute(select(academies).where(academies.c.id == ACADEMY)).mappings().one())
        academy['id'] = OTHER_ACADEMY
        c.execute(academies.insert().values(**academy))

    def inquire(key, *, academy=ACADEMY, grade='M2', subject='MATH', wait=0, retry_due=None, priority=0):
        response = client.post('/api/inquiries', headers={**auth, 'Idempotency-Key': key}, json={
            'inquirer_id': member['inquirer_id'],
            'academy_id': academy,
            'student': {'grade': grade, 'subject': subject, 'level': 'MID', 'region': academy_region},
            'question_codes': ['shuttle'],
        })
        assert response.status_code == 201, response.text
        inquiry_id = response.json()['inquiry_id']
        created = service.now() - timedelta(minutes=wait)
        values = {'created_at': created, 'next_at': created, 'priority': priority}
        if retry_due is not None:
            values.update(status='retry_wait', next_at=service.now() + timedelta(minutes=retry_due))
        with engine.begin() as c:
            c.execute(update(inquiries).where(inquiries.c.id == inquiry_id).values(**values))
        return inquiry_id

    academy_region = academy['region']
    yield engine, service, client, auth, inquire


def reserved_inquiries(engine, service):
    ids = service.reserve()
    with engine.connect() as c:
        return [c.execute(select(calls.c.inquiry_id).where(calls.c.id == cid)).scalar_one() for cid in ids]


def test_preference_changes_only_academy_order(priority_setup):
    engine, service, _, _, inquire = priority_setup
    service.update_academy_settings(ACADEMY, AcademySettingsInput.model_validate(SETTINGS))
    older = inquire('older', subject='ENG', wait=20)
    other = inquire('other', academy=OTHER_ACADEMY, wait=10)
    preferred = inquire('preferred')
    assert reserved_inquiries(engine, service) == [other, preferred]
    with engine.connect() as c:
        assert c.execute(select(inquiries.c.priority).where(inquiries.c.id == preferred)).scalar_one() == 0
        assert c.execute(select(inquiries.c.status).where(inquiries.c.id == older)).scalar_one() == 'queued'


def test_wait_age_starts_when_retry_becomes_due(priority_setup):
    engine, service, _, _, inquire = priority_setup
    service.update_academy_settings(ACADEMY, AcademySettingsInput.model_validate(SETTINGS))
    overdue = inquire('overdue', grade='H1', subject='ENG', wait=240)
    inquire('just-due', grade='H1', subject='ENG', wait=300, retry_due=0)
    inquire('future', wait=360, retry_due=5)
    preferred = inquire('preferred')
    assert reserved_inquiries(engine, service) == [overdue, preferred]


def test_unconfigured_academy_keeps_priority_and_fifo(priority_setup):
    engine, service, _, _, inquire = priority_setup
    oldest = inquire('oldest', wait=10)
    inquire('later', wait=5)
    explicit = inquire('explicit', priority=10)
    assert reserved_inquiries(engine, service) == [explicit, oldest]


def test_call_hours_and_cooldown_limit_reservations(priority_setup):
    engine, service, _, _, inquire = priority_setup
    # The fixture clock is Monday 14:00 KST.
    settings = {**SETTINGS, 'call_hours': [{'day_of_week': 0, 'start_time': '15:00', 'end_time': '17:00'}]}
    service.update_academy_settings(ACADEMY, AcademySettingsInput.model_validate(settings))
    service.set_academy_policy(ACADEMY, AcademyPolicyInput(
        enabled=True, max_concurrent=2, cooldown_seconds=300, closed_dates=[],
        hours=[{'weekday': 0, 'start_minute': 0, 'end_minute': 1440}],
    ))
    first = inquire('first', wait=10)
    inquire('second')
    assert reserved_inquiries(engine, service) == []
    old = service.clock()
    service.clock = lambda: old + timedelta(hours=1)
    assert reserved_inquiries(engine, service) == [first]
    assert reserved_inquiries(engine, service) == []


def test_unmatched_preference_does_not_block_inquiry(priority_setup):
    engine, service, _, _, inquire = priority_setup
    service.update_academy_settings(ACADEMY, AcademySettingsInput.model_validate(SETTINGS))
    inquiry = inquire('unmatched', grade='H1', subject='ENG')
    assert reserved_inquiries(engine, service) == [inquiry]


def test_overnight_wait_does_not_overtake_preference_at_opening(priority_setup):
    engine, service, _, _, inquire = priority_setup
    settings = {**SETTINGS, 'call_hours': [{'day_of_week': 0, 'start_time': '14:00', 'end_time': '19:00'}]}
    service.update_academy_settings(ACADEMY, AcademySettingsInput.model_validate(settings))
    evening = inquire('evening', grade='H1', subject='ENG', wait=17 * 60)
    preferred = inquire('preferred')
    assert reserved_inquiries(engine, service) == [preferred, evening]


def test_ordinary_waiting_bonus_cannot_beat_one_preference_match(priority_setup):
    engine, service, _, _, inquire = priority_setup
    service.update_academy_settings(ACADEMY, AcademySettingsInput.model_validate(SETTINGS))
    partial = inquire('partial', subject='ENG', wait=239)
    preferred = inquire('preferred')
    assert reserved_inquiries(engine, service) == [preferred, partial]


def test_wait_cutoffs_exclude_closed_dates_and_merge_overlapping_overnight_windows():
    seoul = ZoneInfo('Asia/Seoul')
    sunday = datetime(2026, 10, 4, 20, tzinfo=seoul)
    monday = datetime(2026, 10, 5, 2, tzinfo=seoul)
    academy = {'hours': [{'weekday': 6, 'start_minute': 20 * 60, 'end_minute': 2 * 60}]}
    response = [
        {'day_of_week': 6, 'start_time': time(21), 'end_time': time(2)},
        {'day_of_week': 6, 'start_time': time(22), 'end_time': time(23)},
    ]
    windows = academy_windows(academy, response)
    assert waiting_cutoffs(monday, sunday, windows, set(), (240,))[240] == utc(
        sunday.replace(hour=22))
    assert waiting_cutoffs(monday, sunday, windows, {'2026-10-04'}, (120, 240)) == {
        120: utc(monday.replace(hour=0)),
    }


def test_browser_put_and_invalid_settings(priority_setup):
    _, _, client, auth, _ = priority_setup
    path = f'/api/academies/{ACADEMY}/settings'
    preflight = client.options(path, headers={
        'Origin': 'http://localhost:5173',
        'Access-Control-Request-Method': 'PUT',
        'Access-Control-Request-Headers': 'authorization,content-type',
    })
    assert preflight.status_code == 200
    hour = {'day_of_week': 0, 'start_time': '14:00', 'end_time': '16:00'}
    settings = {**SETTINGS, 'call_hours': [hour]}
    assert client.put(path, headers=auth, json=settings).status_code == 200
    before = client.get(path, headers=auth).json()
    assert set(before) == {'classes', 'call_hours'}
    assert before['classes'][0]['level_code'] is None
    assert 'status' not in before['classes'][0]
    assert before['call_hours'][0]['start_time'] == '14:00:00'
    for invalid in [
        {**settings, 'call_hours': [{**hour, 'start_time': '99:99'}]},
        {**settings, 'call_hours': [{**hour, 'end_time': '14:00'}]},
        {**settings, 'classes': SETTINGS['classes'] * 2},
        {**settings, 'classes': [{**SETTINGS['classes'][0], 'status': 'CLOSED'}]},
    ]:
        assert client.put(path, headers=auth, json=invalid).status_code == 422
        assert client.get(path, headers=auth).json() == before
