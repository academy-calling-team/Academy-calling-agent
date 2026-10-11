"""Response gaps (AI start - human end) from a per-segment rows file.

Rows come from one_call.py (<name>_rows.json, field 'who' = '사람' / 'AI') or
from transcribe_turns.py (<name>_asr.json, field 'spk' = 0 / 1; pass --ai-spk
with the AI's number - read the transcript first to see which one it is).

A gap is counted at every human -> AI change between consecutive segments.
Gaps <= 0 s are overlaps (a backchannel such as "네", or a barge-in): they are
listed separately and left out of the statistics. p95 is nearest-rank.
Writes data/results/<name>_gaps.json.

Usage: python scripts/gaps.py luna_rows.json
       python scripts/gaps.py vapi_asr.json --ai-spk 1
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import OUT  # noqa: E402


def pct(v, p):
    s = sorted(v)
    k = max(1, math.ceil(p / 100 * len(s)))  # nearest-rank
    return s[k - 1]


def summary(v):
    if not v:
        return {'n': 0}
    v = sorted(v)
    n = len(v)
    mid = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return {'n': n, 'mean': round(sum(v) / n, 2), 'median': round(mid, 2),
            'p90': pct(v, 90), 'p95': pct(v, 95), 'min': v[0], 'max': v[-1],
            'over_1_5': sum(1 for x in v if x > 1.5)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rows', help='rows file: a name in data/results or a path')
    ap.add_argument('--ai-spk', type=int, help="speaker number of the AI when rows carry 'spk'")
    a = ap.parse_args()

    p = Path(a.rows)
    if not p.exists():
        p = OUT / a.rows
    rows = json.load(open(p, encoding='utf-8'))

    def who(r):
        if 'who' in r:
            return r['who']
        if a.ai_spk is None:
            sys.exit("rows carry speaker numbers: pass --ai-spk N (check the transcript for the AI's number)")
        return 'AI' if r['spk'] == a.ai_spk else '사람'

    for r in rows:
        print(f"{r['start']:7.2f}-{r['end']:7.2f} {who(r):2s} {r['text'][:60]}")

    gaps, overlaps = [], []
    for prev, nxt in zip(rows, rows[1:]):
        if who(prev) == '사람' and who(nxt) == 'AI':
            g = round(nxt['start'] - prev['end'], 2)
            item = {'human_end': prev['end'], 'ai_start': nxt['start'], 'gap': g,
                    'human': prev['text'], 'ai': nxt['text'][:40]}
            (gaps if g > 0 else overlaps).append(item)

    print('-- response gaps (human end -> AI start)')
    for g in gaps:
        print(f"  {g['human_end']:7.2f} -> {g['ai_start']:7.2f}  {g['gap']:.2f}s   [{g['human']}] -> [{g['ai']}]")
    if overlaps:
        print('-- overlaps left out (gap <= 0)')
        for g in overlaps:
            print(f"  {g['human_end']:7.2f} -> {g['ai_start']:7.2f}  {g['gap']:.2f}s   [{g['human']}] -> [{g['ai']}]")
    s = summary([g['gap'] for g in gaps])
    print('summary', s)

    stem = p.stem
    for suffix in ('_rows', '_asr'):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    out = OUT / f'{stem}_gaps.json'
    json.dump({'source': p.name, 'ai_spk': a.ai_spk, 'gaps': gaps, 'overlaps': overlaps, 'summary': s},
              open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('wrote', out)


if __name__ == '__main__':
    main()
