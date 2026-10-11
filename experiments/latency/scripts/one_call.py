"""Analyze one ClawOps server recording whose diarization did not separate the
voices: VAD segments snapped at -50 dBFS, ERes2Net embedding per segment,
2-way clustering, cluster matched to the human voice from call 1, Whisper text.
Writes data/results/<name>_rows.json; response gaps then come from gaps.py.

Usage: python scripts/one_call.py data/recordings/luna_16k.wav luna
       (needs data/results/<name>.json from turns.py, and call1.json + call1_16k.wav
        for the reference human voice)"""
import json
import sys
from pathlib import Path

import numpy as np
import sherpa_onnx
from sklearn.cluster import AgglomerativeClustering

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import embed, load, snap  # noqa: E402
from paths import EMB, OUT, REC, whisper_recognizer  # noqa: E402


def main():
    path, name = sys.argv[1], sys.argv[2]
    ext = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=EMB, num_threads=2))
    rec = whisper_recognizer()

    # human centroid from call 1 (diarization speaker 0 = human there)
    x1, sr1 = load(str(REC / 'call1_16k.wav'))
    d1 = json.load(open(OUT / 'call1.json', encoding='utf-8'))
    hum = []
    for s, e in snap(d1['vad'], x1, sr1):
        cover = {0: 0.0, 1: 0.0}
        for ds, de, spk in d1['diarization']:
            cover[spk] += max(0.0, min(e, de) - max(s, ds))
        tot = cover[0] + cover[1]
        if tot > 0 and cover[0] / tot > 0.9 and e - s > 0.8:
            v = embed(ext, x1, sr1, s, e)
            if v is not None:
                hum.append(v)
    hc = np.mean(hum, axis=0)
    hc /= np.linalg.norm(hc)

    x, sr = load(path)
    d = json.load(open(OUT / f'{name}.json', encoding='utf-8'))
    segs = snap(d['vad'], x, sr)
    embs = [embed(ext, x, sr, s, e) for s, e in segs]
    ok = [i for i, v in enumerate(embs) if v is not None]
    lab = AgglomerativeClustering(n_clusters=2, metric='cosine', linkage='average').fit_predict(
        np.array([embs[i] for i in ok]))
    sim = {c: float(np.mean([embs[i] @ hc for i, l in zip(ok, lab) if l == c])) for c in (0, 1)}
    human_cluster = max(sim, key=sim.get)
    print('cluster similarity to call-1 human', {k: round(v, 3) for k, v in sim.items()}, flush=True)
    rows = []
    li = dict(zip(ok, lab))
    for i, (s, e) in enumerate(segs):
        who = '?' if i not in li else ('사람' if li[i] == human_cluster else 'AI')
        hs = round(float(embs[i] @ hc), 3) if embs[i] is not None else None
        a, b = max(0, int((s - 0.05) * sr)), min(len(x), int((e + 0.05) * sr))
        st = rec.create_stream()
        st.accept_waveform(sr, x[a:b])
        rec.decode_stream(st)
        rows.append({'start': s, 'end': e, 'who': who, 'human_sim': hs, 'text': st.result.text.strip()})
        print(f'{s:7.2f}-{e:7.2f} {who:2s} {hs}  {st.result.text.strip()}', flush=True)
    json.dump(rows, open(OUT / f'{name}_rows.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
