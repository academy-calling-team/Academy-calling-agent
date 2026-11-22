"""계층 판정(tiered-v2.1-spec). 워커가 LLM_JUDGE_MODEL=tiered일 때 쓴다.

구성 (11/18 사람 작성 105사례 평가에서 고른 v2_route_na: 주 정확도 94.2%, 비싼 오류 3회 모두 0)
  1차 분류   gpt-5.6-luna와 gemini-3.5-flash-lite를 같은 프롬프트로 병렬 호출
  코드 검사  인용 불일치 · 1차 signal · 상담 일부 요일만 · 정정 가능성 · 상담 yes인데 가능 시간 없음
             · 두 1차의 값이 다름 (한쪽이 not_asked인 불일치는 제외: 2차가 묻지 않은 질문을 추론으로 채운 일이 있음)
  2차 검토   검사에 걸린 항목만 gpt-5.6-terra가 항목별로 다시 판정
  요약       gpt-5.6-luna가 학부모용 한 줄 요약. 판정은 바꾸지 않음
  코드 마무리 인용 확인 실패 → unknown, 짐작·미룸 → unknown(uncertain)

규칙은 '판정 값 목록 개정안'(11/10 강유준) 3·5·6번에서 가져왔다. 사람 시험 사례 문장은 쓰지 않는다.
지금 계약·화면으로 보낼 때(개정안 10번):
  redirect → reason=refused, detail에 '안내받은 경로: …' (프론트가 '직접 확인 필요'와 안내 문구로 보여 줌)
  조건     → detail 첫 줄 '조건: …' (프론트가 '조건부 가능'으로 보여 줌) + condition 필드
"""
import datetime as dt
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import httpx

from llm_judge import (GEMINI_URL, JUDGE_ATTEMPT_WAITS, OPENAI_URL, UNSURE_LABEL, _evidence, _norm, _supported_times,
                       fact_source, facts_ok, grounded, source_text)

log = logging.getLogger("call_worker")
VERSION = "tiered-v2.1-spec"
SEOUL = ZoneInfo("Asia/Seoul")

# USD per 1M tokens (입력, 출력). 출력에는 추론 토큰 포함. 로그의 비용 추정에만 쓴다 (11/18 기준)
PRICES = {"gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-terra": (2.00, 12.00), "gemini-3.5-flash-lite": (0.30, 2.50)}

STATUS = ["yes", "no", "answered", "unknown", "redirect", "not_asked"]
SIGNAL = ["none", "hedge", "deferred", "corrected", "partial_week", "conditional", "off_topic"]

# 개정안 3번 표 + 11/16 방향 결정(등원·하원)
QUESTION = {
    "shuttle": "등원 차량이 학생 거주 지역(질문별 위치)에서 학생을 태워 학원으로 데려옴. 차량이 있어도 그 지역에 안 가면 no. 하원만 된다는 답은 no. 그 지역에 가는지 확인하지 않고 차량이 있다고만 하면 unknown",
    "pickup": "수업이 끝난 뒤 학원이 학생을 질문별 위치까지 데려다줌(사람이든 차량이든). 등원만 된다는 답은 no. 그 위치까지 가는지 확인하지 않고 하원 차량이 있다고만 하면 unknown",
    "level_fit": "학생 학년·과목·수준에 맞춰 지금 들어갈 수 있는 반이 있음. 자리가 남았는지는 별개",
    "vacancy": "질문 기간(없으면 통화 시점)에 등록할 자리가 있음",
    "level_test": "등록 전 레벨 테스트가 있음. 필수든 선택이든",
    "class_time": "수업 요일과 시간(값은 answered/redirect/unknown/not_asked)",
}
CONSULT = "질문 기간(기본: 이번 주 남은 날)에 학부모 상담 일정을 잡을 수 있음. 상담 제도가 있다는 말만으로는 yes 아님"

RULES = """판정 순서(위에서부터 처음 해당하는 값에서 멈춘다):
1. 물었나: AI가 이 질문을 묻지 않았고 학원도 먼저 말하지 않았으면 not_asked. 학원이 먼저 답했으면 물은 것으로 본다.
2. 확실한 답인가: 학원이 질문별 뜻에 대해 되는지 안 되는지 확실히 말했으면 yes 또는 no. 수업 시간은 요일·시각을 말했으면 answered.
   - 돌려 말한 답은 전사에 보이는 근거로 가린다. 물은 것과 같이 성립할 수 없는 사실을 말하면 no(예: 차량 질문에 "다들 부모님이 직접 데려다주세요"). 물은 것이 있다는 전제로 구체적으로 안내하면 yes(예: 레벨 테스트 질문에 "등록 전에 30분 정도 문제 풀어 보고 반 정해 드려요").
   - '안 돼요'라는 말 없이 이유만 말해도 no다. 서비스 대신 다른 방법(다른 교통편, 다른 반, 연락 방법)을 같이 제안해도 no다.
   - 모른다는 신호가 있으면 확실한 답이 아니다: 아마, 확실하진 않은데, 제가 알기로는, 확인해 봐야, 잘 모르겠는데, 담당이 아니라서.
   - '~것 같아요'는 붙은 자리로 가린다. 학원이 스스로 정하는 일(제안, 안내) 끝에 붙으면 공손한 말투라 확실한 답이고, 확인 안 된 사실(기억, 다른 사람 일정) 끝에 붙으면 추측이다.
   - 첫머리의 '네', '예'는 맞장구일 수 있다. 뒤에 보류, 되묻기, 말 흐림이 오면 답으로 세지 않는다.
   - 경로를 부정한 말('전화로는 안 돼요', '여기서는 확인이 안 돼요')은 질문별 뜻에 대한 답이 아니다. 다음 단계로 넘긴다.
   - AI가 되짚은 말은 학원이 맞다고 했을 때만 근거다. 학원이 앞말을 고치면 마지막에 확정한 답을 따른다.
3. 학부모가 움직여야 하나: 답 대신 학부모가 답을 확인할 다른 경로(방문, 레벨 테스트, 예약 사이트, 홈페이지)를 안내했으면 redirect. 학부모가 정보(성적, 학년 등)를 더 알려 주면 답할 수 있다고 한 것도 redirect다. 서비스 대신 다른 방법을 제안한 것은 redirect가 아니다.
4. 나머지는 unknown: 모름, 추측만 함, 알아보고 연락 주겠다고 함, 말을 흐림, 통화가 끊김.
애매할 때: 2단계에서 확실한지 애매하면 3·4단계로 넘긴다. 3단계와 4단계 사이가 애매하면 다음 할 일이 누구 몫인지 본다. 학부모 몫이면 redirect, 학원 몫이면 unknown이다('알아보고 연락드릴게요', '문자로 보내드릴게요'는 학원 몫). 답 없이 다시 전화해 달라고만 했으면, 학부모가 답을 확인할 경로가 아니므로 unknown이다. 안 된다고 답한 뒤 다시 연락하라고 한 것은 no다.

기간: 질문에 기간이 있으면 그 기간, 없으면 통화 시점이 기준이다. AI가 특정 날을 물었으면 그 날이 기간이다.
- 그 기간에 안 되면 no다. 그 뒤 이야기(다음 달 개강 예정, 대기 등록 가능)는 yes의 근거가 아니다.
- 상담의 기본 기간은 메시지에 적힌 '이번 주 남은 날'이다. 오늘은 통화 시각 이후만 든다.
- 학원이 주말을 먼저 말하면 주말도 기간에 넣는다. 그 주말에 된다고 하면 평일이 안 되더라도 yes다.
- 학원이 안 되는 날을 골라 말했을 때 남은 날을 다 덮으면 no, 언급 안 된 날이 하루라도 남으면 unknown이다. 기간을 통째로 말한 답('이번 주는 안 돼요')은 no다.

조건: 된다고 했지만 조건이 붙었으면 yes로 두고 condition에 조건을 짧게 적는다.
- 학생 정보(거주 지역, 학년, 과목, 수준)로 따질 수 있는 조건은 직접 따져서 yes나 no로 정하고 condition에 적지 않는다.
- 학생 정보로 따질 수 없는 조건만 적는다(예: "수업 끝나는 시간이 차량 시간이랑 맞으면 태워 드려요").
- 가능 여부를 바꾸지 않는 정보(선택 사항이다, 비용이 따로 든다)는 조건이 아니다.
- 조건이 없거나 값이 yes가 아니면 condition은 빈 문자열이다.

섞인 답: 학원이 다른 질문의 답까지 같이 말하면, 그 질문이 확인할 질문 목록에 있을 때만 그 질문에도 기록하고 물은 것으로 본다. 그 질문의 뜻에 직접 답한 말만 기록하고, 다른 질문의 답에서 미루어 채우지 않는다(예: 반이 없다는 말로 자리를 no로 채우지 않는다).
상담(consult): 가능한 때를 말하면 yes이고 available_times에, 안 되는 때는 unavailable_times에 학원이 말한 그대로 적는다."""

TRIAGE_SYSTEM = f"""당신은 학부모를 대신해 학원에 건 전화의 전사를 읽고, 질문마다 학원이 무엇을 말했는지 분류한다.
전사는 받아쓰기 오류가 있을 수 있다. 화자는 AI(우리 상담원)와 학원이다. 전사에 없는 내용을 지어내지 않는다.
이 단계는 분류만 한다. 요약 문장은 쓰지 않는다. 판정은 학원의 말이 '확인할 질문'에 적힌 질문별 뜻에 대한 답인지로 본다.

{RULES}

signal: 2차 검토가 필요한 신호. 해당하는 것이 없으면 none.
- hedge: 학원이 짐작으로 말함
- deferred: 다른 사람이나 나중 확인으로 답을 넘김
- corrected: 학원이 앞에 한 말을 고쳤거나, AI 되짚기에 '아니요'라고 함
- partial_week: 상담에서 안 되는 날만 골라 말함
- conditional: 가능하다고 했지만 학생 정보로 따질 수 없는 조건이 붙음
- off_topic: 대답이 질문과 다른 이야기로 보임
status는 학원이 말한 내용대로 고르고, signal 때문에 status를 바꾸지 않는다.

근거: yes/no/answered/redirect이거나 signal이 none이 아니면 evidence_turns에 학원 발화 번호를, evidence_quote에 그 발화의 핵심 구절을 넣는다.
인용은 전사 글자 그대로 복사한다. 오타도 고치지 않는다."""

REVIEW_SYSTEM = f"""당신은 학원 통화 전사에서 한 가지 질문의 답을 다시 판정하는 검토자다. 1차 분류에서 이 항목이 애매하다고 표시됐다.
전사에 없는 내용을 지어내지 않는다. 판정은 학원의 말이 질문별 뜻에 대한 답인지로 본다.
값(status): yes / no / answered(수업 시간만) / unknown / redirect / not_asked. 애매하면 덜 위험한 쪽(미확정)을 고른다.

{RULES}

certainty: definite(확정) / guess(짐작) / deferred(미룸). 짐작이면 status는 unknown, certainty는 guess. 미룸이면 status는 unknown, certainty는 deferred. status가 unknown이 아니면 definite다.
근거: evidence_turns에 학원 발화 번호를, evidence_quote에 핵심 구절을 글자 그대로 넣는다.
reason_text: 왜 이렇게 판정했는지 한 문장(학부모에게 보일 수 있는 말로)."""

SUMMARY_SYSTEM = """당신은 학원 통화 결과를 학부모에게 보여 줄 한 줄 요약으로 쓰는 작성자다. 판정은 이미 끝났고 바꾸지 않는다.
항목마다 판정 값과 학원 원문이 주어진다. 원문에 있는 내용만 쓰고, 원문에 없는 숫자·요일·시각·오전/오후·인원·금액을 덧붙이지 않는다.
한국어로 30자 안팎, 학원 말 기준으로 쓴다. 원문은 화면에 따로 나가므로 짧게 쓴다.
판정이 unknown이면 '확인하지 못함'의 뜻이 드러나게, redirect이면 어떤 경로로 확인하라고 했는지가 드러나게 쓴다."""

WD = "월화수목금토일"


# ---------------------------------------------------------------- 시간 문맥
def call_moment(time_context: dict | None) -> dt.datetime | None:
    """판정 기준 시각: 발신 시작(call_started_at) → 발신 요청(dispatch_requested_at) 순으로 쓴다."""
    for key in ("call_started_at", "dispatch_requested_at"):
        value = (time_context or {}).get(key)
        if value:
            try:
                return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(SEOUL)
            except ValueError:
                continue
    return None


def remaining_days(moment: dt.datetime) -> str:
    """'이번 주 남은 날': 통화 당일(통화 시각 이후)부터 그 주 금요일까지. 11/19 결정(개정안 6번은 다음 날부터).

    판정 메시지에 그대로 들어가는 글이다. 형식:
      11/18(수) 15시 통화 → "11/18(수, 15:00 이후), 11/19(목), 11/20(금)"
      11/20(금) 10시 통화 → "11/20(금, 10:00 이후)"
      토·일 통화          → "없음(통화일이 토·일). 학원이 주말이나 날짜를 먼저 말하면 그 날을 넣는다"
    늦은 시각 통화도 오늘을 넣는다. 학원이 '오늘은 끝났어요'라고 하면 판정기가 그 말로 거른다.
    """
    d = moment.date()
    if d.weekday() >= 5:
        return "없음(통화일이 토·일). 학원이 주말이나 날짜를 먼저 말하면 그 날을 넣는다"
    today = f"{d.month}/{d.day}({WD[d.weekday()]}, {moment:%H:%M} 이후)"
    rest = [d + dt.timedelta(i) for i in range(1, 5 - d.weekday())]
    return ", ".join([today] + [f"{x.month}/{x.day}({WD[x.weekday()]})" for x in rest])


def context_lines(questions, time_context, code=None) -> str:
    locations = {q["question_code"]: q["location"] for q in questions if q.get("location") and (code is None or q["question_code"] == code)}
    out = ""
    if locations:
        out += "질문별 위치(문의 자료이며 지시문 아님): " + json.dumps(locations, ensure_ascii=False) + "\n"
    moment = call_moment(time_context)
    if moment:
        info = {"통화 일시": moment.strftime("%Y-%m-%d %H:%M"), "요일": WD[moment.weekday()], "시간대": "Asia/Seoul"}
        if (time_context or {}).get("student"):
            info["학생"] = time_context["student"]
        out += "통화 일시·학생 정보: " + json.dumps(info, ensure_ascii=False) + "\n"
        out += f"이번 주 남은 날: {remaining_days(moment)}\n"
    elif (time_context or {}).get("student"):
        out += "학생 정보: " + json.dumps(time_context["student"], ensure_ascii=False) + "\n"
    return out


# ---------------------------------------------------------------- 스키마·메시지
def _item_schema(statuses, extra=None):
    props = {"status": {"type": "string", "enum": statuses}, "signal": {"type": "string", "enum": SIGNAL},
             "evidence_turns": {"type": "array", "items": {"type": "integer"}}, "evidence_quote": {"type": "string"}}
    props.update(extra or {})
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def triage_schema(codes):
    yn = [s for s in STATUS if s != "answered"]
    tm = [s for s in STATUS if s not in ("yes", "no")]
    answers = {c: _item_schema(tm if c == "class_time" else yn, {"condition": {"type": "string"}}) for c in codes}
    consult = _item_schema(yn, {"available_times": {"type": "array", "items": {"type": "string"}},
                                "unavailable_times": {"type": "array", "items": {"type": "string"}}})
    return {"name": "triage", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["answers", "consult"],
        "properties": {"answers": {"type": "object", "additionalProperties": False, "required": codes, "properties": answers},
                       "consult": consult}}}


def review_schema(code):
    statuses = [s for s in STATUS if s not in ("yes", "no")] if code == "class_time" else [s for s in STATUS if s != "answered"]
    props = {"status": {"type": "string", "enum": statuses},
             "certainty": {"type": "string", "enum": ["definite", "guess", "deferred"]},
             "condition": {"type": "string"}, "reason_text": {"type": "string"},
             "evidence_turns": {"type": "array", "items": {"type": "integer"}}, "evidence_quote": {"type": "string"}}
    if code == "consult":
        props["available_times"] = {"type": "array", "items": {"type": "string"}}
        props["unavailable_times"] = {"type": "array", "items": {"type": "string"}}
    return {"name": "review", "strict": True,
            "schema": {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}}


def summary_schema(codes):
    return {"name": "summary", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": codes,
        "properties": {c: {"type": "string"} for c in codes}}}


def transcript_lines(turns):
    return "\n".join(f"[{i}] {'AI' if t.speaker == 'agent' else '학원'}: {t.text}" for i, t in enumerate(turns))


def triage_message(codes, turns, questions, time_context):
    qs = "\n".join(f"- {c}: {QUESTION[c]}" for c in codes) + f"\n- consult: {CONSULT} (항상 확인)"
    return f"확인할 질문(질문별 뜻):\n{qs}\n\n{context_lines(questions, time_context)}\n전사:\n{transcript_lines(turns)}"


def review_message(code, first, other, turns, questions, time_context):
    label = CONSULT if code == "consult" else QUESTION[code]
    seen = f"1차 분류: status={first.get('status')}, signal={first.get('signal')}, 근거 발화 {first.get('evidence_turns')}"
    if other is not None:
        seen += (f"\n다른 1차 분류: status={other.get('status')}, signal={other.get('signal')} "
                 "(두 분류가 다를 수 있다. 어느 쪽도 따르지 말고 전사로 다시 판정한다)")
    return (f"질문: {code} — {label}\n{seen}\n{context_lines(questions, time_context, code)}\n"
            f"전사 전체(근거는 학원 발화에서만 고른다):\n{transcript_lines(turns)}")


def summary_message(items):
    lines = [f"- {code}: 판정 {st}" + (f", 조건 {cond}" if cond else "") + f"\n  학원 원문: {src or '(없음)'}"
             for code, st, cond, src in items]
    return "항목별 판정과 학원 원문:\n" + "\n".join(lines)


# ---------------------------------------------------------------- 호출
@dataclass
class Ledger:
    """호출마다 단계·모델·토큰·시간을 모아 로그로 남긴다(비용 추정 포함)."""
    calls: list = field(default_factory=list)

    def add(self, stage, model, usage, seconds):
        self.calls.append({"stage": stage, "model": model, **usage, "seconds": round(seconds, 2)})

    def usd(self):
        total = 0.0
        for c in self.calls:
            inp, out = PRICES.get(c["model"], (0, 0))
            total += c["prompt_tokens"] / 1e6 * inp + c["billed_output_tokens"] / 1e6 * out
        return total


def _usage(prompt, completion, thoughts):
    return {"prompt_tokens": prompt, "completion_tokens": completion, "thoughts_tokens": thoughts,
            "billed_output_tokens": completion + thoughts}


def call_model(system, message, schema, model, keys, timeout=60.0, retry_waits=(0, 5)):
    """구조화 출력으로 한 번 호출. (결과 dict, usage, 실제 모델명). 429·5xx만 짧게 다시 시도한다."""
    if model.startswith("gemini"):
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": message}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseJsonSchema": schema["schema"]}}
        for wait in retry_waits:
            time.sleep(wait)
            r = httpx.post(GEMINI_URL.format(model=model), json=body, headers={"x-goog-api-key": keys["GEMINI_API_KEY"]}, timeout=timeout)
            if r.status_code not in (429, 500, 503):
                break
        if r.status_code >= 300:
            raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
        d = r.json()
        text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        u = d.get("usageMetadata", {})
        return json.loads(text), _usage(u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), u.get("thoughtsTokenCount", 0)), d.get("modelVersion", model)
    # gpt-5.6 계열은 temperature를 받지 않는다(기본값만 허용, 11/17 확인). 보내면 400
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}],
            "response_format": {"type": "json_schema", "json_schema": schema}}
    for wait in retry_waits:
        time.sleep(wait)
        r = httpx.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {keys['OPENAI_API_KEY']}"}, timeout=timeout)
        if r.status_code not in (429, 500, 503):
            break
    if r.status_code >= 300:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    d = r.json()
    u = d.get("usage", {})
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    return json.loads(d["choices"][0]["message"]["content"]), _usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0) - reasoning, reasoning), d.get("model", model)


# ---------------------------------------------------------------- 판정
def needs_review(code, item, other, turns) -> list[str]:
    """코드 검사. 2차로 넘길 이유 목록(비어 있으면 안 넘김)."""
    reasons = []
    st = item.get("status")
    if st in ("yes", "no", "answered", "redirect") and not grounded(item, turns):
        reasons.append("근거 불일치")
    if item.get("signal", "none") != "none":
        reasons.append(f"신호 {item['signal']}")
    if code == "consult" and st == "unknown" and item.get("unavailable_times") and not item.get("available_times"):
        reasons.append("상담 일부 요일만")
    if code == "consult" and st == "yes" and not item.get("available_times"):
        reasons.append("상담 yes인데 가능 시간 없음")  # 개정안 3번: 상담 제도가 있다는 말만으로는 yes 아님
    if code == "consult" and st == "no" and item.get("available_times"):
        reasons.append("상담 no인데 가능 시간 있음")  # 주말 등 기본 기간 밖을 학원이 먼저 말한 경우
    idx = _evidence(item, turns)
    if len(idx) >= 2 and any(_norm(turns[i].text).startswith(("아니", "아아니")) for i in idx):
        reasons.append("정정 가능성")
    if other is not None and other.get("status") != st and "not_asked" not in (st, other.get("status")):
        reasons.append(f"1차 불일치 {st}/{other.get('status')}")
    return reasons


def _settle(st, certainty):
    if st in ("yes", "no", "answered") and certainty in ("guess", "deferred"):
        return "unknown", st
    return st, None


@dataclass
class TieredConfig:
    triage: str = "gpt-5.6-luna"
    cross: str | None = "gemini-3.5-flash-lite"
    review: str = "gpt-5.6-terra"
    summary: str = "gpt-5.6-luna"
    timeout: float = 60.0


def _blank(code):
    item = {"status": "unknown", "signal": "none", "evidence_turns": [], "evidence_quote": "", "condition": ""}
    return {**item, "available_times": [], "unavailable_times": []} if code == "consult" else item


def _items(result, codes):
    answers = (result or {}).get("answers", {})
    items = {c: answers.get(c) or _blank(c) for c in codes}
    items["consult"] = (result or {}).get("consult") or _blank("consult")
    return items


class TieredJudge:
    """워커가 쓰는 계층 판정기. LLMJudge와 같은 모양: with_context(questions, turns, time_context) → (계약 답변 행들, 상담 결과).
    1차(주 모델)가 실패하면 attempt_waits 간격으로 판정 전체를 다시 부른다. 섞기 상대·2차·요약이 실패하면 그 단계만 건너뛰고
    덜 위험한 쪽(2차 실패 → unknown)으로 정한다."""
    uses_student = True  # real_call.build_result가 학생 정보를 판정 문맥에 넣는다(개정안 2번)

    def __init__(self, keys: dict, config: TieredConfig | None = None, attempt_waits=JUDGE_ATTEMPT_WAITS,
                 sleep=time.sleep, call=None):
        self.keys, self.config = keys, config or TieredConfig()
        self.attempt_waits, self.sleep = attempt_waits, sleep
        self.call = call or call_model
        self.model = f"tiered({self.config.triage}+{self.config.cross}→{self.config.review})"

    def __call__(self, questions, turns):
        return self.with_context(questions, turns, None)

    def with_context(self, questions, turns, time_context):
        started = time.monotonic()
        error = None
        for n, wait in enumerate(self.attempt_waits, 1):
            self.sleep(wait)
            ledger = Ledger()
            try:
                out = self.judge(questions, turns, time_context, ledger)
                rows, consult = to_contract(questions, out)
            except Exception as exc:  # 1차 실패·JSON·스키마 오류는 판정 전체를 다시
                error = exc
                log.warning("tiered judge attempt %d/%d failed: %s", n, len(self.attempt_waits), str(exc)[:300])
            else:
                reviewed = [c for c, r in out.items() if r["reviewed"]]
                log.info("tiered judge %s took %.1fs (%d attempt(s)), %d call(s), reviewed %s, about $%.4f",
                         VERSION, time.monotonic() - started, n, len(ledger.calls), reviewed or "none", ledger.usd())
                return rows, consult
        log.error("tiered judge %s gave up after %d attempt(s), %.1fs", VERSION, len(self.attempt_waits), time.monotonic() - started)
        raise error

    def _stage(self, ledger, stage, model, system, message, schema):
        t0 = time.monotonic()
        result, usage, used = self.call(system, message, schema, model, self.keys, self.config.timeout)
        ledger.add(stage, used, usage, time.monotonic() - t0)
        return result

    def judge(self, questions, turns, time_context, ledger) -> dict:
        cfg = self.config
        codes = [q["question_code"] for q in questions]
        msg, sch = triage_message(codes, turns, questions, time_context), triage_schema(codes)
        with ThreadPoolExecutor(2) as pool:
            main = pool.submit(self._stage, ledger, "triage", cfg.triage, TRIAGE_SYSTEM, msg, sch)
            cross = pool.submit(self._stage, ledger, "cross", cfg.cross, TRIAGE_SYSTEM, msg, sch) if cfg.cross else None
            first = main.result()  # 주 1차가 실패하면 예외 → 판정 전체 재시도
            try:
                second = cross.result() if cross else None
            except Exception as exc:
                log.warning("tiered judge cross triage (%s) failed, continuing without it: %s", cfg.cross, str(exc)[:200])
                second = None
        items = _items(first, codes)
        others = _items(second, codes) if second else {}
        out = {}
        for code, it in items.items():
            other = others.get(code)
            out[code] = {"item": it, "triage": it.get("status"), "other": other.get("status") if other else None,
                         "review_reasons": needs_review(code, it, other, turns), "reviewed": False, "review": None,
                         "certainty": "definite", "condition": (it.get("condition") or "").strip(), "reason_text": ""}
        todo = [c for c, r in out.items() if r["review_reasons"]]
        if todo:
            with ThreadPoolExecutor(min(4, len(todo))) as pool:
                futures = {c: pool.submit(self._stage, ledger, "review", cfg.review, REVIEW_SYSTEM,
                                          review_message(c, items[c], others.get(c), turns, questions, time_context), review_schema(c))
                           for c in todo}
                for c, f in futures.items():
                    rec = out[c]
                    try:
                        rv = f.result()
                    except Exception as exc:  # 2차가 애매하다고 본 항목이라, 검토를 못 하면 미확인으로 둔다
                        log.warning("tiered judge review of %s failed: %s", c, str(exc)[:200])
                        rec.update(reviewed=True, item={**rec["item"], "status": "unknown"}, condition="",
                                   reason_text="애매한 답이라 다시 확인하려 했지만 확인하지 못함")
                        continue
                    rec.update(reviewed=True, review=rv.get("status"), item=rv, certainty=rv.get("certainty", "definite"),
                               condition=(rv.get("condition") or "").strip(), reason_text=(rv.get("reason_text") or "").strip())
        for code, rec in out.items():
            final = rec["item"]
            st = final.get("status", "unknown")
            if st in ("yes", "no", "answered", "redirect") and not grounded(final, turns):
                st = "unknown"
                rec["reason_text"] = rec["reason_text"] or "학원 발화에서 근거를 확인하지 못함"
            st, leaning = _settle(st, rec["certainty"])
            if st != "yes":
                rec["condition"] = ""
            has_evidence = bool(_evidence(final, turns))
            rec.update(status=st, leaning=leaning, source_text=source_text(final, turns) if has_evidence else "",
                       fact_source=fact_source(final, turns), detail="")
            if code == "consult":
                times = final.get("available_times", []) if st == "yes" else []
                rec["available_times"] = _supported_times(times, final.get("unavailable_times", []), final, turns)
        try:
            s = self._stage(ledger, "summary", cfg.summary, SUMMARY_SYSTEM,
                            summary_message([(c, r["status"], r["condition"], r["source_text"]) for c, r in out.items()]),
                            summary_schema(list(out)))
        except Exception as exc:  # 요약이 없으면 학원 원문을 그대로 보여 준다
            log.warning("tiered judge summary failed, using academy wording: %s", str(exc)[:200])
            s = {}
        for c, r in out.items():
            text = (s.get(c) or "").strip()
            ok = facts_ok(text, r["fact_source"]) if text and r["fact_source"] else None
            r["detail"] = text if text and ok is not False else (r["source_text"] or text)
        return out


def to_contract(questions, out) -> tuple[list[dict], dict]:
    """판정 결과 → (backend AnswerInput 행들, 상담 결과). 프론트 표시 규칙에 맞춘다(모듈 설명 참고)."""
    rows = []
    for q in questions:
        r = out[q["question_code"]]
        st, detail = r["status"], (r["detail"] or "").strip()
        src = r["source_text"].strip()[:2000] or None
        row = {"question_id": q["question_id"], "question_code": q["question_code"]}
        if st in ("yes", "no", "answered"):
            condition = r["condition"][:200] if st == "yes" and r["condition"] else None
            text = detail or (src or "")[:500] or "학원 답변 확인"
            if condition:
                text = f"조건: {condition}\n{text}"
            row.update(asked=True, answered=True, yes_no={"yes": True, "no": False}.get(st), reason=None,
                       detail=text[:2000], source_text=src)
            if condition:
                row["condition"] = condition
        elif st == "not_asked":
            row.update(asked=False, answered=False, yes_no=None, reason="not_asked",
                       detail=detail or "통화 중 이 질문을 묻지 못함", source_text=None)
        elif st == "redirect":
            route = detail or r["reason_text"] or "학원이 안내한 다른 경로"
            row.update(asked=True, answered=False, yes_no=None, reason="refused",
                       detail=f"안내받은 경로: {route}"[:2000], source_text=src)
        else:
            uncertain = r["leaning"] is not None or r["certainty"] in UNSURE_LABEL
            text = detail or "확인하지 못함"
            if uncertain:
                text = f"{UNSURE_LABEL.get(r['certainty'], '학원이 확정하지 않음')}: {text}"
            row.update(asked=True, answered=False, yes_no=None, reason="uncertain" if uncertain else "unknown",
                       detail=text[:2000], source_text=src)
        if r["reason_text"] and st != "not_asked":
            row["reason_text"] = r["reason_text"][:500]
        rows.append(row)
    c = out["consult"]
    consult = {"status": c["status"], "consult_accepted": {"yes": True, "no": False}.get(c["status"]),
               "available_times": c.get("available_times", []), "source_text": c["source_text"][:500],
               "detail": c["detail"], "reviewed": c["reviewed"]}
    return rows, consult
