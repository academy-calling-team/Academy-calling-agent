"""Worker result compatibility and per-question source excerpts."""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from contracts import ResultInput
from schema import accounts, answers, calls, results
from service import fingerprint
from test_portable_smoke import login, portable
from worker import make_result


INTERNAL = {'X-Internal-Key': 'synthetic-test-key'}


@pytest.fixture
def reserved(portable):
    engine, service, client = portable
    user, auth = login(client)
    request = {
        'inquirer_id': user['inquirer_id'],
        'academy_id': 'demo-academy',
        'student': {'grade': 'M2', 'subject': 'MATH', 'level': 'MID', 'region': '\ub300\uad6c \ubd81\uad6c \uce68\uc0b0\ub3d9'},
        'question_codes': ['shuttle', 'vacancy'],
    }
    reply = client.post('/api/inquiries', json=request,
                        headers={**auth, 'Idempotency-Key': str(uuid4())})
    assert reply.status_code == 201, reply.text
    inquiry_id = reply.json()['inquiry_id']
    call_id = service.reserve()[0]
    with engine.connect() as c:
        dispatch = c.execute(select(calls.c.dispatch_payload).where(calls.c.id == call_id)).scalar_one()
    return engine, client, user, auth, inquiry_id, call_id, make_result(dispatch, unanswered=['vacancy'])


def test_uncertain_source_saved_and_visible_to_owner(reserved):
    engine, client, user, auth, inquiry_id, call_id, result = reserved
    answer = result['answers'][1]
    excerpt = '\uc544\ub9c8 \uc790\ub9ac\uac00 \uc788\uc744 \uac70\uc608\uc694.'
    answer.update(reason='uncertain', source_text=excerpt)
    url = f'/internal/calls/{call_id}/result'
    first = client.post(url, headers=INTERNAL, json=result)
    assert first.status_code == 200, first.text
    assert first.json() == {'duplicate': False, 'applied': True}
    replay = client.post(url, headers=INTERNAL, json=result)
    assert replay.json() == {'duplicate': True, 'applied': True}
    with engine.connect() as c:
        stored = c.execute(select(answers).where(answers.c.call_id == call_id,
            answers.c.question_id == answer['question_id'])).mappings().one()
        assert stored['source_text'] == excerpt and stored['reason'] == 'uncertain'
    view_url = f'/api/inquiries/{inquiry_id}'
    view = client.get(view_url, headers=auth).json()['result']
    assert view['answers'][1]['source_text'] == excerpt
    assert view['answers'][1]['reason'] == 'uncertain'
    assert 'source_text' not in view['answers'][0]
    assert 'transcript' not in view
    _, other = login(client)
    assert client.get(view_url, headers=other).status_code == 404

    altered = deepcopy(result)
    altered['answers'][1]['source_text'] += '!'
    assert client.post(url, headers=INTERNAL, json=altered).status_code == 409

    # A legacy reviewer can correct the summary without accidentally dropping the excerpt.
    with engine.begin() as c:
        c.execute(update(accounts).where(accounts.c.user_id == user['inquirer_id']).values(role='admin'))
    result['answers'][1].pop('source_text')
    result['summary_text'] = 'Reviewed summary'
    correction = client.post(f'/ops/calls/{call_id}/corrections', headers=auth,
        json={'base_revision': 0, 'reviewer': 'test', 'reason': 'summary correction', 'payload': result})
    assert correction.status_code == 200, correction.text
    assert client.get(view_url, headers=auth).json()['result']['answers'][1]['source_text'] == excerpt


def test_legacy_payload_hash_and_null_source_replay(reserved):
    engine, client, _, _, _, call_id, result = reserved
    old_payload = ResultInput.model_validate(result).model_dump(mode='json',
        exclude={'answers': {'__all__': {'source_text'}}})
    url = f'/internal/calls/{call_id}/result'
    assert client.post(url, headers=INTERNAL, json=result).status_code == 200
    with engine.connect() as c:
        stored = c.execute(select(results).where(results.c.call_id == call_id)).mappings().one()
        assert stored['payload_hash'] == fingerprint(old_payload)
        assert stored['payload'] == old_payload
        assert all(source is None for source in c.execute(
            select(answers.c.source_text).where(answers.c.call_id == call_id)).scalars())
    result['answers'][0]['source_text'] = None
    assert client.post(url, headers=INTERNAL, json=result).json() == {'duplicate': True, 'applied': True}


@pytest.mark.parametrize('change', [
    {'reason': 'uncertain', 'asked': False},
    {'reason': 'uncertain', 'yes_no': True},
    {'asked': False, 'reason': 'not_asked', 'source_text': 'excerpt'},
    {'source_text': ' '},
])
def test_invalid_uncertain_or_excerpt_is_rejected(reserved, change):
    _, client, _, _, _, call_id, result = reserved
    result['answers'][1].update(change)
    response = client.post(f'/internal/calls/{call_id}/result', headers=INTERNAL, json=result)
    assert response.status_code == 422, response.text
