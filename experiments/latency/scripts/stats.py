"""Response-gap statistics for the two ClawOps calls from data/results/analysis.json
(and barge-in overlaps from the diarization in data/results/callN.json).
Prints tables and writes data/results/stats.json.

Usage: python scripts/stats.py"""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import OUT  # noqa: E402

SHORT_HUMAN = ('여보세요', '여세요', '네', '응', '예', '아니요', '네?', '네.')


def fix_label(r):
    """Low-confidence speaker labels: short acknowledgements are the human."""
    if abs(r['margin']) < 0.15:
        t = r['text'].replace(' ', '')
        if r['end'] - r['start'] < 1.2 and any(t.startswith(w.replace(' ', '')) for w in SHORT_HUMAN):
            return '사람', True
    return r['who'], abs(r['margin']) < 0.15


def pct(v, p):
    s = sorted(v)
    k = max(1, math.ceil(p / 100 * len(s)))  # nearest-rank
    return s[k - 1]


def summary(v):
    v = sorted(v)
    n = len(v)
    mid = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return {'n': n, 'mean': round(sum(v) / n, 2), 'median': round(mid, 2),
            'p90': pct(v, 90), 'p95': pct(v, 95), 'min': v[0], 'max': v[-1],
            'over_1_5': sum(1 for x in v if x > 1.5)}


def main():
    a = json.load(open(OUT / 'analysis.json', encoding='utf-8'))
    allgaps = []
    res = {}
    for name, c in a.items():
        rows = c['segments']
        for r in rows:
            r['who2'], r['unsure'] = fix_label(r)
        gaps = []
        for p, q in zip(rows, rows[1:]):
            if p['who2'] == '사람' and q['who2'] == 'AI':
                g = round(q['start'] - p['end'], 2)
                gaps.append({'human_end': p['end'], 'ai_start': q['start'], 'gap': g,
                             'human': p['text'], 'ai': q['text'][:40]})
        print(f'\n== {name} ({c["duration"]:.0f}s) ==')
        for r in rows:
            flag = '?' if r['unsure'] else ' '
            print(f"{r['start']:7.2f}-{r['end']:7.2f} {r['who2']:2s}{flag} {r['text'][:70]}")
        print('-- response gaps (human end -> AI start)')
        for g in gaps:
            print(f"  {g['human_end']:7.2f} -> {g['ai_start']:7.2f}  {g['gap']:.2f}s   [{g['human']}] -> [{g['ai']}]")
        s = summary([g['gap'] for g in gaps])
        print('  summary', s)
        allgaps += [g['gap'] for g in gaps]
        # barge-in from diarization overlaps: human starts while AI still speaking
        d = json.load(open(OUT / f'{name}.json', encoding='utf-8'))
        tr = d['turns']
        barge = []
        for p, q in zip(tr, tr[1:]):
            if p['spk'] != q['spk'] and q['start'] < p['end']:
                barge.append({'interrupt_at': q['start'], 'other_end': p['end'],
                              'overlap': round(p['end'] - q['start'], 2), 'from': p['spk'], 'to': q['spk']})
        print('  overlaps (diarization)', barge)
        res[name] = {'rows': rows, 'gaps': gaps, 'summary': s, 'overlaps': barge}
    res['all'] = summary(allgaps)
    print('\nALL', res['all'])
    json.dump(res, open(OUT / 'stats.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
