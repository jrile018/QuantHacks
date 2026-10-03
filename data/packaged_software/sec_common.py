"""Small shared SEC client and .env reader. No secrets are logged."""
from __future__ import annotations
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def env_value(name):
    if name in os.environ:
        return os.environ[name].strip()
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"\s*(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.*)", line)
            if match:
                value = match[1].strip()
                if value[:1] in ("'", '"'):
                    quote = value[0]
                    return value[1:].split(quote, 1)[0]
                return value.split(" #", 1)[0].strip()
    return ""


class SecClient:
    def __init__(self):
        self.user_agent = env_value("SEC_USER_AGENT")
        self.last_request = None

    def get(self, url):
        if not re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", self.user_agent):
            raise ValueError("Set SEC_USER_AGENT to a descriptive name and real contact email in .env")
        for attempt in range(4):
            if self.last_request is not None:
                time.sleep(max(0, 0.2 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                request = urllib.request.Request(url, headers={"User-Agent": self.user_agent,
                                                               "Accept-Encoding": "identity"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
            time.sleep(2 ** attempt)

    def json(self, url):
        return json.loads(self.get(url))
