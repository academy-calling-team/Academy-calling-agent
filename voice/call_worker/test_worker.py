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
from extract import find_reply, judge, to_turns  # noqa: E402
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
        assert a["answered"] or a["reason"] in ("unknown", "refused", "not_asked")


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
    assert "통학 차량" in sent["CallContext"]["Instruction"]
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
    assert "픽업" in instruction and "레벨 테스트" not in instruction
    # 백엔드 코드(M2, MATH, MID)가 아니라 AI가 읽을 수 있는 말로 넘긴다
    assert "중학교 2학년, 과목 수학, 수준 중간, 대구 북구 침산동 거주" in instruction
    assert "M2" not in instruction and "MATH" not in instruction
    # ClawOps Variables 값은 문자열·숫자·참거짓만 된다
    assert variables["questions"] == "shuttle, vacancy, pickup"
    assert all(isinstance(v, (str, int, float, bool)) for v in variables.values())
