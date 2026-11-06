"""질문별 판정 비교: 키워드 사전(현재 워커) vs LLM. 같은 시험 세트로 정확도와 '틀린 확정 답'을 센다.

시험 세트
- real_1013: 10/13 지연 측정 실통화 16통(Whisper 전사, 대본 A~E·H의 정답지 voice/prompts/test_script_v3.md)
- real_1019: 10/19 실통화 5통(ClawOps 전사, test_worker.py의 시험 자료 2통 + real_1019_joint.json 3통)
- synthetic: 키워드 사전이 어려워하는 말투를 모은 합성 전사(cases_synthetic.json). 프롬프트를 다듬을 때 본 개발용 세트
- agent: 프롬프트와 기존 사례를 보지 못하게 한 별도 AI 에이전트(Sonnet)가 쓴 60개(cases_agent.json). 사람이 쓴 사례가 아니므로 구분해서 밝힌다
- heldout: 프롬프트를 고칠 때 보지 않는 시험용 세트(cases_heldout.json). 평이한 말투와 어려운 말투를 섞음. 정답은 LLM 실행 전에 커밋함

저장소 맨 위에서 실행한다.
  python voice/judge_eval/run_eval.py                 키워드만 (API 호출 없음)
  python voice/judge_eval/run_eval.py --llm           키워드 + LLM (voice/.env의 GEMINI_API_KEY, 결과는 .cache에 저장해 재실행 시 재호출 안 함)
  python voice/judge_eval/run_eval.py --llm --model gpt-4.1-mini   gemini-로 시작하지 않으면 OPENAI_API_KEY 사용
"""
import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "voice" / "call_worker"))
sys.path.insert(0, str(HERE))
from extract import build_answers, consult_result, positions, to_turns  # noqa: E402
from llm_judge import PROMPT_VERSION  # noqa: E402

GREETING = [["A", "안녕하세요, 학부모님을 대신해 문의드리는 AI 상담원입니다. 이 통화는 녹음됩니다. 잠시 통화 괜찮으실까요?"], ["H", "네, 괜찮아요."]]

# 10/13 정답지(test_script_v3.md). D2(ClawOps)는 대본 A로 답함, H는 A와 같은 답
SCRIPT_LABELS = {
    "A": {"vacancy": "yes", "class_time": "answered", "consult": "yes"},
    "B": {"vacancy": "yes", "class_time": "answered", "consult": "yes"},
    "C": {"vacancy": "yes", "class_time": "answered", "consult": "yes"},
    "D": {"vacancy": "no", "class_time": "answered", "consult": "yes"},
    "E": {"vacancy": "unknown", "class_time": "answered", "consult": "unknown"},
}
CALL_SCRIPT = {"co_A": "A", "co_A2": "A", "co_B": "B", "co_C": "C", "co_D": "D", "co_D2": "A", "co_E": "E", "co_H": "A",
               "va_A": "A", "va_A2": "A", "va_B": "B", "va_C": "C", "va_D": "D", "va_D2": "D", "va_E": "E", "va_H": "A"}

# 10/19 공동 시험 통화. 21:31 통화는 test_worker.py의 REAL_1019_RECONFIRM과 같아서 넣지 않음
JOINT = [
    ("2118", ["shuttle", "pickup", "class_time"], {"shuttle": "yes", "pickup": "yes", "class_time": "answered", "consult": "yes"}),
    ("2122", ["pickup", "vacancy", "level_test"], {"pickup": "no", "vacancy": "yes", "level_test": "yes", "consult": "yes"}),
    ("2126", ["shuttle", "pickup", "class_time"], {"shuttle": "yes", "pickup": "no", "class_time": "answered", "consult": "yes"}),
]


def seg(spk, text, i):
    return {"speaker": spk, "start": i, "text": text}


def load_cases() -> list[dict]:
    cases = []
    for name, script in CALL_SCRIPT.items():
        rows = json.loads((ROOT / f"experiments/latency/data/results/1013_{name}_rows.json").read_text(encoding="utf-8"))
        segs = [seg("A" if r["who"] == "AI" else "H", r["text"], r["start"]) for r in rows]
        cases.append({"set": "real_1013", "id": name, "questions": ["vacancy", "class_time"], "segments": segs,
                      "labels": SCRIPT_LABELS[script]})
    spec = importlib.util.spec_from_file_location("tw", ROOT / "voice/call_worker/test_worker.py")
    tw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tw)
    for cid, data in (("1019_local", tw.REAL_1019), ("1019_reconfirm", tw.REAL_1019_RECONFIRM)):
        cases.append({"set": "real_1019", "id": cid, "questions": ["shuttle", "pickup", "class_time"], "segments": data,
                      "labels": {"shuttle": "yes", "pickup": "no", "class_time": "answered", "consult": "yes"}})
    joint = json.loads((HERE / "real_1019_joint.json").read_text(encoding="utf-8"))
    for cid, qs, labels in JOINT:
        cases.append({"set": "real_1019", "id": cid, "questions": qs, "segments": joint[cid], "labels": labels})
    for name, fname in (("synthetic", "cases_synthetic.json"), ("heldout", "cases_heldout.json"), ("agent", "cases_agent.json")):
        for c in json.loads((HERE / fname).read_text(encoding="utf-8")):
            body = GREETING + c["body"]
            cases.append({"set": name, "id": c["id"], "note": c["note"], "questions": c["questions"],
                          "segments": [seg(s, t, i) for i, (s, t) in enumerate(body)], "labels": c["labels"]})
    return cases


def status_of(row: dict) -> str:
    if not row["asked"]:
        return "not_asked"
    if row["answered"]:
        return {True: "yes", False: "no"}.get(row["yes_no"], "answered")
    return "refused" if row.get("reason") == "refused" else "unknown"


def keyword_predict(case, turns) -> dict:
    qs = [{"question_id": f"q{i}", "question_code": c} for i, c in enumerate(case["questions"])]
    pred = {r["question_code"]: status_of(r) for r in build_answers(qs, turns)}
    accepted, _ = consult_result(turns, qs)
    pred["consult"] = {True: "yes", False: "no"}.get(accepted, "unknown")
    if positions(qs, turns)[1] is None:
        pred["consult"] = "not_asked"
    return pred


def llm_predict(case, turns, model, key, cache) -> tuple[dict, dict]:
    from llm_judge import call_llm, to_contract
    qs = [{"question_id": f"q{i}", "question_code": c} for i, c in enumerate(case["questions"])]
    out = call_llm(case["questions"], turns, model, key, cache)
    answers, consult = to_contract(qs, turns, out["result"])
    pred = {a["question_code"]: a["status"] for a in answers}
    pred["consult"] = consult["status"]
    return pred, {"answers": answers, "consult": consult, "usage": out.get("usage", {}), "model": out.get("model")}


UNRESOLVED = {"unknown", "refused"}
DEFINITE = {"yes", "no", "answered"}


def grade(truth: str, pred: str) -> str:
    if truth == pred or (truth in UNRESOLVED and pred in UNRESOLVED):
        return "ok"
    if {truth, pred} == {"yes", "no"}:
        return "flip"          # 예↔아니오 뒤바뀜: 학부모에게 가장 해로움
    if pred in DEFINITE:
        return "overclaim"     # 모르는데 확정 답을 냄
    return "underclaim"        # 답했는데 미확인/못 물음으로 둠


def summarize(rows, method):
    out = {}
    for s in ("real_1013", "real_1019", "synthetic", "heldout", "agent", "전체"):
        rs = [r for r in rows if s == "전체" or r["set"] == s]
        g = [r[f"{method}_grade"] for r in rs]
        out[s] = {"n": len(g), "ok": g.count("ok"), "flip": g.count("flip"), "over": g.count("overclaim"), "under": g.count("underclaim")}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--model", default="gemini-3.5-flash")
    args = ap.parse_args()
    key = None
    if args.llm:
        env = dict(l.split("=", 1) for l in (ROOT / "voice/.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
        name = "GEMINI_API_KEY" if args.model.startswith("gemini") else "OPENAI_API_KEY"
        key = env.get(name, "").strip().strip('"')
        if not key:
            sys.exit(f"voice/.env의 {name}가 비어 있습니다.")
    rows, usage, served = [], {"prompt_tokens": 0, "completion_tokens": 0}, set()
    for case in load_cases():
        turns = to_turns(case["segments"])
        kw = keyword_predict(case, turns)
        llm, extra = ({}, {})
        if args.llm:
            llm, extra = llm_predict(case, turns, args.model, key, HERE / ".cache")
            served.add(extra.get("model"))
            for k in usage:
                usage[k] += extra["usage"].get(k, 0)
        for item, truth in case["labels"].items():
            r = {"set": case["set"], "case": case["id"], "item": item, "truth": truth,
                 "keyword": kw.get(item, "not_asked"), "note": case.get("note", "")}
            r["keyword_grade"] = grade(truth, r["keyword"])
            if args.llm:
                r["llm"] = llm.get(item, "not_asked")
                r["llm_grade"] = grade(truth, r["llm"])
                if item == "consult":
                    got = extra["consult"]
                    r["llm_detail"] = f"가능 {got['available_times']} / 불가 {got['unavailable_times']}"
                else:
                    got = next((a for a in extra["answers"] if a["question_code"] == item), {})
                    r["llm_detail"] = got.get("detail", "")
                r["source_text"] = got.get("source_text", "")
                r["detail_checked"] = got.get("detail_checked", True)
                r["certainty"] = got.get("certainty", "")
                r["leaning"] = got.get("leaning") or ""
            rows.append(r)

    res = HERE / "results"
    res.mkdir(exist_ok=True)
    suffix = f"_{args.model}_{PROMPT_VERSION}" if args.llm else "_keyword"
    with open(res / f"items{suffix}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    methods = ["keyword"] + (["llm"] if args.llm else [])
    lines = [f"# 질문별 판정 비교 ({'키워드 vs LLM ' + args.model if args.llm else '키워드만'})", "",
             "| 세트 | 방법 | 항목 | 맞음 | 정확도 | 예↔아니오 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |", "|---|---|---|---|---|---|---|---|"]
    for m in methods:
        for s, v in summarize(rows, m).items():
            lines.append(f"| {s} | {m} | {v['n']} | {v['ok']} | {v['ok'] / v['n']:.0%} | {v['flip']} | {v['over']} | {v['under']} |")
    if args.llm:
        bad = [r for r in rows if not r["detail_checked"]]
        lines += ["", f"요약 사실 검사(숫자·요일이 학원 원문에 있는지) 실패: {len(bad)}/{len(rows)}건 (실패하면 요약 대신 인용 원문을 씀)"]
        lines += [f"- {r['set']} {r['case']} {r['item']}: 요약 '{r['llm_detail']}' / 원문 '{r['source_text']}'" for r in bad]
        unsure = [r for r in rows if r["leaning"]]
        lines += ["", f"학원이 확정하지 않아 미확인으로 돌린 항목: {len(unsure)}건 (확실성 guess·deferred)"]
        lines += [f"- {r['set']} {r['case']} {r['item']}: 정답 {r['truth']} / 기운 쪽 {r['leaning']} ({r['certainty']}) / 원문 '{r['source_text']}'" for r in unsure]
        lines += ["", f"실제 응답 모델: {sorted(str(m) for m in served)} / 프롬프트 판: {PROMPT_VERSION}", f"토큰: 입력 {usage['prompt_tokens']:,} / 출력 {usage['completion_tokens']:,} (캐시된 결과는 처음 호출 때 값)"]
    lines += ["", "## 틀린 항목", "", "| 세트 | 통화 | 항목 | 정답 | " + " | ".join(methods) + " | 메모 |", "|---|---|---|---|" + "---|" * len(methods) + "---|"]
    for r in rows:
        if any(r[f"{m}_grade"] != "ok" for m in methods):
            cells = " | ".join(f"{r[m]}{'' if r[m + '_grade'] == 'ok' else ' ✗'}" for m in methods)
            note = r["note"] + (f" · LLM: {r['llm_detail']}" if args.llm else "")
            lines.append(f"| {r['set']} | {r['case']} | {r['item']} | {r['truth']} | {cells} | {note} |")
    (res / f"report{suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:4 + 6 * len(methods)]))
    print(f"\n자세한 결과: {res / f'report{suffix}.md'}")


if __name__ == "__main__":
    main()
