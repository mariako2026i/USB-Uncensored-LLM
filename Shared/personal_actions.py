"""Run only actions defined in the Windows companion."""

import ctypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading

LOCK = threading.Lock()


def execute(action):
    if os.name != "nt":
        return {"output": "Команда доступна в Windows."}
    windows = Path(os.environ["SystemRoot"]) / "System32"
    settings = os.environ
    project = Path(settings.get("USB_AI_PROJECT", str(Path.home()))).resolve(strict=True)
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
        "status": ["git.exe", "status", "--short", "--branch"],
        "console": [str(powershell), "-NoProfile", "-NoExit"],
        "project": [str(windows.parent / "explorer.exe"), str(project)],
    }
    if action == "deploy":
        alias = settings.get("USB_AI_SSH_ALIAS", "")
        script = settings.get("USB_AI_REMOTE_SCRIPT", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", alias):
            return {"output": "Укажите SSH-профиль в USB_AI_SSH_ALIAS."}
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", script):
            return {"output": "Укажите путь к скрипту на VPS в USB_AI_REMOTE_SCRIPT."}
        prompt = f"Выполнить на {alias}?\n\n{script}"
        if ctypes.windll.user32.MessageBoxW(None, prompt, "FirstVDS", 0x124) != 6:
            return {"output": "Деплой отменён."}
        command = [str(windows / "OpenSSH" / "ssh.exe"), "-o", "BatchMode=yes",
                   "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10",
                   "--", alias, "/bin/bash", script]
    else:
        command = commands[action]

    if action in {"console", "project"}:
        flags = subprocess.CREATE_NEW_CONSOLE if action == "console" else 0
        subprocess.Popen(command, cwd=project, env=clean_env, creationflags=flags)
        return {"output": "Окно открыто."}

    if not LOCK.acquire(blocking=False):
        return {"output": "Другая команда ещё выполняется."}
    try:
        with tempfile.TemporaryFile() as output:
            try:
                result = subprocess.run(command, cwd=project, env=clean_env, stdin=subprocess.DEVNULL,
                                        stdout=output, stderr=subprocess.STDOUT, timeout=180)
            except subprocess.TimeoutExpired:
                return {"output": "Истекло время ожидания. Для деплоя проверьте состояние на VPS."}
            output.seek(0)
            raw = output.read(32769)
            message = raw[:32768].decode("utf-8", errors="replace")
            if len(raw) > 32768:
                message += "\n… вывод сокращён"
            return {"output": message or "Команда завершилась без вывода.", "exit_code": result.returncode}
    finally:
        LOCK.release()
