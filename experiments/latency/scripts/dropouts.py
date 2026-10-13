"""말하는 도중의 '완전 무음' 조각을 센다 (음성 패킷이 빠진 흔적).

ClawOps 서버 녹음은 말이 없을 때 디지털 0이다. 한 사람이 말하는 구간 안에 0이 이어지는
짧은 조각(20~300ms)이 있으면 그 쪽 음성이 중간에 끊긴 것으로 본다. 사람 구간은 대조군이다.
사용: dropouts.py <experiments/latency 경로> 이름...
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

L = Path(sys.argv[1])
REC, OUT = L / 'data' / 'recordings', L / 'data' / 'results'
BINS = [(0.02, 0.06), (0.06, 0.12), (0.12, 0.3)]


def load(p):
    w = wave.open(str(p))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16), w.getframerate()


def zero_runs(seg, sr, min_len=0.02):
    z = np.abs(seg.astype(np.int32)) <= 1
    edges = np.diff(np.concatenate([[0], z.astype(np.int8), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    return [(e - s) / sr for s, e in zip(starts, ends) if (e - s) / sr >= min_len]


tot = {}
for name in sys.argv[2:]:
    x, sr = load(REC / f'{name}_16k.wav')
    rows = json.load(open(OUT / f'{name}_rows.json', encoding='utf-8'))
    eng = name.split('_')[1]
    for who in ('AI', '사람'):
        secs, runs = 0.0, []
        for r in rows:
            if r['who'] != who or r['end'] - r['start'] < 0.3:
                continue
            a, b = int((r['start'] + 0.05) * sr), int((r['end'] - 0.05) * sr)
            secs += (b - a) / sr
            runs += [d for d in zero_runs(x[a:b], sr) if d < 0.3]
        t = tot.setdefault((eng, who), {'secs': 0.0, 'runs': []})
        t['secs'] += secs
        t['runs'] += runs
        counts = [sum(lo <= d < hi for d in runs) for lo, hi in BINS]
        print(f'{name} {who:2s}: 말한 {secs:5.1f}s, 무음 조각 {len(runs):3d}개 (20-60ms {counts[0]}, 60-120ms {counts[1]}, 120-300ms {counts[2]})')

print('\n엔진별 합계 (말한 1분당 무음 조각 수)')
for (eng, who), t in sorted(tot.items()):
    counts = [sum(lo <= d < hi for d in t['runs']) for lo, hi in BINS]
    per_min = len(t['runs']) / (t['secs'] / 60) if t['secs'] else 0
    print(f'{eng} {who:2s}: {t["secs"]:6.1f}s, {len(t["runs"])}개, 1분당 {per_min:.1f}개'
          f' | 20-60ms {counts[0]}, 60-120ms {counts[1]}, 120-300ms {counts[2]}'
          f' | 무음 합계 {sum(t["runs"]):.2f}s')
