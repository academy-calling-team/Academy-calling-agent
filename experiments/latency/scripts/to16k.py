"""Convert a call recording (WAV, m4a, mp3 ...) to the 16 kHz mono 16-bit WAV
the analysis scripts read, next to the original as <name>_16k.wav. Needs ffmpeg.

Usage: python scripts/to16k.py data/recordings/call3.wav [more files ...]"""
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    if not shutil.which('ffmpeg'):
        sys.exit('ffmpeg not found: install it first (macOS: brew install ffmpeg, Windows: winget install ffmpeg)')
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for src in map(Path, sys.argv[1:]):
        dst = src.with_name(src.stem + '_16k.wav')
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', str(src),
                        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(dst)], check=True)
        print(dst)


if __name__ == '__main__':
    main()
