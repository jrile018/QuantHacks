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


# Exhibit filenames, so a scan of a filing folder can tell the filing itself from the
# exhibits filed with it. This matters because exhibits are downloaded into the same folder:
# globbing a 10-K folder and taking the last file returns an exhibit, not the 10-K.
EXHIBIT_NAME_RE = re.compile(
    r"(?:\b|_|-)(?:ex|exhibit)[-_]?\d{1,3}(?:[._\-]|$)"      # ex-21, ex10, exhibit99_1
    r"|press[-_]?release|subsidiar|consent|certification"
    r"|^ex\d|graphic|logo|signature", re.I)


def is_exhibit(path) -> bool:
    return bool(EXHIBIT_NAME_RE.search(Path(path).name))


def primary_documents(folder) -> list[Path]:
    """The filing documents in a folder, excluding exhibits, largest first.

    Exhibits are excluded by filename, then the remainder are ordered by size, because the
    filing itself is far larger than anything filed beside it. If every file looks like an
    exhibit, all of them are returned so the caller still gets something rather than nothing.
    """
    folder = Path(folder)
    if not folder.exists():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".htm", ".html", ".txt")]
    candidates = [p for p in files if not is_exhibit(p)] or files
    return sorted(candidates, key=lambda p: p.stat().st_size, reverse=True)


def primary_document(folder):
    """The single filing document for one filing folder, or None."""
    docs = primary_documents(folder)
    return docs[0] if docs else None


def filing_documents(company_folder, forms):
    """[(filing_date, form, primary document)] for a company, newest last.

    Walks each filing folder under the given forms and resolves one primary document per
    filing, so callers never read an exhibit by accident.
    """
    out = []
    company_folder = Path(company_folder)
    for form in forms:
        base = company_folder / form
        if not base.exists():
            continue
        for filing in sorted(base.iterdir()):
            if not filing.is_dir():
                continue
            doc = primary_document(filing)
            if doc is not None:
                out.append((filing.name.split("_")[0], form.replace("_", "/"), doc))
    return sorted(out)


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
