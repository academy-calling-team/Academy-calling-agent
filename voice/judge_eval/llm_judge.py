"""통화 전사로 질문별 답을 LLM이 판정한다 (오프라인 평가용, 워커에는 아직 연결하지 않음).

키워드 사전(voice/call_worker/extract.py)의 대안으로 10/28 9주차 회의에서 정한 방향이다.
LLM은 판정과 함께 근거가 된 학원 발화 번호와 원문을 인용해야 하고, 인용이 실제 학원 발화에 없으면
코드가 그 판정을 '미확인'으로 돌린다(지어낸 답이 결과로 나가지 않게).

결과는 extract.build_answers / consult_result 와 같은 모양으로 돌려준다.
"""
import hashlib
import json
import re
from pathlib import Path

import httpx

PROMPT_VERSION = "judge-v1"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

QUESTION_TEXT = {
    "shuttle": "통학 차량이 있는지(있다면 운행 지역·시간)",
    "pickup": "수업 후 픽업을 해 주는지",
    "level_fit": "학생 학년·과목·수준에 맞는 반이 있는지",
    "vacancy": "지금 등록할 자리가 남아 있는지",
    "level_test": "레벨 테스트가 있는지(있다면 언제)",
    "class_time": "수업 요일과 시간",
}

SYSTEM = """당신은 학부모를 대신해 학원에 건 전화의 전사를 읽고, 질문별로 학원이 어떻게 답했는지 판정한다.
전사는 받아쓰기 오류가 있을 수 있다. 화자는 AI(우리 상담원)와 학원 두 명이다.

판정 값(status):
- yes: 학원이 그렇다고 확실히 답함 (예: "네, 두 자리 있어요", "원하시면 해 드릴 수 있어요")
- no: 학원이 아니라고 확실히 답함. 정중한 거절·완곡한 부정도 no다
  (예: "안 될 것 같습니다", "어렵습니다", "따로 안 해 드리고 있어요", "마감이라 대기만 돼요")
- answered: 수업 시간처럼 예/아니오가 아닌 질문에 요일·시각을 구체적으로 답함
- unknown: 모른다, 확인해 보겠다, 반마다 다르다, '아마' 같은 진짜 추측, 질문과 관계없는 대답
- refused: 전화로는 말해 줄 수 없다고 거절함
- not_asked: AI가 그 질문을 하지 않음

규칙:
1. 학원 발화만 근거로 한다. AI가 되짚은 말은 학원이 "네, 맞아요"로 확인한 경우에만 근거가 된다.
2. 학원이 나중에 고쳐 말하면("아, 아니요. 두 자리예요") 마지막으로 확정한 답을 따른다.
3. "아니요"가 말버릇처럼 붙어도 뒤 내용으로 판단한다("아니요, 픽업 해요" → yes).
4. 이중 부정은 풀어서 판단한다("없지는 않아요" → yes).
5. 우리 학생(학년·과목·수준·지역)에게 해당하지 않는다고 하면 그 학생 기준으로 no다
   ("차량은 있는데 중학생은 안 태워요" → no).
6. 애매하면 unknown. 틀린 yes/no보다 unknown이 낫다. 지어내지 않는다.
7. 상담(consult)은 이번 주 학부모 상담 가능 여부다. 가능한 시간은 available_times, 안 되는 시간은
   unavailable_times에 학원이 말한 그대로 짧게 적는다("금토일은 안 될 것 같고 월요일 네 시는 돼요" →
   status yes, available ["월요일 4시"], unavailable ["금·토·일"]). 안 되는 시간만 말하고 가능한 시간을
   말하지 않았으면 unknown이다.
8. yes/no/answered이면 evidence_turns에 근거 학원 발화 번호를, evidence_quote에 그 발화에서 그대로
   옮긴 핵심 구절(10~40자)을 넣는다. unknown/refused/not_asked이면 근거가 있으면 넣고 없으면 비운다.
9. detail은 학부모에게 보여 줄 한 줄 요약(학원 말 기준, 30자 안팎)이다."""

STATUS_Q = ["yes", "no", "answered", "unknown", "refused", "not_asked"]
STATUS_C = ["yes", "no", "unknown", "refused", "not_asked"]


def schema(codes: list[str]) -> dict:
    item = {
        "type": "object", "additionalProperties": False,
        "required": ["question_code", "status", "detail", "evidence_turns", "evidence_quote"],
        "properties": {
            "question_code": {"type": "string", "enum": codes},
            "status": {"type": "string", "enum": STATUS_Q},
            "detail": {"type": "string"},
            "evidence_turns": {"type": "array", "items": {"type": "integer"}},
            "evidence_quote": {"type": "string"},
        },
    }
    consult = {
        "type": "object", "additionalProperties": False,
        "required": ["status", "available_times", "unavailable_times", "evidence_turns", "evidence_quote"],
        "properties": {
            "status": {"type": "string", "enum": STATUS_C},
            "available_times": {"type": "array", "items": {"type": "string"}},
            "unavailable_times": {"type": "array", "items": {"type": "string"}},
            "evidence_turns": {"type": "array", "items": {"type": "integer"}},
            "evidence_quote": {"type": "string"},
        },
    }
    return {"name": "call_judgement", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["answers", "consult"],
        "properties": {"answers": {"type": "array", "items": item}, "consult": consult}}}


def user_message(codes: list[str], turns) -> str:
    qs = "\n".join(f"- {c}: {QUESTION_TEXT[c]}" for c in codes)
    lines = "\n".join(f"[{i}] {'AI' if t.speaker == 'agent' else '학원'}: {t.text}" for i, t in enumerate(turns))
    return f"확인할 질문:\n{qs}\n- consult: 이번 주 학부모 상담 가능 여부와 가능한 시간(항상 확인)\n\n전사:\n{lines}"


def _norm(s: str) -> str:
    return re.sub(r"[\s.,!?~·'\"…]+", "", s)


def grounded(item: dict, turns) -> bool:
    """인용 구절이 지목한 학원 발화 안에 실제로 있는가."""
    idx = [i for i in item.get("evidence_turns", []) if 0 <= i < len(turns) and turns[i].speaker == "academy"]
    quote = _norm(item.get("evidence_quote", ""))
    return bool(idx and quote) and quote in _norm(" ".join(turns[i].text for i in idx))


def call_llm(codes, turns, model, api_key, cache_dir: Path | None = None, timeout=60.0) -> dict:
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_message(codes, turns)}],
            "response_format": {"type": "json_schema", "json_schema": schema(codes)}}
    key = hashlib.sha256(json.dumps([PROMPT_VERSION, body], ensure_ascii=False).encode()).hexdigest()[:24]
    path = cache_dir / f"{key}.json" if cache_dir else None
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    r = httpx.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    out = {"result": json.loads(data["choices"][0]["message"]["content"]), "usage": data.get("usage", {}), "model": data.get("model")}
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def to_contract(questions: list[dict], turns, raw: dict) -> tuple[list[dict], dict]:
    """LLM 결과 → (답변 행들, 상담 결과). 근거가 없는 확정 판정은 미확인으로 돌린다."""
    by_code = {a["question_code"]: a for a in raw.get("answers", [])}
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
