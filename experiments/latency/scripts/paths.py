"""Project paths shared by every script. Folders are relative to the project
root, so the scripts run the same on any machine. Set MODELS_DIR to keep the
~1 GB of models somewhere else."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = Path(os.environ.get('MODELS_DIR', ROOT / 'models'))
REC = ROOT / 'data' / 'recordings'   # call recordings (originals + *_16k.wav), one folder per date
OUT = ROOT / 'data' / 'results'      # JSON written by the scripts



def rec_file(filename: str) -> Path:
    """Recording path inside its date folder: data/recordings/<MMDD>/<file>.
    The date is the first four digits of the name (1013_co_A.wav -> 1013/). Names without a date
    (call1, call2, luna, vapi, vapi_low) are the 10/7 recordings -> 1007/.
    Falls back to the old flat layout if the file is still there."""
    head = filename[:4]
    path = REC / (head if head.isdigit() else '1007') / filename
    flat = REC / filename
    return flat if not path.exists() and flat.exists() else path


VAD = str(MODELS / 'vad' / 'silero_vad.onnx')
SEG = str(MODELS / 'seg' / 'sherpa-onnx-pyannote-segmentation-3-0' / 'model.onnx')
EMB = str(MODELS / 'emb' / 'eres2net.onnx')
WHISPER = MODELS / 'whisper' / 'sherpa-onnx-whisper-turbo'


def whisper_recognizer(num_threads=2):
    """Whisper turbo (int8), Korean, through sherpa-onnx."""
    import sherpa_onnx
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=str(WHISPER / 'turbo-encoder.int8.onnx'),
        decoder=str(WHISPER / 'turbo-decoder.int8.onnx'),
        tokens=str(WHISPER / 'turbo-tokens.txt'),
        language='ko', task='transcribe', num_threads=num_threads)
