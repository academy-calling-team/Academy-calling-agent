"""통화 전사로 질문별 답을 LLM이 판정한다. 실제 통화 워커(real_call.py)와 오프라인 평가(voice/judge_eval)가 같이 쓴다.
배포 이미지에는 voice/call_worker/만 들어가므로 이 파일은 여기에 둔다.

키워드 사전(voice/call_worker/extract.py)의 대안으로 10/28 9주차 회의에서 정한 방향이다.
LLM은 판정과 함께 근거가 된 학원 발화 번호와 원문을 인용해야 하고, 인용이 실제 학원 발화에 없으면
코드가 그 판정을 '미확인'으로 돌린다(지어낸 답이 결과로 나가지 않게).

결과는 extract.build_answers / consult_result 와 같은 모양으로 돌려준다.

judge-v3 (11/4 10주차 회의 반영)
- 학부모 화면에 판정과 함께 학원 원문과 요약을 같이 보여 준다(멘토 동의). 원문(source_text)은 LLM이 아니라
  코드가 근거 발화 번호로 전사에서 그대로 꺼낸다.
- 요약(detail)에 근거 발화에 없는 숫자·요일이 들어가면 요약을 버리고 인용 원문으로 바꾼다(detail_checked=False).
- 애매한 말투마다 규칙을 덧붙이지 않는다(10주차 멘토 의견). 대신 답의 내용(status)과 학원이 얼마나 확실하게
  말했는지(certainty: definite·guess·deferred)를 따로 받고, 확정이 아니면 코드가 미확인으로 돌린다.
  LLM이 원래 잘하는 '이 사람이 알고 말하나'의 판단을 규칙 없이 쓰고, 정책은 코드 한 곳에 둔다.
"""
import hashlib
import json
import logging
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import httpx

log = logging.getLogger("call_worker")

PROMPT_VERSION = "judge-v3.1"
GROUNDED_MIN = 0.7
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_PACE_SEC = 8              # 평가용: 무료 등급 분당 제한에 맞춘 호출 간격
EVAL_RETRY_WAITS = (0, 30, 60, 90, 120, 180, 240)   # 평가용: 제한에 걸리면 오래 기다려도 됨
WORKER_RETRY_WAITS = (0,)        # 워커용: HTTP 재시도는 하지 않고, 판정 전체 재시도(JUDGE_ATTEMPT_WAITS)로 처리
# 워커 판정 재시도 간격(초). 429·시간 초과·망가진 JSON 등 어떤 실패든 판정을 처음부터 다시 부른다.
# 최악: 4번 × 시간 제한 30초 + 대기 100초 = 약 220초. 전사 대기(최대 180초)와 합쳐도 백엔드 결과 대기 600초 안이다.
JUDGE_ATTEMPT_WAITS = (0, 10, 30, 60)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

QUESTION_TEXT = {
    "shuttle": "통학 차량이 있는지(있다면 운행 지역·시간)",
    "pickup": "수업 후 픽업을 해 주는지",
    "level_fit": "학생 학년·과목·수준에 맞는 반이 있는지(자리 여부는 별개)",
    "vacancy": "지금 등록할 자리가 남아 있는지",
    "level_test": "레벨 테스트가 있는지(있다면 언제)",
    "class_time": "수업 요일과 시간",
}

SYSTEM = """당신은 학부모를 대신해 학원에 건 전화의 전사를 읽고, 질문별로 학원이 어떻게 답했는지 판정한다.
전사는 받아쓰기 오류가 있을 수 있다. 화자는 AI(우리 상담원)와 학원 두 명이다. 전사에 없는 내용을 지어내지 않는다.

판정 값(status):
- yes: 질문이 묻는 사실을 학원이 그렇다고 답함. 조건이 붙어도 사실 자체를 인정하면 yes
- no: 학원이 아니라고 답함. 정중한 거절, 완곡한 표현, 부정어 없이 뜻으로 거절한 경우도 no
- answered: 수업 시간 질문에 요일이나 시각을 구체적으로 답함
- unknown: 모른다, 정해지지 않았다, 질문과 관계없는 대답, 답이 없음
- refused: 전화로는 알려 줄 수 없다고 거절함
- not_asked: AI가 그 질문을 하지 않음

확실성(certainty): status와 따로, 학원이 그 답을 얼마나 확실하게 말했는지
- definite: 학원이 사실을 알고 말함. 정중하거나 부드럽게 돌려 말해도 뜻이 분명하면 definite
- guess: 학원 스스로 확실하지 않다고 드러냄. 짐작으로 말함
- deferred: 다른 사람(원장님 등)이나 나중 확인으로 답을 넘김. 앞에 답을 말했어도 확정을 넘기면 deferred
status는 학원이 말한 내용대로 고르고, 확실성으로 status를 바꾸지 않는다. 답을 주지 않고 다른 사람이나 나중 확인으로 넘겼으면 status=unknown, certainty=deferred로 둔다. 단순히 모르거나 답이 없는 경우와 refused·not_asked는 definite로 둔다.

규칙:
1. 각 질문은 그 질문이 묻는 사실만 판정한다. 다른 사실로 답을 뒤집지 않는다. 예를 들어 '맞는 반이 있는지'는 반의 존재를 묻는 것이고, 자리가 있는지는 별개다.
2. 학원 발화의 뜻으로 판단한다. 부정어가 있어도 전체 뜻이 긍정이면 yes이고, 말 앞의 '네', '아니요'가 말버릇이면 뒤 내용을 따른다.
3. AI가 되짚은 말은 학원이 맞다고 확인했을 때만 근거가 된다. 학원이 나중에 고쳐 말하면 마지막으로 확정한 답을 따른다.
4. 학생 조건(학년·과목·수준·지역)이 전사에 나오고, 학원이 그 학생에게는 해당하지 않는다고 하면 no다.
5. 무엇을 말했는지가 애매하면 unknown. 틀린 yes/no보다 unknown이 낫다.
6. 상담(consult)은 이번 주 학부모 상담 가능 여부다. 가능한 때를 하나라도 말하면 yes이고 available_times에 적는다. 안 된다고 한 때는 unavailable_times에 적는다. 이번 주 전체가 안 된다고 하면 no다. 일부 시간만 안 된다고 하고 가능한 때를 말하지 않으면 unknown이다.
7. yes/no/answered 또는 guess/deferred이면 evidence_turns에 근거 학원 발화 번호를, evidence_quote에 그 발화의 핵심 구절을 넣는다. 인용은 전사 글자 그대로 복사한다. 오타도 고치지 않고, 번역하거나 다시 쓰지 않는다.
8. detail은 학부모에게 보여 줄 한 줄 요약이다(한국어, 학원 말 기준, 30자 안팎). 학원 원문은 화면에 따로 나가므로 요약은 짧게 쓴다.
9. detail과 available_times에는 학원이 말한 숫자·요일·시각만 쓴다. 숫자는 아라비아 숫자로 바꿔 써도 되지만, 학원이 말하지 않은 오전·오후, 날짜, 인원, 금액을 덧붙이지 않는다."""

CERTAINTY = ["definite", "guess", "deferred"]

STATUS_YN = ["yes", "no", "unknown", "refused", "not_asked"]
STATUS_TIME = ["answered", "unknown", "refused", "not_asked"]


def schema(codes: list[str]) -> dict:
    def item(enum):
        return {"type": "object", "additionalProperties": False,
                "required": ["status", "certainty", "detail", "evidence_turns", "evidence_quote"],
                "properties": {"status": {"type": "string", "enum": enum},
                               "certainty": {"type": "string", "enum": CERTAINTY}, "detail": {"type": "string"},
                               "evidence_turns": {"type": "array", "items": {"type": "integer"}},
                               "evidence_quote": {"type": "string"}}}
    consult = {
        "type": "object", "additionalProperties": False,
        "required": ["status", "certainty", "available_times", "unavailable_times", "evidence_turns", "evidence_quote"],
        "properties": {
            "status": {"type": "string", "enum": STATUS_YN},
            "certainty": {"type": "string", "enum": CERTAINTY},
            "available_times": {"type": "array", "items": {"type": "string"}},
            "unavailable_times": {"type": "array", "items": {"type": "string"}},
            "evidence_turns": {"type": "array", "items": {"type": "integer"}},
            "evidence_quote": {"type": "string"},
        },
    }
    answers = {c: item(STATUS_TIME if c == "class_time" else STATUS_YN) for c in codes}
    return {"name": "call_judgement", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["answers", "consult"],
        "properties": {"answers": {"type": "object", "additionalProperties": False, "required": codes, "properties": answers},
                       "consult": consult}}}


def user_message(codes: list[str], turns) -> str:
    qs = "\n".join(f"- {c}: {QUESTION_TEXT[c]}" for c in codes)
    lines = "\n".join(f"[{i}] {'AI' if t.speaker == 'agent' else '학원'}: {t.text}" for i, t in enumerate(turns))
    return f"확인할 질문:\n{qs}\n- consult: 이번 주 학부모 상담 가능 여부와 가능한 시간(항상 확인)\n\n전사:\n{lines}"


def _norm(s: str) -> str:
    return re.sub(r"[\s.,!?~·'\"…]+", "", s)


def grounded(item: dict, turns) -> bool:
    """인용 구절이 지목한 학원 발화 안에 실제로 있는가. 전사의 받아쓰기 오류를 LLM이 고쳐 옮길 수 있어
    완전 일치 대신 글자의 GROUNDED_MIN 이상이 순서대로 맞으면 인정한다(10/13 전사 '저 7시터' → 인용 '저녁 7시부터')."""
    idx = [i for i in item.get("evidence_turns", []) if 0 <= i < len(turns) and turns[i].speaker == "academy"]
    quote = _norm(item.get("evidence_quote", ""))
    if not idx or not quote:
        return False
    said = _norm(" ".join(turns[i].text for i in idx))
    if quote in said:
        return True
    matched = sum(m.size for m in SequenceMatcher(None, quote, said, autojunk=False).get_matching_blocks())
    return matched / len(quote) >= GROUNDED_MIN


CONFIRM_MAX = 6   # "네 맞습니다"처럼 내용 없이 확인만 한 학원 발화의 글자 수(공백·문장부호 뺀 길이)


def _evidence(item: dict, turns) -> list[int]:
    return sorted({i for i in item.get("evidence_turns", []) if 0 <= i < len(turns) and turns[i].speaker == "academy"})


def _prev_agent(i: int, turns) -> int | None:
    j = i - 1
    while j >= 0 and turns[j].speaker != "agent":
        j -= 1
    return j if j >= 0 else None


def source_text(item: dict, turns) -> str:
    """근거로 지목한 학원 발화를 전사 그대로 이어 붙인다. 학부모 화면의 '학원 원문'.
    학원이 "네 맞습니다"처럼 확인만 했으면 그 앞의 AI 되짚기를 함께 보여 준다(무엇을 확인했는지 알 수 있게)."""
    parts = []
    for i in _evidence(item, turns):
        j = _prev_agent(i, turns)
        if len(_norm(turns[i].text)) <= CONFIRM_MAX and j is not None:
            parts.append(f"(AI: {turns[j].text})")
        parts.append(turns[i].text)
    return " / ".join(parts)


def fact_source(item: dict, turns) -> str:
    """요약 사실 검사의 기준 글. 근거 학원 발화와 그 바로 앞 AI 발화(되짚기·질문)를 합친다.
    규칙 3에 따라 학원이 확인한 되짚기는 근거가 되고, 받아쓰기가 끊긴 학원 발화('수요일 오')를 되짚기가 보완한다."""
    idx = set()
    for i in _evidence(item, turns):
        idx.add(i)
        j = _prev_agent(i, turns)
        if j is not None:
            idx.add(j)
    return " ".join(turns[i].text for i in sorted(idx))


# 한국어 수 표현 → 숫자. 받아쓰기는 "일곱 시", "두 자리", "여섯 시 반"처럼 한글로, 요약은 "7시"처럼 숫자로 쓰기 쉽다
_NATIVE = {"열한": 11, "열하나": 11, "열두": 12, "열둘": 12, "열": 10, "한": 1, "하나": 1, "두": 2, "둘": 2,
           "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
_SINO = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9, "십": 10,
         "이십": 20, "삼십": 30, "사십": 40, "오십": 50}
_COUNTER = r"\s?(?:시(?![간험작])|자|석|명|분|호차|개|번|학년|살|대|층|주)"   # '자': 받아쓰기가 '두 자리'를 '두자'로 자름
_NATIVE_RE = re.compile(rf"(?<![가-힣])({'|'.join(sorted(_NATIVE, key=len, reverse=True))}){_COUNTER}")
_SINO_RE = re.compile(rf"(?<![가-힣])({'|'.join(sorted(_SINO, key=len, reverse=True))})\s?(?:분|호차|학년|층)")
_DAY = "월화수목금토일"
_AFTER_DAY = r"(?=[은는이가을를에랑과와도만요]|[^가-힣]|$)"   # 요일 묶음 뒤에 붙는 조사(금토일은, 화목에)
_DAY_RE = re.compile(rf"([{_DAY}])요일|(?<![가-힣])([{_DAY}]{{2,}}){_AFTER_DAY}")


def numbers(s: str) -> set[int]:
    s = re.sub(r"[초중고]\s?\d", "", s)   # 학생 학년(중2)은 AI 질문에서 온 말이라 뺀다
    out = {int(n) for n in re.findall(r"\d+", s)}
    out |= {_NATIVE[m] for m in _NATIVE_RE.findall(s)} | {_SINO[m] for m in _SINO_RE.findall(s)}
    if re.search(r"시\s?반", s):
        out.add(30)
    if re.search(r"한두|한\s?두", s):
        out |= {1, 2}
    return out - {0}


def weekdays(s: str) -> set[str]:
    s = re.sub(rf"(?<=[{_DAY}])\s?[·,/]\s?(?=[{_DAY}]{_AFTER_DAY})", "", s)   # 화·목, 화, 목요 → 화목
    s = re.sub(rf"(?<![가-힣])([{_DAY}])(?=\s?\d)", r"\1요일", s)          # 토 10:00 → 토요일 10:00
    out = set()
    for one, run in _DAY_RE.findall(s):
        out |= set(one or run)
    return out


def facts_ok(detail: str, source: str) -> bool | None:
    """요약의 숫자·요일이 모두 기준 글에 있는가. 오후 시각(19시)은 원문의 7시로도 인정한다.
    근거 발화가 없으면(미확인 등) 비교할 것이 없어 None."""
    if not source.strip():
        return None
    have = numbers(source)
    nums_ok = all(n in have or (13 <= n <= 23 and n - 12 in have) for n in numbers(detail))
    return nums_ok and weekdays(detail) <= weekdays(source)


def _time_phrase(text: str) -> str:
    text = _NATIVE_RE.sub(lambda m: str(_NATIVE[m[1]]) + m[0][len(m[1]):], text)
    return re.sub(r"\s+", "", text)


def _supported_times(times: list[str], unavailable: list[str], item: dict, turns) -> list[str]:
    replies = [_time_phrase(turns[i].text) for i in _evidence(item, turns)]
    unavailable_phrases = {_time_phrase(value) for value in unavailable}
    supported = []
    for value in times:
        phrase = _time_phrase(value)
        if not phrase or phrase in unavailable_phrases:
            continue
        # Match the day and time together in one academy reply. A bare hour cannot match a partial time.
        end = r"(?!\d|반|간|험|작)" if phrase.endswith("시") else r"(?!\d)"
        if any(re.search(r"(?<!\d)" + re.escape(phrase) + end, reply) for reply in replies):
            supported.append(value)
    return supported


def _post_gemini(codes, turns, model, api_key, timeout, pace_sec, retry_waits):
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": user_message(codes, turns)}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "responseJsonSchema": schema(codes)["schema"]}}
    time.sleep(pace_sec)
    for wait in retry_waits:  # 제한(429)이나 일시 오류면 기다렸다 다시 부른다
        time.sleep(wait)
        r = httpx.post(GEMINI_URL.format(model=model), json=body, headers={"x-goog-api-key": api_key}, timeout=timeout)
        if r.status_code not in (429, 500, 503):
            break
    if r.status_code >= 300:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:800]}")
    data = r.json()
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    u = data.get("usageMetadata", {})
    return {"result": json.loads(text), "model": data.get("modelVersion", model),
            "usage": {"prompt_tokens": u.get("promptTokenCount", 0), "completion_tokens": u.get("candidatesTokenCount", 0)}}


def _post_openai(codes, turns, model, api_key, timeout, pace_sec, retry_waits):
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message(codes, turns)}],
            "response_format": {"type": "json_schema", "json_schema": schema(codes)}}
    r = httpx.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return {"result": json.loads(data["choices"][0]["message"]["content"]), "usage": data.get("usage", {}), "model": data.get("model")}


def call_llm(codes, turns, model, api_key, cache_dir: Path | None = None, timeout=120.0,
             pace_sec: float = 0, retry_waits=WORKER_RETRY_WAITS) -> dict:
    key = hashlib.sha256(json.dumps([PROMPT_VERSION, model, SYSTEM, user_message(codes, turns), schema(codes)], ensure_ascii=False).encode()).hexdigest()[:24]
    path = cache_dir / f"{key}.json" if cache_dir else None
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    post = _post_gemini if model.startswith("gemini") else _post_openai
    out = post(codes, turns, model, api_key, timeout, pace_sec, retry_waits)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


UNSURE_LABEL = {"guess": "학원이 확실하지 않다고 함", "deferred": "학원이 다른 분 확인이 필요하다고 함"}


def settle(st: str, certainty: str) -> tuple[str, str | None]:
    """확실성 정책을 한 곳에 둔다. 학원이 확정하지 않은 yes/no/answered는 미확인으로 돌리고,
    학원이 기운 쪽(leaning)은 따로 남긴다. 계약에서는 reason='uncertain'으로 보낸다(11/8 backend 반영)."""
    if st in ("yes", "no", "answered") and certainty in UNSURE_LABEL:
        return "unknown", st
    return st, None


def to_contract(questions: list[dict], turns, raw: dict) -> tuple[list[dict], dict]:
    """LLM 결과 → (답변 행들, 상담 결과). 근거가 없거나 학원이 확정하지 않은 판정은 미확인으로 돌린다."""
    by_code = raw.get("answers", {})
    answers = []
    for q in questions:
        a = by_code.get(q["question_code"], {"status": "unknown", "detail": "판정 누락", "evidence_turns": [], "evidence_quote": ""})
        st = a["status"]
        has_evidence = grounded(a, turns)
        if st in ("yes", "no", "answered") and not has_evidence:
            st, a = "unknown", {**a, "detail": f"근거 확인 실패: {a['detail']}"}
        certainty = a.get("certainty", "definite")
        st, leaning = settle(st, certainty)
        uncertain = st == "unknown" and certainty in UNSURE_LABEL and has_evidence
        src = source_text(a, turns) if has_evidence else ""
        checked = facts_ok(a["detail"], fact_source(a, turns))
        detail = a["detail"] if checked is not False else (a.get("evidence_quote") or src)
        if uncertain:
            detail = f"{UNSURE_LABEL[certainty]}: {detail}"
        row = {**q, "asked": st != "not_asked", "answered": st in ("yes", "no", "answered"),
               "yes_no": {"yes": True, "no": False}.get(st), "reason": None, "detail": detail[:500] or "대답을 알아듣지 못함",
               "status": st, "certainty": certainty, "leaning": leaning, "source_text": src[:2000] if src.strip() and st != "not_asked" else None,
               "detail_checked": checked}
        if not row["answered"]:
            row["reason"] = "uncertain" if uncertain else {"refused": "refused", "not_asked": "not_asked"}.get(st, "unknown")
        answers.append(row)
    c = raw.get("consult", {})
    st = c.get("status", "unknown")
    if st in ("yes", "no") and not grounded(c, turns):
        st = "unknown"
    certainty = c.get("certainty", "definite")
    st, leaning = settle(st, certainty)
    src = source_text(c, turns)
    times = c.get("available_times", []) if st == "yes" else []
    unavailable = c.get("unavailable_times", [])
    checks = [facts_ok(t, fact_source(c, turns)) for t in times + unavailable]
    checked = False if False in checks else (None if None in checks else True)
    consult = {"status": st, "consult_accepted": {"yes": True, "no": False}.get(st),
               "available_times": _supported_times(times, unavailable, c, turns), "unavailable_times": unavailable,
               "certainty": certainty, "leaning": leaning, "source_text": src[:500], "detail_checked": checked}
    return answers, consult


# backend/contracts.py AnswerInput의 필드 (StrictModel extra='forbid'라 그 밖의 키를 보내면 거부됨)
ANSWER_FIELDS = ("question_id", "question_code", "asked", "answered", "yes_no", "reason", "detail", "source_text")


def contract_answers(rows: list[dict]) -> list[dict]:
    """to_contract의 답변 행에서 평가용 필드(status·certainty·leaning·detail_checked)를 빼고 계약 필드만 남긴다."""
    return [{k: r[k] for k in ANSWER_FIELDS if k in r} for r in rows]


class LLMJudge:
    """워커가 쓰는 판정기. judge(questions, turns) → (계약 답변 행들, 상담 결과).
    실패하면 attempt_waits 간격으로 판정 전체를 다시 부른다. 모두 실패하면 마지막 예외를 올리고,
    그때 보낼 결과는 부르는 쪽(real_call.judge_answers)이 정한다."""

    def __init__(self, model: str, api_key: str, timeout: float = 30.0,
                 attempt_waits=JUDGE_ATTEMPT_WAITS, sleep=time.sleep):
        self.model, self.api_key, self.timeout = model, api_key, timeout
        self.attempt_waits, self.sleep = attempt_waits, sleep

    def __call__(self, questions: list[dict], turns) -> tuple[list[dict], dict]:
        codes = [q["question_code"] for q in questions]
        started = time.monotonic()
        error = None
        for n, wait in enumerate(self.attempt_waits, 1):
            self.sleep(wait)
            try:
                out = call_llm(codes, turns, self.model, self.api_key, timeout=self.timeout)
                rows, consult = to_contract(questions, turns, out["result"])
            except Exception as exc:  # 네트워크·제한·JSON·스키마 오류 모두 다시 시도
                error = exc
                log.warning("LLM judge attempt %d/%d failed: %s", n, len(self.attempt_waits), str(exc)[:300])
            else:
                log.info("LLM judge %s (%s) took %.1fs (%d attempt(s))",
                         self.model, PROMPT_VERSION, time.monotonic() - started, n)
                return contract_answers(rows), consult
        log.error("LLM judge %s (%s) gave up after %d attempt(s), %.1fs",
                  self.model, PROMPT_VERSION, len(self.attempt_waits), time.monotonic() - started)
        raise error
