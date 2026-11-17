"""계층 판정(tiered.py)을 시험 세트로 채점한다. 층별 점수와 모델별 토큰·비용을 함께 낸다.

저장소 맨 위에서 실행한다. 키는 voice/.env(OPENAI_API_KEY, GEMINI_API_KEY)에서 읽는다.
  python voice/judge_eval/run_tiered.py --config luna_terra                 실험 1: 같은 회사 (1차 luna → 2차 terra)
  python voice/judge_eval/run_tiered.py --config luna_gemini                실험 2: 다른 회사 (1차 luna → 2차 gemini)
  python voice/judge_eval/run_tiered.py --config luna_only                  기준: 1차만(2차 없음), 요약은 luna
  python voice/judge_eval/run_tiered.py --config gemini_terra               참고: 1차 gemini → 2차 terra
  python voice/judge_eval/run_tiered.py --config luna_terra --sets real_1013,real_1019    실통화 68항목만
  python voice/judge_eval/run_tiered.py --config luna_terra --limit 3       사례 3개만 (비용 확인용)

응답은 .cache/에 저장되어 같은 입력은 다시 부르지 않는다. 결과는 results/tiered_<config>.csv와 .md.
채점은 run_eval.grade와 같다(정답 refused·unknown과 판정 redirect·unknown은 같은 '미확정' 묶음).
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "voice" / "call_worker"))
sys.path.insert(0, str(HERE))
from extract import to_turns  # noqa: E402
from run_eval import load_cases  # noqa: E402
from tiered import VERSION, Ledger, Tier, judge  # noqa: E402

LUNA, TERRA, GEM = "gpt-5.6-luna", "gpt-5.6-terra", "gemini-3.5-flash-lite"
CONFIGS = {
    "luna_only": {"triage": Tier(LUNA), "review": None, "summary": Tier(LUNA)},
    "luna_terra": {"triage": Tier(LUNA), "review": Tier(TERRA), "summary": Tier(LUNA)},
    "luna_gemini": {"triage": Tier(LUNA), "review": Tier(GEM), "summary": Tier(LUNA)},
    "gemini_terra": {"triage": Tier(GEM), "review": Tier(TERRA), "summary": Tier(GEM)},
    "gemini_only": {"triage": Tier(GEM), "review": None, "summary": Tier(GEM)},
}
UNRESOLVED = {"unknown", "refused", "redirect"}
DEFINITE = {"yes", "no", "answered"}


def grade(truth, pred):
    if truth == pred or (truth in UNRESOLVED and pred in UNRESOLVED):
        return "ok"
    if {truth, pred} == {"yes", "no"}:
        return "flip"
    if pred in DEFINITE:
        return "overclaim"
    return "underclaim"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, choices=list(CONFIGS))
    ap.add_argument("--sets", default="", help="쉼표로 나눈 세트 이름. 비우면 전체")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N개 사례만")
    ap.add_argument("--reasoning", default="", help="1차·요약 모델의 추론 설정(OpenAI: none/low/medium/high, Gemini: low/medium/high)")
    args = ap.parse_args()
    keys = dict(l.split("=", 1) for l in (ROOT / "voice/.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
    keys = {k: v.strip().strip('"') for k, v in keys.items()}
    tiers = dict(CONFIGS[args.config])
    if args.reasoning:
        tiers = {k: (Tier(t.model, args.reasoning) if t and k != "review" else t) for k, t in tiers.items()}
    tag = args.config + (f"_{args.reasoning}" if args.reasoning else "")

    cases = load_cases()
    if args.sets:
        want = set(args.sets.split(","))
        cases = [c for c in cases if c["set"] in want]
    if args.limit:
        cases = cases[:args.limit]
    ledger, rows = Ledger(), []
    for n, case in enumerate(cases, 1):
        turns = to_turns(case["segments"])
        qs = [{"question_id": f"q{i}", "question_code": c} for i, c in enumerate(case["questions"])]
        out, _ = judge(qs, turns, tiers, keys, HERE / ".cache", ledger=ledger)
        for item, truth in case["labels"].items():
            r = out.get(item)
            pred = r["status"] if r else "not_asked"
            rows.append({"set": case["set"], "case": case["id"], "item": item, "truth": truth,
                         "triage": r["triage"] if r else "", "triage_grade": grade(truth, r["triage"]) if r else "",
                         "signal": r["signal"] if r else "", "review_reasons": " · ".join(r["review_reasons"]) if r else "",
                         "reviewed": "Y" if r and r["reviewed"] else "", "review": r["review"] or "" if r else "",
                         "final": pred, "final_grade": grade(truth, pred),
                         "certainty": r["certainty"] if r else "", "condition": r["condition"] if r else "",
                         "detail": r.get("detail", "") if r else "", "detail_checked": r.get("detail_checked", "") if r else "",
                         "source_text": r["source_text"] if r else "", "note": case.get("note", "")})
        print(f"  {n}/{len(cases)} {case['id']}  누적 ${ledger.usd():.3f}", flush=True)

    res = HERE / "results"
    res.mkdir(exist_ok=True)
    with open(res / f"tiered_{tag}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def summ(key):
        out = {}
        for s in ("real_1013", "real_1019", "synthetic", "heldout", "agent", "전체"):
            rs = [r for r in rows if (s == "전체" or r["set"] == s) and r[key]]
            if not rs:
                continue
            g = Counter(r[key] for r in rs)
            out[s] = (len(rs), g["ok"], g["flip"], g["overclaim"], g["underclaim"])
        return out

    desc = " / ".join(f"{k}: {t.model}{'(' + t.reasoning + ')' if t.reasoning else ''}" if t else f"{k}: 없음" for k, t in tiers.items())
    lines = [f"# 계층 판정 {tag} ({VERSION})", "", f"구성: {desc}", "",
             "| 세트 | 층 | 항목 | 맞음 | 정확도 | 뒤바뀜 | 모르는데 확정 | 답했는데 미확인 |", "|---|---|---|---|---|---|---|---|"]
    for layer, key in (("1차", "triage_grade"), ("최종", "final_grade")):
        for s, (n, ok, fl, ov, un) in summ(key).items():
            lines.append(f"| {s} | {layer} | {n} | {ok} | {ok / n:.0%} | {fl} | {ov} | {un} |")
    reviewed = [r for r in rows if r["reviewed"]]
    fixed = [r for r in reviewed if r["triage_grade"] != "ok" and r["final_grade"] == "ok"]
    broke = [r for r in reviewed if r["triage_grade"] == "ok" and r["final_grade"] != "ok"]
    lines += ["", f"2차로 넘어간 항목 {len(reviewed)}/{len(rows)} ({len(reviewed) / len(rows):.0%}) · 2차가 고침 {len(fixed)} · 2차가 망가뜨림 {len(broke)}",
              "넘긴 이유: " + ", ".join(f"{k} {v}" for k, v in Counter(x for r in reviewed for x in r["review_reasons"].split(" · ")).most_common())]
    lines += ["", "## 비용 (캐시 적중은 처음 호출 값)", "", "| 모델 | 호출 | 입력 토큰 | 출력(추론 포함) | 추론 | 시간(초) |", "|---|---|---|---|---|---|"]
    for m, a in ledger.by_model().items():
        lines.append(f"| {m} | {a['calls']} | {a['prompt_tokens']:,} | {a['billed_output_tokens']:,} | {a['thoughts_tokens']:,} | {a['seconds']:.0f} |")
    lines += [f"\n합계 약 ${ledger.usd():.3f} (사례 {len(cases)}개, 사례당 ${ledger.usd() / max(len(cases), 1):.4f})"]
    lines += ["", "## 틀린 항목 (최종)", "", "| 세트 | 통화 | 항목 | 정답 | 1차 | 2차 | 최종 | 넘긴 이유 | 메모 |", "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {r['set']} | {r['case']} | {r['item']} | {r['truth']} | {r['triage']} | {r['review']} | {r['final']} ✗ | {r['review_reasons']} | {r['note']} |"
              for r in rows if r["final_grade"] != "ok"]
    lines += ["", "## 2차가 바꾼 항목", "", "| 세트 | 통화 | 항목 | 정답 | 1차 | 2차 | 결과 |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {r['set']} | {r['case']} | {r['item']} | {r['truth']} | {r['triage']} | {r['review']} | {'고침' if r in fixed else '망가뜨림' if r in broke else '같은 묶음'} |"
              for r in reviewed if r["triage"] != r["review"]]
    (res / f"tiered_{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:8 + 2 * len(summ('final_grade'))]))
    print(f"\n자세한 결과: {res / f'tiered_{tag}.md'}")


if __name__ == "__main__":
    main()
