"""Download the four sherpa-onnx models the analysis scripts use into models/
(or MODELS_DIR). About 610 MB to download, 1.1 GB on disk; Whisper turbo is
most of it. Files already in place are skipped. Each file the scripts load is
checked against the SHA-256 of the copy used for the 10/7 measurements.

Usage: python scripts/download_models.py            # all four
       python scripts/download_models.py vad seg    # only some
"""
import hashlib
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import MODELS  # noqa: E402

BASE = 'https://github.com/k2-fsa/sherpa-onnx/releases/download'

# name: (url, kind, target folder, {file the scripts load: sha256})
MODELS_LIST = {
    'vad': (f'{BASE}/asr-models/silero_vad.onnx', 'file', 'vad/silero_vad.onnx', {
        'vad/silero_vad.onnx': '9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6'}),
    'emb': (f'{BASE}/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx',
            'file', 'emb/eres2net.onnx', {
                'emb/eres2net.onnx': '1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b'}),
    'seg': (f'{BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2', 'tar', 'seg', {
        'seg/sherpa-onnx-pyannote-segmentation-3-0/model.onnx':
            '220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079'}),
    'whisper': (f'{BASE}/asr-models/sherpa-onnx-whisper-turbo.tar.bz2', 'tar', 'whisper', {
        'whisper/sherpa-onnx-whisper-turbo/turbo-encoder.int8.onnx':
            'b02dcdf54f348741e93fe732b67d933c8dcb6735655f710640143081db38878b',
        'whisper/sherpa-onnx-whisper-turbo/turbo-decoder.int8.onnx':
            '20accd02388482eb3a46bd615631adfdc85e1eb2c7db9ea3f02a40ffe6b81547',
        'whisper/sherpa-onnx-whisper-turbo/turbo-tokens.txt':
            'b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126'}),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest):
    print(f'  downloading {url}', flush=True)
    with urllib.request.urlopen(url) as r, open(dest, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f'\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB', end='', flush=True)
    print(flush=True)


def safe_extract(archive, dest):
    with tarfile.open(archive, 'r:bz2') as tf:
        try:
            tf.extractall(dest, filter='data')
        except TypeError:  # Python without tar filters: check paths ourselves
            root = Path(dest).resolve()
            for m in tf.getmembers():
                if not (root / m.name).resolve().is_relative_to(root) or m.issym() or m.islnk():
                    raise RuntimeError(f'unsafe path in archive: {m.name}')
            tf.extractall(dest)


def main():
    wanted = sys.argv[1:] or list(MODELS_LIST)
    unknown = [w for w in wanted if w not in MODELS_LIST]
    if unknown:
        sys.exit(f'unknown model {unknown}; choose from {list(MODELS_LIST)}')
    MODELS.mkdir(parents=True, exist_ok=True)
    ok = True
    for name in wanted:
        url, kind, target, checks = MODELS_LIST[name]
        print(f'[{name}]')
        if all((MODELS / f).exists() for f in checks):
            print('  already there')
        else:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_file = Path(tmp) / url.rsplit('/', 1)[1]
                fetch(url, tmp_file)
                if kind == 'file':
                    (MODELS / target).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(tmp_file), MODELS / target)
                else:
                    (MODELS / target).mkdir(parents=True, exist_ok=True)
                    print('  extracting', flush=True)
                    safe_extract(tmp_file, MODELS / target)
        for f, want in checks.items():
            got = sha256(MODELS / f)
            same = got == want
            ok &= same
            print(f'  {"ok      " if same else "CHANGED "} {f}' + ('' if same else f'\n    sha256 {got}\n    expected {want}'))
    if not ok:
        print('\nSome files differ from the 10/7 copies. The release may have been updated; '
              'results can then differ slightly from data/results.')
    print(f'\nmodels in {MODELS}')


if __name__ == '__main__':
    main()
