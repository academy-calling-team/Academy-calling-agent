"""Speaker turns and response gaps for a mono, two-party call recording.

Pipeline: 16 kHz audio -> pyannote segmentation + ERes2Net embeddings (2 clusters)
-> silero VAD segments -> energy-refined boundaries -> per-segment speaker label
-> turns (same-speaker segments merged) -> gaps at every speaker change.
Writes <out>/<name>.json and prints a table.

Usage: python scripts/turns.py data/recordings/call1_16k.wav call1 [outdir]
       (outdir defaults to data/results)
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import EMB, OUT, SEG, VAD  # noqa: E402


def load(path):
    w = wave.open(path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return x, sr


def diarize(x, sr):
    cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=SEG),
            num_threads=2,
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=EMB, num_threads=2),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=2),
        min_duration_on=0.2,
        min_duration_off=0.3,
    )
    sd = sherpa_onnx.OfflineSpeakerDiarization(cfg)
    assert sd.sample_rate == sr, (sd.sample_rate, sr)
    res = sd.process(x).sort_by_start_time()
    return [(r.start, r.end, r.speaker) for r in res]


def vad_segments(x, sr):
    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = VAD
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.2
    cfg.silero_vad.min_speech_duration = 0.15
    cfg.silero_vad.max_speech_duration = 30
    cfg.sample_rate = sr
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=600)
    ws = cfg.silero_vad.window_size
    out = []
    for i in range(0, len(x), ws):
        vad.accept_waveform(x[i:i + ws])
        while not vad.empty():
            s = vad.front
            out.append((s.start / sr, (s.start + len(s.samples)) / sr))
            vad.pop()
    vad.flush()
    while not vad.empty():
        s = vad.front
        out.append((s.start / sr, (s.start + len(s.samples)) / sr))
        vad.pop()
    return out


def energy_db(x, sr, hop=0.01):
    n = int(sr * hop)
    frames = len(x) // n
    e = np.array([np.mean(x[i * n:(i + 1) * n] ** 2) for i in range(frames)])
    return 10 * np.log10(e + 1e-10)


def refine(segs, db, hop=0.01, search=0.30):
    """Snap VAD edges to the energy envelope: first/last 10 ms frame above
    noise floor + 12 dB within +-search seconds of each edge."""
    floor = np.percentile(db, 10)
    thr = floor + 12
    out = []
    for s, e in segs:
        i0 = max(0, int((s - search) / hop))
        i1 = min(len(db) - 1, int((s + search) / hop))
        above = np.where(db[i0:i1 + 1] > thr)[0]
        ns = (i0 + above[0]) * hop if len(above) else s
        j0 = max(0, int((e - search) / hop))
        j1 = min(len(db) - 1, int((e + search) / hop))
        above = np.where(db[j0:j1 + 1] > thr)[0]
        ne = (j0 + above[-1] + 1) * hop if len(above) else e
        if ne > ns:
            out.append((round(ns, 2), round(ne, 2)))
    return out, floor, thr


def label(segs, dia):
    """Speaker for each VAD segment by largest overlap with diarization;
    split a segment where diarization changes speaker inside it."""
    out = []
    for s, e in segs:
        parts = []
        for ds, de, spk in dia:
            a, b = max(s, ds), min(e, de)
            if b - a > 0.05:
                parts.append((a, b, spk))
        if not parts:
            out.append((s, e, None))
            continue
        spks = {p[2] for p in parts}
        if len(spks) == 1:
            out.append((s, e, parts[0][2]))
            continue
        # several speakers: keep diarization pieces, stretched to VAD edges
        parts.sort()
        merged = []
        for a, b, spk in parts:
            if merged and merged[-1][2] == spk:
                merged[-1] = (merged[-1][0], b, spk)
            else:
                merged.append((a, b, spk))
        merged[0] = (s, merged[0][1], merged[0][2])
        merged[-1] = (merged[-1][0], e, merged[-1][2])
        out.extend(merged)
    return out


def turns(labeled, join_gap=1.0):
    t = []
    for s, e, spk in labeled:
        if t and t[-1]['spk'] == spk and s - t[-1]['end'] <= join_gap:
            t[-1]['end'] = e
            t[-1]['segs'].append([s, e])
        else:
            t.append({'spk': spk, 'start': s, 'end': e, 'segs': [[s, e]]})
    return t


def main():
    path, name = sys.argv[1], sys.argv[2]
    outdir = sys.argv[3] if len(sys.argv) > 3 else str(OUT)
    x, sr = load(path)
    dia = diarize(x, sr)
    vs = vad_segments(x, sr)
    db = energy_db(x, sr)
    rs, floor, thr = refine(vs, db)
    lab = label(rs, dia)
    tr = turns(lab)
    gaps = []
    for a, b in zip(tr, tr[1:]):
        if a['spk'] != b['spk']:
            gaps.append({'from': a['spk'], 'to': b['spk'], 'prev_end': a['end'],
                         'next_start': b['start'], 'gap': round(b['start'] - a['end'], 2)})
    json.dump({'duration': len(x) / sr, 'diarization': dia, 'vad': vs, 'refined': rs,
               'labeled': lab, 'turns': tr, 'gaps': gaps, 'floor_db': float(floor),
               'thr_db': float(thr)}, open(f'{outdir}/{name}.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    talk = {}
    for s, e, spk in lab:
        talk[spk] = talk.get(spk, 0) + (e - s)
    print(f'{name}: {len(x)/sr:.1f}s  floor {floor:.1f} dB  thr {thr:.1f} dB  talk', {k: round(v, 1) for k, v in talk.items()})
    for t in tr:
        print(f"  spk{t['spk']}  {t['start']:7.2f} - {t['end']:7.2f}  ({t['end']-t['start']:5.2f}s, {len(t['segs'])} seg)")
    print('  gaps:', [(g['from'], g['to'], g['gap']) for g in gaps])


if __name__ == '__main__':
    main()
