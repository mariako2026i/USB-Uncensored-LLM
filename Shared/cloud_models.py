"""Server-side adapter for explicitly configured OpenAI-compatible providers."""

import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

CONFIG = Path(__file__).with_name("personal-models.json")
PREFIX = "cloud/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def providers():
    if not CONFIG.exists():
        return {}
    entries = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    result = {}
    for entry in entries:
        name = entry["id"]
        url = urlsplit(entry["base_url"])
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name) or url.scheme != "https" or not url.hostname:
            raise ValueError("Invalid cloud provider ID or HTTPS URL")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Provider URL must not have credentials, query or fragment")
        key = os.environ.get(entry["key_env"])
        if key:
            result[PREFIX + name] = (entry["base_url"].rstrip("/"), entry["model"], key)
    return result


def complete(provider, messages):
    base, model, key = provider
    if not isinstance(messages, list) or any(
        not isinstance(message, dict)
        or message.get("role") not in ("system", "user", "assistant")
        or not isinstance(message.get("content"), str)
        or message.get("images")
        for message in messages
    ):
        raise ValueError("Cloud providers accept text messages only")
    body = json.dumps({
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=90) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Cloud response too large")
    data = json.loads(raw)
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("Cloud response did not contain text")
    return json.dumps({"message": {"content": content}, "done": True}).encode() + b"\n"
