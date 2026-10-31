"""실제 통화 한 건: ClawOps 발신 → 상태 조회로 진행 이벤트 전송 → 전사로 결과 전송.

웹훅 대신 상태를 몇 초마다 조회한다. 그래서 공동 서버에 외부 공개 경로를 새로 열 필요가 없다.
같은 call_id로 전화를 두 번 걸지 않도록, 발신 직후 ClawOps 통화 ID를 접수 기록 옆에 저장한다.
"""
import json
import logging
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

from clawops import ClawOps, ClawOpsError
from extract import CONSULT, QUESTIONS, build_answers, consult_result, disclosure_played, to_turns

log = logging.getLogger("call_worker")

# ClawOps 통화 상태 → 백엔드 진행 이벤트 (docs/api/README.md의 지원 type)
STATUS_EVENT = {"queued": "initiated", "ringing": "ringing", "in-progress": "answered",
                "completed": "completed", "no-answer": "no_answer", "busy": "busy", "rejected": "rejected"}
FINAL = {"completed", "no-answer", "busy", "rejected", "failed", "canceled"}
NOT_CONNECTED_DETAIL = "연결되지 않아 확인하지 못함"


class ProviderCalls:
    """call_id ↔ ClawOps 통화 ID, 그리고 보낸 진행 이벤트. 접수 기록과 같은 SQLite 파일의 별도 표.

    이벤트 본문을 보내기 전에 저장해 두고, 다시 보낼 때는 저장한 본문을 그대로 보낸다.
    같은 event_id에 다른 본문(예: occurred_at만 다름)을 보내면 백엔드가 409로 거절하기 때문이다.
    """

    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS provider_calls (call_id TEXT PRIMARY KEY,"
                       " provider_call_id TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS call_events (call_id TEXT NOT NULL, event_type TEXT NOT NULL,"
                       " body TEXT NOT NULL, PRIMARY KEY (call_id, event_type))")

    def event_body(self, call_id: str, event_type: str, make) -> dict:
        """저장된 본문이 있으면 그것을, 없으면 make()로 만들어 저장한 뒤 돌려준다."""
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("INSERT OR IGNORE INTO call_events VALUES (?, ?, ?)",
                       (call_id, event_type, json.dumps(make(), ensure_ascii=False)))
            (body,) = db.execute("SELECT body FROM call_events WHERE call_id = ? AND event_type = ?",
                                 (call_id, event_type)).fetchone()
        return json.loads(body)

    def event_types(self, call_id: str) -> list[str]:
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            rows = db.execute("SELECT event_type FROM call_events WHERE call_id = ? ORDER BY rowid", (call_id,)).fetchall()
        return [t for (t,) in rows]

    def save(self, call_id: str, provider_call_id: str) -> None:
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("INSERT OR IGNORE INTO provider_calls VALUES (?, ?, ?)",
                       (call_id, provider_call_id, datetime.now(timezone.utc).isoformat()))

    def get(self, call_id: str) -> str | None:
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            row = db.execute("SELECT provider_call_id FROM provider_calls WHERE call_id = ?", (call_id,)).fetchone()
        return row[0] if row else None


# 백엔드 코드(docs/api/README.md) → AI가 그대로 읽을 수 있는 말
SCHOOL = {"E": "초등학교", "M": "중학교", "H": "고등학교"}
SUBJECT = {"KOR": "국어", "ENG": "영어", "MATH": "수학", "SCI": "과학", "SOC": "사회"}
LEVEL = {"HIGH": "상위권", "MID": "중간", "LOW": "기초"}


def describe_student(s: dict) -> str:
    grade = s["grade"]
    school = SCHOOL.get(grade[:1])
    grade_text = f"{school} {grade[1:]}학년" if school and grade[1:].isdigit() else grade
    return (f"{grade_text}, 과목 {SUBJECT.get(s['subject'], s['subject'])}, "
            f"수준 {LEVEL.get(s['level'], s['level'])}, {s['region']} 거주")


def build_instruction(request: dict) -> tuple[str, dict]:
    """이번 통화에만 적용할 지시와 변수. 서비스 에이전트의 범용 프롬프트가 말투·고지·확인 규칙을 맡는다."""
    s = request["student"]
    asks = [QUESTIONS[q["question_code"]][0] for q in request["questions"]] + [CONSULT[0]]
    lines = "\n".join(f"{i}. {text}" for i, text in enumerate(asks, 1))
    instruction = (
        f"{request['academy_name']}에 학부모를 대신해 문의하는 통화다.\n"
        f"첫인사의 고지 문구: {request['disclosure_text']}\n"
        f"학생: {describe_student(s)}.\n"
        f"아래 순서로 한 번에 하나씩 묻고, 답을 들은 뒤 다음으로 넘어간다. 목록에 없는 것은 묻지 않는다.\n{lines}\n"
        f"답이 불분명하면 최대 {request['policy']['max_reask']}번만 다시 묻는다. "
        f"모두 들으면 짧게 요약해 확인받고 인사한 뒤 끊는다."
    )
    # ClawOps Variables의 값은 문자열·숫자·참거짓만 된다(배열·객체는 400). 백엔드의 질문 배열은 그대로 두고 여기서만 바꾼다
    variables = {"academy_name": request["academy_name"], "student": describe_student(s),
                 "questions": ", ".join(q["question_code"] for q in request["questions"])}
    return instruction, variables


class RealCalls:
    def __init__(self, clawops: ClawOps, provider_calls: ProviderCalls, post, *,
                 poll_sec: float = 2.0, transcript_wait_sec: float = 180.0, sleep=time.sleep):
        """post(path, body) -> (outcome, detail): mock_worker Sender의 재시도 포함 전송을 그대로 쓴다."""
        self.clawops = clawops
        self.provider_calls = provider_calls
        self.post = post
        self.poll_sec = poll_sec
        self.transcript_wait_sec = transcript_wait_sec
        self.sleep = sleep

    def run(self, store, call_id: str) -> bool:
        """새 접수: 발신부터 결과 전송까지."""
        receipt = store.receipt(call_id)
        request = receipt.payload
        instruction, variables = build_instruction(request)
        try:
            provider_id = self.clawops.create_call(request["to"], instruction, variables)
        except ClawOpsError as error:  # ClawOps가 발신을 거절함: 전화가 걸리지 않았으므로 미연결 결과
            log.error("%s: dial refused %s", call_id, error)
            failed = {"status": "failed", "hangupSource": "system" if error.status >= 500 else "app"}
            return self._finish(store, call_id, request, failed, None, [])
        except Exception as error:  # 응답을 못 받음: 이미 걸렸을 수도 있어 다시 걸지 않고 사람이 확인
            log.error("%s: dial outcome unknown %s", call_id, error)
            store.mark_rejected(call_id, f"발신 여부 불명, ClawOps 통화 목록 확인 필요: {error}")
            return False
        self.provider_calls.save(call_id, provider_id)
        log.info("%s: dialed %s", call_id, provider_id)
        return self.follow(store, call_id)

    def follow(self, store, call_id: str) -> bool:
        """발신된 통화를 끝까지 따라간다. 워커 재시작 뒤 이어 받을 때도 이 함수를 쓴다."""
        request = store.receipt(call_id).payload
        provider_id = self.provider_calls.get(call_id)
        if provider_id is None:
            store.mark_rejected(call_id, "ClawOps 통화 ID가 없음, 사람이 확인")
            return False
        deadline = time.monotonic() + request["policy"]["max_seconds"] + 120
        # 재시작해서 이어 받는 경우: 전에 만든 이벤트는 같은 본문으로 다시 보내 둔다(백엔드는 중복으로 처리)
        sent: list[str] = []
        for kind in self.provider_calls.event_types(call_id):
            if not self._event(store, call_id, kind):
                return False
            sent.append(kind)
        call = {}
        while time.monotonic() < deadline:
            call = self.clawops.get_call(provider_id)
            status = call.get("status")
            event = STATUS_EVENT.get(status)
            if status == "in-progress" and call.get("answeredBy") == "machine":
                event = "machine"
            if event and event not in sent:
                if not self._event(store, call_id, event):
                    return False
                sent.append(event)
            if status in FINAL:
                break
            self.sleep(self.poll_sec)
        else:
            log.error("%s: call still running after deadline", call_id)
            store.mark_rejected(call_id, "통화가 제한 시간 안에 끝나지 않음, 사람이 확인")
            return False
        segments, summary = [], None
        if call.get("status") == "completed" and call.get("answeredBy") != "machine":
            segments, summary = self._transcript(provider_id)
        return self._finish(store, call_id, request, call, summary, segments)

    def _event(self, store, call_id: str, kind: str) -> bool:
        """event_id는 순서 번호가 아니라 이벤트 종류로 정한다. 재시작해도 같은 종류는 같은 ID·같은 본문이다."""
        body = self.provider_calls.event_body(call_id, kind, lambda: {
            "event_id": f"evt_{call_id}_{kind}", "type": kind,
            "occurred_at": datetime.now(timezone.utc).isoformat()})
        outcome, detail = self.post(f"/internal/calls/{call_id}/events", body)
        if outcome == "rejected":
            store.mark_rejected(call_id, f"events {detail}")
        return outcome == "ok"

    def _transcript(self, provider_id: str) -> tuple[list[dict], dict | None]:
        waited = 0.0
        requested = False
        while waited <= self.transcript_wait_sec:
            t = self.clawops.get_transcript(provider_id)
            if t.get("status") == "completed":
                summary = self.clawops.get_summary(provider_id)
                return t.get("segments") or [], (summary.get("resultJson") if summary.get("status") == "completed" else None)
            if t.get("status") == "failed":
                break
            if t.get("status") == "not_requested" and not requested:
                self.clawops.request_transcript(provider_id)
                requested = True
            self.sleep(3)
            waited += 3
        log.warning("%s: transcript not available", provider_id)
        return [], None

    def _finish(self, store, call_id: str, request: dict, call: dict, summary: dict | None, segments: list[dict]) -> bool:
        result = build_result(call_id, request, call, summary, segments)
        outcome, detail = self.post(f"/internal/calls/{call_id}/result", result)
        if outcome == "ok":
            store.mark_delivered(call_id)
            log.info("%s: result delivered (%s)", call_id, result["outcome"])
            return True
        if outcome == "rejected":
            store.mark_rejected(call_id, f"result {detail}")
        return False


def outcome_of(call: dict) -> tuple[str, str | None]:
    """(outcome, rejection_reason). ClawOps 종료 상태와 종료 사유를 백엔드 outcome으로 바꾼다."""
    status = call.get("status")
    if status == "completed":
        return ("machine" if call.get("answeredBy") == "machine" else "answered"), None
    if status in ("no-answer", "busy"):
        return status.replace("-", "_"), None
    cause = str(call.get("hangupCause") or "")
    if "invalid" in cause or call.get("hangupCauseQ850") in (1, 5, 28):
        return "invalid_number", None
    if status == "rejected":
        # Pressing decline does not prove an explicit request to stop future calls.
        return "rejected", "unknown"
    # failed, canceled: ClawOps·통신망 쪽 문제면 다시 걸어 볼 만하다
    return "rejected", "temporary" if call.get("hangupSource") in ("app", "system", "carrier") else "unknown"


def build_result(call_id: str, request: dict, call: dict, summary: dict | None, segments: list[dict]) -> dict:
    outcome, rejection = outcome_of(call)
    connected = outcome == "answered"
    turns = to_turns(segments) if connected else []
    if connected and turns:
        answers = build_answers(request["questions"], turns)
        consult, times = consult_result(turns, request["questions"])
        disclosure = disclosure_played(turns)
    else:
        reason, detail = ("unknown", "전사를 받지 못해 확인하지 못함") if connected else ("not_asked", NOT_CONNECTED_DETAIL)
        answers = [{**q, "asked": connected, "answered": False, "yes_no": None, "reason": reason, "detail": detail}
                   for q in request["questions"]]
        consult, times, disclosure = None, [], None
    unresolved = [a["question_id"] for a in answers if not a["answered"]]
    core = (summary or {}).get("coreSummary")
    confirmed = len(answers) - len(unresolved)
    return {
        "result_id": f"result_{call_id}",
        "outcome": outcome,
        # 연결이 안 된 통화는 고지, 상담, 지연, 전사를 만들지 않는다 (목업과 같은 규칙)
        "disclosure_played": disclosure if connected else None,
        "consult_accepted": consult if connected else None,
        "available_times": times if connected else [],
        "answers": answers,
        "unresolved": unresolved,
        "summary_text": (str(core)[:2000] if core else
                         (f"{len(answers)}개 중 {confirmed}개 확인" if connected else "연결되지 않아 모든 항목이 미확인")),
        "notes": "실제 통화(ClawOps). 질문별 판정은 전사 규칙 기반",
        "latency": None,
        "duration_sec": int(call.get("duration") or 0) if connected else 0,
        "transcript": [{"speaker": t.speaker, "at_ms": t.at_ms, "text": t.text} for t in turns][:1000],
        "recording_url": None,
        "callback_requested": False,
        "callback_at": None,
        "rejection_reason": rejection if outcome == "rejected" else None,
    }
