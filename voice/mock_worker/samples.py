"""목업 결과 만들기. 실제 통화 대신 정해 둔 답으로 events와 result를 만든다.

결과 규칙은 백엔드 ResultInput(result_json_schema.json)과 노션 API 명세 '3. 음성 → 백엔드'를 따른다.
같은 접수 기록에서는 항상 같은 ID와 본문이 나오므로, 다시 보내도 백엔드가 중복으로 처리한다.
"""
from datetime import datetime, timedelta
from typing import Literal

Scenario = Literal["answered", "partial", "no_answer"]
# MOCK_SCENARIO 값. retry는 첫 시도를 부재중, 다시 건 전화를 연결로 만든다 (E2E-03 재시도 시험용)
SCENARIO_MODES = ("answered", "partial", "no_answer", "retry")

# 문의 항목별 가짜 답: (yes_no, detail). class_time은 예/아니오가 없는 시간 텍스트라 yes_no=None
ANSWERS: dict[str, tuple[bool | None, str]] = {
    "shuttle": (True, "침산동 경유, 오후 4시와 6시 운행"),
    "pickup": (False, "수업 후 픽업은 하지 않음"),
    "level_fit": (True, "중2 중간 수준 수학반 있음"),
    "vacancy": (True, "현재 2자리 남음"),
    "level_test": (True, "등록 전 토요일 오전에 레벨 테스트"),
    "class_time": (None, "화목 19:00"),
}

# /docs에서 바로 눌러 볼 수 있는 발신 요청 예시 (노션 API 명세의 예시와 같음)
SAMPLE_REQUEST = {
    "call_id": "c_02",
    "inquiry_id": "q_8812",
    "attempt_no": 2,
    "to": "0531234567",
    "academy_name": "OO수학학원",
    "student": {"grade": "M2", "subject": "MATH", "level": "MID", "region": "대구 북구 침산동"},
    "questions": [
        {"question_id": "q1", "question_code": "shuttle"},
        {"question_id": "q2", "question_code": "level_fit"},
        {"question_id": "q3", "question_code": "vacancy"},
    ],
    "fixed_checks": ["consult_accepted", "available_times"],
    "disclosure_text": "개발용 예시: AI가 진행하는 녹음 통화입니다.",
    "policy": {"max_reask": 1, "max_seconds": 180, "is_retry": True},
    "is_mock": True,
}


def pick_scenario(mode: str, attempt_no: int) -> Scenario:
    if mode == "retry":
        return "no_answer" if attempt_no == 1 else "answered"
    if mode not in SCENARIO_MODES:
        raise ValueError(f"Unknown MOCK_SCENARIO: {mode}")
    return mode


def build_events(call_id: str, scenario: Scenario, started_at: datetime) -> list[dict]:
    """통화 진행 이벤트. 백엔드는 시각이 뒤로 가는 이벤트를 반영하지 않으므로 순서대로 시각을 늘린다."""
    steps = [("initiated", 0.0), ("ringing", 0.2)]
    if scenario == "no_answer":
        steps.append(("no_answer", 1.2))
    else:
        steps += [("answered", 0.6), ("completed", 1.2)]
    return [
        {
            "event_id": f"evt_{call_id}_{number}",
            "type": kind,
            "occurred_at": (started_at + timedelta(seconds=offset)).isoformat(),
        }
        for number, (kind, offset) in enumerate(steps, 1)
    ]


def build_result(request: dict, scenario: Scenario) -> dict:
    """요청한 질문마다 답변 행을 하나씩 만든다. 못 물었거나 못 받은 항목도 빼지 않는다."""
    questions = request["questions"]
    connected = scenario != "no_answer"
    answers = []
    for index, question in enumerate(questions):
        if not connected:
            answers.append(_missing(question, asked=False, reason="not_asked", detail="연결되지 않아 확인하지 못함"))
        elif scenario == "partial" and index == len(questions) - 1:
            answers.append(_missing(question, asked=True, reason="unknown", detail="원장님 확인 필요"))
        else:
            yes_no, detail = ANSWERS[question["question_code"]]
            answers.append({**question, "asked": True, "answered": True, "yes_no": yes_no, "reason": None, "detail": detail})
    unresolved = [answer["question_id"] for answer in answers if not answer["answered"]]
    confirmed = len(answers) - len(unresolved)
    return {
        "result_id": f"result_{request['call_id']}",
        "outcome": "answered" if connected else "no_answer",
        # 연결이 안 된 통화는 고지, 상담, 지연, 전사를 만들지 않는다
        "disclosure_played": True if connected else None,
        "consult_accepted": True if connected else None,
        "available_times": ["평일 14:00-16:00"] if connected else [],
        "answers": answers,
        "unresolved": unresolved,
        "summary_text": f"목업 결과: {len(answers)}개 중 {confirmed}개 확인" if connected else "연결되지 않아 모든 항목이 미확인",
        "notes": "목업 결과, 실제 전화 아님",
        "latency": None,
        "duration_sec": 0,
        "transcript": [],
        "recording_url": None,
        "callback_requested": False,
        "callback_at": None,
        "rejection_reason": None,
    }


def _missing(question: dict, *, asked: bool, reason: str, detail: str) -> dict:
    return {**question, "asked": asked, "answered": False, "yes_no": None, "reason": reason, "detail": detail}
