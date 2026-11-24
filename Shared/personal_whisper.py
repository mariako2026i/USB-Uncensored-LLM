"""Transcribe short microphone clips with the local Whisper executable."""

import io
from pathlib import Path
import subprocess
import tempfile
import threading
import wave

ROOT = Path(__file__).resolve().parent / "bin" / "mira-whisper"
EXE = ROOT / "Release" / "whisper-cli.exe"
STANDARD_MODEL = ROOT / "ggml-base-q5_1.bin"
ACCURATE_MODEL = ROOT / "ggml-small-q5_1.bin"
MAX_BYTES = 400_000
LOCK = threading.Lock()


def model_path():
    return ACCURATE_MODEL if ACCURATE_MODEL.is_file() else STANDARD_MODEL


def ready():
    return EXE.is_file() and model_path().is_file()


def transcribe(data, interrupt=False):
    try:
        with wave.open(io.BytesIO(data), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                raise ValueError("Ожидается моно WAV 16 кГц.")
            if not 0 < audio.getnframes() <= 12 * 16000:
                raise ValueError("Запись должна быть не длиннее 12 секунд.")
    except (wave.Error, EOFError) as error:
        raise ValueError("Некорректная запись WAV.") from error

    if not ready():
        raise OSError("Сначала запустите Windows\\install-mira.bat.")
    if not LOCK.acquire(blocking=False):
        raise OSError("Мира уже распознаёт голос в другом окне.")
    try:
        with tempfile.TemporaryDirectory(prefix="usb-ai-mira-") as folder:
            recording = Path(folder) / "voice.wav"
            recording.write_bytes(data)
            model = STANDARD_MODEL if interrupt and STANDARD_MODEL.is_file() else model_path()
            command = [str(EXE), "-m", str(model), "-f", str(recording), "-l", "ru",
                       "-ng", "-t", "4", "-otxt", "-of", str(recording.with_suffix(""))]
            if interrupt:
                command.extend(["--beam-size", "1", "--best-of", "1", "--no-fallback"])
            subprocess.run(
                command,
                cwd=EXE.parent, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=40, check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return recording.with_suffix(".txt").read_text(encoding="utf-8").strip()
    finally:
        LOCK.release()
