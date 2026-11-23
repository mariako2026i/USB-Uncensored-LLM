"""Answer project questions through a ChatGPT-authenticated local Codex CLI."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

RUN_LOCK = threading.Lock()


def cli_path():
    override = os.environ.get("USB_AI_CODEX_EXE")
    if override:
        path = Path(override)
        if path.is_absolute() and path.is_file() and (os.name != "nt" or path.suffix.lower() == ".exe"):
            return str(path)
        raise ValueError("USB_AI_CODEX_EXE должен указывать на исполняемый файл Codex.")
    cli = shutil.which("codex.exe" if os.name == "nt" else "codex")
    if cli:
        return cli
    if os.name == "nt":
        shim = shutil.which("codex.cmd")
        if shim:
            packages = Path(shim).parent / "node_modules" / "@openai"
            triple = "x86_64-pc-windows-msvc"
            for root in (packages / "codex-win32-x64", packages / "codex" / "node_modules" / "@openai" /
                         "codex-win32-x64", packages / "codex"):
                path = root / "vendor" / triple / "bin" / "codex.exe"
                if path.is_file():
                    return str(path)
    raise ValueError("Установите Codex CLI и заново откройте окно Миры.")


def ask(project_dir, question):
    project = Path(project_dir).expanduser().resolve()
    if not project.is_dir():
        raise ValueError("Папка CRM не найдена. Заново запустите start-crm-codex.bat.")
    cli = cli_path()
    blocked_env = {"OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE",
                   "CODEX_BASE_URL", "CHATGPT_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID"}
    env = {key: value for key, value in os.environ.items() if key.upper() not in blocked_env}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not RUN_LOCK.acquire(blocking=False):
        raise ValueError("Кодекс ещё отвечает на предыдущий вопрос. Попробуйте чуть позже.")
    try:
        auth = subprocess.run(
            [cli, "login", "status"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=15, env=env, creationflags=flags,
        )
        if auth.returncode or b"logged in using chatgpt" not in auth.stdout.lower():
            raise ValueError("В отдельном терминале выполните codex login и войдите через ChatGPT.")
        prompt = (
            "Ответь на вопрос владельца о проекте CRM Мариако. Работай в текущей папке проекта "
            "в режиме чтения. Не читай секреты, .env, ключи, данные клиентов и файлы вне проекта. "
            "Не изменяй файлы и не выполняй деплой. Дай краткий ответ на языке пользователя, "
            "при необходимости назови релевантные пути в проекте.\n\nВопрос:\n" + question
        )
        with tempfile.TemporaryDirectory(prefix="mira-codex-") as folder:
            answer_path = Path(folder) / "answer.txt"
            command = [cli, "-a", "never", "-c", 'forced_login_method="chatgpt"',
                       "-c", 'model_provider="openai"']
            if os.name == "nt":
                command.extend(["-c", 'windows.sandbox="unelevated"'])
            command.extend([
                "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never",
                "-C", str(project), "--output-last-message", str(answer_path), "-",
            ])
            result = subprocess.run(
                command, cwd=project, env=env, input=prompt.encode("utf-8"),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=150, creationflags=flags,
            )
            if result.returncode or not answer_path.is_file():
                raise ValueError("Codex CLI не ответил. Проверьте интернет, вход в ChatGPT и версию Codex CLI.")
            answer = answer_path.read_text(encoding="utf-8").strip()
            if not answer:
                raise ValueError("Codex CLI не вернул текст.")
            return answer
    except subprocess.TimeoutExpired as error:
        raise ValueError("Истекло время ожидания ответа Codex CLI.") from error
    finally:
        RUN_LOCK.release()
