"""실제 음성 워커 시험. 전화는 걸지 않는다 (ClawOps와 백엔드를 가짜로 바꿈).

실행: python -m pytest voice/call_worker -q
"""
import copy
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mock_worker"))

from app import ReceiptStore  # noqa: E402  (mock_worker)
from samples import SAMPLE_REQUEST  # noqa: E402
from sender import Sender  # noqa: E402

from clawops import ClawOps, ClawOpsConfig  # noqa: E402
from extract import build_answers, find_reply, judge, to_turns  # noqa: E402
from real_call import ProviderCalls, RealCalls, build_instruction, build_result  # noqa: E402
from worker import create_app, resume_pending  # noqa: E402

KEY = "test-key"
HEADERS = {"X-Internal-Key": KEY}
TEAM_PHONE = "010-1234-5678"
SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "docs/api/result_json_schema.json").read_text(encoding="utf-8"))

# 10/13 통화 말투를 본뜬 전사. 받아쓰기에서 "자리"가 "자"로 적힌 것도 그대로 둔다
SEGMENTS = [
    {"speaker": "speaker_0", "start": 0.9, "end": 1.5, "text": "네 여보세요"},
    {"speaker": "speaker_1", "start": 3.4, "end": 8.8, "text": "안녕하세요 학부모님을 대신해 문의드리는 AI 상담원입니다. 이 통화는 녹음됩니다."},
    {"speaker": "speaker_0", "start": 9.5, "end": 10.4, "text": "네 말씀하세요"},
    {"speaker": "speaker_1", "start": 11.9, "end": 14.8, "text": "통학 차량을 운행하시나요?"},
    {"speaker": "speaker_0", "start": 16.0, "end": 18.2, "text": "네 침산동 쪽으로 다녀요"},
    {"speaker": "speaker_1", "start": 19.7, "end": 23.0, "text": "중2 수학반에 지금 등록할 자가 있을까요?"},
    {"speaker": "speaker_0", "start": 24.2, "end": 25.6, "text": "두 자리 남았어요"},
    {"speaker": "speaker_1", "start": 27.1, "end": 29.9, "text": "이번 주에 학부모 상담이 가능할까요?"},
    {"speaker": "speaker_0", "start": 31.0, "end": 33.5, "text": "수요일 오후 3시에 돼요"},
    {"speaker": "speaker_1", "start": 35.0, "end": 44.0, "text": "정리하면 차량 운행하고 자리는 두 자리 남았습니다. 감사합니다."},
]


# 10/19 단독 실통화(서비스 에이전트, 질문: 통학 차량·픽업·수업 시간)에서 받은 ClawOps 전사 그대로.
# 대본은 "픽업은 안 해요"였지만 실제로는 "안 합니다"라고 말했고, AI의 통학 차량 질문에 "시간이"가 들어 있다
REAL_1019 = [
    {"speaker": "speaker_0", "start": 1.66, "text": "네, 여보세요?"},
    {"speaker": "speaker_1", "start": 3.56, "text": "안녕하세요. 학부모님을 대신해 문의 드리는 AI 상담원입니다. 이 통화는 녹음됩니다. 잠시 통화 괜찮으실까요?"},
    {"speaker": "speaker_0", "start": 13.04, "text": "네, 가능합니다."},
    {"speaker": "speaker_1", "start": 15.30, "text": "감사합니다. 통학차량이 있는지, 있다면 운행 지역과 시간이 어떻게 되는지 여쭤봐도 될까 요?"},
    {"speaker": "speaker_0", "start": 22.90, "text": "네, 침산동 쪽으로 다녀요."},
    {"speaker": "speaker_1", "start": 26.42, "text": "침산동 쪽으로 운행하는 거죠? 운행  시간대도 알려주실 수 있을까요?"},
    {"speaker": "speaker_0", "start": 34.34, "text": "운행은 시, 수업 시간 전후로 10분 정도입니다."},
    {"speaker": "speaker_1", "start": 38.98, "text": "수업 시간 전후로 10분 정도 운행하는 거로 이해했습니다. 그럼 수업 후 픽업도 해주시나요?"},
    {"speaker": "speaker_0", "start": 45.86, "text": "픽업은 안 합니다."},
    {"speaker": "speaker_1", "start": 48.32, "text": "네, 수업 후 픽업은 하지 않으시는 거 맞죠? 중2 수학 수업 요일과 시간은 어떻게 되나요?"},
    {"speaker": "speaker_0", "start": 55.80, "text": "화, 목 저녁 7시요."},
    {"speaker": "speaker_1", "start": 58.96, "text": "화요일과 목요일 저녁 7시가 맞을까요? 그리고 이번 주에 학부모 상담이 가능한지, 가능하 다면 요일과 시간도 알려주실 수 있을까요?"},
    {"speaker": "speaker_0", "start": 69.46, "text": "수요일 3시에 오세요."},
    {"speaker": "speaker_1", "start": 72.52, "text": "네, 수요일 오후 3시에 가능하신 거죠? 그럼 정리해서 말씀드리겠습니다. 통학차량은 침산 동 쪽으로 수업 시간 전후 10분 정도 운행하고요. 수 업 후 픽업은 하지 않습니다. 수업은 화요일과 목요일 저녁 7시이며, 학부모 상담은 이번 주 수요일 오후 3시에 가능합니다. 맞으시면 이대로 학부모님께 전해드리겠습니다. 확인해 주셔서 감사합니다. 좋은 하루 보내세요."},
]


# 10/19 공동 시험의 다른 한 통 전사(ClawOps 화면 그대로). 학원이 픽업을 "합니다"라고 했다가 되짚기에 "아니요, 안 해요"로
# 고쳤고, AI가 "수업 요일과..."를 말하다 끊기고 픽업을 다시 되짚어 "네, 맞습니다"가 수업 시간 질문 바로 뒤에 왔다.
# 첫인사도 "상담 가능하신가요?"로 끝나 상담 질문처럼 보인다
REAL_1019_RECONFIRM = [
    {"speaker": "speaker_0", "start": 1, "text": "네, 여보세요."},
    {"speaker": "speaker_1", "start": 3, "text": "안녕하세요. 학부모님을 대신해 문의드리는 AI 상담원입니다. 개발용 예시로 AI가 진행하는 녹음 통화입니다. 상담 가능하신가요?"},
    {"speaker": "speaker_0", "start": 14, "text": "네, 가능합니다."},
    {"speaker": "speaker_1", "start": 16, "text": "네, 통학 차량이 있는지 궁금합니다. 있다면 운행 지역과 시간도 알려주실 수 있을까요?"},
    {"speaker": "speaker_0", "start": 25, "text": "네, 침산동 쪽으로 다니고 수업 전후로 20분 있습니다."},
    {"speaker": "speaker_1", "start": 30, "text": "네, 침산동 쪽으로 다니고 수업 전후 20분 운행이 있다는 말씀이시죠?"},
    {"speaker": "speaker_0", "start": 36, "text": "네, 맞습니다."},
    {"speaker": "speaker_1", "start": 36, "text": "그럼 수업 후 픽업도..."},
    {"speaker": "speaker_1", "start": 39, "text": "네, 그럼 수업 후 픽업도 해주시는지요?"},
    {"speaker": "speaker_0", "start": 43, "text": "네, 픽업합니다."},
    {"speaker": "speaker_1", "start": 46, "text": "네, 수업 후에 픽업도 해주신다는 거죠?"},
    {"speaker": "speaker_0", "start": 49, "text": "아니요, 픽업은 안 해요."},
    {"speaker": "speaker_1", "start": 50, "text": "수업 요일과..."},
    {"speaker": "speaker_1", "start": 53, "text": "아, 픽업은 안 하신다는 말씀이시죠?"},
    {"speaker": "speaker_0", "start": 56, "text": "네, 맞습니다."},
    {"speaker": "speaker_1", "start": 56, "text": "그럼 수업 요일과 시간은 어떻게 되나요?"},
    {"speaker": "speaker_0", "start": 61, "text": "화, 목 저녁 7시요."},
    {"speaker": "speaker_1", "start": 64, "text": "화요일과 목요일 저녁 7시 맞으실까요?"},
    {"speaker": "speaker_0", "start": 68, "text": "네, 맞습니다."},
    {"speaker": "speaker_1", "start": 70, "text": "네, 이번 주에 학부모 상담이 가능하신지요? 가능하다면 요일과 시간도 알려주실 수 있을까요?"},
    {"speaker": "speaker_0", "start": 78, "text": "수요일 3시에 오세요."},
    {"speaker": "speaker_1", "start": 81, "text": "네, 수요일 오후 3시에 오면 된다는 거죠? 정리해보면 통학 차량은 침산동 쪽으로 수업 전후 20분 운행이 있고, 수업 후 픽업은 하지 않으시며, 수업은 화요일과 목요일 저녁 7시입니다. 그리고 이번 주 학부모 상담은 수요일 오후 3시에 가능합니다. 맞으시면 이대로 학부모님께 전해드리겠습니다. 확인해 주셔서 감사합니다. 좋은 하루 보내세요."},
]


class FakeClawOps:
    """httpx MockTransport용 ClawOps. 상태를 차례로 돌려주고, 받은 요청을 기록한다."""

    def __init__(self, statuses, segments=SEGMENTS, answered_by=None, transcript_first="not_requested"):
        self.statuses = list(statuses)
        self.segments = segments
        self.answered_by = answered_by
        self.transcript_states = [transcript_first, "completed"] if transcript_first else ["completed"]
        self.created = []
        self.transcript_requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        if method == "POST" and path.endswith("/calls"):
            body = json.loads(request.content)
            # 실제 명세처럼 Variables 값은 문자열·숫자·참거짓만 받는다
            if any(not isinstance(v, (str, int, float, bool)) for v in body["CallContext"].get("Variables", {}).values()):
                return httpx.Response(400, json={"code": "validation_error", "error": "Variables values must be scalar"})
            self.created.append(body)
            return httpx.Response(201, json={"callId": "CA_test_1", "status": "queued"})
        if method == "POST" and path.endswith("/transcript"):
            self.transcript_requests += 1
            return httpx.Response(202, json={"status": "pending", "callId": "CA_test_1"})
        if path.endswith("/transcript"):
            state = self.transcript_states.pop(0) if len(self.transcript_states) > 1 else self.transcript_states[0]
            body = {"status": state}
            if state == "completed":
                body.update(callId="CA_test_1", segmentCount=len(self.segments), segments=self.segments)
            return httpx.Response(200, json=body)
        if path.endswith("/summary"):
            return httpx.Response(200, json={"status": "completed", "resultJson": {"coreSummary": "차량 운행, 두 자리 남음"}})
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return httpx.Response(200, json={"callId": "CA_test_1", "status": status, "duration": 44,
                                         "answeredBy": self.answered_by})


class FakeBackend:
    """실제 백엔드처럼 같은 event_id에 같은 본문은 중복(200), 다른 본문은 409로 거절한다."""

    def __init__(self):
        self.requests = []
        self.event_bodies = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body))
        if request.url.path.endswith("/events"):
            seen = self.event_bodies.setdefault(body["event_id"], body)
            if seen != body:
                return httpx.Response(409, json={"detail": "event_id reused with different body"})
            return httpx.Response(200, json={"duplicate": seen is not body, "applied": True})
        return httpx.Response(200, json={"duplicate": False, "applied": True})

    def events(self):
        return [body["type"] for path, body in self.requests if path.endswith("/events")]

    def result(self):
        return next(body for path, body in self.requests if path.endswith("/result"))


def real_request(**changes) -> dict:
    request = copy.deepcopy(SAMPLE_REQUEST)
    request.update(is_mock=False, to=TEAM_PHONE, call_id="c_real_1", questions=[
        {"question_id": "q1", "question_code": "shuttle"},
        {"question_id": "q2", "question_code": "vacancy"},
        {"question_id": "q3", "question_code": "pickup"},
    ])
    request.update(changes)
    return request


@pytest.fixture
def parts(tmp_path):
    def make(clawops: FakeClawOps, real_enabled=True):
        backend = FakeBackend()
        store = ReceiptStore(tmp_path / "receipts.sqlite3")
        sender = Sender("http://backend.test", KEY, delay_sec=0, retry_wait=0, transport=httpx.MockTransport(backend))
        provider_calls = ProviderCalls(tmp_path / "receipts.sqlite3")
        client = ClawOps(ClawOpsConfig("k", "acc", "agent", "07000000000"), transport=httpx.MockTransport(clawops))
        real = RealCalls(client, provider_calls, sender._post, sleep=lambda s: None) if real_enabled else None
        app = create_app(KEY, store, sender, real=real, allowed_to=frozenset({"01012345678"}))
        return TestClient(app), backend, store, real, provider_calls
    return make


def check_schema(result: dict) -> None:
    assert set(SCHEMA["required"]) <= set(result)
    assert set(result) <= set(SCHEMA["properties"])
    assert result["outcome"] in SCHEMA["properties"]["outcome"]["enum"]
    assert set(result["unresolved"]) == {a["question_id"] for a in result["answers"] if not a["answered"]}
    for a in result["answers"]:
        assert a["answered"] or a["reason"] in ("unknown", "refused", "not_asked", "uncertain")


# 목업 요청은 지금처럼

def test_mock_request_still_gets_mock_result(parts):
    client, backend, *_ = parts(FakeClawOps(["completed"]), real_enabled=False)
    assert client.post("/internal/calls", json=SAMPLE_REQUEST, headers=HEADERS).status_code == 202
    assert backend.events() == ["initiated", "ringing", "answered", "completed"]
    assert backend.result()["notes"].startswith("목업")


# 실제 발신을 막는 장치

def test_real_request_refused_when_disabled(parts):
    clawops = FakeClawOps(["completed"])
    client, *_ = parts(clawops, real_enabled=False)
    assert client.post("/internal/calls", json=real_request(), headers=HEADERS).status_code == 422
    assert clawops.created == []


def test_real_request_refused_for_number_not_on_allow_list(parts):
    clawops = FakeClawOps(["completed"])
    client, *_ = parts(clawops)
    reply = client.post("/internal/calls", json=real_request(to="0531234567"), headers=HEADERS)
    assert reply.status_code == 422
    assert clawops.created == []


# 실제 통화 흐름

def test_answered_call_sends_events_then_result(parts):
    clawops = FakeClawOps(["queued", "ringing", "in-progress", "in-progress", "completed"])
    client, backend, store, *_ = parts(clawops)
    assert client.post("/internal/calls", json=real_request(), headers=HEADERS).status_code == 202

    sent = clawops.created[0]
    assert sent["To"] == TEAM_PHONE and sent["AgentId"] == "agent" and sent["MachineDetection"] == "Enable"
    assert "등원 차량" in sent["CallContext"]["Instruction"]
    assert "셔틀" not in sent["CallContext"]["Instruction"] and "픽업" not in sent["CallContext"]["Instruction"]
    assert clawops.transcript_requests == 1  # 받아쓰기가 꺼져 있으면 이 통화만 요청
    assert backend.events() == ["initiated", "ringing", "answered", "completed"]

    result = backend.result()
    check_schema(result)
    assert result["outcome"] == "answered" and result["duration_sec"] == 44
    assert result["disclosure_played"] is True
    assert result["summary_text"] == "차량 운행, 두 자리 남음"
    assert {t["speaker"] for t in result["transcript"]} == {"agent", "academy"}
    by_code = {a["question_code"]: a for a in result["answers"]}
    assert by_code["shuttle"]["asked"] and by_code["shuttle"]["detail"] == "네 침산동 쪽으로 다녀요"
    assert by_code["vacancy"]["asked"] and by_code["vacancy"]["detail"] == "두 자리 남았어요"
    assert by_code["pickup"] == {"question_id": "q3", "question_code": "pickup", "asked": False, "answered": False,
                                 "yes_no": None, "reason": "not_asked", "detail": "통화에서 이 질문을 확인하지 못함"}
    # 상담은 첫인사의 'AI 상담원'이 아니라 실제 상담 질문 뒤의 대답에서 뽑는다
    assert result["consult_accepted"] is True
    assert result["available_times"] == ["수요일 오후 3시에 돼요"]
    assert store.pending() == []


def test_no_answer_call_has_no_conversation_fields(parts):
    clawops = FakeClawOps(["queued", "ringing", "no-answer"])
    client, backend, *_ = parts(clawops)
    client.post("/internal/calls", json=real_request(), headers=HEADERS)
    assert backend.events() == ["initiated", "ringing", "no_answer"]
    result = backend.result()
    check_schema(result)
    assert result["outcome"] == "no_answer"
    assert result["disclosure_played"] is None and result["transcript"] == [] and result["duration_sec"] == 0
    assert all(a["reason"] == "not_asked" for a in result["answers"])


def test_voicemail_is_reported_as_machine(parts):
    clawops = FakeClawOps(["queued", "in-progress", "completed"], answered_by="machine")
    client, backend, *_ = parts(clawops)
    client.post("/internal/calls", json=real_request(), headers=HEADERS)
    assert "machine" in backend.events()
    assert backend.result()["outcome"] == "machine"


@pytest.mark.parametrize('source', ['callee', 'app', 'system', 'carrier', None])
def test_decline_button_is_not_classified_as_permanent_refusal(source):
    result = build_result('decline', real_request(),
        dict(status='rejected', hangupSource=source), None, [])
    check_schema(result)
    assert result['outcome'] == 'rejected'
    assert result['rejection_reason'] == 'unknown'
    assert result['transcript'] == [] and result['disclosure_played'] is None


def test_declined_call_sends_event_and_retryable_result(parts):
    client, backend, store, *_ = parts(FakeClawOps(['queued', 'ringing', 'rejected']))
    assert client.post('/internal/calls', json=real_request(), headers=HEADERS).status_code == 202
    assert backend.events() == ['initiated', 'ringing', 'rejected']
    assert backend.result()['rejection_reason'] == 'unknown'
    assert store.pending() == []


def test_same_call_id_never_dials_twice(parts):
    clawops = FakeClawOps(["completed"])
    client, *_ = parts(clawops)
    client.post("/internal/calls", json=real_request(), headers=HEADERS)
    again = client.post("/internal/calls", json=real_request(), headers=HEADERS)
    assert again.status_code == 202 and again.json()["duplicate"] is True
    assert len(clawops.created) == 1


# 재시작

def test_restart_without_provider_id_does_not_redial(parts):
    clawops = FakeClawOps(["completed"])
    _, backend, store, real, provider_calls = parts(clawops)
    store.accept("c_lost", real_request(call_id="c_lost"), "real")
    resume_pending(store, Sender("http://backend.test", KEY, delay_sec=0), real, provider_calls)
    assert clawops.created == []
    assert "c_lost" in store.rejected()


def test_restart_resends_same_event_bodies_without_409(parts):
    """재시작 전에 initiated·ringing을 보냈던 통화: 같은 ID·같은 본문으로 다시 보내고 이어서 끝까지 간다."""
    clawops = FakeClawOps(["in-progress", "completed"])
    _, backend, store, real, provider_calls = parts(clawops)
    store.accept("c_resume", real_request(call_id="c_resume"), "real")
    provider_calls.save("c_resume", "CA_test_1")
    for kind in ("initiated", "ringing"):  # 재시작 전 워커가 보낸 이벤트
        assert real._event(store, "c_resume", kind)
    resume_pending(store, Sender("http://backend.test", KEY, delay_sec=0), real, provider_calls)
    assert "c_resume" not in store.rejected()
    assert backend.events() == ["initiated", "ringing", "initiated", "ringing", "answered", "completed"]
    assert len(backend.event_bodies) == 4  # 다시 보낸 두 건은 같은 본문이라 중복 처리
    assert backend.result()["outcome"] == "answered"
    assert clawops.created == []


def test_restart_with_provider_id_follows_existing_call(parts):
    clawops = FakeClawOps(["in-progress", "completed"])
    _, backend, store, real, provider_calls = parts(clawops)
    store.accept("c_live", real_request(call_id="c_live"), "real")
    provider_calls.save("c_live", "CA_test_1")
    resume_pending(store, Sender("http://backend.test", KEY, delay_sec=0), real, provider_calls)
    assert clawops.created == []
    assert backend.result()["outcome"] == "answered"


# 전사 정리

def test_agent_found_by_disclosure_and_first_question_used():
    turns = to_turns(SEGMENTS)
    assert turns[0].speaker == "academy" and turns[1].speaker == "agent"
    # 마지막 요약에도 '자리'가 나오지만 처음 물은 곳의 대답을 쓴다
    assert find_reply(turns, ("자리", "등록할 자")) == (True, "두 자리 남았어요")
    # 첫인사 "AI 상담원입니다"는 상담 질문이 아니다
    assert find_reply(turns, ("상담",)) == (True, "수요일 오후 3시에 돼요")


def test_real_call_1019_transcript_gives_expected_answers():
    """10/19 실통화 전사: 예(통학 차량) / 아니오(픽업) / 시간(수업 시간) / 상담 가능이 모두 맞아야 한다."""
    request = real_request(questions=[
        {"question_id": "q1", "question_code": "shuttle"},
        {"question_id": "q2", "question_code": "pickup"},
        {"question_id": "q3", "question_code": "class_time"},
    ])
    result = build_result("c_1019", request, {"status": "completed", "duration": 103}, None, REAL_1019)
    check_schema(result)
    got = {a["question_code"]: (a["answered"], a["yes_no"], a["detail"]) for a in result["answers"]}
    assert got["shuttle"] == (True, True, "네, 침산동 쪽으로 다녀요.")
    assert got["pickup"] == (True, False, "픽업은 안 합니다.")
    assert got["class_time"] == (True, None, "화, 목 저녁 7시요.")
    assert result["unresolved"] == []
    assert result["consult_accepted"] is True and result["available_times"] == ["수요일 3시에 오세요."]
    assert result["disclosure_played"] is True


def test_real_call_1019_corrected_in_reconfirm_and_interrupted_question():
    """되짚기에서 고쳐 말한 대답(픽업)과 끊긴 질문 뒤 앞 질문 되짚기(수업 시간), 첫인사의 '상담'을 맞게 처리한다."""
    request = real_request(questions=[
        {"question_id": "q1", "question_code": "shuttle"},
        {"question_id": "q2", "question_code": "pickup"},
        {"question_id": "q3", "question_code": "class_time"},
    ])
    result = build_result("c_1019b", request, {"status": "completed", "duration": 100}, None, REAL_1019_RECONFIRM)
    check_schema(result)
    got = {a["question_code"]: (a["answered"], a["yes_no"], a["detail"]) for a in result["answers"]}
    assert got["shuttle"] == (True, True, "네, 침산동 쪽으로 다니고 수업 전후로 20분 있습니다.")
    assert got["pickup"] == (True, False, "아니요, 픽업은 안 해요.")
    assert got["class_time"] == (True, None, "화, 목 저녁 7시요.")
    assert result["unresolved"] == []
    assert result["consult_accepted"] is True and result["available_times"] == ["수요일 3시에 오세요."]


def test_correction_without_content_becomes_unknown():
    turns = to_turns([
        {"speaker": "A", "start": 0, "text": "AI 상담원입니다. 녹음됩니다."},
        {"speaker": "H", "start": 1, "text": "네"},
        {"speaker": "A", "start": 2, "text": "수업 후 픽업도 해 주시나요?"},
        {"speaker": "H", "start": 3, "text": "네, 해요."},
        {"speaker": "A", "start": 4, "text": "픽업해 주신다는 거죠?"},
        {"speaker": "H", "start": 5, "text": "아니요."},
    ])
    [answer] = build_answers([{"question_id": "q1", "question_code": "pickup"}], turns)
    assert (answer["answered"], answer["reason"]) == (False, "unknown")


def test_consult_not_asked_when_only_greeting_mentions_it():
    greeting_only = [s for s in SEGMENTS if "상담이 가능" not in s["text"]]
    assert find_reply(to_turns(greeting_only), ("상담",)) == (False, "")


# 판정 규칙 (10/19 김규림 결정을 그대로 사례로 고정)

@pytest.mark.parametrize("code, reply, expected", [
    # '네'로 시작해도 부정어가 있으면 아니오
    ("pickup", "네, 그건 없어요", (True, False, None)),
    ("pickup", "수업 후 픽업은 안 해요", (True, False, None)),
    # 어미가 바뀌어도 부정 (10/19 실통화에서 "안 합니다")
    ("pickup", "픽업은 안 합니다.", (True, False, None)),
    ("pickup", "픽업은 안 하고 있어요", (True, False, None)),
    ("shuttle", "차량은 안 됩니다", (True, False, None)),
    # '안녕', '안내'는 부정이 아니다
    ("shuttle", "안녕하세요 네 운행해요", (True, True, None)),
    # '네'만 하면 예
    ("shuttle", "네", (True, True, None)),
    ("vacancy", "네 지금 두 자리 남아 있어요", (True, True, None)),
    # 조건부·추측은 미확인
    ("shuttle", "보통은 돼요", (False, None, "unknown")),
    ("vacancy", "아마 있을 거예요", (False, None, "unknown")),
    # 모름과 거절을 단서로 구분
    ("level_test", "원장님께 여쭤봐야 해요", (False, None, "unknown")),
    ("vacancy", "전화로는 말씀드리기 어려워요", (False, None, "refused")),
    ("level_fit", "직접 오셔서 상담받으세요", (False, None, "refused")),
    # 자리가 없고 대기만 되면 아니오, 대기 없이 바로면 예
    ("vacancy", "지금은 없고 대기 걸어 드릴게요", (True, False, None)),
    ("vacancy", "대기 없이 바로 등록 가능해요", (True, True, None)),
    # '없'이 들어가도 긍정인 관용구
    ("pickup", "그건 상관없어요 해 드려요", (True, True, None)),
    # 수업 시간은 요일·시각이 있어야 답함
    ("class_time", "화요일이랑 목요일 저녁 7시부터 9시까지요", (True, None, None)),
    ("class_time", "반마다 달라요", (False, None, "unknown")),
    # 상담은 시간을 말하면 가능, '어려워요'는 아니오
    ("consult", "수요일 3시에 오세요", (True, True, None)),
    ("consult", "이번 주는 어려워요", (True, False, None)),
    ("pickup", "", (False, None, "unknown")),
])
def test_judge_rules(code, reply, expected):
    assert judge(code, reply) == expected


def test_instruction_lists_only_requested_questions():
    instruction, variables = build_instruction(real_request())
    # 셔틀·픽업 대신 방향을 넣은 등원·하원 차량으로 묻는다(11/16)
    assert "하원 차량" in instruction and "등원 차량" in instruction and "레벨 테스트" not in instruction
    assert "픽업" not in instruction and "셔틀" not in instruction
    # 백엔드 코드(M2, MATH, MID)가 아니라 AI가 읽을 수 있는 말로 넘긴다
    assert "중학교 2학년, 과목 수학, 수준 중간, 대구 북구 침산동 거주" in instruction
    assert "M2" not in instruction and "MATH" not in instruction
    # ClawOps Variables 값은 문자열·숫자·참거짓만 된다
    assert variables["questions"] == "shuttle, vacancy, pickup"
    assert all(isinstance(v, (str, int, float, bool)) for v in variables.values())


# ---- 수업 문의 묻는 순서 (맞는 반 → 자리 → 시간, 11/22) ----------------------------
from extract import QUESTIONS  # noqa: E402
from real_call import SKIPPED_NO_CLASS, ask_order  # noqa: E402


def _qs(*codes):
    return [{"question_id": f"q{i}", "question_code": c} for i, c in enumerate(codes, 1)]


@pytest.mark.parametrize("codes, expected", [
    (("shuttle", "class_time", "level_fit", "pickup", "vacancy"), ("shuttle", "level_fit", "vacancy", "class_time", "pickup")),
    (("vacancy", "level_fit"), ("level_fit", "vacancy")),
    (("pickup", "vacancy"), ("pickup", "vacancy")),
    (("shuttle", "level_test"), ("shuttle", "level_test")),
])
def test_ask_order_groups_lesson_questions(codes, expected):
    assert tuple(q["question_code"] for q in ask_order(_qs(*codes))) == expected


@pytest.mark.parametrize("codes, rule", [
    (("class_time", "level_fit", "vacancy"), "맞는 반이 없다고 하면 자리와 수업 시간은 묻지 않고"),
    (("level_fit", "vacancy"), "맞는 반이 없다고 하면 자리는 묻지 않고"),
    (("level_fit", "class_time"), "맞는 반이 없다고 하면 수업 시간은 묻지 않고"),
    (("vacancy", "class_time"), None),  # 맞는 반을 묻지 않으면 건너뛰기 규칙도 없음
])
def test_instruction_asks_lesson_in_order_and_skips_without_class(codes, rule):
    instruction, _ = build_instruction(real_request(questions=_qs(*codes)))
    asked = [QUESTIONS[c][0] for c in ("level_fit", "vacancy", "class_time") if c in codes]
    assert [instruction.index(text) for text in asked] == sorted(instruction.index(text) for text in asked)
    if rule:
        assert rule in instruction
    else:
        assert "맞는 반이 없다고 하면" not in instruction


def test_skipped_lesson_questions_are_explained_in_request_order(monkeypatch):
    segments = copy.deepcopy(REAL_1019)
    segments[4]["text"] = "중2 중간 수준 반은 지금 없어요."
    raw = copy.deepcopy(LLM_1019)
    raw["answers"] = {"level_fit": item("no", [4], "중2 중간 수준 반은 지금 없어요", "맞는 반 없음"),
                      "vacancy": item("not_asked", [], "", "묻지 않음"), "class_time": item("not_asked", [], "", "묻지 않음")}
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": raw})
    request = real_request(questions=_qs("vacancy", "class_time", "level_fit"))
    result = build_result("c_lesson", request, {"status": "completed"}, None, segments, no_wait_judge())
    ResultInput.model_validate(result)
    assert [a["question_code"] for a in result["answers"]] == ["vacancy", "class_time", "level_fit"]  # 요청 순서 그대로
    got = {a["question_code"]: a for a in result["answers"]}
    assert (got["level_fit"]["answered"], got["level_fit"]["yes_no"]) == (True, False)
    for code in ("vacancy", "class_time"):
        assert got[code]["reason"] == "not_asked" and got[code]["detail"] == SKIPPED_NO_CLASS


# ---- LLM 판정 연결 (11/9) -------------------------------------------------
# 실제 LLM은 부르지 않는다. llm_judge.call_llm을 바꿔 끼워, 판정 출력 → 계약 변환 → 결과 전송 본문을 확인한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import llm_judge  # noqa: E402
from contracts import ResultInput  # noqa: E402  (backend 계약: extra='forbid'라 남는 키가 있으면 실패)
from llm_judge import LLMJudge  # noqa: E402

Q1019 = [{"question_id": "q1", "question_code": "shuttle"}, {"question_id": "q2", "question_code": "pickup"},
         {"question_id": "q3", "question_code": "class_time"}]


def item(status, turns_, quote, detail, certainty="definite"):
    return {"status": status, "certainty": certainty, "detail": detail, "evidence_turns": turns_, "evidence_quote": quote}


LLM_1019 = {"answers": {
    "shuttle": item("yes", [4], "침산동 쪽으로 다녀요", "침산동 쪽으로 운행"),
    "pickup": item("no", [8], "픽업은 안 합니다", "수업 후 픽업 안 함", certainty="guess"),
    "class_time": item("answered", [10], "화, 목 저녁 7시요", "화·목 저녁 7시")},
    "consult": {"status": "yes", "certainty": "definite", "available_times": ["수요일 3시"], "unavailable_times": [],
                "evidence_turns": [12], "evidence_quote": "수요일 3시에 오세요"}}


def test_llm_judge_result_passes_backend_contract(monkeypatch):
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": LLM_1019})
    result = build_result("c_llm", real_request(questions=Q1019), {"status": "completed", "duration": 103}, None,
                          REAL_1019, LLMJudge("gemini-test", "k"))
    ResultInput.model_validate(result)
    check_schema(result)
    got = {a["question_code"]: a for a in result["answers"]}
    assert (got["shuttle"]["answered"], got["shuttle"]["yes_no"]) == (True, True)
    assert got["shuttle"]["source_text"] == "네, 침산동 쪽으로 다녀요."
    # 학원이 확정하지 않은 답(certainty=guess)은 미확인 + uncertain, 기운 쪽은 문구로만 남는다
    assert (got["pickup"]["answered"], got["pickup"]["yes_no"], got["pickup"]["reason"]) == (False, None, "uncertain")
    assert got["pickup"]["detail"].startswith("학원이 확실하지 않다고 함")
    assert got["class_time"]["detail"] == "화·목 저녁 7시"
    assert result["unresolved"] == ["q2"]
    assert result["consult_accepted"] is True and result["available_times"] == ["수요일 3시"]
    assert result["notes"] == ""


# ---------------------------------------------------------------- 종료 원인(end_reason)·재통화 요청
from extract import Turn as _Turn, find_callback  # noqa: E402
from real_call import end_reason_of  # noqa: E402

_CLOSED = [_Turn("agent", 0, "질문입니다"), _Turn("academy", 1000, "네"),
           _Turn("agent", 2000, "맞으시면 이대로 학부모님께 전해 드리겠습니다. 좋은 하루 보내세요.")]
_CUT = [_Turn("agent", 0, "등원 차량이 있을까요?"), _Turn("academy", 1000, "아 잠깐만요")]


@pytest.mark.parametrize("call, turns, expected", [
    ({"hangupSource": "callee", "hangupCause": "normal_clearing"}, _CLOSED, "completed"),  # 마무리 인사 뒤 학원이 끊음
    ({"hangupSource": "caller", "hangupCause": "normal_clearing"}, _CUT, "completed"),     # 상담원이 끊음
    ({"hangupSource": "callee", "hangupCause": "normal_clearing"}, _CUT, "academy_hung_up"),
    ({"hangupSource": "carrier", "hangupCause": "recovery_on_timer_expire"}, _CUT, "connection_lost"),
    ({"hangupSource": "app", "hangupCause": "media_timeout"}, _CUT, "agent_error"),
    ({}, _CUT, "completed"),  # 종료 정보가 없으면 정상 종료로 봄
])
def test_end_reason_of(call, turns, expected):
    assert end_reason_of(call, turns) == expected


@pytest.mark.parametrize("text, found", [
    ("이번 주는 좀 힘들 것 같아요. 다음 주에 다시 연락 주세요.", "학원이 다시 연락해 달라고 함"),
    ("원장님 오시면 다시 전화 주세요", "학원이 다시 연락해 달라고 함"),
    ("지금은 통화가 어려워서요", "학원이 지금은 통화가 어렵다고 함"),
    ("지금 수업 중이라서요", "학원이 지금은 통화가 어렵다고 함"),
    ("나중에 다시 주세요", "학원이 다시 연락해 달라고 함"),
    ("잠시 뒤에 다시 걸어주시겠어요?", "학원이 다시 연락해 달라고 함"),
    ("원장님은 오후 3시에 오세요. 그때 다시 거세요.", "학원이 다시 연락해 달라고 함"),
    ("알아보고 다시 연락드릴게요", None),  # 학원이 직접 연락하겠다는 말은 재통화 요청이 아님
    ("나중에 다시 알려드릴게요", None),
    ("전화 주시면 알려 드릴게요", None),
])
def test_find_callback(text, found):
    got = find_callback([_Turn("agent", 0, "질문"), _Turn("academy", 1000, text)])
    assert (got[0] if got else None) == found
    if got:
        assert got[1] == text


def test_callback_request_is_sent_without_time_and_passes_contract(monkeypatch):
    # 학원이 다시 걸어 달라고 했고 확인 못 한 질문이 남았으면 재통화 요청을 보낸다. 시각은 비워 사람이 확인한다
    segments = copy.deepcopy(REAL_1019)
    segments[8]["text"] = "그건 원장님 오시면 다시 전화 주세요"
    raw = copy.deepcopy(LLM_1019)
    raw["answers"]["pickup"] = item("unknown", [8], "원장님 오시면 다시 전화 주세요", "원장 확인 필요")
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": raw})
    result = build_result("c_cb", real_request(questions=Q1019), {"status": "completed", "hangupSource": "callee",
                          "hangupCause": "normal_clearing"}, None, segments, no_wait_judge())
    ResultInput.model_validate(result)
    assert result["callback_requested"] is True and result["callback_at"] is None
    assert result["callback_reason_text"] == "학원이 다시 연락해 달라고 함"
    assert result["callback_source_text"] == "그건 원장님 오시면 다시 전화 주세요"
    assert result["end_reason"] in ("completed", "academy_hung_up")


def test_no_callback_when_everything_is_confirmed(monkeypatch):
    segments = copy.deepcopy(REAL_1019)
    segments[2]["text"] = "네, 가능합니다. 나중에 또 전화 주세요"  # 모두 확인됐으면 다시 걸 이유가 없음
    raw = copy.deepcopy(LLM_1019)
    raw["answers"]["pickup"] = item("no", [8], "픽업은 안 합니다", "수업 후 픽업 안 함")
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": raw})
    result = build_result("c_nocb", real_request(questions=Q1019), {"status": "completed"}, None, segments, no_wait_judge())
    ResultInput.model_validate(result)
    assert result["unresolved"] == [] and result["consult_accepted"] is True
    assert result["callback_requested"] is False and result["callback_reason_text"] is None


@pytest.mark.parametrize("status, quote, expected_reason", [
    ("unknown", "원장님께 여쭤봐야 해요", "uncertain"),
    ("unknown", "전사에 없는 답변", "unknown"),
    ("not_asked", "원장님께 여쭤봐야 해요", "not_asked"),
])
def test_deferred_reply_requires_evidence_and_an_asked_question(monkeypatch, status, quote, expected_reason):
    raw = copy.deepcopy(LLM_1019)
    raw["answers"]["pickup"] = item(status, [8], quote, "원장 확인 필요", certainty="deferred")
    segments = copy.deepcopy(REAL_1019)
    segments[8]["text"] = "원장님께 여쭤봐야 해요"
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": raw})
    result = build_result("c_deferred", real_request(questions=Q1019), {"status": "completed"}, None,
                          segments, no_wait_judge())
    ResultInput.model_validate(result)
    answer = result["answers"][1]
    assert (answer["asked"], answer["answered"], answer["yes_no"]) == (status != "not_asked", False, None)
    assert answer["reason"] == expected_reason
    assert answer["source_text"] == (quote if expected_reason == "uncertain" else None)
    assert result["unresolved"] == ["q2"]


def test_consult_times_must_match_an_available_time_in_the_academy_reply(monkeypatch):
    raw = copy.deepcopy(LLM_1019)
    raw["consult"].update(
        evidence_quote="수요일 세 시에 오세요",
        available_times=["수요일 3시", "수요일 오후 3시", "월요일 3시", "월요일 오전 9시"],
        unavailable_times=["월요일 오전 9시"],
    )
    segments = copy.deepcopy(REAL_1019)
    segments[12]["text"] = "월요일 오전 9시는 어렵고 수요일 세 시에 오세요."
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": raw})
    result = build_result("c_consult", real_request(questions=Q1019), {"status": "completed"}, None,
                          segments, no_wait_judge())
    ResultInput.model_validate(result)
    assert result["consult_accepted"] is True
    assert result["available_times"] == ["수요일 3시"]


def test_restart_resends_saved_result_without_rejudging_or_dialing(parts, monkeypatch):
    calls = []

    def model(*args, **kwargs):
        calls.append(1)
        return {"result": LLM_1019}

    monkeypatch.setattr(llm_judge, "call_llm", model)
    clawops = FakeClawOps(["completed"])
    client, backend, store, real, _ = parts(clawops)
    real.judge = no_wait_judge()
    initial_post = real.post

    def post_with_lost_reply(path, body):
        outcome = initial_post(path, body)
        if path.endswith("/result"):
            return "failed", "response lost after result commit"
        return outcome

    real.post = post_with_lost_reply
    request = real_request(questions=Q1019)
    assert client.post("/internal/calls", json=request, headers=HEADERS).status_code == 202
    saved = store.result_body(request["call_id"])
    assert saved is not None and store.pending() == [request["call_id"]]
    assert saved == backend.result()

    restarted_store = ReceiptStore(store.path)
    sender = Sender("http://backend.test", KEY, delay_sec=0, transport=httpx.MockTransport(backend))
    resume_pending(restarted_store, sender, None, None)

    results = [body for path, body in backend.requests if path.endswith("/result")]
    assert results == [saved, saved]
    assert calls == [1] and len(clawops.created) == 1
    assert restarted_store.pending() == []
    assert restarted_store.result_body(request["call_id"]) is None


def no_wait_judge():
    return LLMJudge("gemini-test", "k", sleep=lambda sec: None)


def test_location_directions_and_call_day_reach_the_instruction():
    request = real_request(student={'grade': 'M2', 'subject': 'MATH', 'level': 'MID', 'region': None}, questions=[
        {'question_id': 'q1', 'question_code': 'shuttle', 'location': {'kind': '학교', 'name': '침산초등학교'}},
        {'question_id': 'q2', 'question_code': 'pickup', 'location': {'kind': '집 근처', 'name': '침산네거리'}},
    ])
    request['time_context'] = {'inquiry_created_at': '2026-11-14T01:00:00Z',
                               'dispatch_requested_at': '2026-11-14T14:59:00Z', 'timezone': 'Asia/Seoul'}
    instruction, variables = build_instruction(request, reference_at='2026-11-14T15:01:00+00:00')
    assert '2026-11-15T00:01:00+09:00' in instruction
    assert '침산초등학교' in instruction and '침산네거리' in instruction
    assert '등원 차량으로' in instruction and '하원 차량으로 학원에서' in instruction
    assert 'None 거주' not in instruction and '거주 지역 미입력' in instruction
    assert variables['timezone'] == 'Asia/Seoul'


def test_location_and_time_context_reach_judgement_without_leaking_to_answers(monkeypatch):
    seen = []
    def model(codes, turns, *args, **kwargs):
        seen.append(kwargs)
        return {'result': LLM_1019}
    monkeypatch.setattr(llm_judge, 'call_llm', model)
    questions = copy.deepcopy(Q1019)
    questions[0]['location'] = {'kind': '학교', 'name': '침산초등학교'}
    request = real_request(questions=questions)
    reference = '2026-11-15T03:00:00+00:00'
    result = build_result('context-result', request, {'status': 'completed'}, None, REAL_1019,
                          no_wait_judge(), reference_at=reference)
    ResultInput.model_validate(result)
    assert seen[0]['questions'][0]['location']['name'] == '침산초등학교'
    assert seen[0]['time_context']['call_started_at'] == reference
    assert '2026-11-15 12:00' in result['notes']
    message = llm_judge.user_message(
        ['shuttle'], to_turns(REAL_1019), questions=questions, time_context=seen[0]['time_context'])
    assert '침산초등학교' in message and reference in message
    assert all('location' not in row for row in result['answers'])


def test_saved_call_reference_survives_restart_and_receipt_retry(parts):
    clawops = FakeClawOps(['completed'])
    client, backend, store, _, provider_calls = parts(clawops)
    request = real_request()
    assert client.post('/internal/calls', json=request, headers=HEADERS).status_code == 202
    started = provider_calls.started_at(request['call_id'])
    assert started and ProviderCalls(store.path).started_at(request['call_id']) == started
    assert client.post('/internal/calls', json=request, headers=HEADERS).json()['duplicate'] is True
    assert len(clawops.created) == 1


def test_real_worker_accepts_locations_and_optional_region_without_result_extras(parts):
    clawops = FakeClawOps(['completed'])
    client, backend, *_ = parts(clawops)
    questions = copy.deepcopy(Q1019)
    questions[0]['location'] = {'kind': '학교', 'name': '침산초등학교'}
    questions[1]['location'] = {'kind': '집 근처', 'name': '침산네거리'}
    request = real_request(questions=questions, student={'grade': 'M2', 'subject': 'MATH', 'level': 'MID'})
    assert client.post('/internal/calls', json=request, headers=HEADERS).status_code == 202
    ResultInput.model_validate(backend.result())
    assert all('location' not in row for row in backend.result()['answers'])
    assert '날짜 해석 기준:' in backend.result()['notes']


def test_llm_failure_is_retried_then_succeeds(monkeypatch, caplog):
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("Gemini 429")
        return {"result": LLM_1019}
    monkeypatch.setattr(llm_judge, "call_llm", flaky)
    with caplog.at_level("INFO", logger="call_worker"):
        result = build_result("c_llm_retry", real_request(questions=Q1019), {"status": "completed", "duration": 103}, None,
                              REAL_1019, no_wait_judge())
    ResultInput.model_validate(result)
    assert len(calls) == 3 and result["notes"] == ""
    assert f"gemini-test ({llm_judge.PROMPT_VERSION})" in caplog.text and "3 attempt(s)" in caplog.text


def test_llm_giving_up_sends_all_unknown_not_keyword(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise ValueError("망가진 JSON")
    monkeypatch.setattr(llm_judge, "call_llm", boom)
    result = build_result("c_llm_fail", real_request(questions=Q1019), {"status": "completed", "duration": 103}, None,
                          REAL_1019, no_wait_judge())
    ResultInput.model_validate(result)
    assert len(calls) == len(llm_judge.JUDGE_ATTEMPT_WAITS)
    assert all(not a["answered"] and a["reason"] == "unknown" for a in result["answers"])
    assert result["unresolved"] == ["q1", "q2", "q3"]
    assert result["consult_accepted"] is None and result["available_times"] == []
    assert result["notes"] == "통화는 연결됐지만 답변을 확인하지 못했습니다."
    assert result["transcript"]  # 판정은 실패해도 전사는 보낸다


def test_keyword_only_when_judge_not_configured():
    result = build_result("c_kw2", real_request(questions=Q1019), {"status": "completed", "duration": 103}, None, REAL_1019)
    ResultInput.model_validate(result)
    assert result["notes"] == ""


def test_not_connected_call_never_calls_llm(monkeypatch):
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: pytest.fail("연결 안 된 통화에서 LLM 호출"))
    result = build_result("c_na", real_request(), {"status": "no-answer"}, None, [], LLMJudge("gemini-test", "k"))
    ResultInput.model_validate(result)


def test_load_judge_from_env(monkeypatch):
    from worker import load_judge
    monkeypatch.delenv("LLM_JUDGE_MODEL", raising=False)
    assert load_judge() is None
    monkeypatch.setenv("LLM_JUDGE_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_judge()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert load_judge().model == "gemini-3.5-flash-lite"


# ---- 계층 판정 연결 (11/18) ------------------------------------------------
# 실제 LLM은 부르지 않는다. TieredJudge의 call을 가짜로 바꿔 단계별 출력 → 라우팅 → 계약·화면 형식을 확인한다.
import tiered_judge  # noqa: E402
from tiered_judge import TieredConfig, TieredJudge  # noqa: E402

TQ = [{"question_id": "q1", "question_code": "shuttle"}, {"question_id": "q2", "question_code": "pickup"},
      {"question_id": "q3", "question_code": "class_time"}, {"question_id": "q4", "question_code": "vacancy"}]


def tri(status, turns_=(), quote="", signal="none", condition="", **extra):
    return {"status": status, "signal": signal, "evidence_turns": list(turns_), "evidence_quote": quote, "condition": condition, **extra}


def triage_out(**changes):
    answers = {"shuttle": tri("yes", [4], "침산동 쪽으로 다녀요", condition="수업 시간 전후로만 운행"),
               "pickup": tri("no", [8], "픽업은 안 합니다"),
               "class_time": tri("answered", [10], "화, 목 저녁 7시요"),
               "vacancy": tri("not_asked")}
    answers.update(changes)
    return {"answers": answers, "consult": tri("yes", [12], "수요일 3시에 오세요", available_times=["수요일 3시"], unavailable_times=[])}


class FakeStages:
    """단계(스키마 이름)와 모델로 가짜 출력을 고른다. 부른 기록을 남긴다."""
    def __init__(self, main, cross=None, review=None, fail=()):
        self.main, self.cross, self.review, self.fail, self.seen = main, cross, review or {}, set(fail), []

    def __call__(self, system, message, schema, model, keys, timeout):
        stage = schema["name"]
        if stage == "triage" and model.startswith("gemini"):
            stage = "cross"
        self.seen.append((stage, model, message))
        if stage in self.fail:
            raise RuntimeError(f"{stage} down")
        usage = {"prompt_tokens": 100, "completion_tokens": 10, "thoughts_tokens": 0, "billed_output_tokens": 10}
        if stage == "triage":
            return self.main, usage, model
        if stage == "cross":
            return self.cross or self.main, usage, model
        if stage == "review":
            code = message.split("질문: ", 1)[1].split(" —", 1)[0]
            return self.review[code], usage, model
        codes = [line[2:].split(":", 1)[0] for line in message.splitlines() if line.startswith("- ")]
        return {c: {"shuttle": "침산동 쪽 운행", "pickup": "수업 후 픽업 안 함", "class_time": "화·목 저녁 7시",
                    "vacancy": "묻지 못함", "consult": "수요일 3시 상담 가능"}.get(c, "확인") for c in codes}, usage, model

    def stages(self):
        return [s for s, _, _ in self.seen]


def tiered(stages, **kw):
    return TieredJudge({"OPENAI_API_KEY": "k", "GEMINI_API_KEY": "g"}, TieredConfig(), sleep=lambda s: None, call=stages, **kw)


def review_out(status, turns_=(), quote="", condition="", reason_text="", certainty="definite"):
    return {"status": status, "certainty": certainty, "condition": condition, "reason_text": reason_text,
            "evidence_turns": list(turns_), "evidence_quote": quote}


def test_tiered_result_passes_contract_and_uses_frontend_wording():
    # 섞기 상대가 pickup을 unknown으로 봐서 불일치 → 2차가 redirect로 판정
    stages = FakeStages(triage_out(), cross=triage_out(pickup=tri("unknown")),
                        review={"pickup": review_out("redirect", [8], "픽업은 안 합니다", reason_text="홈페이지 공지 확인")})
    request = real_request(questions=TQ)
    result = build_result("c_tiered", request, {"status": "completed", "duration": 103}, None, REAL_1019, tiered(stages),
                          reference_at="2026-11-18T06:00:00+00:00")
    ResultInput.model_validate(result)
    check_schema(result)
    rows = {a["question_code"]: a for a in result["answers"]}
    assert rows["shuttle"]["answered"] and rows["shuttle"]["yes_no"] is True
    assert rows["shuttle"]["detail"].startswith("조건: 수업 시간 전후로만 운행\n")  # 프론트 '조건부 가능'
    assert rows["shuttle"]["condition"] == "수업 시간 전후로만 운행"
    assert rows["pickup"]["reason"] == "refused" and rows["pickup"]["detail"].startswith("안내받은 경로: ")  # 프론트 '직접 확인 필요'
    assert rows["class_time"]["answered"] and rows["class_time"]["yes_no"] is None
    assert rows["vacancy"]["asked"] is False and rows["vacancy"]["reason"] == "not_asked"
    assert result["consult_accepted"] is True and result["available_times"] == ["수요일 3시"]
    assert stages.stages().count("review") == 1 and set(stages.stages()) == {"triage", "cross", "review", "summary"}
    triage_message = next(m for s, _, m in stages.seen if s == "triage")
    assert "이번 주 남은 날: 11/18(수, 15:00 이후), 11/19(목), 11/20(금)" in triage_message  # 11/18(수) 15시 통화
    assert "학생" in triage_message


def test_tiered_not_asked_disagreement_is_not_reviewed():
    # 섞기 상대가 묻지 않은 vacancy를 다른 답에서 추론해 no로 채워도 2차로 넘기지 않는다
    stages = FakeStages(triage_out(), cross=triage_out(vacancy=tri("no", [8], "픽업은 안 합니다")))
    result = build_result("c_na", real_request(questions=TQ), {"status": "completed"}, None, REAL_1019, tiered(stages))
    ResultInput.model_validate(result)
    assert "review" not in stages.stages()
    assert {a["question_code"]: a["reason"] for a in result["answers"]}["vacancy"] == "not_asked"


def test_tiered_consult_yes_without_times_goes_to_review():
    main = triage_out()
    main["consult"] = tri("yes", [12], "수요일 3시에 오세요", available_times=[], unavailable_times=[])
    stages = FakeStages(main, review={"consult": review_out("no", [12], "수요일 3시에 오세요", reason_text="상담 불가")})
    result = build_result("c_consult", real_request(questions=TQ), {"status": "completed"}, None, REAL_1019, tiered(stages))
    ResultInput.model_validate(result)
    assert stages.stages().count("review") == 1 and result["consult_accepted"] is False


def test_tiered_cross_and_review_failures_degrade_safely():
    # 섞기 상대가 죽어도 계속하고, 2차가 죽은 항목은 미확인으로 보낸다(틀린 예/아니오보다 미확인)
    main = triage_out(pickup=tri("no", [8], "픽업은 안 합니다", signal="hedge"))
    stages = FakeStages(main, fail={"cross", "review"})
    result = build_result("c_degrade", real_request(questions=TQ), {"status": "completed"}, None, REAL_1019, tiered(stages))
    ResultInput.model_validate(result)
    pickup = {a["question_code"]: a for a in result["answers"]}["pickup"]
    assert pickup["answered"] is False and pickup["reason"] == "unknown"
    assert {a["question_code"]: a["answered"] for a in result["answers"]}["shuttle"] is True


def test_tiered_main_triage_failure_retries_then_sends_all_unknown():
    stages = FakeStages(triage_out(), fail={"triage"})
    judge = tiered(stages, attempt_waits=(0, 0))
    result = build_result("c_fail", real_request(questions=TQ), {"status": "completed"}, None, REAL_1019, judge)
    ResultInput.model_validate(result)
    assert stages.stages().count("triage") == 2
    assert all(not a["answered"] and a["reason"] == "unknown" for a in result["answers"])


def test_tiered_openai_call_sends_no_temperature(monkeypatch):
    sent = []

    class Response:
        status_code = 200

        def json(self):
            return {"model": "gpt-5.6-luna", "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(tiered_judge.httpx, "post", lambda url, json, headers, timeout: sent.append(json) or Response())
    tiered_judge.call_model("s", "m", {"name": "x", "strict": True, "schema": {}}, "gpt-5.6-luna", {"OPENAI_API_KEY": "k"})
    assert "temperature" not in sent[0]  # gpt-5.6은 temperature를 보내면 400


def test_load_tiered_judge_from_env(monkeypatch):
    from worker import load_judge
    monkeypatch.setenv("LLM_JUDGE_MODEL", "tiered")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_judge()  # 섞기 상대가 gemini라 GEMINI_API_KEY도 필요
    monkeypatch.setenv("TIERED_CROSS_MODEL", "")
    assert load_judge().config.cross is None  # 섞기를 끄면 OpenAI 키만으로 동작
    monkeypatch.delenv("TIERED_CROSS_MODEL")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    judge = load_judge()
    assert isinstance(judge, TieredJudge) and judge.config.review == "gpt-5.6-terra"


# ---------------------------------------------------------------- 근거 발화 (transcript turn_no + evidence_turns)
from extract import Turn  # noqa: E402
from llm_judge import evidence_turns  # noqa: E402
from real_call import consult_explanation, number_transcript  # noqa: E402


def test_evidence_turns_add_agent_recap_for_short_confirmation():
    # 학원이 "네 맞습니다"처럼 확인만 했으면 무엇을 확인했는지 보이게 앞의 AI 되짚기도 근거 발화에 넣는다 (source_text와 같은 규칙)
    turns = [Turn("agent", 0, "화요일과 목요일 저녁 7시가 맞을까요?"), Turn("academy", 3000, "네 맞습니다"),
             Turn("academy", 5000, "수업은 화요일, 목요일 저녁 일곱 시예요.")]
    assert evidence_turns({"evidence_turns": [1]}, turns) == [0, 1]
    assert evidence_turns({"evidence_turns": [2]}, turns) == [2]
    assert evidence_turns({"evidence_turns": [0, 9]}, turns) == []  # AI 발화·없는 번호는 근거가 아님


def test_llm_judge_sends_numbered_transcript_and_evidence(monkeypatch):
    monkeypatch.setattr(llm_judge, "call_llm", lambda *a, **k: {"result": LLM_1019})
    result = build_result("c_ev", real_request(questions=Q1019), {"status": "completed", "duration": 103}, None,
                          REAL_1019, LLMJudge("gemini-test", "k"))
    ResultInput.model_validate(result)  # 계약: 근거 번호는 이 결과의 transcript turn_no에 있어야 함
    assert [t["turn_no"] for t in result["transcript"]] == list(range(len(result["transcript"])))
    got = {a["question_code"]: a for a in result["answers"]}
    assert got["shuttle"]["evidence_turns"] == [4] and got["class_time"]["evidence_turns"] == [10]
    assert result["consult"] == {"source_text": "수요일 3시에 오세요.", "evidence_turns": [12]}  # 확정이라 사유 없음


def test_tiered_judge_sends_evidence_and_no_evidence_for_unasked():
    stages = FakeStages(triage_out())
    result = build_result("c_tev", real_request(questions=TQ), {"status": "completed"}, None, REAL_1019, tiered(stages))
    ResultInput.model_validate(result)
    rows = {a["question_code"]: a for a in result["answers"]}
    assert rows["shuttle"]["evidence_turns"] == [4] and rows["pickup"]["evidence_turns"] == [8]
    assert "evidence_turns" not in rows["vacancy"]  # 묻지 않은 질문에는 근거 발화를 보내지 않음
    assert result["consult"]["evidence_turns"] == [12] and "reason" not in result["consult"]


def test_consult_explanation_reason_and_unasked():
    assert consult_explanation({"status": "redirect", "consult_accepted": None, "source_text": "방문하시면 정해요",
                                "evidence_turns": [3]}) == {"reason": "refused", "source_text": "방문하시면 정해요", "evidence_turns": [3]}
    assert consult_explanation({"status": "unknown", "consult_accepted": None, "source_text": "", "evidence_turns": []}) == {"reason": "unknown"}
    assert consult_explanation({"status": "not_asked", "consult_accepted": None, "source_text": "x", "evidence_turns": [1]}) == {"reason": "not_asked"}
    assert consult_explanation({"status": "yes", "consult_accepted": True, "source_text": "", "evidence_turns": []}) is None


def test_evidence_outside_sent_transcript_is_dropped():
    turns = [Turn("agent", 0, "질문"), Turn("academy", 1000, "답")]
    keep, drop = {"evidence_turns": [1, 5]}, {"evidence_turns": [5]}
    transcript = number_transcript(turns, [keep, drop])
    assert [t["turn_no"] for t in transcript] == [0, 1]
    assert keep["evidence_turns"] == [1] and "evidence_turns" not in drop


# ---------------------------------------------------------------- 11/19 판정 규칙 (tiered-v2.1-spec)
import datetime as _dt  # noqa: E402


def _seoul(text):
    return _dt.datetime.fromisoformat(text).astimezone(tiered_judge.SEOUL)


def test_remaining_days_includes_today_after_call_time():
    # 11/19 결정: 상담 기간 '이번 주 남은 날'에 통화 당일(통화 시각 이후)을 넣는다
    assert tiered_judge.remaining_days(_seoul("2026-11-18T15:00:00+09:00")) == "11/18(수, 15:00 이후), 11/19(목), 11/20(금)"
    assert tiered_judge.remaining_days(_seoul("2026-11-16T10:30:00+09:00")).startswith("11/16(월, 10:30 이후), 11/17(화)")
    assert tiered_judge.remaining_days(_seoul("2026-11-20T10:00:00+09:00")) == "11/20(금, 10:00 이후)"
    assert tiered_judge.remaining_days(_seoul("2026-11-21T10:00:00+09:00")).startswith("없음(통화일이 토·일)")


def test_consult_no_with_available_times_goes_to_review():
    # 기본 기간(평일) 밖의 주말을 학원이 먼저 말해 가능 시간이 있는데 no로 분류하면 2차로 넘긴다
    item = {"status": "no", "signal": "none", "available_times": ["토요일 오전"], "unavailable_times": ["평일"]}
    assert "상담 no인데 가능 시간 있음" in tiered_judge.needs_review("consult", item, None, [])
    item_plain = {"status": "no", "signal": "none", "available_times": [], "unavailable_times": ["이번 주"]}
    assert "상담 no인데 가능 시간 있음" not in tiered_judge.needs_review("consult", item_plain, None, [])


def test_rules_carry_definition_answers_1118():
    # 강유준 정의 답(11/18)과 11/19 결정이 1차·2차 공통 규칙에 들어 있는지
    rules = tiered_judge.RULES
    assert "정보(성적, 학년 등)를 더 알려 주면 답할 수 있다고 한 것도 redirect" in rules  # (1)
    assert "다른 질문의 답에서 미루어 채우지 않는다" in rules  # (2)
    assert "답 없이 다시 전화해 달라고만 했으면" in rules and "안 된다고 답한 뒤 다시 연락하라고 한 것은 no다" in rules  # (4)
    assert "AI가 특정 날을 물었으면 그 날이 기간" in rules  # 개정안 6번
    assert "오늘은 통화 시각 이후만 든다" in rules
    assert "확인하지 않고 차량이 있다고만 하면 unknown" in tiered_judge.QUESTION["shuttle"]


from real_call import align_place_names  # noqa: E402

# 11/25 시험 통화 1(역할극): 상담원은 '침산동'이라고 말했는데 ClawOps 전사가 '춘산동'으로 적었다
STT_1125 = [
    {"speaker": "speaker_0", "start": 3.18, "end": 3.76, "text": "네, 여보세요?"},
    {"speaker": "speaker_1", "start": 5.60, "end": 15.20, "text": "안녕하세요. 학부모님을 대신해 문의드리는 AI 상담원입니다. 상담 가능하신가요?"},
    {"speaker": "speaker_0", "start": 16.62, "end": 16.76, "text": "네."},
    {"speaker": "speaker_1", "start": 18.80, "end": 28.72, "text": "그럼 먼저 등원 차량으로 춘산동 집 근처에서 학생을 태워 학원으로 데려올 수 있을지 알려주실 수 있을까요?"},
    {"speaker": "speaker_0", "start": 30.28, "end": 31.06, "text": "네, 태워드려요."},
]


def _place_request():
    request = real_request(questions=[
        {"question_id": "q1", "question_code": "shuttle", "location": {"kind": "집 근처", "name": "침산동"}}])
    request["student"] = {**request["student"], "region": "대구 북구 침산동"}
    return request


def test_align_place_names_fixes_agent_speech_only():
    request = _place_request()
    turns = [_Turn("agent", 0, "춘산동 집 근처에서 태워 주실 수 있나요? 춘산동이요."),
             _Turn("academy", 1, "춘산동은 안 가요."),
             _Turn("agent", 2, "칠성동 말고 침산동이요.")]
    aligned = align_place_names(turns, request)
    assert aligned[0].text == "침산동 집 근처에서 태워 주실 수 있나요? 침산동이요."
    assert aligned[1] is turns[1]  # 학원은 다른 동네를 말했을 수 있다
    assert aligned[2] is turns[2]  # 두 글자 차이(칠성동)와 이미 맞는 이름은 그대로
    assert [t.text for t in turns][0].startswith("춘산동")  # 원본은 바꾸지 않는다


def test_align_place_names_skips_short_names_and_missing_locations():
    turns = [_Turn("agent", 0, "집뒤에서 태워 주실 수 있나요?")]
    request = real_request(questions=[
        {"question_id": "q1", "question_code": "shuttle", "location": {"kind": "집 근처", "name": "집앞"}}])
    request["student"] = {**request["student"], "region": None}
    assert align_place_names(turns, request) == turns  # 두 글자 이름은 보지 않는다
    assert align_place_names(turns, real_request()) == turns  # 위치도 지역도 없으면 그대로


def test_build_result_judges_aligned_names_but_keeps_raw_transcript():
    seen = []

    class SeeTurns:
        uses_student = True

        def with_context(self, questions, turns, time_context):
            seen.append([t.text for t in turns])
            rows = [{"question_id": q["question_id"], "question_code": q["question_code"], "asked": True,
                     "answered": True, "yes_no": True, "reason": None, "detail": "침산동 집 근처에서 태워 줌",
                     "evidence_turns": [3, 4]} for q in questions]
            return rows, {"consult_accepted": None, "available_times": [], "status": "not_asked"}

    result = build_result("place-1125", _place_request(), {"status": "completed"}, None, STT_1125, SeeTurns(),
                          reference_at="2026-11-25T09:59:13+00:00")
    ResultInput.model_validate(result)
    assert "침산동 집 근처" in seen[0][3] and not any("춘산동" in t for t in seen[0])
    assert "춘산동" in result["transcript"][3]["text"]  # 화면에 보내는 전사는 원문
    assert result["answers"][0]["evidence_turns"] == [3, 4]
