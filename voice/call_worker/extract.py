"""통화 전사를 백엔드 결과 형식(result_json_schema.json)의 질문별 답으로 정리한다.

순서
1. ClawOps 전사의 화자(speaker_0, speaker_1 …) 중 AI를 찾는다. 첫인사의 "AI 상담원"/"녹음" 고지로 구분
2. AI가 질문을 처음 꺼낸 발화를 키워드로 찾고, 그 뒤 학원이 한 말을 그 질문의 대답으로 본다
   (AI가 되짚거나 마지막에 요약할 때도 같은 키워드가 나오므로 '처음' 꺼낸 곳만 쓴다)
3. judge()가 대답을 예/아니오/미확인으로 판정한다

전사는 받아쓰기 오류가 있다. 10/13 통화에서 "자리"가 "자"로 적힌 예가 있어 키워드에 그런 형태도 넣었다.
"""
import re
from dataclasses import dataclass

# 질문 코드별: (AI에게 줄 질문 문장, 전사에서 AI 질문을 찾을 키워드)
QUESTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "shuttle": ("통학 차량이 있는지, 있다면 운행 지역과 시간", ("차량", "셔틀", "통학")),
    "pickup": ("수업 후 픽업을 해 주는지", ("픽업",)),
    "level_fit": ("학생 학년·과목·수준에 맞는 반이 있는지", ("수준", "맞는 반")),
    "vacancy": ("지금 등록할 자리가 남아 있는지", ("자리", "등록할 자", "남은 자")),
    "level_test": ("레벨 테스트가 있는지, 있다면 언제 보는지", ("레벨", "테스트")),
    # 10/13 전사에서 "요일"이 "유일"로 적힌 예가 있다
    "class_time": ("수업 요일과 시간", ("요일", "유일", "수업 시간", "시간은", "시간이")),
}
# 문의마다 항상 묻는 상담 확인 (fixed_checks의 consult_accepted, available_times)
CONSULT = ("이번 주에 학부모 상담이 가능한지, 가능하면 요일과 시간", ("상담",))


@dataclass(frozen=True)
class Turn:
    speaker: str  # "agent" 또는 "academy" (백엔드 TranscriptTurn과 같은 값)
    at_ms: int
    text: str


def find_agent_speaker(segments: list[dict]) -> str | None:
    """AI 화자 번호. 고지 문구로 먼저 찾고, 없으면 말을 가장 많이 한 화자(AI가 질문과 요약을 해서 길다)."""
    for seg in segments:
        text = seg.get("text") or ""
        if "AI" in text or "상담원" in text or "녹음" in text:
            return seg.get("speaker")
    totals: dict[str, int] = {}
    for seg in segments:
        speaker = str(seg.get("speaker"))
        totals[speaker] = totals.get(speaker, 0) + len(seg.get("text") or "")
    return max(totals, key=lambda s: totals[s]) if totals else None


def to_turns(segments: list[dict]) -> list[Turn]:
    agent = find_agent_speaker(segments)
    turns = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if text:
            turns.append(Turn("agent" if seg.get("speaker") == agent else "academy",
                              max(0, int(float(seg.get("start") or 0) * 1000)), text[:4000]))
    return turns


# AI가 질문이 아닌데도 늘 하는 말. 키워드를 찾기 전에 지운다
# (첫인사 "AI 상담원입니다"의 '상담'이 상담 질문으로 잡혀 "네 말씀하세요"를 상담 대답으로 집던 문제, 10/19 박찬원 재현)
NOT_QUESTION = ("상담원",)


def locate(turns: list[Turn], keywords: tuple[str, ...], start: int = 0) -> int | None:
    """start번째 발화부터 보아, AI가 키워드로 질문한 첫 발화의 위치."""
    for i in range(start, len(turns)):
        if turns[i].speaker != "agent":
            continue
        text = turns[i].text
        for word in NOT_QUESTION:
            text = text.replace(word, "")
        if any(k in text for k in keywords):
            return i
    return None


def reply_after(turns: list[Turn], i: int) -> str:
    """i번째 AI 질문 뒤부터 다음 AI 발화 전까지 학원이 한 말."""
    reply = []
    for later in turns[i + 1:]:
        if later.speaker == "agent":
            if reply:
                break
            continue  # AI가 질문을 두 발화로 나눠 말한 경우
        reply.append(later.text)
    return " ".join(reply)


def find_reply(turns: list[Turn], keywords: tuple[str, ...], start: int = 0) -> tuple[bool, str]:
    """(AI가 물었는지, 학원 대답). AI가 키워드로 처음 물은 뒤부터 다음 AI 발화 전까지 학원이 한 말을 잇는다."""
    i = locate(turns, keywords, start)
    return (False, "") if i is None else (True, reply_after(turns, i))


def disclosure_played(turns: list[Turn]) -> bool:
    agent_text = " ".join(t.text for t in turns if t.speaker == "agent")
    return ("AI" in agent_text or "상담원" in agent_text) and "녹음" in agent_text


# 판정 단서 (10/19 김규림 결정). 위에서부터 차례로 보고, 걸리면 거기서 끝낸다
REFUSED = ("말씀드리기 어려", "말씀 드리기 어려", "안내 안 해", "안내를 안", "안내해 드리기 어려", "알려 드리기 어려")
VISIT = ("방문하", "오셔서", "직접 오")  # 상담 질문에서는 '오세요'가 가능 대답이라 거절로 보지 않는다
UNKNOWN = ("확인해", "확인하고", "확인 후", "여쭤", "원장님께", "원장님한테", "모르", "알아보", "담당", "나중에 연락")
HEDGE = ("아마", "보통", "상황", "그때그때", "경우에 따라", "될 수도", "있을 수도", "글쎄")
POSITIVE_IDIOMS = ("상관없", "문제없", "걱정 없", "대기 없")  # '없'이 들어가도 긍정인 말. 부정어 검사 전에 지운다
# "안 해요/안 합니다/안 하고요/안 돼요/안 됩니다"처럼 어미가 바뀌어도 잡는다 (10/19 실통화의 "픽업은 안 합니다")
NEGATIVE = re.compile(r"없|안\s?(해|합|하|돼|됩|되)|않|아니|어려|못\s?해|못\s|불가|마감|다\s?찼|꽉\s?차")
POSITIVE = ("네", "예", "있", "해요", "해 드", "돼요", "됩니다", "가능", "운행", "다녀요", "남아", "남았", "맞아요", "그럼요", "물론")
TIME = re.compile(r"[월화수목금토일](요일)?|\d+\s*시|\d+:\d+|오전|오후|저녁|아침|점심|방과\s*후|주말|평일")


def judge(question_code: str, reply: str) -> tuple[bool, bool | None, str | None]:
    """학원 대답을 판정한다. 돌려주는 값: (answered, yes_no, reason)

    - 예/아니오 질문에 확실히 답함:  (True, True 또는 False, None)
    - class_time 처럼 시간 답:       (True, None, None)   # 예/아니오 없음, 시간은 detail에 원문으로 남는다
    - 모른다/확인해 보겠다:          (False, None, "unknown")
    - 말하기 곤란하다/거절:          (False, None, "refused")
    question_code에는 상담 확인용 "consult"도 온다 (예=상담 가능).

    규칙(10/19 김규림): 부정어가 있으면 '네'로 시작해도 아니오. '네'만 하면 예. 조건부·추측 대답은 미확인.
    자리가 없고 대기만 된다면 아니오. 수업 시간은 요일·시각이 있어야 답함. 상담은 시간을 말하면 가능.
    '어려워요'는 아니오, '말씀드리기 어려워요'는 거절. 판정이 애매하면 미확인(틀린 예/아니오보다 안전).
    """
    text = reply.strip()
    has = lambda cues: any(c in text for c in cues)  # noqa: E731
    if not text:
        return False, None, "unknown"
    if has(REFUSED) or (question_code != "consult" and has(VISIT)):
        return False, None, "refused"
    if has(UNKNOWN) or has(HEDGE):
        return False, None, "unknown"
    if question_code == "class_time":
        return (True, None, None) if TIME.search(text) else (False, None, "unknown")
    for idiom in POSITIVE_IDIOMS:
        text = text.replace(idiom, "")
    if NEGATIVE.search(text) or (question_code == "vacancy" and "대기" in text):
        return True, False, None
    if has(POSITIVE) or (question_code == "consult" and TIME.search(text)):
        return True, True, None
    return False, None, "unknown"


def positions(questions: list[dict], turns: list[Turn]) -> tuple[list[int | None], int | None]:
    """요청한 질문마다 AI가 처음 물은 발화 위치(못 찾으면 None)와 상담 질문 위치.

    AI는 지시한 순서대로 묻는다. 그래서 각 질문은 앞 질문을 찾은 발화 다음부터 찾는다.
    처음부터 찾으면 앞 질문의 단어에 걸린다(10/19 실통화: 통학 차량 질문의 "운행 지역과 시간이"가
    수업 시간 질문으로 잡혀 통학 차량 대답을 수업 시간 대답으로 집었다). 순서대로 못 찾으면 처음부터 다시 찾는다.
    상담은 마지막에 묻고, 첫인사(고지 발화)는 건너뛴다(10/19 공동 시험: 첫인사를 "상담 가능하신가요?"로 끝냄).
    """
    found, start = [], 0
    for q in questions:
        keywords = QUESTIONS[q["question_code"]][1]
        i = locate(turns, keywords, start)
        if i is None:
            i = locate(turns, keywords)
        if i is not None:
            start = max(start, i + 1)
        found.append(i)
    greeting = next((i for i, t in enumerate(turns) if t.speaker == "agent"), None)
    if greeting is not None and "녹음" in turns[greeting].text:
        start = max(start, greeting + 1)
    return found, locate(turns, CONSULT[1], start)


def reply_blocks(turns: list[Turn], i: int, end: int) -> list[tuple[str, str]]:
    """i번째 AI 질문부터 end 전까지, 학원이 이어서 한 말 묶음마다 (바로 앞 AI 발화, 학원 말)."""
    blocks, prev, said = [], turns[i].text, []
    for t in turns[i + 1:end]:
        if t.speaker == "agent":
            if said:
                blocks.append((prev, " ".join(said)))
                said = []
            prev = t.text
        else:
            said.append(t.text)
    if said:
        blocks.append((prev, " ".join(said)))
    return blocks


def _mentions(text: str, keywords: tuple[str, ...]) -> bool:
    for word in NOT_QUESTION:
        text = text.replace(word, "")
    return any(k in text for k in keywords)


# 되짚기에 학원이 "아니요, …"로 고쳐 말한 경우 (10/19 공동 시험: "네, 픽업합니다" → 되짚기 → "아니요, 픽업은 안 해요")
CORRECTION = re.compile(r"^\s*(아니요|아니오|아뇨|아니)[\s,.!]*")


def decide(code: str, blocks: list[tuple[str, str]], keywords: tuple[str, ...],
           others: tuple[str, ...]) -> tuple[bool, bool | None, str | None, str]:
    """질문 하나의 대답 묶음들로 최종 판정. 돌려주는 값: (answered, yes_no, reason, 근거가 된 학원 말)

    - 바로 앞 AI 발화가 다른 질문 이야기면 건너뛴다. AI가 질문하다 끊기고 앞 질문을 되짚은 경우
      그 되짚기에 한 "네, 맞습니다"를 이 질문의 대답으로 집지 않는다(10/19 공동 시험의 수업 시간).
    - 처음으로 판정되는 대답을 쓴다. 그 뒤 되짚기에 맞다고 한 말은 판정을 바꾸지 않는다.
    - 그 뒤 "아니요, …"로 고쳐 말하면 고친 말로 다시 판정한다. 고친 내용이 판정되지 않으면 미확인
      (앞 대답과 어긋나 애매하면 미확인, 10/19 김규림 기준).
    """
    result = None
    for prev, said in blocks:
        if not _mentions(prev, keywords) and _mentions(prev, others):
            continue
        if result is None or not result[0]:
            answered, yes_no, reason = judge(code, said)
            if result is None or answered:
                result = (answered, yes_no, reason, said)
        elif CORRECTION.match(said):
            answered, yes_no, reason = judge(code, CORRECTION.sub("", said, count=1))
            result = (answered, yes_no, reason, said) if answered else (False, None, "unknown", said)
    return result or (False, None, "unknown", "")


# AI 발화가 '다른 질문 이야기'인지 볼 때 쓰는 주제어. 질문 찾기 키워드와 같되, 상담 질문에도 늘 나오는
# "요일·시간"은 빼고 수업 시간만의 말을 쓴다(10/13 전사: "가능하다면 요일과 시간은…"이 수업 시간 이야기로 잡힘)
TOPICS = {**{code: kws for code, (_, kws) in QUESTIONS.items()},
          "class_time": ("수업 요일", "수업 시간", "유일"), "consult": CONSULT[1]}


def _segments(questions: list[dict], turns: list[Turn]):
    """질문마다 (질문 코드, 키워드, 다른 질문 주제어, 위치, 대답 묶음). 상담은 코드 "consult"로 맨 끝에."""
    found, consult_at = positions(questions, turns)
    items = [(q["question_code"], QUESTIONS[q["question_code"]][1], i) for q, i in zip(questions, found)]
    items.append(("consult", CONSULT[1], consult_at))
    starts = sorted(i for _, _, i in items if i is not None)
    out = []
    for code, keywords, i in items:
        others = tuple(k for c, _, _ in items if c != code for k in TOPICS[c])
        if i is None:
            out.append((code, keywords, others, None, []))
            continue
        end = next((s for s in starts if s > i), len(turns))
        out.append((code, keywords, others, i, reply_blocks(turns, i, end)))
    return out


def build_answers(questions: list[dict], turns: list[Turn]) -> list[dict]:
    """요청한 질문마다 답변 행을 하나씩 만든다. 못 물었거나 못 받은 항목도 빼지 않는다.

    대답은 그 질문부터 다음 질문 전까지 학원이 한 말 전체에서 decide()로 고른다
    (바로 다음 한 마디만 보면 되짚기에서 고쳐 말한 것을 놓친다).
    """
    answers = []
    for q, (code, keywords, others, i, blocks) in zip(questions, _segments(questions, turns)):
        if i is None:
            answers.append({**q, "asked": False, "answered": False, "yes_no": None,
                            "reason": "not_asked", "detail": "통화에서 이 질문을 확인하지 못함"})
            continue
        answered, yes_no, reason, said = decide(code, blocks, keywords, others)
        if code == "class_time" and answered:
            yes_no = None
        answers.append({**q, "asked": True, "answered": answered,
                        "yes_no": yes_no if answered else None,
                        "reason": None if answered else (reason or "unknown"),
                        "detail": said[:500] or "대답을 알아듣지 못함"})
    return answers


def consult_result(turns: list[Turn], questions: list[dict] | None = None) -> tuple[bool | None, list[str]]:
    """(consult_accepted, available_times). 상담을 묻지 못했거나 판정이 안 되면 (None, [])."""
    code, keywords, others, i, blocks = _segments(questions or [], turns)[-1]
    if i is None:
        return None, []
    answered, yes_no, _, said = decide(code, blocks, keywords, others)
    if not answered:
        return None, []
    return yes_no, ([said[:200]] if yes_no and said else [])
