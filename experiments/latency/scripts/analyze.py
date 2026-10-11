"""Label every speech segment of both calls as AI or human, transcribe it, and
measure response gaps.

- Edges: silero VAD segments (from turns.py JSON) snapped to the energy
  envelope at -50 dBFS (10 ms frames). Silence in these recordings is digital
  zero, so edges are sharp.
- Speaker: ERes2Net embedding per segment, nearest of two centroids built from
  call 1, whose diarization separated the two voices cleanly (spk1 = AI,
  confirmed by transcript "AI 상담원입니다").
- Text: Whisper turbo (ko) per segment.
Needs data/results/call1.json and call2.json from turns.py.
Writes data/results/analysis.json.

Usage: python scripts/analyze.py
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import EMB, OUT, REC, whisper_recognizer  # noqa: E402


def load(path):
    w = wave.open(path)
    sr = w.getframerate()
    return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0, sr


def snap(segs, x, sr, thr_db=-50.0, hop=0.01, search=0.3):
    n = int(sr * hop)
    db = 10 * np.log10(np.array([np.mean(x[i * n:(i + 1) * n] ** 2) for i in range(len(x) // n)]) + 1e-10)
    out = []
    for s, e in segs:
        i0, i1 = max(0, int((s - search) / hop)), min(len(db) - 1, int((s + search) / hop))
        a = np.where(db[i0:i1 + 1] > thr_db)[0]
        ns = (i0 + a[0]) * hop if len(a) else s
        j0, j1 = max(0, int((e - search) / hop)), min(len(db) - 1, int((e + search) / hop))
        a = np.where(db[j0:j1 + 1] > thr_db)[0]
        ne = (j0 + a[-1] + 1) * hop if len(a) else e
        if ne - ns > 0.05:
            out.append([round(ns, 2), round(ne, 2)])
    # merge segments that now touch or overlap
    merged = []
    for s, e in sorted(out):
        if merged and s <= merged[-1][1] + 0.02:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def embed(ext, x, sr, s, e):
    a, b = int(s * sr), int(e * sr)
    seg = x[a:b]
    if len(seg) < int(0.6 * sr):  # pad short segments by repetition
        reps = int(np.ceil(0.6 * sr / max(len(seg), 1)))
        seg = np.tile(seg, reps)
    st = ext.create_stream()
    st.accept_waveform(sr, seg)
    st.input_finished()
    if not ext.is_ready(st):
        return None
    v = np.array(ext.compute(st))
    return v / (np.linalg.norm(v) + 1e-9)


def main():
    ext = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=EMB, num_threads=2))
    rec = whisper_recognizer()

    calls = {}
    for name in ('call1', 'call2'):
        x, sr = load(str(REC / f'{name}_16k.wav'))
        d = json.load(open(OUT / f'{name}.json', encoding='utf-8'))
        segs = snap(d['vad'], x, sr)
        calls[name] = {'x': x, 'sr': sr, 'segs': segs, 'dia': d['diarization']}

    # reference centroids from call 1 diarization (1 = AI, 0 = human)
    c1 = calls['call1']
    ref = {0: [], 1: []}
    for s, e in c1['segs']:
        cover = {0: 0.0, 1: 0.0}
        for ds, de, spk in c1['dia']:
            cover[spk] += max(0.0, min(e, de) - max(s, ds))
        tot = cover[0] + cover[1]
        if tot > 0 and max(cover.values()) / tot > 0.9 and e - s > 0.8:
            v = embed(ext, c1['x'], c1['sr'], s, e)
            if v is not None:
                ref[max(cover, key=cover.get)].append(v)
    cent = {k: np.mean(v, axis=0) for k, v in ref.items()}
    cent = {k: v / np.linalg.norm(v) for k, v in cent.items()}
    print('reference segments', {k: len(v) for k, v in ref.items()},
          'centroid cos', round(float(cent[0] @ cent[1]), 3), flush=True)

    result = {}
    for name, c in calls.items():
        rows = []
        for s, e in c['segs']:
            v = embed(ext, c['x'], c['sr'], s, e)
            if v is None:
                who, margin = '?', 0.0
            else:
                ai, hu = float(v @ cent[1]), float(v @ cent[0])
                who, margin = ('AI' if ai > hu else '사람'), round(ai - hu, 3)
            a, b = max(0, int((s - 0.05) * c['sr'])), min(len(c['x']), int((e + 0.05) * c['sr']))
            st = rec.create_stream()
            st.accept_waveform(c['sr'], c['x'][a:b])
            rec.decode_stream(st)
            rows.append({'start': s, 'end': e, 'who': who, 'margin': margin, 'text': st.result.text.strip()})
            print(f'{name} {s:7.2f}-{e:7.2f} {who:2s} {margin:+.3f}  {st.result.text.strip()}', flush=True)
        result[name] = {'duration': len(c['x']) / c['sr'], 'segments': rows}
    json.dump(result, open(OUT / 'analysis.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
