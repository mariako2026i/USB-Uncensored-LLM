"""Synthesize Russian speech through the locally installed Piper voice."""

import io
import json
from pathlib import Path
import subprocess
import threading
import wave

ROOT = Path(__file__).resolve().parent / "bin" / "mira-voice" / "piper"
EXE = ROOT / "piper.exe"
MODEL = "ru_RU-irina-medium.onnx"
LOCK = threading.Lock()


def ready():
    return all(path.is_file() for path in (EXE, ROOT / MODEL, ROOT / (MODEL + ".json")))


def synthesize(text):
    if not ready():
        raise OSError("Piper voice is not installed.")
    if not LOCK.acquire(blocking=False):
        raise OSError("Piper is busy.")
    try:
        result = subprocess.run(
            [str(EXE), "--model", MODEL, "--output_raw"],
            cwd=ROOT, input=(" ".join(text.split()) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=30, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not result.stdout or len(result.stdout) % 2:
            raise OSError("Piper did not return PCM audio.")
        config = json.loads((ROOT / (MODEL + ".json")).read_text(encoding="utf-8"))
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(config["audio"]["sample_rate"])
                audio.writeframes(result.stdout)
            return buffer.getvalue()
    finally:
        LOCK.release()
