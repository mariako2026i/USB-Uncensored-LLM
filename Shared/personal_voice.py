"""Synthesize Russian speech through the locally installed Piper voice."""

import io
import json
from pathlib import Path
import re
import subprocess
import threading
import wave

ROOT = Path(__file__).resolve().parent / "bin" / "mira-voice" / "piper"
EXE = ROOT / "piper.exe"
MODEL = "ru_RU-irina-medium.onnx"
LOCK = threading.Lock()


def ready():
    return all(path.is_file() for path in (EXE, ROOT / MODEL, ROOT / (MODEL + ".json")))



SPOKEN_TERMS = {
    "CRM": "си эр эм", "VPS": "ви пи эс", "VDS": "ви ди эс", "SSH": "эс эс аш",
    "API": "эй пи ай", "URL": "ю эр эл", "GitHub": "гитха́б", "YouTube": "юту́б",
    "PowerShell": "па́уэршелл", "FirstVDS": "фёрст ви ди эс", "Codex": "ко́декс",
    "Docker": "до́кер", "Windows": "ви́ндоус", "Next.js": "некст джей эс",
    "FastAPI": "фаст эй пи ай", "PostgreSQL": "по́стгрес", "Nginx": "энджини́кс",
}
TERMS_PATTERN = re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, SPOKEN_TERMS)) + r")(?![\w-])", re.I)
TERMS_CASEFOLD = {word.casefold(): spoken for word, spoken in SPOKEN_TERMS.items()}


def speech_text(text):
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://[^\s<>]+", "ссылка в тексте", text)
    text = TERMS_PATTERN.sub(lambda match: TERMS_CASEFOLD[match.group().casefold()], text)
    return " ".join(text.split())


def synthesize(text):
    if not ready():
        raise OSError("Piper voice is not installed.")
    if not LOCK.acquire(blocking=False):
        raise OSError("Piper is busy.")
    try:
        result = subprocess.run(
            [str(EXE), "--model", MODEL, "--output_raw", "--length_scale", "1.06"],
            cwd=ROOT, input=(speech_text(text) + "\n").encode("utf-8"),
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
