"""Run user-requested actions in the Windows companion."""

import base64
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit
import webbrowser
import threading
import time
import uuid

LOCK = threading.Lock()
DELETE_LOCK = threading.Lock()
GITHUB_TASK_ACTIONS = {
    "website", "youtube", "github", "crm", "test-crm", "chatgpt",
    "console", "project", "notepad", "calculator", "windows-settings", "system", "status",
}
PENDING_DELETE = None
LOCAL_COMMANDS = {"get-location": "Get-Location", "get-date": "Get-Date",
                  "get-childitem": "Get-ChildItem", "git status": "git --no-optional-locks -c core.fsmonitor=false status"}
FIRSTVDS_CHECKS = ("whoami", "docker compose version", "docker ps -a")
REMOTE_COMMANDS = {
    "pwd", "uptime", "df -h", "free -h", "whoami", "ls",
    "docker ps", "docker ps -a", "docker compose version",
    "ss -lntp | grep -E ':(80|443)[[:space:]]'",
}


def project_directory():
    return str(Path(os.environ.get("USB_AI_PROJECT") or os.environ.get("USB_AI_CRM_PROJECT")
                    or Path.home()).resolve(strict=True))


def execute(action, argument=None):
    if os.name != "nt":
        return {"output": "Команда доступна в Windows."}
    windows = Path(os.environ["SystemRoot"]) / "System32"
    settings = os.environ
    project = Path(project_directory())
    if not project.is_dir():
        raise ValueError("Project must be a directory")
    clean_env = {key: value for key, value in os.environ.items()
                 if not key.upper().endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))}
    powershell = windows / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    commands = {
        "system": [str(powershell), "-NoProfile", "-NonInteractive", "-Command",
                   "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                   "Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version; "
                   "Get-CimInstance Win32_Processor | Select-Object Name"],
        "status": ["git.exe", "--no-optional-locks", "-c", "core.fsmonitor=false", "status", "--short", "--branch"],
        "console": [str(powershell), "-NoProfile", "-NoExit"],
        "project": [str(windows.parent / "explorer.exe"), str(project)],
        "notepad": [str(windows / "notepad.exe")],
        "calculator": [str(windows / "calc.exe")],
    }
    repo = settings.get("USB_AI_GITHUB_REPO", "mariako2026i/mariako_crm")
    if action == "github-task":
        result = execute("github-issue", argument)
        if result.get("exit_code") != 0:
            return result
        next_action, parameter = github_task(result["output"])
        label = next_action if parameter is None else f"{next_action}: {parameter}"
        if not confirmed(f"GitHub: {repo} #{argument}", label):
            return {"output": "Задача отменена."}
        return execute(next_action, parameter)

    if action == "windows-settings":
        os.startfile("ms-settings:")
        return {"output": "Открыты настройки Windows."}

    if action in ("youtube", "github", "crm", "test-crm", "chatgpt", "website", "mail", "gmail", "outlook", "yandex-mail"):
        if action == "github" and not valid_repo(repo):
            raise ValueError("Invalid GitHub repository")
        if action == "mail" and not settings.get("USB_AI_MAIL_URL"):
            return {"output": "Скажите «открой Gmail», «открой Outlook» или «открой Яндекс Почту»."}
        links = {
            "youtube": "https://www.youtube.com/",
            "github": "https://github.com/" + repo,
            "crm": settings.get("USB_AI_CRM_URL") or "http://localhost:3000/",
            "test-crm": "http://127.0.0.1:8081/",
            "chatgpt": "https://chatgpt.com/",
            "website": argument,
            "mail": settings.get("USB_AI_MAIL_URL"),
            "gmail": "https://mail.google.com/",
            "outlook": "https://outlook.live.com/mail/",
            "yandex-mail": "https://mail.yandex.ru/",
        }
        url = browser_url(links[action])
        if not webbrowser.open(url, new=2):
            raise OSError("Browser could not be opened")
        return {"output": f"Открыто в браузере: {url}"}

    if action in {"prepare-delete", "confirm-delete", "cancel-delete"}:
        if not (settings.get("USB_AI_PROJECT") or settings.get("USB_AI_CRM_PROJECT")):
            return {"output": "Сначала выберите папку проекта."}
        return deletion(action, project, argument)

    if action == "deploy":
        return {"output": "Автозапуск деплоя выключен: скрипт может удалять файлы. Откройте консоль сервера."}

    if action in ("ssh", "ssh-command", "firstvds-check"):
        profile = Path.home() / ".ssh" / "mira-firstvds.conf"
        alias = settings.get("USB_AI_SSH_ALIAS") or ("firstvds" if profile.is_file() else "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", alias):
            return {"output": "Запустите Windows\\setup-firstvds.bat или укажите SSH-профиль в USB_AI_SSH_ALIAS."}
        command = [str(windows / "OpenSSH" / "ssh.exe")]
        if alias == "firstvds" and profile.is_file() and action != "ssh":
            command.extend(["-F", str(profile)])
        elif not settings.get("USB_AI_SSH_ALIAS") and action == "ssh":
            return {"output": "Ключ Миры предназначен для диагностики. Для интерактивного входа используйте обычный SSH."}
        command.extend(["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o",
                        "ConnectTimeout=10", "--", alias])
        if action == "firstvds-check":
            if not confirmed(f"FirstVDS: {alias}", "\n".join(FIRSTVDS_CHECKS)):
                return {"output": "Проверка отменена."}
            return firstvds_check(command, project, clean_env)
        if action == "ssh-command":
            text = command_text(argument, multiline=False)
            if text not in REMOTE_COMMANDS:
                return {"output": "Через Миру доступны диагностические команды SSH:\n" + "\n".join(sorted(REMOTE_COMMANDS))}
            if not confirmed(f"FirstVDS: {alias}", text):
                return {"output": "Команда отменена."}
            command.append(text)
    elif action == "powershell":
        text = command_text(argument)
        executable = LOCAL_COMMANDS.get(text.lower())
        if not executable:
            return {"output": "В голосовом режиме доступны только команды PowerShell: " + ", ".join(LOCAL_COMMANDS)}
        if not confirmed(f"PowerShell: {project}", text):
            return {"output": "Команда отменена."}
        script = "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + executable
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        command = [str(powershell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    elif action == "github-issues":
        if not valid_repo(repo):
            raise ValueError("Invalid GitHub repository")
        command = ["gh.exe", "issue", "list", "--repo", repo, "--limit", "15"]
    elif action == "github-issue":
        if not valid_repo(repo) or not re.fullmatch(r"[1-9][0-9]{0,8}", argument or ""):
            raise ValueError("Invalid GitHub issue")
        command = ["gh.exe", "issue", "view", argument, "--repo", repo, "--json", "body", "--jq", ".body"]
    else:
        command = commands[action]

    if action in {"console", "project", "ssh", "notepad", "calculator"}:
        flags = subprocess.CREATE_NEW_CONSOLE if action in {"console", "ssh"} else 0
        subprocess.Popen(command, cwd=project, env=clean_env, creationflags=flags)
        return {"output": "Открыто окно SSH." if action == "ssh" else "Окно открыто."}

    if not LOCK.acquire(blocking=False):
        return {"output": "Другая команда ещё выполняется."}
    try:
        with tempfile.TemporaryFile() as output:
            try:
                result = subprocess.run(command, cwd=project, env=clean_env, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=subprocess.STDOUT, timeout=180)
            except subprocess.TimeoutExpired:
                return {"output": "Истекло время ожидания. Для команды SSH или деплоя проверьте её состояние на VPS."}
            output.seek(0)
            raw = output.read(32769)
            message = raw[:32768].decode("utf-8", errors="replace")
            if len(raw) > 32768:
                message += "\n… вывод сокращён"
            return {"output": message or "Команда завершилась без вывода.", "exit_code": result.returncode}
    finally:
        LOCK.release()



def firstvds_check(command, project, env):
    if not LOCK.acquire(blocking=False):
        return {"output": "Другая команда ещё выполняется."}
    try:
        sections = []
        exit_code = 0
        for probe in FIRSTVDS_CHECKS:
            try:
                result = subprocess.run(
                    [*command, probe], cwd=project, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15,
                )
            except subprocess.TimeoutExpired:
                sections.append(f"$ {probe}\nSSH: истекло время ожидания.")
                exit_code = 124
                break
            output = result.stdout[:8192].decode("utf-8", errors="replace").strip()
            if len(result.stdout) > 8192:
                output += "\n… вывод сокращён"
            sections.append(f"$ {probe} (код {result.returncode})\n{output}")
            exit_code = exit_code or result.returncode
            if result.returncode == 255:
                break
        return {"output": "\n\n".join(sections), "exit_code": exit_code}
    finally:
        LOCK.release()



def github_task(body):
    blocks = re.findall(r"^```mira[ \t]*\r?\n([\s\S]*?)^```[ \t]*$", body, re.M)
    if len(blocks) != 1:
        raise ValueError("Expected one Mira action block")
    task = json.loads(blocks[0])
    if not isinstance(task, dict) or not set(task) <= {"action", "argument"}:
        raise ValueError("Invalid Mira task")
    action = task.get("action")
    argument = task.get("argument")
    if not isinstance(action, str) or action not in GITHUB_TASK_ACTIONS:
        raise ValueError("Task action not allowed")
    if action == "website":
        # GitHub tasks may open public HTTPS tabs. Explicit local commands
        # continue to support the configured CRM and localhost pages.
        argument = browser_url(argument)
        if urlsplit(argument).scheme != "https":
            raise ValueError("A GitHub website task requires HTTPS")
    elif argument is not None:
        raise ValueError("This action takes no argument")
    return action, argument


def valid_repo(repo):
    return bool(re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo))


def browser_url(value):
    if not isinstance(value, str) or not value or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ValueError("Invalid URL")
    url = urlsplit(value)
    if url.username or url.password or not url.hostname:
        raise ValueError("Invalid URL")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Only HTTPS and local HTTP URLs are accepted")
    return value


def command_text(value, multiline=True):
    if not isinstance(value, str) or not 0 < len(value.strip()) <= 1800:
        raise ValueError("Invalid command length")
    text = value.strip()
    for character in text:
        if ord(character) < 32 and (not multiline or character not in "\r\n\t"):
            raise ValueError("Invalid command character")
        if character in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069":
            raise ValueError("Invalid command direction control")
    return text


def confirmed(title, text):
    message = f"Выполнить эту команду?\n\n{text}"
    return ctypes.windll.user32.MessageBoxW(None, message, title, 0x10124) == 6



def project_file(project, argument):
    if (not isinstance(argument, str) or not argument.strip()
            or any(ord(char) < 32 or "\u202a" <= char <= "\u202e" or "\u2066" <= char <= "\u2069"
                   for char in argument)):
        raise ValueError("Missing filename")
    relative = Path(argument.strip().strip('"'))
    if relative.anchor or any(part.casefold() in {"..", ".mira-trash", ".git"} or ":" in part
                              for part in relative.parts):
        raise ValueError("Use a relative path inside the project")
    lexical = project / relative
    target = lexical.resolve(strict=True)
    if lexical != target or not target.is_relative_to(project) or not target.is_file():
        raise ValueError("Use a regular file inside the project")
    return target


def file_identity(target):
    stat = target.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def deletion(action, project, argument):
    global PENDING_DELETE
    with DELETE_LOCK:
        if action == "prepare-delete":
            PENDING_DELETE = None
            target = project_file(project, argument)
            token = uuid.uuid4().hex
            PENDING_DELETE = (project, target, file_identity(target), token, time.monotonic() + 30)
            return {"output": f"Переместить в карантин файл {target}? Скажите «да» или «нет».",
                    "delete_token": token}
        if not PENDING_DELETE or argument != PENDING_DELETE[3]:
            return {"output": "Запрос на удаление отсутствует или уже обработан."}
        root, target, identity, token, deadline = PENDING_DELETE
        PENDING_DELETE = None
        if action == "cancel-delete" or time.monotonic() > deadline:
            return {"output": "Удаление отменено."}
        if root != project or project_file(project, str(target.relative_to(root))) != target:
            raise ValueError("File path changed after confirmation")
        if file_identity(target) != identity:
            return {"output": "Файл изменился. Запросите новое подтверждение."}
        trash = root / ".mira-trash"
        trash.mkdir(exist_ok=True)
        if trash.resolve(strict=True) != trash:
            raise ValueError("Unsafe quarantine folder")
        destination = trash / token
        destination.mkdir()
        target.rename(destination / target.name)
        return {"output": f"Файл перемещён в карантин: {destination / target.name}"}
