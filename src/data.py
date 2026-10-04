"""Massive/SEC access, trading calendar, event construction, and option-chain data."""

import hashlib
import json
import os
import re
import sys
import time
from getpass import getpass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)
from pandas.tseries.offsets import CustomBusinessDay

from .config import PLACEBO_GAP_DAYS, RISK_FREE, SEC_USER_AGENT, STRIKE_WINDOW

BASE_URL = "https://api.massive.com"
CACHE_DIR = Path(__file__).resolve().parents[1] / ".massive_cache"
_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        key = load_api_key()
        _SESSION = requests.Session()
        _SESSION.headers["Authorization"] = f"Bearer {key}"
    CACHE_DIR.mkdir(exist_ok=True)
    return _SESSION


def load_api_key(name: str = "MASSIVE_API_KEY") -> str:
    """Read the environment or private root .env; prompt only in a terminal."""
    key = (os.environ.get(name) or "").strip()
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key and sys.stdin.isatty():
        key = getpass(f"{name} (https://massive.com/dashboard/keys): ").strip()
    if not key:
        raise RuntimeError(f"{name} is missing; set it in the environment or root .env file")
    return key

def api_get(path_or_url: str, params: dict | None = None) -> dict:
    """GET one page from the Massive REST API. Cached on disk by the full URL, so reruns are free."""
    url = path_or_url if path_or_url.startswith("http") else BASE_URL + path_or_url
    full_url = requests.Request("GET", url, params=params).prepare().url
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / (hashlib.sha1(full_url.encode()).hexdigest() + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    for attempt in range(10):
        resp = _session().get(full_url, timeout=60)
        if resp.status_code in (429, 500, 502, 503, 504):   # rate-limited or a transient server error
            retry_after = resp.headers.get("Retry-After", "")
            time.sleep(float(retry_after) if retry_after.isdigit() else min(2 ** attempt, 20))
            continue
        break
    resp.raise_for_status()
    payload = resp.json()
    cache_file.write_text(json.dumps(payload))
    return payload

def api_get_all(path: str, params: dict | None = None, max_pages: int = 500) -> list[dict]:
    """Follow `next_url` pagination and return every result row."""
    payload = api_get(path, params)
    rows = list(payload.get("results") or [])
    pages = 1
    while payload.get("next_url") and pages < max_pages:
        payload = api_get(payload["next_url"])
        rows.extend(payload.get("results") or [])
        pages += 1
    return rows

class NYSEHolidays(AbstractHolidayCalendar):
    """NYSE full-day closures. Differs from the federal calendar: Good Friday closed, Columbus and
    Veterans Day open, no observance when New Year's Day falls on a Saturday."""
    rules = [
        Holiday("New Year's Day", month=1, day=1,
                observance=lambda d: d + pd.Timedelta(days=1) if d.weekday() == 6 else d),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
        Holiday("National day of mourning, President Carter", year=2025, month=1, day=9),
    ]

def trading_sessions(start, end) -> pd.DatetimeIndex:
    holidays = NYSEHolidays().holidays(pd.Timestamp(start) - pd.Timedelta(days=7), pd.Timestamp(end) + pd.Timedelta(days=7))
    return pd.bdate_range(start, end, freq=CustomBusinessDay(holidays=holidays))

CAL = trading_sessions("2021-06-01", "2027-12-31")
TODAY = pd.Timestamp.today().normalize()
LAST_SESSION = CAL[CAL.searchsorted(TODAY, side="right") - 1]


def session_on_or_after(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="left")]

def safe_entry_session(day) -> pd.Timestamp:
    """First session strictly after the filing date; safe when acceptance time is unknown."""
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="right")]

def session_before(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="left") - 1]

def sessions_between(a, b) -> int:
    """Number of sessions strictly after `a` up to and including `b`."""
    return int(CAL.searchsorted(pd.Timestamp(b), side="right") - CAL.searchsorted(pd.Timestamp(a), side="right"))

def normalize_ticker(t) -> str | None:
    """Filings write share classes as BRK/B or BRK.B; Massive's options use BRK.B as the underlying."""
    if not isinstance(t, str) or not t.strip():
        return None
    return t.strip().upper().replace("/", ".")

def fetch_disclosures(tag: str, start: str, end: str) -> pd.DataFrame:
    rows = api_get_all("/stocks/filings/8-K/vX/disclosures", {
        "tertiary_category": tag, "filing_date.gte": start, "filing_date.lte": end,
        "limit": 1000, "sort": "filing_date.asc",
    })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["filing_date"] = pd.to_datetime(df["filing_date"])
    return df

def build_events(tag: str, start: str, end: str, universe: list[str]) -> pd.DataFrame:
    """One row per filer/date, with a pre-filing mark and conservative next-session entry."""
    raw = fetch_disclosures(tag, start, end)
    print(f"{len(raw):,} '{tag}' disclosures across all filers, {start}..{end}")
    if raw.empty:
        return pd.DataFrame(columns=["cik", "filing_date", "ticker", "accession_number",
                                     "filing_url", "supporting_text", "t_0", "t_pre",
                                     "days_since_prev_event"])
    ex = raw.explode("tickers").rename(columns={"tickers": "ticker"})
    ex["ticker"] = ex["ticker"].map(normalize_ticker)
    ex = ex[ex["ticker"].isin(universe)]
    ev = (ex.sort_values(["cik", "filing_date"])
            .groupby(["cik", "filing_date"], as_index=False)
            .agg(ticker=("ticker", "first"), accession_number=("accession_number", "first"),
                 filing_url=("filing_url", "first"), supporting_text=("supporting_text", "first"))
            .sort_values("filing_date").reset_index(drop=True))
    ev["t_0"] = ev["filing_date"].map(safe_entry_session)
    ev["t_pre"] = ev["filing_date"].map(session_before)
    ev["days_since_prev_event"] = ev.groupby("ticker")["filing_date"].diff().dt.days
    return ev

def option_bars(opt_ticker: str, start, end) -> pd.DataFrame:
    """Daily bars for one contract: index = session, columns close and volume. Only sessions where it traded."""
    rows = api_get_all(f"/v2/aggs/ticker/{opt_ticker}/range/1/day/{pd.Timestamp(start):%Y-%m-%d}/{pd.Timestamp(end):%Y-%m-%d}",
                       {"adjusted": "false", "sort": "asc", "limit": 50000})
    if not rows:
        return pd.DataFrame(columns=["close", "volume"], index=pd.DatetimeIndex([], name="session"))
    idx = (pd.to_datetime([r["t"] for r in rows], unit="ms", utc=True)
             .tz_convert("America/New_York").normalize().tz_localize(None))
    return pd.DataFrame({"close": [float(r["c"]) for r in rows], "volume": [float(r.get("v") or 0) for r in rows]},
                        index=pd.DatetimeIndex(idx, name="session"))

def fetch_chain(ticker: str, as_of: pd.Timestamp, dte_lo: int, dte_hi: int) -> pd.DataFrame:
    """Every standard contract that existed on `as_of` with an expiry `dte_lo`..`dte_hi` days out."""
    rows = api_get_all("/v3/reference/options/contracts", {
        "underlying_ticker": ticker, "as_of": as_of.strftime("%Y-%m-%d"),
        "expiration_date.gte": (as_of + pd.Timedelta(days=dte_lo)).strftime("%Y-%m-%d"),
        "expiration_date.lte": (as_of + pd.Timedelta(days=dte_hi)).strftime("%Y-%m-%d"),
        "limit": 1000,
    })
    chain = pd.DataFrame(rows)
    if chain.empty:
        return chain
    if "shares_per_contract" not in chain:
        chain["shares_per_contract"] = np.nan
    chain["shares_per_contract"] = pd.to_numeric(chain["shares_per_contract"], errors="coerce")
    chain = chain[chain["shares_per_contract"] == 100]  # reject unknown and adjusted series
    chain = chain[["ticker", "contract_type", "strike_price", "expiration_date",
                   "shares_per_contract"]].copy()
    chain["expiration_date"] = pd.to_datetime(chain["expiration_date"])
    chain["dte"] = (chain["expiration_date"] - as_of).dt.days
    chain["strike_price"] = chain["strike_price"].astype(float)
    return chain.reset_index(drop=True)

def paired_strikes(e: pd.DataFrame) -> np.ndarray:
    both = e.groupby("strike_price")["contract_type"].nunique()
    return both[both == 2].index.to_numpy(dtype=float)

def contract(e: pd.DataFrame, strike: float, kind: str) -> str:
    return e[(e.strike_price == strike) & (e.contract_type == kind)]["ticker"].iloc[0]

def last_close_on_or_before(opt_ticker: str, day: pd.Timestamp, lookback_days: int = 7) -> float | None:
    bars = option_bars(opt_ticker, day - pd.Timedelta(days=lookback_days), day)
    return float(bars["close"].iloc[-1]) if len(bars) else None

def locate_spot(chain: pd.DataFrame, day: pd.Timestamp, max_iter: int = 8) -> dict | None:
    """Recover the stock price on `day` from the option chain alone, via put-call parity.

    At any strike K with both a call and a put, S = K·e^(−rT) + C − P. The strike that minimises |C − P|
    is at-the-money, and the estimate is best there because both legs are liquid. We start at the
    median strike of the nearest expiry (new weekly series are listed around the current price, so that
    median is already close), then step to the strike nearest our estimate until it stops moving.
    """
    near = chain[chain.dte >= 3]
    if near.empty:
        return None
    near = near[near.dte == near.dte.min()]
    strikes = paired_strikes(near)
    if len(strikes) < 3:
        return None
    T = near.dte.iloc[0] / 365
    k, tried, est = float(np.median(strikes)), set(), None
    k = strikes[np.abs(strikes - k).argmin()]
    for _ in range(max_iter):
        tried.add(k)
        c = last_close_on_or_before(contract(near, k, "call"), day)
        p = last_close_on_or_before(contract(near, k, "put"), day)
        if c is None or p is None:                                   # an illiquid strike: try the next-nearest untried one
            rest = [s for s in strikes if s not in tried]
            if not rest:
                break
            k = rest[int(np.abs(np.array(rest) - k).argmin())]
            continue
        est = k * np.exp(-RISK_FREE * T) + c - p
        k_new = strikes[np.abs(strikes - est).argmin()]
        if k_new == k or k_new in tried:
            break
        k = k_new
    if est is None:
        return None
    return {"spot": float(est), "strike": float(k), "expiry": near.expiration_date.iloc[0], "dte": int(near.dte.iloc[0])}

def pick_expiry(chain: pd.DataFrame, lo: int, hi: int, target: int) -> pd.Timestamp | None:
    cand = chain[(chain.dte >= lo) & (chain.dte <= hi)]
    if cand.empty:
        return None
    dte_of = cand.groupby("expiration_date")["dte"].first()
    ok = [x for x, g in cand.groupby("expiration_date") if len(paired_strikes(g)) >= 3]   # needs a real chain, not a stub
    if not ok:
        return None
    return min(ok, key=lambda x: abs(dte_of[x] - target))

def select_strikes(e: pd.DataFrame, spot: float, otm_pcts: list[float]) -> dict[str, float] | None:
    """ATM strike K (nearest to spot, both legs listed) plus, for each OTM level, the call strike U at or
    above spot·(1+pct) and the put strike L at or below spot·(1−pct)."""
    both = paired_strikes(e)
    both = both[(both >= spot * (1 - STRIKE_WINDOW)) & (both <= spot * (1 + STRIKE_WINDOW))]
    if len(both) == 0:
        return None
    calls = np.sort(e.loc[e.contract_type == "call", "strike_price"].unique())
    puts = np.sort(e.loc[e.contract_type == "put", "strike_price"].unique())
    out = {"K": float(both[np.abs(both - spot).argmin()])}
    for pct in otm_pcts:
        up, dn = calls[calls >= spot * (1 + pct)], puts[puts <= spot * (1 - pct)]
        out[f"U{pct}"] = float(up.min()) if len(up) else float(calls.max())
        out[f"L{pct}"] = float(dn.max()) if len(dn) else float(puts.min())
    return out

def sample_placebo(ev: pd.DataFrame, n: int, start: str, end: str, gap_days: int = PLACEBO_GAP_DAYS, seed: int = 7) -> pd.DataFrame:
    """Ordinary sessions for the same tickers, drawn in proportion to how often each ticker has an event,
    at least `gap_days` from any of that ticker's events."""
    rng = np.random.default_rng(seed)
    sessions = CAL[(CAL >= pd.Timestamp(start)) & (CAL <= pd.Timestamp(end))]
    by_ticker = ev.groupby("ticker")["filing_date"].apply(list)
    rows = []
    for t in rng.choice(ev["ticker"].to_numpy(), size=n, replace=True):
        for _ in range(25):
            d = sessions[rng.integers(len(sessions))]
            if all(abs((d - a).days) > gap_days for a in by_ticker.get(t, [])):
                rows.append({"ticker": t, "filing_date": d, "event_date": d,
                             "t_0": safe_entry_session(d), "t_pre": session_before(d)})
                break
    return pd.DataFrame(rows)

def fetch_acceptance_time(filing_url: str) -> pd.Timestamp | None:
    """Acceptance timestamp (US/Eastern) from the EDGAR submission header; None if not found."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = CACHE_DIR / ("sec_" + hashlib.sha1(filing_url.encode()).hexdigest() + ".txt")
    if key.exists():
        head = key.read_text()
    else:
        resp = requests.get(filing_url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30, stream=True)
        resp.raise_for_status()
        head = next(resp.iter_content(4096, decode_unicode=True))
        key.write_text(head)
        time.sleep(0.12)
    m = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})", head)
    return pd.Timestamp(m.group(1)) if m else None
