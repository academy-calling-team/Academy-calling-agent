"""10/13 시험 통화 보고: 엔진별 응답 지연, 겹침(끼어들기), 통화 간 AI 목소리 비교.

사용: python report_1013.py <experiments/latency 경로> <접두어> 이름... [--latency 이름...]
  예: report_1013.py .../latency co 1013_co_A 1013_co_B ... --latency 1013_co_A 1013_co_B ...
"""
import json
import math
import sys
import wave
from itertools import combinations
from pathlib import Path

import numpy as np

L = Path(sys.argv[1])
sys.path.insert(0, str(L / 'scripts'))
import sherpa_onnx  # noqa: E402
from paths import EMB, OUT, REC  # noqa: E402

args = sys.argv[3:]
if '--latency' in args:
    i = args.index('--latency')
    names, lat_names = args[:i], args[i + 1:]
else:
    names, lat_names = args, args


def pct(v, p):
    s = sorted(v)
    return s[max(1, math.ceil(p / 100 * len(s))) - 1]


def summary(v):
    if not v:
        return {'n': 0}
    v = sorted(v)
    n = len(v)
    mid = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return {'n': n, 'mean': round(sum(v) / n, 2), 'median': round(mid, 2), 'p90': pct(v, 90),
            'p95': pct(v, 95), 'max': v[-1], 'over_1_5': sum(x > 1.5 for x in v)}


def load(path):
    w = wave.open(str(path))
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0, w.getframerate()


# 1. 응답 지연
print('=== 응답 지연 (사람 말 끝 → AI 첫 소리) ===')
pool = []
for n in names:
    g = json.load(open(OUT / f'{n}_gaps.json', encoding='utf-8'))
    vals = [x['gap'] for x in g['gaps']]
    if n in lat_names:
        pool += vals
    s = g['summary']
    print(f"{n}: n={s.get('n')} 평균 {s.get('mean')} 중앙 {s.get('median')} 최대 {s.get('max')} 1.5초초과 {s.get('over_1_5')}"
          f" | 겹침 {len(g['overlaps'])}개" + ('' if n in lat_names else '  (통계 제외)'))
    print('   ', [x['gap'] for x in g['gaps']])
print('합계(통계 대상):', summary(pool))

# 2. 겹침: 화자 분리 결과에서 두 화자가 동시에 말한 구간
print('\n=== 겹침 구간 (화자 분리 기준, 0.15초 이상) ===')
for n in names:
    d = json.load(open(OUT / f'{n}.json', encoding='utf-8'))
    rows = json.load(open(OUT / f'{n}_rows.json', encoding='utf-8'))
    # 화자 분리 번호 → AI/사람: 라벨 붙은 행과 겹치는 시간으로 정한다
    score = {}
    for s, e, spk in d['diarization']:
        for r in rows:
            ov = max(0.0, min(e, r['end']) - max(s, r['start']))
            if ov and r['who'] in ('AI', '사람'):
                score.setdefault(spk, {'AI': 0.0, '사람': 0.0})[r['who']] += ov
    name_of = {spk: max(v, key=v.get) for spk, v in score.items()}
    segs = [(s, e, name_of.get(spk, '?')) for s, e, spk in d['diarization']]
    found = []
    for (s1, e1, w1), (s2, e2, w2) in combinations(segs, 2):
        if w1 == w2 or '?' in (w1, w2):
            continue
        a, b = max(s1, s2), min(e1, e2)
        if b - a >= 0.15:
            first, second = ((w1, s1, e1), (w2, s2, e2)) if s1 <= s2 else ((w2, s2, e2), (w1, s1, e1))
            found.append((round(a, 2), round(b - a, 2), first[0], second[0], round(first[2] - second[1], 2)))
    print(f'{n}: 화자 분리 번호 {name_of}')
    for a, dur, first, second, cont in sorted(found):
        kind = '사람이 AI 말을 끊음' if first == 'AI' else 'AI가 사람 말 도중 시작'
        print(f'   {a:7.2f}s  겹침 {dur:.2f}s  {kind}  (먼저 말하던 쪽이 상대 시작 뒤 {cont:.2f}s 더 말함)')
    if not found:
        print('   없음')

# 3. 통화 간 목소리 비교: 1초 넘는 구간의 임베딩 평균을 통화·화자별로 내 코사인 유사도를 본다
print('\n=== 통화 간 목소리 비교 (ERes2Net 임베딩, 코사인 유사도) ===')
ext = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=EMB, num_threads=2))


def emb(x, sr, s, e):
    st = ext.create_stream()
    st.accept_waveform(sr, x[int(s * sr):int(e * sr)])
    st.input_finished()
    if not ext.is_ready(st):
        return None
    v = np.array(ext.compute(st))
    return v / (np.linalg.norm(v) + 1e-9)


cent = {'AI': {}, '사람': {}}
spread = {'AI': [], '사람': []}
for n in names:
    x, sr = load(REC / f'{n}_16k.wav')
    rows = json.load(open(OUT / f'{n}_rows.json', encoding='utf-8'))
    for who in ('AI', '사람'):
        vs = [v for r in rows if r['who'] == who and r['end'] - r['start'] >= 1.0
              for v in [emb(x, sr, r['start'], r['end'])] if v is not None]
        if vs:
            c = np.mean(vs, axis=0)
            c /= np.linalg.norm(c)
            cent[who][n] = c
            spread[who] += [float(v @ c) for v in vs]
for who in ('AI', '사람'):
    keys = list(cent[who])
    sims = [float(cent[who][a] @ cent[who][b]) for a, b in combinations(keys, 2)]
    print(f'{who}: 통화 {len(keys)}개, 통화끼리 유사도 평균 {np.mean(sims):.3f} (최소 {min(sims):.3f}, 최대 {max(sims):.3f})'
          f' | 같은 통화 안 구간→평균 유사도 {np.mean(spread[who]):.3f}')
    print('   ' + ' '.join(k.split('_')[-1] for k in keys))
    for a in keys:
        print('   ' + a.split('_')[-1] + ' ' + ' '.join(f'{float(cent[who][a] @ cent[who][b]):.2f}' for b in keys))
