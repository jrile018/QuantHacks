"""
Massive: catalog every filing day from 2022 onward, with volume of each form type per company,
exported as nested JSON. Source: EDGAR filing index (list_stocks_filings_index).
Counts are kept in SQLite (low RAM, resumable); the JSON is streamed out at the end.

Run from the repo root:  python scripts/filings_catalog.py
Outputs go to data/processed/ (git-ignored).
"""
import itertools
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

from massive import RESTClient

# Reuse the project's key loader (environment variable, then the root .env file).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.data import load_api_key  # noqa: E402

# ============================ CONFIG ============================
API_KEY = load_api_key()                       # reads MASSIVE_API_KEY from the environment or .env
START_DATE = "2022-01-01"        # inclusive
END_DATE = None                  # None = through the latest filing in the index; or e.g. "2026-06-30"
FORMS = None                     # None = every form type. Or a list to limit volume, e.g.
#   FORMS = ["8-K", "8-K/A", "10-K", "10-K/A", "10-Q", "10-Q/A", "DEF 14A", "S-1", "S-3", "6-K", "20-F"]
KEY_BY = "cik"                   # "cik" (stable) or "ticker" (falls back to the CIK when no ticker)
INCLUDE_DAYS = True              # False = skip the per-company day-by-day detail (much smaller file)
SLEEP = 12.5                     # pause per 10,000-row page; use 0.1 on a paid plan
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "processed")
DB = os.path.join(OUT_DIR, "filings_catalog.sqlite")
OUT = os.path.join(OUT_DIR, "filings_catalog.json")
FRESH = False                    # True = delete the SQLite file and start over

try:
    client = RESTClient(API_KEY, retries=2)
except TypeError:
    client = RESTClient(API_KEY)


# ============================ SQLITE ============================
def open_db():
    os.makedirs(OUT_DIR, exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS agg(
            company TEXT, filing_date TEXT, form TEXT, n INTEGER,
            PRIMARY KEY (company, filing_date, form));
        CREATE TABLE IF NOT EXISTS company(
            key TEXT PRIMARY KEY, ticker TEXT, cik TEXT, name TEXT);
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    """)
    db.commit()
    return db


def get_meta(db, k, default=None):
    row = db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def set_meta(db, k, v):
    db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)", (k, v))


def check_config(db):
    cfg = json.dumps({"start": START_DATE, "end": END_DATE, "forms": FORMS, "key_by": KEY_BY})
    old = get_meta(db, "config")
    if old and old != cfg:
        raise SystemExit(f"{DB} was built with a different config:\n  {old}\n"
                         f"Set FRESH = True (or delete {DB}) to start over.")
    with db:
        set_meta(db, "config", cfg)


def company_key(ticker, cik):
    if KEY_BY == "ticker" and ticker:
        return ticker
    return cik or (f"TICKER:{ticker}" if ticker else "UNKNOWN")


UPSERT_AGG = ("INSERT INTO agg(company, filing_date, form, n) VALUES (?, ?, ?, ?) "
              "ON CONFLICT(company, filing_date, form) DO UPDATE SET n = n + excluded.n")
UPSERT_CO = ("INSERT INTO company(key, ticker, cik, name) VALUES (?, ?, ?, ?) "
             "ON CONFLICT(key) DO UPDATE SET name = COALESCE(excluded.name, name), "
             "ticker = COALESCE(excluded.ticker, ticker)")


def flush(db, name, counts, comps, cur_date, cur_acc):
    """Commit counts and the resume point together, so the two never disagree."""
    with db:
        db.executemany(UPSERT_AGG, [(k[0], k[1], k[2], v) for k, v in counts.items()])
        db.executemany(UPSERT_CO, [(k, *v) for k, v in comps.items()])
        set_meta(db, f"resume:{name}",
                 json.dumps({"last_date": cur_date, "boundary": sorted(cur_acc)}))
        total = int(get_meta(db, "rows_ingested", "0")) + sum(counts.values())
        set_meta(db, "rows_ingested", str(total))


# ============================ STREAM THE FILING INDEX ============================
def open_stream(form, gte):
    for lim in ("10000", "5000", "1000"):            # 10,000 is the documented maximum
        kw = dict(limit=lim, sort="filing_date.asc")
        if form:
            kw["form_type"] = form
        if gte:
            kw["filing_date_gte"] = gte
        if END_DATE:
            kw["filing_date_lte"] = END_DATE
        try:
            gen = client.list_stocks_filings_index(**kw)
            first = next(iter(gen))
            return itertools.chain([first], gen), int(lim)
        except StopIteration:
            return iter(()), int(lim)                # nothing (more) to read
        except Exception as e:
            print(f"  {form or 'ALL'} limit={lim} failed: {type(e).__name__}: {str(e)[:150]}")
    raise RuntimeError("filing index failed with every page size")


def run_stream(db, form):
    name = form or "ALL"
    if get_meta(db, f"done:{name}") == "1":
        print(f"{name}: already complete")
        return True
    rs = json.loads(get_meta(db, f"resume:{name}", '{"last_date": null, "boundary": []}'))
    resume_date, resume_acc = rs["last_date"], set(rs["boundary"])
    if resume_date:
        print(f"{name}: resuming from {resume_date}")
    stream, page = open_stream(form, resume_date or START_DATE)
    cur_date, cur_acc = resume_date, set(resume_acc)
    counts, comps, seen, note = Counter(), {}, 0, None
    try:
        for r in stream:
            seen += 1
            date = str(getattr(r, "filing_date", "") or "")[:10]
            if not date:
                continue
            if END_DATE and date > END_DATE:
                break                                # sorted oldest first, so we're past the window
            if date < START_DATE:
                continue                             # only if the server ignored the date filter
            acc = getattr(r, "accession_number", None)
            if date == resume_date and acc in resume_acc:
                continue                             # already counted before the last commit
            if date != cur_date:
                cur_date, cur_acc = date, set()
            if acc:
                cur_acc.add(acc)
            ticker, cik = getattr(r, "ticker", None), getattr(r, "cik", None)
            key = company_key(ticker, cik)
            counts[(key, date, getattr(r, "form_type", None) or "(unknown)")] += 1
            comps[key] = (ticker, cik, getattr(r, "issuer_name", None))
            if seen % page == 0:
                flush(db, name, counts, comps, cur_date, cur_acc)
                counts.clear()
                comps.clear()
                total = get_meta(db, "rows_ingested")
                print(f"  {name}: {int(total):,} rows ingested, now at {cur_date}")
                time.sleep(SLEEP)
    except KeyboardInterrupt:
        note = "interrupted"
    except Exception as e:
        note = f"{type(e).__name__}: {str(e)[:150]}"
    flush(db, name, counts, comps, cur_date, cur_acc)
    if note:
        print(f"NOTE: {name} stopped early ({note}); rerun to resume.")
        return False
    with db:
        set_meta(db, f"done:{name}", "1")
    return True


# ============================ NESTED JSON EXPORT ============================
def iter_companies(db):
    q = """SELECT a.company, c.ticker, c.cik, c.name, a.filing_date, a.form, a.n
           FROM agg a LEFT JOIN company c ON c.key = a.company
           ORDER BY a.company, a.filing_date, a.form"""

    def finish(o):
        o["n_filing_days"] = len(o.pop("_days"))
        o["forms"] = dict(sorted(o["forms"].items(), key=lambda kv: -kv[1]))
        if not INCLUDE_DAYS:
            o.pop("filing_days")
        return o

    cur, obj = None, None
    for key, ticker, cik, name, date, form, n in db.execute(q):
        if key != cur:
            if obj is not None:
                yield cur, finish(obj)
            cur = key
            obj = {"ticker": ticker, "cik": cik, "issuer_name": name, "total_filings": 0,
                   "n_filing_days": 0, "first_filing_date": date, "last_filing_date": date,
                   "forms": {}, "filing_days": {}, "_days": set()}
        obj["total_filings"] += n
        obj["last_filing_date"] = date
        obj["forms"][form] = obj["forms"].get(form, 0) + n
        obj["_days"].add(date)
        if INCLUDE_DAYS:
            obj["filing_days"].setdefault(date, {})[form] = n
    if obj is not None:
        yield cur, finish(obj)


def export(db, partial):
    form_totals = {f: int(n) for f, n in db.execute(
        "SELECT form, SUM(n) FROM agg GROUP BY form ORDER BY SUM(n) DESC")}
    calendar = {}
    for date, form, n in db.execute(
            "SELECT filing_date, form, SUM(n) FROM agg GROUP BY filing_date, form "
            "ORDER BY filing_date, form"):
        calendar.setdefault(date, {})[form] = int(n)
    n_filings, n_companies, n_days, first, last = db.execute(
        "SELECT SUM(n), COUNT(DISTINCT company), COUNT(DISTINCT filing_date), "
        "MIN(filing_date), MAX(filing_date) FROM agg").fetchone()
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date_range_requested": {"start": START_DATE, "end": END_DATE},
        "forms_requested": FORMS or "all",
        "company_key": KEY_BY,
        "partial": partial,
        "total_filings": int(n_filings or 0),
        "n_companies": n_companies,
        "n_filing_days": n_days,
        "coverage": {"first_filing_date": first, "last_filing_date": last},
    }
    head = json.dumps({"meta": meta, "form_totals": form_totals, "calendar": calendar},
                      ensure_ascii=False)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(head[:-1] + ',\n"companies": {\n')       # reopen the object to stream companies
        first_row = True
        for key, obj in iter_companies(db):
            f.write(("" if first_row else ",\n") + json.dumps(key) + ": "
                    + json.dumps(obj, ensure_ascii=False))
            first_row = False
        f.write("\n}}\n")
    print(f"\n{meta['total_filings']:,} filings, {n_companies:,} companies, "
          f"{n_days:,} filing days ({first} -> {last})")
    print("Top forms:", list(form_totals.items())[:8])
    print(f"Saved {OUT} (one company per line) and {DB}")


# ============================ MAIN ============================
if __name__ == "__main__":
    if FRESH:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(DB + suffix):
                os.remove(DB + suffix)
    db = open_db()
    check_config(db)
    complete = True
    for form in (FORMS or [None]):
        if not run_stream(db, form):
            complete = False
            break
    export(db, partial=not complete)
