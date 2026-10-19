"""사람이 직접 잰 응답 지연(data/human_result/human_1013.csv)으로 논문과 비교 문서의 통계를 다시 계산한다.

- 포함 기준: latency 열이 1인 행만 쓴다. H 통화, 응답이 아닌 간격(note에 이유)은 0이다.
- p90, p95, 최대: nearest-rank(정렬한 값의 ceil(p/100*n)번째).
- 대본 A~E 분위수 차이: numpy 기본(선형 보간) 분위수의 차이.
- 부트스트랩: 플랫폼마다 응답을 복원 추출해 중앙값 차이를 20,000번 계산, 2.5와 97.5 백분위(시드 0).
  같은 통화 안의 응답이 독립이 아니라서 탐색적 값이다.
- Mann-Whitney U: scipy.stats.mannwhitneyu 기본값(양측).
- 통화 단위 비교(논문 7판): 같은 통화의 응답은 독립이 아니므로 통화별 중앙값에 Mann-Whitney를 쓰고,
  통화를 복원 추출해 응답을 모은 뒤 중앙값 차이를 20,000번 계산한 2.5와 97.5 백분위를 구간으로 쓴다(시드 0, 별도 생성기).
- 그림: 응답별 지연을 플랫폼마다 점으로 찍은 SVG(그림 2용). 1.5초 기준선, 중앙값, p95 표시.

사용: python human_stats.py [csv 경로] [svg 저장 경로]
"""
import csv
import math
import random
import sys
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu

HERE = Path(__file__).resolve().parent
CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / 'data' / 'human_result' / 'human_1013.csv'
SVG = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent / 'data' / 'human_result' / 'fig2_latency_1013.svg'
AE = {'A', 'B', 'C', 'D', 'E'}
ENGINES = [('co', 'ClawOps'), ('va', 'Vapi')]


def load(path):
    rows = []
    for r in csv.DictReader(open(path, encoding='utf-8')):
        if r['latency'] != '1' or not r['gap_manual']:
            continue
        _, engine, script = r['name'].split('_')
        rows.append({'engine': engine, 'script': script, 'no': r['no'], 'gap': float(r['gap_manual'])})
    return rows


def nearest_rank(values, p):
    v = sorted(values)
    return v[math.ceil(p / 100 * len(v)) - 1]


def summary(values):
    v = np.array(values)
    return {'n': len(v), 'mean': v.mean(), 'median': float(np.median(v)), 'p90': nearest_rank(v, 90),
            'p95': nearest_rank(v, 95), 'max': v.max(), 'over_1_5': int((v > 1.5).sum()), 'under_1_2': int((v < 1.2).sum())}


def boot_median_diff(a, b, rng, n=20000):
    a, b = np.array(a), np.array(b)
    d = [np.median(rng.choice(a, len(a))) - np.median(rng.choice(b, len(b))) for _ in range(n)]
    return np.percentile(d, [2.5, 97.5])


def boot_call_median_diff(a_calls, b_calls, rng, n=20000):
    a_calls, b_calls = [np.array(c) for c in a_calls], [np.array(c) for c in b_calls]
    d = []
    for _ in range(n):
        a = np.concatenate([a_calls[i] for i in rng.integers(0, len(a_calls), len(a_calls))])
        b = np.concatenate([b_calls[i] for i in rng.integers(0, len(b_calls), len(b_calls))])
        d.append(np.median(a) - np.median(b))
    return np.percentile(d, [2.5, 97.5])


def main():
    rows = load(CSV)
    by = {e: [r['gap'] for r in rows if r['engine'] == e] for e, _ in ENGINES}
    ae = {e: [r['gap'] for r in rows if r['engine'] == e and r['script'] in AE] for e, _ in ENGINES}
    first = {e: [r['gap'] for r in rows if r['engine'] == e and r['no'] == '1'] for e, _ in ENGINES}

    for e, label in ENGINES:
        s = summary(by[e])
        print(f"{label}: n={s['n']} 평균 {s['mean']:.2f} 중앙값 {s['median']:.3f} p90 {s['p90']:.2f} p95 {s['p95']:.2f} "
              f"최대 {s['max']:.2f} 1.5초 넘음 {s['over_1_5']} ({s['over_1_5'] / s['n']:.0%}) 1.2초 미만 {s['under_1_2']} "
              f"첫 응답 중앙값 {np.median(first[e]):.2f} (통화 {len(first[e])}개)")

    co, va = by['co'], by['va']
    print(f"차이(ClawOps-Vapi): 평균 {np.mean(co) - np.mean(va):.3f} 중앙값 {np.median(co) - np.median(va):.3f} "
          f"p95 {nearest_rank(co, 95) - nearest_rank(va, 95):.2f}")
    rng = np.random.default_rng(0)
    lo, hi = boot_median_diff(co, va, rng)
    print(f"부트스트랩 95% 구간(전체): {lo:.2f}~{hi:.2f}, Mann-Whitney p={mannwhitneyu(co, va).pvalue:.2g}")
    lo, hi = boot_median_diff(ae['co'], ae['va'], rng)
    print(f"대본 A~E: n={len(ae['co'])}/{len(ae['va'])} 중앙값 차이 {np.median(ae['co']) - np.median(ae['va']):.3f}, "
          f"부트스트랩 95% 구간 {lo:.2f}~{hi:.2f}")
    print('대본 A~E 분위수 차이: ' + ', '.join(
        f"p{p} {np.percentile(ae['co'], p) - np.percentile(ae['va'], p):+.2f}" for p in (10, 25, 50, 75, 90)))

    calls = {e: {} for e, _ in ENGINES}
    for r in rows:
        calls[r['engine']].setdefault(r['script'], []).append(r['gap'])
    med = {e: [float(np.median(v)) for v in calls[e].values()] for e, _ in ENGINES}
    for e, label in ENGINES:
        print(f"{label} 통화별 중앙값: " + ', '.join(f'{s} {np.median(v):.2f}' for s, v in calls[e].items()))
    lo, hi = boot_call_median_diff(list(calls['co'].values()), list(calls['va'].values()), np.random.default_rng(0))
    print(f"통화 단위: 통화 중앙값 Mann-Whitney p={mannwhitneyu(med['co'], med['va']).pvalue:.3f}, "
          f"통화 재추출 부트스트랩 95% 구간 {lo:.2f}~{hi:.2f}")

    write_svg(rows, by)
    print(f'그림: {SVG}')


def write_svg(rows, by):
    W, H, left, right, top, bottom = 560, 380, 70, 20, 40, 60
    ymin, ymax = 0.8, 2.6
    y = lambda s: top + (ymax - s) / (ymax - ymin) * (H - top - bottom)
    cols = {'co': left + 140, 'va': left + 330}
    color = {'ae': '#1f4e79', 'extra': '#d0802a'}
    font = "font-family='Malgun Gothic, Apple SD Gothic Neo, sans-serif'"
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>",
           f"<rect width='{W}' height='{H}' fill='white'/>"]
    for t in [0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6]:
        out.append(f"<line x1='{left}' x2='{W - right}' y1='{y(t):.1f}' y2='{y(t):.1f}' stroke='#e5e5e5'/>")
        out.append(f"<text x='{left - 8}' y='{y(t) + 4:.1f}' font-size='11' text-anchor='end' {font}>{t:.1f}</text>")
    out.append(f"<line x1='{left}' x2='{left}' y1='{top}' y2='{H - bottom}' stroke='#333'/>")
    out.append(f"<text x='18' y='{(top + H - bottom) / 2:.0f}' font-size='12' {font} transform='rotate(-90 18 {(top + H - bottom) / 2:.0f})' text-anchor='middle'>응답 지연 (초)</text>")
    out.append(f"<line x1='{left}' x2='{W - right}' y1='{y(1.5):.1f}' y2='{y(1.5):.1f}' stroke='#c00' stroke-dasharray='6 4'/>")
    out.append(f"<text x='{W - right}' y='{y(1.5) - 5:.1f}' font-size='11' fill='#c00' text-anchor='end' {font}>목표: 중앙값 1.5초</text>")
    rnd = random.Random(1)
    for e, label in ENGINES:
        cx = cols[e]
        for r in (r for r in rows if r['engine'] == e):
            group = 'ae' if r['script'] in AE else 'extra'
            out.append(f"<circle cx='{cx + rnd.uniform(-45, 45):.1f}' cy='{y(r['gap']):.1f}' r='3.6' fill='{color[group]}' fill-opacity='0.75'/>")
        med, p95 = float(np.median(by[e])), nearest_rank(by[e], 95)
        out.append(f"<line x1='{cx - 60}' x2='{cx + 60}' y1='{y(med):.1f}' y2='{y(med):.1f}' stroke='#000' stroke-width='2.5'/>")
        out.append(f"<text x='{cx + 64}' y='{y(med) + 4:.1f}' font-size='11' {font}>중앙값 {med:.2f}</text>")
        out.append(f"<line x1='{cx - 30}' x2='{cx + 30}' y1='{y(p95):.1f}' y2='{y(p95):.1f}' stroke='#000' stroke-dasharray='3 3'/>")
        out.append(f"<text x='{cx + 64}' y='{y(p95) + 4:.1f}' font-size='11' {font}>p95 {p95:.2f}</text>")
        out.append(f"<text x='{cx}' y='{H - bottom + 20}' font-size='13' text-anchor='middle' {font}>{label} (n={len(by[e])})</text>")
    lx, ly = left + 10, H - 18
    out.append(f"<circle cx='{lx}' cy='{ly - 4}' r='4' fill='{color['ae']}'/><text x='{lx + 8}' y='{ly}' font-size='11' {font}>대본 A~E</text>")
    out.append(f"<circle cx='{lx + 90}' cy='{ly - 4}' r='4' fill='{color['extra']}'/><text x='{lx + 98}' y='{ly}' font-size='11' {font}>추가 통화(A2, D2)</text>")
    out.append(f"<text x='{lx + 230}' y='{ly}' font-size='11' {font}>굵은 선: 중앙값, 점선: p95</text>")
    out.append('</svg>')
    SVG.write_text('\n'.join(out), encoding='utf-8')


if __name__ == '__main__':
    main()
