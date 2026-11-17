"""계층 판정(평가용): 1차 분류 → 코드 검사 → 2차 특수 사례 → 요약 → 코드 마무리.

11/12 멘토 의견을 따른 구조다. 프롬프트 하나에 역할 하나만 두고, 오류는 여러 겹으로 처리한다.
  1차 (TRIAGE)   모든 질문. 학원이 무엇을 말했는지 분류하고 근거 발화를 인용한다. 요약은 쓰지 않는다.
  코드 검사      근거 인용이 실제 학원 발화에 있는지(grounded), 1차가 애매하다고 표시했는지, 상담이 일부 요일만 말했는지.
                 걸린 항목만 2차로 넘긴다. 1차가 자신 있게 틀린 답은 여기서 못 잡으므로, 그 몫은 시험 세트가 보여 준다.
  2차 (REVIEW)   넘어온 항목만. 그 질문 하나와 특수 사례 규칙(짐작·미룸, 되짚기 정정, 경로 안내, 조건)만 주고 다시 판정한다.
  요약 (SUMMARY) 확정된 상태와 근거 원문으로 학부모용 한 줄 요약을 쓴다. 판정은 바꾸지 않는다.
  코드 마무리    요약의 숫자·요일이 원문에 있는지(facts_ok). 없으면 원문 인용으로 바꾼다.

워커 코드(voice/call_worker/llm_judge.py)는 바꾸지 않고 검사 함수만 가져다 쓴다. 모델·추론 설정은 Tier 조합으로 넘긴다.
비용 추적: 호출마다 모델·토큰을 모아 usd()로 금액을 낸다(단가는 PRICES, 2026-11 공식 가격표 기준).
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from llm_judge import (GEMINI_URL, OPENAI_URL, QUESTION_TEXT, _evidence, _norm, fact_source, facts_ok, grounded,
                       source_text)

log = logging.getLogger("tiered")
VERSION = "tiered-v1"

# 100만 토큰당 달러 (입력, 출력). 추론 토큰은 출력 단가로 센다
PRICES = {"gpt-5.6-luna": (0.20, 1.20), "gpt-5.6-terra": (2.00, 12.00), "gemini-3.5-flash-lite": (0.30, 2.50)}

STATUS = ["yes", "no", "answered", "unknown", "redirect", "not_asked"]
SIGNAL = ["none", "hedge", "deferred", "corrected", "partial_week", "conditional", "off_topic"]

# ---------------------------------------------------------------- 1차: 분류만
TRIAGE_SYSTEM = """당신은 학부모를 대신해 학원에 건 전화의 전사를 읽고, 질문마다 학원이 무엇을 말했는지 분류한다.
전사는 받아쓰기 오류가 있을 수 있다. 화자는 AI(우리 상담원)와 학원이다. 전사에 없는 내용을 지어내지 않는다.
이 단계는 분류만 한다. 요약 문장은 쓰지 않는다.

판정 순서(위에서부터 처음 해당하는 값):
1. AI가 묻지 않았고 학원도 먼저 말하지 않았으면 not_asked. 학원이 먼저 답했으면 물은 것으로 본다.
2. 학원이 질문이 묻는 사실에 대해 되는지 안 되는지 분명히 말했으면 yes 또는 no. 수업 시간은 요일·시각을 말했으면 answered.
   - 정중하게 돌려 말해도 뜻이 분명하면 여기에 든다. 이유만 말해도 뜻이 분명하면 no다.
   - 조건이 붙어도 사실을 인정하면 yes다. 학생 조건(학년·과목·수준·지역)에 그 학생이 해당하지 않는다고 하면 no다.
   - AI가 되짚은 말은 학원이 맞다고 했을 때만 근거다. 학원이 나중에 고치면 마지막에 확정한 답을 따른다.
3. 답 대신 학부모가 확인할 다른 경로(방문, 홈페이지, 레벨 테스트 등)를 안내했으면 redirect.
4. 나머지는 unknown. 모른다, 정해지지 않았다, 전화로는 안 된다고만 함, 관계없는 대답, 답 없음.

signal: 2차 검토가 필요한 신호. 해당하는 것이 없으면 none.
- hedge: 학원이 짐작으로 말함('아마', '~일 거예요', 확실하지 않다고 함)
- deferred: 다른 사람이나 나중 확인으로 답을 넘김('원장님께 여쭤보고', '확인하고 연락드릴게요')
- corrected: 학원이 앞에 한 말을 고쳤거나, AI 되짚기에 '아니요'라고 함
- partial_week: 상담에서 안 되는 요일·시간만 말하고 되는 때는 말하지 않음
- conditional: 가능하다고 했지만 학생 정보로 따질 수 없는 조건이 붙음
- off_topic: 대답이 질문과 다른 이야기로 보임
status는 학원이 말한 내용대로 고르고, signal 때문에 status를 바꾸지 않는다.

근거: yes/no/answered/redirect이거나 signal이 none이 아니면 evidence_turns에 학원 발화 번호를, evidence_quote에 그 발화의 핵심 구절을 넣는다.
인용은 전사 글자 그대로 복사한다. 오타도 고치지 않는다.
상담(consult)은 이번 주 학부모 상담 가능 여부다. 가능한 때를 말하면 yes이고 available_times에, 안 되는 때는 unavailable_times에 학원이 말한 그대로 적는다."""

# ---------------------------------------------------------------- 2차: 특수 사례만
REVIEW_SYSTEM = """당신은 학원 통화 전사에서 한 가지 질문의 답을 다시 판정하는 검토자다. 1차 분류기가 이 항목을 애매하다고 표시했다.
질문 하나와 그 근거 발화만 본다. 전사에 없는 내용을 지어내지 않는다.

값(status): yes / no / answered(수업 시간만) / unknown / redirect / not_asked
애매하면 unknown을 고른다. 틀린 yes/no보다 unknown이 낫다.

특수 사례 규칙:
- 짐작('아마', '~일 거예요', '확실하진 않은데'): 학원이 확정하지 않은 것이다. status는 unknown, certainty는 guess.
- 미룸('원장님께 여쭤보고', '확인하고 연락드릴게요'): 답이 없는 것이다. status는 unknown, certainty는 deferred.
- '~것 같아요'는 붙은 자리로 가른다. 학원이 스스로 정하는 안내 끝에 붙으면 공손한 말투라 확정이고, 확인 안 된 사실 끝에 붙으면 짐작이다.
- 되짚기 정정: 학원이 AI의 되짚기에 '아니요'라고 하거나 다시 말했으면 마지막에 확정한 내용을 따른다.
- 경로 안내: 답 대신 학부모가 확인할 방법(방문, 홈페이지, 레벨 테스트)을 말했으면 redirect. '전화로는 안 돼요'만 말하고 경로가 없으면 unknown.
- 조건: 가능 여부를 바꾸는 조건이 붙으면 yes에 condition을 짧게 적는다. 절차 안내(미리 연락, 비용)는 조건이 아니다.
- 상담에서 안 되는 때만 말했으면: 되는 때를 말하지 않았으므로 unknown. 이번 주 전체가 안 된다고 했으면 no.
- 학생 조건(학년·과목·수준·지역)에 그 학생이 해당하지 않는다고 했으면 no.

certainty: definite(확정) / guess(짐작) / deferred(미룸). status가 unknown이 아니면 definite다.
근거: evidence_turns에 학원 발화 번호를, evidence_quote에 핵심 구절을 글자 그대로 넣는다.
reason_text: 왜 이렇게 판정했는지 한 문장(학부모에게 보일 수 있는 말로)."""

# ---------------------------------------------------------------- 요약: 글만
SUMMARY_SYSTEM = """당신은 학원 통화 결과를 학부모에게 보여 줄 한 줄 요약으로 쓰는 작성자다. 판정은 이미 끝났고 바꾸지 않는다.
항목마다 판정 값과 학원 원문이 주어진다. 원문에 있는 내용만 쓰고, 원문에 없는 숫자·요일·시각·오전/오후·인원·금액을 덧붙이지 않는다.
한국어로 30자 안팎, 학원 말 기준으로 쓴다. 원문은 화면에 따로 나가므로 짧게 쓴다.
판정이 unknown이면 '확인하지 못함'의 뜻이 드러나게, redirect이면 어떤 경로로 확인하라고 했는지가 드러나게 쓴다."""


def _item_schema(statuses, extra=None):
    props = {"status": {"type": "string", "enum": statuses}, "signal": {"type": "string", "enum": SIGNAL},
             "evidence_turns": {"type": "array", "items": {"type": "integer"}}, "evidence_quote": {"type": "string"}}
    props.update(extra or {})
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def triage_schema(codes):
    yn = [s for s in STATUS if s != "answered"]
    tm = [s for s in STATUS if s not in ("yes", "no")]
    answers = {c: _item_schema(tm if c == "class_time" else yn) for c in codes}
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


def triage_message(codes, turns, questions=None, time_context=None):
    qs = "\n".join(f"- {c}: {QUESTION_TEXT[c]}" for c in codes)
    ctx = ""
    locations = {q["question_code"]: q["location"] for q in questions or [] if q.get("location")}
    if locations:
        ctx += "질문별 위치(문의 자료): " + json.dumps(locations, ensure_ascii=False) + \
               "\nshuttle은 해당 출발지에서 학원으로 등원, pickup은 학원에서 해당 목적지로 하원이다.\n"
    if time_context:
        ctx += "시간 문맥: " + json.dumps(time_context, ensure_ascii=False) + "\n"
    return f"확인할 질문:\n{qs}\n- consult: 이번 주 학부모 상담 가능 여부와 가능한 시간(항상 확인)\n\n{ctx}\n전사:\n{transcript_lines(turns)}"


def review_message(code, first, turns, time_context=None):
    label = "이번 주 학부모 상담 가능 여부와 가능한 시간" if code == "consult" else QUESTION_TEXT[code]
    ctx = f"시간 문맥: {json.dumps(time_context, ensure_ascii=False)}\n" if time_context else ""
    return (f"질문: {code} — {label}\n1차 분류: status={first.get('status')}, signal={first.get('signal')}, "
            f"근거 발화 {first.get('evidence_turns')}\n{ctx}\n전사 전체(근거는 학원 발화에서만 고른다):\n{transcript_lines(turns)}")


def summary_message(items):
    lines = [f"- {code}: 판정 {st}" + (f", 조건 {cond}" if cond else "") + f"\n  학원 원문: {src or '(없음)'}"
             for code, st, cond, src in items]
    return "항목별 판정과 학원 원문:\n" + "\n".join(lines)


# ---------------------------------------------------------------- 호출
@dataclass
class Tier:
    model: str
    reasoning: str | None = None   # OpenAI: reasoning_effort(none/low/medium/high). Gemini: thinking_level(low/medium/high). None이면 기본값


@dataclass
class Ledger:
    """호출마다 모델·토큰·시간을 모은다."""
    calls: list = field(default_factory=list)

    def add(self, stage, model, usage, seconds):
        self.calls.append({"stage": stage, "model": model, **usage, "seconds": round(seconds, 2)})

    def usd(self):
        total = 0.0
        for c in self.calls:
            inp, out = PRICES.get(c["model"], (0, 0))
            total += c["prompt_tokens"] / 1e6 * inp + c["billed_output_tokens"] / 1e6 * out
        return total

    def by_model(self):
        agg = {}
        for c in self.calls:
            a = agg.setdefault(c["model"], {"calls": 0, "prompt_tokens": 0, "billed_output_tokens": 0, "thoughts_tokens": 0, "seconds": 0.0})
            a["calls"] += 1
            for k in ("prompt_tokens", "billed_output_tokens", "thoughts_tokens", "seconds"):
                a[k] += c[k]
        return agg


def _usage(prompt, completion, thoughts):
    return {"prompt_tokens": prompt, "completion_tokens": completion, "thoughts_tokens": thoughts,
            "billed_output_tokens": completion + thoughts}


def _call(system, message, schema, tier: Tier, keys: dict, timeout=120.0, retry_waits=(0, 15, 45)):
    """구조화 출력으로 한 번 호출. (결과 dict, usage, 실제 모델명)"""
    if tier.model.startswith("gemini"):
        cfg = {"temperature": 0, "responseMimeType": "application/json", "responseJsonSchema": schema["schema"]}
        if tier.reasoning:
            cfg["thinkingConfig"] = {"thinkingLevel": tier.reasoning}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": message}]}], "generationConfig": cfg}
        for wait in retry_waits:
            time.sleep(wait)
            r = httpx.post(GEMINI_URL.format(model=tier.model), json=body, headers={"x-goog-api-key": keys["GEMINI_API_KEY"]}, timeout=timeout)
            if r.status_code not in (429, 500, 503):
                break
        if r.status_code >= 300:
            raise RuntimeError(f"Gemini {r.status_code}: {r.text[:500]}")
        d = r.json()
        text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        u = d.get("usageMetadata", {})
        return json.loads(text), _usage(u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), u.get("thoughtsTokenCount", 0)), d.get("modelVersion", tier.model)
    body = {"model": tier.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": message}],
            "response_format": {"type": "json_schema", "json_schema": schema}}
    # gpt-5.6 계열은 temperature를 받지 않는다(기본값 1만 허용, 11/17 확인). 추론 강도로만 조절한다.
    # 워커의 llm_judge._post_openai는 아직 temperature=0을 보내므로 gpt-5.6으로 바꿀 때 같이 고쳐야 한다.
    if tier.reasoning:
        body["reasoning_effort"] = tier.reasoning
    for wait in retry_waits:
        time.sleep(wait)
        r = httpx.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {keys['OPENAI_API_KEY']}"}, timeout=timeout)
        if r.status_code not in (429, 500, 503):
            break
    if r.status_code >= 300:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:500]}")
    d = r.json()
    u = d.get("usage", {})
    reasoning = (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    return json.loads(d["choices"][0]["message"]["content"]), _usage(u.get("prompt_tokens", 0), u.get("completion_tokens", 0) - reasoning, reasoning), d.get("model", tier.model)


def cached(cache_dir, stage, tier, system, message, schema, keys, ledger, timeout=120.0):
    """같은 입력이면 캐시를 읽는다. 캐시 적중도 ledger에 남긴다(비용은 처음 호출 값, seconds=0)."""
    key = hashlib.sha256(json.dumps([VERSION, stage, tier.model, tier.reasoning, system, message, schema], ensure_ascii=False).encode()).hexdigest()[:24]
    path = cache_dir / f"{key}.json" if cache_dir else None
    if path and path.exists():
        out = json.loads(path.read_text(encoding="utf-8"))
        ledger.add(stage, out["model"], out["usage"], 0.0)
        return out["result"]
    started = time.monotonic()
    result, usage, model = _call(system, message, schema, tier, keys, timeout)
    seconds = time.monotonic() - started
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"result": result, "usage": usage, "model": model, "seconds": seconds}, ensure_ascii=False, indent=1), encoding="utf-8")
    ledger.add(stage, model, usage, seconds)
    return result


# ---------------------------------------------------------------- 파이프라인
def needs_review(code, item, turns) -> list[str]:
    """코드 검사. 2차로 넘길 이유 목록(비어 있으면 안 넘김)."""
    reasons = []
    st = item.get("status")
    if st in ("yes", "no", "answered", "redirect") and not grounded(item, turns):
        reasons.append("근거 불일치")
    if item.get("signal", "none") != "none":
        reasons.append(f"신호 {item['signal']}")
    # 1차가 '이번 주 전체 불가'로 확정한 no는 넘기지 않는다(S03 "금토일 안될 것 같습니다"를 2차가 unknown으로 되돌린 일이 있음)
    if code == "consult" and st == "unknown" and item.get("unavailable_times") and not item.get("available_times"):
        reasons.append("상담 일부 요일만")
    # 같은 질문에 학원 발화가 여럿이고 '아니' 류가 있으면 정정 가능성
    idx = _evidence(item, turns)
    if len(idx) >= 2 and any(_norm(turns[i].text).startswith(("아니", "아아니")) for i in idx):
        reasons.append("정정 가능성")
    return reasons


def _settle(st, certainty):
    if st in ("yes", "no", "answered") and certainty in ("guess", "deferred"):
        return "unknown", st
    return st, None


def judge(questions, turns, tiers: dict, keys: dict, cache_dir: Path | None, *, time_context=None, ledger: Ledger | None = None):
    """tiers: {'triage': Tier, 'review': Tier, 'summary': Tier}. review가 None이면 1차 결과를 그대로 쓴다.
    반환: 항목별 결과 dict(code → {...})와 단계 기록."""
    ledger = ledger if ledger is not None else Ledger()
    codes = [q["question_code"] for q in questions]
    first = cached(cache_dir, "triage", tiers["triage"], TRIAGE_SYSTEM, triage_message(codes, turns, questions, time_context),
                   triage_schema(codes), keys, ledger)
    items = {c: first["answers"].get(c, {"status": "unknown", "signal": "none", "evidence_turns": [], "evidence_quote": ""}) for c in codes}
    items["consult"] = first.get("consult", {"status": "unknown", "signal": "none", "evidence_turns": [], "evidence_quote": "",
                                             "available_times": [], "unavailable_times": []})
    out = {}
    for code, it in items.items():
        rec = {"triage": it["status"], "signal": it.get("signal", "none"), "review_reasons": needs_review(code, it, turns),
               "reviewed": False, "review": None, "certainty": "definite", "condition": "", "reason_text": "", "leaning": None}
        final = it
        if rec["review_reasons"] and tiers.get("review"):
            rv = cached(cache_dir, "review", tiers["review"], REVIEW_SYSTEM, review_message(code, it, turns, time_context),
                        review_schema(code), keys, ledger)
            rec.update(reviewed=True, review=rv["status"], certainty=rv.get("certainty", "definite"),
                       condition=rv.get("condition", ""), reason_text=rv.get("reason_text", ""))
            final = rv
        st = final["status"]
        if st in ("yes", "no", "answered", "redirect") and not grounded(final, turns):
            st = "unknown"
            rec["reason_text"] = rec["reason_text"] or "근거 확인 실패"
        st, leaning = _settle(st, rec["certainty"])
        src = source_text(final, turns) if _evidence(final, turns) else ""
        rec.update(status=st, leaning=leaning, source_text=src, evidence_turns=_evidence(final, turns),
                   available_times=final.get("available_times", []) if code == "consult" and st == "yes" else [],
                   unavailable_times=final.get("unavailable_times", []) if code == "consult" else [], fact_source=fact_source(final, turns))
        out[code] = rec
    if tiers.get("summary"):
        s = cached(cache_dir, "summary", tiers["summary"], SUMMARY_SYSTEM,
                   summary_message([(c, r["status"], r["condition"], r["source_text"]) for c, r in out.items()]),
                   summary_schema(list(out)), keys, ledger)
        for c, r in out.items():
            text = s.get(c, "")
            ok = facts_ok(text, r["fact_source"]) if r["fact_source"] else None
            r["detail"] = text if ok is not False else (r["source_text"] or text)
            r["detail_checked"] = ok
    return out, ledger
