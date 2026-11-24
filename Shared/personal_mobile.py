"""Authenticated, loopback-only Android remote for the Windows companion."""

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import subprocess
import threading
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import cloud_models
import personal_actions
import personal_voice
import personal_whisper

PORT = 3334
UI = Path(__file__).with_name("mobile")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/remote.css": ("remote.css", "text/css; charset=utf-8"),
    "/remote.js": ("remote.js", "application/javascript; charset=utf-8"),
    "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),
    "/manifest.json": ("manifest.json", "application/manifest+json"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}
ACTIONS = {
    "открой youtube": "youtube", "открой ютуб": "youtube", "включи ютуб": "youtube",
    "открой github": "github", "открой гитхаб": "github",
    "открой crm": "crm", "открой црм": "crm",
    "открой почту": "mail", "открой gmail": "gmail", "открой outlook": "outlook",
    "открой яндекс почту": "yandex-mail",
    "открой консоль": "console", "покажи статус проекта": "status",
    "покажи систему": "system", "покажи задачи github": "github-issues",
}
BLOCKED_ACTION = re.compile(r"^(?:/ps|/ssh|/delete|удали|подготовь удаление|разверни|запусти|выполни)(?:\s|$)", re.I)


class MobileServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, ollama):
        super().__init__(address, MobileHandler)
        self.ollama = ollama
        self.token = secrets.token_urlsafe(18)
        self.commands_lock = threading.Lock()
        self.history = []

    def answer(self, text):
        text = re.sub(r"^(?:мира|нира)[\s,!.?—:;-]+", "", text.strip(), flags=re.I)
        phrase = " ".join(text.lower().rstrip(".!?…").split())
        if not phrase:
            raise ValueError("Напишите или произнесите команду.")
        if phrase == "/ps get-location":
            return personal_actions.project_directory()
        if BLOCKED_ACTION.match(phrase):
            raise ValueError("Эта операция недоступна с телефона.")
        action = ACTIONS.get(phrase)
        if action:
            result = personal_actions.execute(action)
            if result.get("exit_code", 0):
                raise ValueError(result["output"].strip() or "Команда завершилась с ошибкой.")
            return result["output"].strip()
        codex = re.match(r"^(?:/codex|спроси\s+у\s+кодекс?а)(?=$|[\s,.!?—:;-])[\s,.!?—:;-]*", text, re.I)
        if codex:
            return json.loads(cloud_models.ask_codex(text[codex.end():]))["message"]["content"]

        with urlopen(self.ollama + "/api/tags", timeout=5) as response:
            models = json.load(response)["models"]
        if not models:
            raise ValueError("На ноутбуке нет установленной локальной модели.")
        names = [model["name"] for model in models]
        model = next((name for name in names if name.lower().startswith("phi3-local")), names[0])
        messages = [*self.history, {"role": "user", "content": text}]
        payload = json.dumps({"model": model, "messages": messages, "stream": False,
                              "options": {"num_predict": 384, "temperature": 0.4}}).encode()
        request = Request(self.ollama + "/api/chat", payload, {"Content-Type": "application/json"})
        with urlopen(request, timeout=150) as response:
            answer = json.load(response)["message"]["content"]
        self.history = [*messages, {"role": "assistant", "content": answer}][-8:]
        return answer


class MobileHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(15)
        super().setup()

    def log_message(self, *_args):
        pass

    def reply(self, status, payload, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def json_reply(self, status, data):
        self.reply(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        asset = ASSETS.get(urlsplit(self.path).path)
        if not asset:
            self.send_error(404)
            return
        filename, content_type = asset
        self.reply(200, (UI / filename).read_bytes(), content_type)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/connect", "/api/message", "/api/transcribe", "/api/speak"):
            self.send_error(404)
            return
        authorization = self.headers.get("Authorization", "").encode("utf-8")
        if not hmac.compare_digest(authorization, b"Bearer " + self.server.token.encode("ascii")):
            self.json_reply(401, {"error": "Проверьте код подключения на ноутбуке."})
            return
        if path == "/api/connect":
            self.json_reply(200, {"connected": True})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            limit = personal_whisper.MAX_BYTES if path == "/api/transcribe" else 16384
            content_type = "audio/wav" if path == "/api/transcribe" else "application/json"
            if not 0 < size <= limit or self.headers.get_content_type() != content_type:
                raise ValueError("Запись или запрос слишком большой либо имеет неверный формат.")
            body = self.rfile.read(size)
            if path == "/api/transcribe":
                result = personal_whisper.transcribe(body)
            else:
                data = json.loads(body)
                text = data.get("text") if isinstance(data, dict) else None
                max_text = 300 if path == "/api/speak" else 4000
                if not isinstance(text, str) or not 0 < len(text.strip()) <= max_text:
                    raise ValueError("Проверьте длину сообщения.")
                if path == "/api/speak":
                    self.reply(200, personal_voice.synthesize(text), "audio/wav")
                    return
                if not self.server.commands_lock.acquire(blocking=False):
                    self.json_reply(409, {"error": "Мира ещё выполняет предыдущую команду."})
                    return
                try:
                    result = self.server.answer(text)
                finally:
                    self.server.commands_lock.release()
        except ValueError as error:
            self.json_reply(400, {"error": str(error)})
            return
        except (OSError, LookupError, TypeError, subprocess.SubprocessError):
            self.json_reply(502, {"error": "Ноутбук не смог обработать запрос. Проверьте Миру и выбранный режим."})
            return
        self.json_reply(200, {"text": result})


def start(ollama):
    server = MobileServer(("127.0.0.1", PORT), ollama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"  Mira Android: http://127.0.0.1:{PORT}")
    print(f"  Phone access code: {server.token}")
    return server
