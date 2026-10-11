"""Transcribe every labeled segment of a turns.py result with Whisper and keep
its diarization speaker number. Used for the Vapi web-call recordings, where
diarization separated the two voices. Writes data/results/<name>_asr.json;
then run gaps.py with --ai-spk.

Usage: python scripts/transcribe_turns.py data/recordings/vapi_16k.wav vapi
       (needs data/results/<name>.json from turns.py)"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import load  # noqa: E402
from paths import OUT, whisper_recognizer  # noqa: E402

PAD = 0.05  # seconds of audio added on each side before transcribing


def main():
    path, name = sys.argv[1], sys.argv[2]
    x, sr = load(path)
    d = json.load(open(OUT / f'{name}.json', encoding='utf-8'))
    rec = whisper_recognizer()
    out = []
    for s, e, spk in d['labeled']:
        a, b = max(0, int((s - PAD) * sr)), min(len(x), int((e + PAD) * sr))
        st = rec.create_stream()
        st.accept_waveform(sr, x[a:b])
        rec.decode_stream(st)
        text = st.result.text.strip()
        out.append({'start': s, 'end': e, 'spk': spk, 'text': text})
        print(f'{s:7.2f}-{e:7.2f} spk{spk}  {text}', flush=True)
    json.dump(out, open(OUT / f'{name}_asr.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
