"""판정 값 목록 개정안(11/10 강유준)의 8번 표대로 기존 정답 라벨을 새 값으로 옮긴다.

두 단계로 쓴다. 저장소 맨 위에서 실행한다.
  (가상환경 파이썬: voice/.venv/Scripts/python.exe. 시스템 파이썬에는 httpx가 없음)
  1) 초안:  python voice/judge_eval/relabel_v4.py   (검토용 CSV가 이미 있으면 멈춤. 새로 만들려면 --force)
     기본 새 값으로 일괄 바꾸고, 8번 표의 '다시 볼 항목'에 걸릴 만한 항목에 표시와 이유를 단다.
     → results/labels_v4_review.csv (사람이 final 열을 채움), results/labels_v4_summary.md
  2) 확정:  python voice/judge_eval/relabel_v4.py --apply
     검토한 CSV의 final(비어 있으면 기본 새 값)과 condition, 통화 일시·학생 정보를 읽어 확정한다.
     → labels_v4.json (run_eval이 읽을 새 정답), results/labels_v4_summary.md (바뀐 라벨 수)

'다시 볼 항목' 표시는 학원 발화에서 단어를 찾는 힌트일 뿐이다. 값을 자동으로 바꾸지 않는다. 판정은 사람이 한다.
학원 발화는 v3 판정 캐시의 근거 발화를 먼저 쓰고(있으면), 없으면 그 통화의 학원 발화 전체를 쓴다.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "voice" / "call_worker"))
sys.path.insert(0, str(HERE))
import llm_judge  # noqa: E402
import run_eval  # noqa: E402
from extract import to_turns  # noqa: E402


def _no_api_call(*a, **k):
    raise RuntimeError("캐시 없음")  # 이 스크립트는 LLM을 부르지 않는다. 캐시에 있는 v3 판정만 읽는다


llm_judge._post_gemini = llm_judge._post_openai = _no_api_call

REVIEW_CSV = HERE / "results" / "labels_v4_review.csv"
SUMMARY_MD = HERE / "results" / "labels_v4_summary.md"
LABELS_JSON = HERE / "labels_v4.json"
NEW_VALUES = {"yes", "no", "redirect", "unknown", "not_asked", "answered"}

# 8번 표: 기존 값 → 기본 새 값
DEFAULT = {"yes": "yes", "no": "no", "refused": "redirect", "unknown": "unknown", "uncertain": "unknown",
           "answered": "answered", "not_asked": "not_asked"}

# 통화 일시와 학생 정보 기본값 (개정안 2번·8번: 모든 항목에 채움). 실통화는 실제 날짜, 시각은 모름
DEFAULT_STUDENT = {"grade": "중2", "subject": "수학", "level": "중급", "region": "대구 북구 침산동"}
CALL_AT = {"real_1013": "2026-10-13 화", "real_1019": "2026-10-19 월"}
# 월요일로 둔다: 이번 주 남은 날(다음 날~금)이 화~금이 되어, 수요일 상담을 답한 사례(G47·G55)가 기간 안에 든다
DEFAULT_CALL_AT = "2026-11-09 월 15:00"

# 힌트 단어. 개정안 5·6번에 나온 신호를 옮겼다. 걸리면 '다시 봄' 표시만 한다
HINTS = {
    "추측·보류 신호(→unknown?)": r"아마|확실하진|확실치|제가 알기로|확인해 ?봐야|잘 모르|모르겠|담당이 아니|것 같은데|었던 것 같",
    # '오시면 돼요'처럼 학원이 정해 주는 안내(~시면)는 조건이 아니라서 뺀다. '원하시면', '중급이면'은 남긴다
    "조건(→condition?)": r"(?<!시)면 |원하시면|경우|맞으면|따라|에 한해|만 가능|미리 말씀",
    "학생 정보로 따질 조건(→no?)": r"학년|초등|중등|고등|중학생|고등학생|동만|동은|지역|쪽만|쪽은",
    "기간 밖 이야기(→no?)": r"다음 ?달|다음 ?주|나중에|개강|대기|마감|다음 학기|방학",
    "다른 경로 안내(→redirect?)": r"홈페이지|방문|오셔서|와서 보|사이트|예약|공지|앱|카톡|카카오|레벨 ?테스트 (보|받)고",
    "학원 몫 후속(→unknown, 재통화 표시)": r"연락 ?(드릴|드리|주실)|문자 ?(로 )?(보내|드릴|드리)|알아보고|확인하고 (연락|전화)",
    "이유만 말함(→no?)": r"차서|꽉|없어서|못 해|운영 안|안 해|안 돼|안 됩|어려워",
}
# 학원이 먼저 답했는지 볼 질문별 단어 (not_asked → 물은 것으로?)
TOPIC = {"shuttle": r"차량|셔틀|버스|태워", "pickup": r"픽업|데려다|데리러", "level_fit": r"반이|수준|레벨에 맞",
         "vacancy": r"자리|정원|마감", "level_test": r"레벨 ?테스트|테스트", "class_time": r"요일|[0-9한두세네]+ ?시",
         "consult": r"상담"}


# 요일: '수요일' 또는 '금토일은'처럼 두 글자 이상 묶음. '일정', '일단'의 '일'은 요일이 아니다
WEEKDAY = r"[월화수목금토일]요일|(?<![가-힣])[월화수목금토일]{2,}(?=[은는이가을를에랑과와도만요]|[^가-힣]|$)"


def academy_text(case, item) -> str:
    """그 항목의 근거 학원 발화. v3 캐시가 있으면 근거 발화 번호로, 없으면 통화 전체 학원 발화."""
    turns = to_turns(case["segments"])
    try:
        raw = llm_judge.call_llm(case["questions"], turns, "gemini-3.5-flash-lite", "", HERE / ".cache")["result"]
        got = raw["consult"] if item == "consult" else raw["answers"].get(item, {})
        idx = [i for i in got.get("evidence_turns", []) if 0 <= i < len(turns) and turns[i].speaker == "academy"]
        if idx:
            return " / ".join(turns[i].text for i in idx)
    except Exception:  # 캐시가 없으면 통화 전체 학원 발화로
        pass
    return " / ".join(t.text for t in turns if t.speaker == "academy")


def hints_for(old: str, item: str, text: str) -> list[str]:
    """8번 표 '다시 볼 항목'에 해당할 수 있는 이유들."""
    found = [name for name, pat in HINTS.items() if re.search(pat, text)]
    if old == "yes":
        keep = ["추측·보류 신호(→unknown?)", "조건(→condition?)", "학생 정보로 따질 조건(→no?)", "기간 밖 이야기(→no?)"]
        out = [h for h in found if h in keep]
        if item == "level_fit" and re.search(TOPIC["vacancy"], text):
            out.append("level_fit 뜻 확정 필요(자리 언급)")
        return out
    if old == "refused":
        return ([] if "다른 경로 안내(→redirect?)" in found else ["경로 안내 없음(→unknown?)"])
    if old in ("unknown", "uncertain"):
        keep = ["이유만 말함(→no?)", "다른 경로 안내(→redirect?)", "학원 몫 후속(→unknown, 재통화 표시)"]
        out = [h for h in found if h in keep]
        if item == "consult" and re.search(WEEKDAY, text):
            out.append("일부 요일만 말함(이번 주 남은 날 규칙, 통화 일시 필요)")
        return out
    if old == "not_asked":
        return ["학원이 먼저 답함(→물은 것으로?)"] if re.search(TOPIC.get(item, "$^"), text) else []
    if old == "no":
        return ["다른 경로 안내(→redirect?)"] if "다른 경로 안내(→redirect?)" in found else []
    return []


def draft(force: bool = False):
    if REVIEW_CSV.exists() and not force:
        sys.exit(f"검토용 CSV가 이미 있어 멈춤: {REVIEW_CSV}\n"
                 "사람이 채운 final·condition이 지워지지 않게 막았음. 확정은 --apply, 처음부터 다시 만들려면 --force")
    rows = []
    for case in run_eval.load_cases():
        for item, old in case["labels"].items():
            text = academy_text(case, item)
            reasons = hints_for(old, item, text)
            rows.append({
                "set": case["set"], "case": case["id"], "item": item, "old": old, "new_default": DEFAULT[old],
                "review": "Y" if reasons else "", "reasons": " · ".join(reasons), "final": "", "condition": "",
                "call_at": CALL_AT.get(case["set"], DEFAULT_CALL_AT), **{f"student_{k}": v for k, v in DEFAULT_STUDENT.items()},
                "note": case.get("note", ""), "academy_text": text[:400]})
    REVIEW_CSV.parent.mkdir(exist_ok=True)
    with open(REVIEW_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    flagged = [r for r in rows if r["review"]]
    by_reason = Counter(x for r in flagged for x in r["reasons"].split(" · "))
    lines = ["# 라벨 옮기기 초안 (개정안 8번 표)", "",
             f"항목 {len(rows)}개 · 기본 매핑으로 값이 바뀐 항목 {sum(r['old'] != r['new_default'] for r in rows)}개"
             f"(refused→redirect) · 다시 볼 항목 {len(flagged)}개", "",
             "| 기존 값 | 기본 새 값 | 항목 수 | 다시 볼 항목 |", "|---|---|---|---|"]
    for old, n in Counter(r["old"] for r in rows).most_common():
        lines.append(f"| {old} | {DEFAULT[old]} | {n} | {sum(1 for r in flagged if r['old'] == old)} |")
    lines += ["", "## 다시 볼 이유 (한 항목에 여러 개일 수 있음)", "", "| 이유 | 항목 수 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in by_reason.most_common()]
    lines += ["", f"검토: `{REVIEW_CSV.relative_to(ROOT).as_posix()}`의 final 열에 새 값을 적는다(비우면 기본 새 값).",
              "조건부 가능이면 condition 열에 조건 문장을 적는다. 통화 일시·학생 정보는 기본값이 들어 있으니 답과 어긋나는 항목만 고친다.",
              "다 채우면 `python voice/judge_eval/relabel_v4.py --apply`"]
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:4 + 2 + len(Counter(r['old'] for r in rows))]))
    print(f"\n검토용 CSV: {REVIEW_CSV}")


def apply():
    rows = list(csv.DictReader(open(REVIEW_CSV, encoding="utf-8-sig")))
    bad = [r for r in rows if r["final"].strip() and r["final"].strip() not in NEW_VALUES]
    if bad:
        sys.exit("final 값 오류: " + ", ".join(f"{r['case']}/{r['item']}={r['final']}" for r in bad[:10]))
    out, changes = {}, Counter()
    for r in rows:
        new = r["final"].strip() or r["new_default"]
        if new == "answered" and r["item"] != "class_time":
            sys.exit(f"{r['case']}/{r['item']}: answered는 class_time에만 씀")
        if r["condition"].strip() and new != "yes":
            sys.exit(f"{r['case']}/{r['item']}: condition은 yes에만 붙임")
        key = f"{r['set']}/{r['case']}"
        case = out.setdefault(key, {"call_at": r["call_at"], "student": {k: r[f"student_{k}"] for k in DEFAULT_STUDENT},
                                    "labels": {}, "conditions": {}})
        case["labels"][r["item"]] = new
        if r["condition"].strip():
            case["conditions"][r["item"]] = r["condition"].strip()
        changes[(r["old"], new)] += 1
    LABELS_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    changed = sum(n for (o, nw), n in changes.items() if o != nw)
    lines = ["# 라벨 옮기기 확정 (개정안 8번 표)", "",
             f"항목 {len(rows)}개 중 정답 값이 바뀐 항목 {changed}개 "
             f"(기본 매핑 refused→redirect {changes[('refused', 'redirect')]}개 포함) · "
             f"condition 붙은 항목 {sum(len(c['conditions']) for c in out.values())}개", "",
             "| 기존 값 | 새 값 | 항목 수 |", "|---|---|---|"]
    lines += [f"| {o} | {n} | {c} |" for (o, n), c in sorted(changes.items())]
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n새 정답: {LABELS_JSON}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="검토한 CSV로 새 정답을 확정")
    ap.add_argument("--force", action="store_true", help="검토용 CSV가 있어도 초안을 새로 만듦(검토 내용이 지워짐)")
    args = ap.parse_args()
    apply() if args.apply else draft(args.force)
