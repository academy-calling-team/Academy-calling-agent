"""목업 워커 시험. 실행: python -m pytest voice/mock_worker -q"""
import copy
import json
import re
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app import ReceiptStore, create_app
from fake_backend import create_backend
from samples import SAMPLE_REQUEST, build_events, build_result, pick_scenario
from sender import Sender

KEY = "test-key"
HEADERS = {"X-Internal-Key": KEY}
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")


def make_request(**changes) -> dict:
    request = copy.deepcopy(SAMPLE_REQUEST)
    request.update(changes)
    return request


class FakeBackend:
    """httpx MockTransport용. 받은 요청을 기록하고, 정해 둔 상태 코드를 차례로 돌려준다."""

    def __init__(self, statuses=()):
        self.requests = []
        self.statuses = list(statuses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.url.path, json.loads(request.content), request.headers.get("x-internal-key")))
        status = self.statuses.pop(0) if self.statuses else 200
        return httpx.Response(status, json={"duplicate": False, "applied": status == 200})


def make_sender(backend: FakeBackend) -> Sender:
    return Sender("http://backend.test", KEY, delay_sec=0, retry_wait=0, transport=httpx.MockTransport(backend))


@pytest.fixture
def store(tmp_path):
    return ReceiptStore(tmp_path / "receipts.sqlite3")


@pytest.fixture
def client(store):
    return TestClient(create_app(KEY, store))


# 접수와 조회

def test_rejects_missing_or_wrong_key(client):
    assert client.post("/internal/calls", json=SAMPLE_REQUEST).status_code == 401
    assert client.get("/internal/calls/c_02", headers={"X-Internal-Key": "wrong"}).status_code == 401


def test_accept_is_idempotent_and_survives_restart(tmp_path, client, store):
    first = client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS)
    again = client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS)
    assert (first.status_code, first.json()) == (202, {"call_id": "c_02", "accepted": True, "duplicate": False})
    assert (again.status_code, again.json()["duplicate"]) == (202, True)

    restarted = TestClient(create_app(KEY, ReceiptStore(store.path)))
    reply = restarted.get("/internal/calls/c_02", headers=HEADERS)
    assert (reply.status_code, reply.json()) == (200, {"call_id": "c_02", "accepted": True})


def test_unknown_call_is_404(client):
    assert client.get("/internal/calls/nothing", headers=HEADERS).status_code == 404


def test_same_call_id_with_other_payload_conflicts(client):
    client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS)
    assert client.post("/internal/calls", json=make_request(attempt_no=3), headers=HEADERS).status_code == 409


@pytest.mark.parametrize("request_body", [
    make_request(is_mock=False),
    make_request(questions=[{"question_id": "q1", "question_code": "shuttle"},
                            {"question_id": "q1", "question_code": "pickup"}]),
    make_request(questions=[{"question_id": "q1", "question_code": "tuition"}]),
    make_request(extra_field=1),
    make_request(attempt_no="2"),
], ids=["not-mock", "duplicate-question-id", "unknown-code", "unknown-field", "string-number"])
def test_rejects_invalid_requests(client, request_body):
    assert client.post("/internal/calls", json=request_body, headers=HEADERS).status_code == 422


# 가짜 결과가 백엔드 규칙(ResultInput)에 맞는지

def assert_backend_rules(request: dict, result: dict) -> None:
    requested = {q["question_id"]: q["question_code"] for q in request["questions"]}
    assert {a["question_id"]: a["question_code"] for a in result["answers"]} == requested
    for answer in result["answers"]:
        if answer["answered"]:
            assert answer["asked"] and answer["reason"] is None and answer["detail"].strip()
            assert (answer["yes_no"] is None) == (answer["question_code"] == "class_time")
        else:
            assert answer["yes_no"] is None and answer["reason"] is not None
            assert (not answer["asked"]) == (answer["reason"] == "not_asked")
    assert result["unresolved"] == [a["question_id"] for a in result["answers"] if not a["answered"]]
    if result["available_times"]:
        assert result["consult_accepted"] is True
    if result["outcome"] == "answered":
        assert result["disclosure_played"] is True
    else:
        assert result["disclosure_played"] is None and result["consult_accepted"] is None
        assert result["available_times"] == [] and result["latency"] is None and result["transcript"] == []
        assert not any(a["asked"] for a in result["answers"])
    assert ID_PATTERN.fullmatch(result["result_id"])


ALL_CODES = make_request(questions=[
    {"question_id": f"q{n}", "question_code": code}
    for n, code in enumerate(["shuttle", "pickup", "level_fit", "vacancy", "level_test", "class_time"], 1)
])


@pytest.mark.parametrize("scenario", ["answered", "partial", "no_answer"])
@pytest.mark.parametrize("request_body", [SAMPLE_REQUEST, ALL_CODES], ids=["3-questions", "all-codes"])
def test_results_follow_backend_rules(scenario, request_body):
    result = build_result(request_body, scenario)
    assert_backend_rules(request_body, result)
    assert result == build_result(request_body, scenario)


def test_partial_leaves_only_last_question_unresolved():
    assert build_result(SAMPLE_REQUEST, "partial")["unresolved"] == ["q3"]


@pytest.mark.parametrize("scenario,last", [("answered", "completed"), ("no_answer", "no_answer")])
def test_events_are_ordered_with_timezone(scenario, last):
    events = build_events("c_02", scenario, datetime.fromisoformat("2026-10-12T05:00:00+00:00"))
    times = [datetime.fromisoformat(e["occurred_at"]) for e in events]
    assert events[-1]["type"] == last
    assert times == sorted(times) and all(t.tzinfo for t in times)
    assert all(ID_PATTERN.fullmatch(e["event_id"]) for e in events)


def test_retry_mode_misses_first_attempt_only():
    assert pick_scenario("retry", 1) == "no_answer"
    assert pick_scenario("retry", 2) == "answered"
    with pytest.raises(ValueError):
        pick_scenario("unknown", 1)


# 백엔드로 보내기

def test_accept_sends_events_then_result(store):
    backend = FakeBackend()
    client = TestClient(create_app(KEY, store, make_sender(backend)))
    assert client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS).status_code == 202

    paths = [path for path, _, _ in backend.requests]
    assert paths == ["/internal/calls/c_02/events"] * 4 + ["/internal/calls/c_02/result"]
    assert [body["type"] for _, body, _ in backend.requests[:4]] == ["initiated", "ringing", "answered", "completed"]
    assert all(key == KEY for _, _, key in backend.requests)
    assert store.pending() == []


def test_duplicate_accept_does_not_send_again(store):
    backend = FakeBackend()
    client = TestClient(create_app(KEY, store, make_sender(backend)))
    client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS)
    client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS)
    assert len(backend.requests) == 5


def test_resend_uses_same_ids_and_bodies(store):
    store.accept("c_02", SAMPLE_REQUEST, "answered")
    first, second = FakeBackend(), FakeBackend()
    make_sender(first).deliver(store, "c_02")
    make_sender(second).deliver(store, "c_02")
    assert first.requests == second.requests


def test_retries_temporary_errors(store):
    store.accept("c_02", SAMPLE_REQUEST, "answered")
    backend = FakeBackend(statuses=[503, 200])
    assert make_sender(backend).deliver(store, "c_02") is True
    assert len(backend.requests) == 6
    assert store.pending() == []


def test_stops_on_rejection_and_keeps_pending(store):
    store.accept("c_02", SAMPLE_REQUEST, "answered")
    backend = FakeBackend(statuses=[409])
    assert make_sender(backend).deliver(store, "c_02") is False
    assert len(backend.requests) == 1
    assert store.pending() == ["c_02"]


def test_deliver_pending_sends_unsent_receipts(store):
    store.accept("c_02", SAMPLE_REQUEST, "no_answer")
    backend = FakeBackend()
    make_sender(backend).deliver_pending(store)
    result = backend.requests[-1][1]
    assert result["outcome"] == "no_answer"
    assert store.pending() == []


# 가짜 백엔드

def test_fake_backend_applies_duplicate_and_conflict_rules():
    backend = TestClient(create_backend(KEY))
    event = build_events("c_02", "answered", datetime.fromisoformat("2026-10-12T05:00:00+00:00"))[0]
    url = "/internal/calls/c_02/events"
    assert backend.post(url, json=event).status_code == 401
    assert backend.post(url, json=event, headers=HEADERS).json()["duplicate"] is False
    assert backend.post(url, json=event, headers=HEADERS).json()["duplicate"] is True
    assert backend.post(url, json={**event, "type": "ringing"}, headers=HEADERS).status_code == 409
