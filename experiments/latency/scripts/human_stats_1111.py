"""11/11 시험(프롬프트 길이·말하는 모델)의 직접 측정 지연을 묶음별로 정리한다.

자료: data/human_result/human_1111_phone.csv (김규림이 휴대폰 녹음을 뷰어 -60 dB로 직접 잼, 묶음을 가린 채)
  - call: 1111_co_<대본>_<묶음>. 묶음 L=기준(v3 프롬프트, gpt-live-1), S=짧은 프롬프트, M=gpt-realtime-2.1-mini
  - blind: 측정할 때 쓴 번호(01~18). kind: 자동(뷰어가 잡은 간격) / 직접(사람이 경계를 찍어 추가)
통계 기준은 human_stats.py(10/13)와 같다.
  - 대본 A~E만 지연 통계에 넣는다. H는 쉼에 끼어드는지 보는 대본이라 참고로만 출력한다.
  - p90·p95·최대는 nearest-rank.
  - 같은 통화의 응답은 독립이 아니므로, 통화별 중앙값에 Mann-Whitney U(양측)를 쓴다.
  - 구간: 묶음마다 통화를 복원 추출해 응답을 모은 뒤 중앙값 차이를 20,000번 계산한 2.5·97.5 백분위(시드 0).
  - 11/2 같은 에이전트(ClawOps)의 휴대폰 직접 측정(human_1102_phone.csv, 대본 A~E, use=1)과 기준선을 비교한다.

사용: python experiments/latency/scripts/human_stats_1111.py
"""
import csv
import math
import random
import statistics as st
import sys
from pathlib import Path

from scipy.stats import mannwhitneyu

HERE = Path(__file__).resolve().parent
HR = HERE.parent / 'data' / 'human_result'
VARIANTS = {'L': '기준 (v3 프롬프트, gpt-live-1)', 'S': '짧은 프롬프트 (v3의 44%, gpt-live-1)',
            'M': 'gpt-realtime-2.1-mini (v3 프롬프트)'}


def nearest_rank(vals, p):
    s = sorted(vals)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def per_call(rows):
    out = {}
    for r in rows:
        out.setdefault(r['call'], []).append(float(r['gap']))
    return out


def boot_ci(base, other, n=20000, seed=0):
    rng = random.Random(seed)
    a, b = list(base.values()), list(other.values())
    diffs = []
    for _ in range(n):
        ga = [x for c in (rng.choice(a) for _ in a) for x in c]
        gb = [x for c in (rng.choice(b) for _ in b) for x in c]
        diffs.append(st.median(gb) - st.median(ga))
    diffs.sort()
    return diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    rows = [r for r in csv.DictReader(open(HR / 'human_1111_phone.csv', encoding='utf-8-sig')) if r['use'] == '1']
    ae = [r for r in rows if r['call'].split('_')[2] != 'H']
    calls = {v: per_call([r for r in ae if r['call'].endswith('_' + v)]) for v in VARIANTS}

    print('대본 A~E, 휴대폰 직접 측정 (초)')
    print('| 묶음 | 통화 | 응답 | 평균 | 중앙값 | p90 | p95 | 최대 | 1.5초 넘음 | 통화별 중앙값 |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for v, desc in VARIANTS.items():
        g = [x for c in calls[v].values() for x in c]
        meds = ' '.join(f"{n.split('_')[2]} {st.median(c):.2f}" for n, c in sorted(calls[v].items()))
        print(f'| {v} {desc} | {len(calls[v])} | {len(g)} | {st.mean(g):.2f} | {st.median(g):.2f} | {nearest_rank(g, 90):.2f} '
              f'| {nearest_rank(g, 95):.2f} | {max(g):.2f} | {sum(x > 1.5 for x in g)}/{len(g)} | {meds} |')
    base = calls['L']
    base_med = st.median([x for c in base.values() for x in c])
    for v in ('S', 'M'):
        med = st.median([x for c in calls[v].values() for x in c])
        lo, hi = boot_ci(base, calls[v])
        p = mannwhitneyu([st.median(c) for c in calls[v].values()], [st.median(c) for c in base.values()]).pvalue
        print(f'{v}−L 중앙값 차이 {med - base_med:+.2f}초 | 통화 단위 부트스트랩 95% 구간 {lo:+.2f} ~ {hi:+.2f}'
              f' | 통화별 중앙값 Mann-Whitney U p={p:.2f}')

    print('\n대본 H (지연 통계 제외, 참고)')
    for v in VARIANTS:
        g = [float(r['gap']) for r in rows if r['call'] == f'1111_co_H_{v}']
        if g:
            print(f'  {v}: 응답 {len(g)} 중앙값 {st.median(g):.2f}')

    p2 = [float(r['gap']) for r in csv.DictReader(open(HR / 'human_1102_phone.csv', encoding='utf-8-sig'))
          if r['call'].startswith('1102_co_') and r['call'].split('_')[2] in 'ABCDE' and r['use'] == '1']
    print(f'\n기준선 비교: 11/2 같은 에이전트 휴대폰 직접 측정(대본 A~E) 응답 {len(p2)} 중앙값 {st.median(p2):.2f}'
          f' / 11/11 L 중앙값 {base_med:.2f}')


if __name__ == '__main__':
    main()
