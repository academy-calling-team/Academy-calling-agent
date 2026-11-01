"""통화 전사로 질문별 답을 LLM이 판정한다 (오프라인 평가용, 워커에는 아직 연결하지 않음).

키워드 사전(voice/call_worker/extract.py)의 대안으로 10/28 9주차 회의에서 정한 방향이다.
LLM은 판정과 함께 근거가 된 학원 발화 번호와 원문을 인용해야 하고, 인용이 실제 학원 발화에 없으면
코드가 그 판정을 '미확인'으로 돌린다(지어낸 답이 결과로 나가지 않게).

결과는 extract.build_answers / consult_result 와 같은 모양으로 돌려준다.
"""
import hashlib
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import httpx

PROMPT_VERSION = "judge-v2"
GROUNDED_MIN = 0.7
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_PACE_SEC = 8
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
- unknown: 모른다, 확인이 필요하다, 정해지지 않았다, 진짜 추측, 질문과 관계없는 대답
- refused: 전화로는 알려 줄 수 없다고 거절함
- not_asked: AI가 그 질문을 하지 않음

규칙:
1. 각 질문은 그 질문이 묻는 사실만 판정한다. 다른 사실로 답을 뒤집지 않는다. 예를 들어 '맞는 반이 있는지'는 반의 존재를 묻는 것이고, 자리가 있는지는 별개다.
2. 학원 발화의 뜻으로 판단한다. 부정어가 있어도 전체 뜻이 긍정이면 yes이고, 말 앞의 '네', '아니요'가 말버릇이면 뒤 내용을 따른다.
3. AI가 되짚은 말은 학원이 맞다고 확인했을 때만 근거가 된다. 학원이 나중에 고쳐 말하면 마지막으로 확정한 답을 따른다.
4. 학생 조건(학년·과목·수준·지역)이 전사에 나오고, 학원이 그 학생에게는 해당하지 않는다고 하면 no다.
5. 애매하면 unknown. 틀린 yes/no보다 unknown이 낫다.
6. 상담(consult)은 이번 주 학부모 상담 가능 여부다. 가능한 때를 하나라도 말하면 yes이고 available_times에 적는다. 안 된다고 한 때는 unavailable_times에 적는다. 이번 주 전체가 안 된다고 하면 no다. 일부 시간만 안 된다고 하고 가능한 때를 말하지 않으면 unknown이다.
7. yes/no/answered이면 evidence_turns에 근거 학원 발화 번호를, evidence_quote에 그 발화의 핵심 구절을 넣는다. 인용은 전사 글자 그대로 복사한다. 오타도 고치지 않고, 번역하거나 다시 쓰지 않는다.
8. detail은 학부모에게 보여 줄 한 줄 요약이다(한국어, 학원 말 기준, 30자 안팎)."""

STATUS_YN = ["yes", "no", "unknown", "refused", "not_asked"]
STATUS_TIME = ["answered", "unknown", "refused", "not_asked"]


def schema(codes: list[str]) -> dict:
    def item(enum):
        return {"type": "object", "additionalProperties": False,
                "required": ["status", "detail", "evidence_turns", "evidence_quote"],
                "properties": {"status": {"type": "string", "enum": enum}, "detail": {"type": "string"},
                               "evidence_turns": {"type": "array", "items": {"type": "integer"}},
                               "evidence_quote": {"type": "string"}}}
    consult = {
        "type": "object", "additionalProperties": False,
        "required": ["status", "available_times", "unavailable_times", "evidence_turns", "evidence_quote"],
        "properties": {
            "status": {"type": "string", "enum": STATUS_YN},
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


def _post_gemini(codes, turns, model, api_key, timeout):
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": user_message(codes, turns)}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "responseJsonSchema": schema(codes)["schema"]}}
    time.sleep(GEMINI_PACE_SEC)  # 무료 등급 분당 제한에 맞춰 호출 간격을 둔다
    for wait in (0, 30, 60, 90, 120, 180, 240):  # 제한에 걸리면 기다렸다 다시 부른다
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


def _post_openai(codes, turns, model, api_key, timeout):
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message(codes, turns)}],
            "response_format": {"type": "json_schema", "json_schema": schema(codes)}}
    r = httpx.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return {"result": json.loads(data["choices"][0]["message"]["content"]), "usage": data.get("usage", {}), "model": data.get("model")}


def call_llm(codes, turns, model, api_key, cache_dir: Path | None = None, timeout=120.0) -> dict:
    key = hashlib.sha256(json.dumps([PROMPT_VERSION, model, SYSTEM, user_message(codes, turns), schema(codes)], ensure_ascii=False).encode()).hexdigest()[:24]
    path = cache_dir / f"{key}.json" if cache_dir else None
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    post = _post_gemini if model.startswith("gemini") else _post_openai
    out = post(codes, turns, model, api_key, timeout)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def to_contract(questions: list[dict], turns, raw: dict) -> tuple[list[dict], dict]:
    """LLM 결과 → (답변 행들, 상담 결과). 근거가 없는 확정 판정은 미확인으로 돌린다."""
    by_code = raw.get("answers", {})
    answers = []
    for q in questions:
        a = by_code.get(q["question_code"], {"status": "unknown", "detail": "판정 누락", "evidence_turns": [], "evidence_quote": ""})
        st = a["status"]
        if st in ("yes", "no", "answered") and not grounded(a, turns):
            st, a = "unknown", {**a, "detail": f"근거 확인 실패: {a['detail']}"}
        row = {**q, "asked": st != "not_asked", "answered": st in ("yes", "no", "answered"),
               "yes_no": {"yes": True, "no": False}.get(st), "reason": None, "detail": a["detail"][:500] or "대답을 알아듣지 못함",
               "status": st}
        if not row["answered"]:
            row["reason"] = {"refused": "refused", "not_asked": "not_asked"}.get(st, "unknown")
        answers.append(row)
    c = raw.get("consult", {})
    st = c.get("status", "unknown")
    if st in ("yes", "no") and not grounded(c, turns):
        st = "unknown"
    consult = {"status": st, "consult_accepted": {"yes": True, "no": False}.get(st),
               "available_times": c.get("available_times", []) if st == "yes" else [],
               "unavailable_times": c.get("unavailable_times", [])}
    return answers, consult
