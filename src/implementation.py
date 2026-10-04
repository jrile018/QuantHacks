"""Option-leg pricing and the six strategy P&L calculations."""

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (ENTRY, EXPIRY_BUCKETS, HORIZONS, MAX_STALE_SESSIONS, OTM_GRID, OTM_PCT,
                     RISK_FREE, STRATEGIES, TOP_100)
from .data import (CAL, LAST_SESSION, build_events, contract, fetch_chain, locate_spot,
                   option_bars, pick_expiry, select_strikes, sessions_between)

@dataclass
class Leg:
    ticker: str
    kind: str                 # "call" or "put"
    strike: float
    bars: pd.DataFrame        # close, volume by session (only sessions with trades)
    shares_per_contract: int  # from the selected reference contract

    def mark(self, day: pd.Timestamp) -> float:
        """Last traded close on or before `day`, if it is at most MAX_STALE_SESSIONS sessions old."""
        b = self.bars.loc[: pd.Timestamp(day)]
        if b.empty or sessions_between(b.index[-1], day) > MAX_STALE_SESSIONS:
            return np.nan
        return float(b["close"].iloc[-1])

    def volume_on(self, day: pd.Timestamp) -> float:
        return float(self.bars["volume"].get(pd.Timestamp(day), 0.0))

@dataclass
class PricedEvent:
    """One event × one expiry bucket: the chain-derived spot, the expiry and every leg a strategy may need."""
    ticker: str
    event_date: pd.Timestamp
    t_pre: pd.Timestamp
    t_0: pd.Timestamp
    bucket: str
    expiry: pd.Timestamp
    expiry_session: pd.Timestamp        # last session on or before expiry
    spot_pre: float                     # chain-implied spot on t_pre
    strikes: dict[str, float]
    legs: dict[str, Leg]                # "C_K", "P_K", "C_U0.05", "P_L0.05", ...

    def marks(self, day) -> dict[str, float]:
        return {name: leg.mark(day) for name, leg in self.legs.items()}

    def synthetic_spot(self, day, m: dict[str, float] | None = None) -> float:
        """Stock price implied by the ATM pair on `day`: K·e^(−rT) + C_K − P_K. Exact at expiry."""
        m = m if m is not None else self.marks(day)
        T = max((self.expiry - pd.Timestamp(day)).days, 0) / 365
        return self.strikes["K"] * np.exp(-RISK_FREE * T) + m["C_K"] - m["P_K"]


OPTION_LEG_COLUMNS = ("event_id", "bucket", "leg_code", "contract_ticker", "underlying_ticker",
                      "contract_type", "strike", "expiration_date", "selection_date", "spot_pre",
                      "shares_per_contract")
OPTION_BAR_COLUMNS = ("contract_ticker", "session", "close", "volume")


def option_leg_rows(events: pd.DataFrame, priced: list[PricedEvent]) -> pd.DataFrame:
    """Export the exact selected contracts while the event-to-leg mapping is still in memory."""
    event_ids = {}
    for event in events.to_dict("records"):
        key = (str(event["ticker"]), pd.Timestamp(event["event_date"]),
               pd.Timestamp(event["t_pre"]), pd.Timestamp(event["t_0"]))
        event_id = f"CIK:{str(event['cik']).zfill(10)}:{event['accession_number']}:{event['ticker']}"
        if key in event_ids:
            raise ValueError(f"ambiguous matching event for {key}")
        event_ids[key] = event_id
    rows = []
    for pe in priced:
        key = (pe.ticker, pd.Timestamp(pe.event_date), pd.Timestamp(pe.t_pre), pd.Timestamp(pe.t_0))
        if key not in event_ids:
            raise ValueError(f"no matching event for priced option legs: {key}")
        for code, leg in pe.legs.items():
            if leg.shares_per_contract != 100:
                raise ValueError(f"unsupported contract multiplier for {leg.ticker}")
            rows.append({"event_id": event_ids[key], "bucket": pe.bucket, "leg_code": code,
                         "contract_ticker": leg.ticker, "underlying_ticker": pe.ticker,
                         "contract_type": leg.kind, "strike": leg.strike,
                         "expiration_date": pd.Timestamp(pe.expiry).date().isoformat(),
                         "selection_date": pd.Timestamp(pe.t_pre).date().isoformat(),
                         "spot_pre": pe.spot_pre, "shares_per_contract": leg.shares_per_contract})
    return pd.DataFrame(rows, columns=OPTION_LEG_COLUMNS)


def option_bar_rows(priced: list[PricedEvent]) -> pd.DataFrame:
    """Export observed bars once per contract/session, even when a contract is reused."""
    bars = {}
    for pe in priced:
        for leg in pe.legs.values():
            for session, bar in leg.bars.iterrows():
                key = (leg.ticker, pd.Timestamp(session).date().isoformat())
                value = (float(bar["close"]), float(bar["volume"]))
                if key in bars and bars[key] != value:
                    raise ValueError(f"conflicting option bar for {key}")
                bars[key] = value
    rows = [{"contract_ticker": ticker, "session": session, "close": close, "volume": volume}
            for (ticker, session), (close, volume) in sorted(bars.items())]
    return pd.DataFrame(rows, columns=OPTION_BAR_COLUMNS)

def price_event(ticker: str, t_pre: pd.Timestamp, t_0: pd.Timestamp, event_date: pd.Timestamp,
                buckets: dict, otm_pcts: list[float]) -> tuple[list[PricedEvent], list[str]]:
    dte_hi = max(b[1] for b in buckets.values())
    chain = fetch_chain(ticker, t_pre, 2, dte_hi)
    if chain.empty:
        return [], ["no option chain as of the pre-event session"]
    loc = locate_spot(chain, t_pre)
    if loc is None:
        return [], ["could not recover spot from the chain (no liquid near-dated pair)"]
    priced, notes = [], []
    for name, (lo, hi, target) in buckets.items():
        expiry = pick_expiry(chain, lo, hi, target)
        if expiry is None:
            notes.append(f"{name}: no expiry {lo}-{hi} days out")
            continue
        e = chain[chain.expiration_date == expiry]
        strikes = select_strikes(e, loc["spot"], otm_pcts)
        if strikes is None:
            notes.append(f"{name}: no paired strikes near spot")
            continue
        wanted = {"C_K": ("call", strikes["K"]), "P_K": ("put", strikes["K"])}
        for pct in otm_pcts:
            wanted[f"C_U{pct}"] = ("call", strikes[f"U{pct}"])
            wanted[f"P_L{pct}"] = ("put", strikes[f"L{pct}"])
        legs = {}
        for key, (kind, k) in wanted.items():
            selected = e[(e.strike_price == k) & (e.contract_type == kind)].iloc[0]
            tk = selected["ticker"]
            legs[key] = Leg(tk, kind, k, option_bars(tk, t_pre - pd.Timedelta(days=10), expiry),
                            int(selected["shares_per_contract"]))
        pe = PricedEvent(ticker, event_date, t_pre, t_0, name, expiry, CAL[CAL.searchsorted(expiry, side="right") - 1],
                         loc["spot"], strikes, legs)
        if np.isnan(pe.legs["C_K"].mark(t_pre)) or np.isnan(pe.legs["P_K"].mark(t_pre)):
            notes.append(f"{name}: ATM pair did not trade on or near the pre-event session")
            continue
        priced.append(pe)
    return priced, notes

def price_events(ev: pd.DataFrame, buckets: dict = None, otm_pcts: list[float] = None, label: str = "events") -> tuple[list[PricedEvent], pd.DataFrame]:
    buckets = buckets or EXPIRY_BUCKETS
    otm_pcts = otm_pcts or OTM_GRID
    priced, dropped, t0 = [], [], time.time()
    for n, row in enumerate(ev.itertuples(index=False), 1):
        got, notes = price_event(row.ticker, row.t_pre, row.t_0, row.event_date if hasattr(row, "event_date") else row.filing_date,
                                 buckets, otm_pcts)
        priced += got
        dropped += [(row.ticker, row.t_0, note) for note in notes]
        if n % 25 == 0:
            print(f"  {label}: {n}/{len(ev)} events, {time.time() - t0:.0f}s")
    print(f"{label}: {len(ev)} events -> {len(priced)} priced (event, bucket) pairs; {len(dropped)} drops; {time.time() - t0:.0f}s")
    return priced, pd.DataFrame(dropped, columns=["ticker", "t_0", "reason"])

def summarize_priced(priced: list[PricedEvent]) -> pd.DataFrame:
    rows = []
    for pe in priced:
        m = pe.marks(pe.t_pre)
        rows.append({"ticker": pe.ticker, "event_date": pe.event_date, "t_pre": pe.t_pre, "t_0": pe.t_0, "bucket": pe.bucket,
                     "expiry": pe.expiry, "dte": (pe.expiry - pe.t_pre).days, "spot_pre": pe.spot_pre, "K": pe.strikes["K"],
                     "moneyness": pe.strikes["K"] / pe.spot_pre - 1, "call": pe.legs["C_K"].ticker, "put": pe.legs["P_K"].ticker,
                     "call_px": m["C_K"], "put_px": m["P_K"], "implied_move": (m["C_K"] + m["P_K"]) / pe.spot_pre,
                     "spot_gap": pe.synthetic_spot(pe.t_pre, m) / pe.spot_pre - 1,     # this bucket's parity spot vs the near-dated one
                     "atm_volume": pe.legs["C_K"].volume_on(pe.t_pre) + pe.legs["P_K"].volume_on(pe.t_pre)})
    return pd.DataFrame(rows)

def strategy_pnl(m_e: dict, m_x: dict, S_e: float, S_x: float, otm: float) -> dict[str, float]:
    """P&L per $1 of stock at entry, from entry marks `m_e` to exit marks `m_x`.

    The 100 shares behind the covered call, protective put and collar are replaced by the synthetic
    stock (long ATM call, short ATM put), which is what `S_e` and `S_x` are.
    """
    dS = S_x - S_e
    dC_U = m_x[f"C_U{otm}"] - m_e[f"C_U{otm}"]     # the OTM call we sell
    dP_L = m_x[f"P_L{otm}"] - m_e[f"P_L{otm}"]     # the OTM put we buy (or sell, cash-secured)
    dC_K = m_x["C_K"] - m_e["C_K"]                 # the ATM call we buy
    return {
        "stock":            dS / S_e,
        "long_call":        dC_K / S_e,
        "covered_call":     (dS - dC_U) / S_e,
        "protective_put":   (dS + dP_L) / S_e,
        "collar":           (dS + dP_L - dC_U) / S_e,
        "cash_secured_put": (-dP_L) / S_e,
    }

def evaluate(priced: list[PricedEvent], otm_pcts: list[float] = None) -> pd.DataFrame:
    """Long table: one row per (event, bucket, entry, OTM level, horizon) with every strategy's P&L."""
    otm_pcts = otm_pcts or OTM_GRID
    rows = []
    for pe in priced:
        i0 = CAL.get_loc(pe.t_0)
        exits = {0: pe.t_0}
        exits.update({h: CAL[i0 + h] for h in HORIZONS if i0 + h < len(CAL) and CAL[i0 + h] <= pe.expiry_session})
        exits["exp"] = pe.expiry_session
        for entry, e_day in (("pre", pe.t_pre), ("post", pe.t_0)):
            m_e = pe.marks(e_day)
            S_e = pe.synthetic_spot(e_day, m_e)
            if np.isnan(S_e):
                continue
            implied = (m_e["C_K"] + m_e["P_K"]) / S_e
            dte_sessions = sessions_between(e_day, pe.expiry_session)
            for h, x_day in exits.items():
                if x_day > LAST_SESSION:
                    continue
                m_x = pe.marks(x_day)
                S_x = pe.synthetic_spot(x_day, m_x)
                held = sessions_between(e_day, x_day)
                base = {"ticker": pe.ticker, "event_date": pe.event_date, "t_0": pe.t_0, "bucket": pe.bucket, "expiry": pe.expiry,
                        "entry": entry, "entry_date": e_day, "horizon": h, "exit_date": x_day, "sessions_held": held,
                        "dte_sessions": dte_sessions, "S_entry": S_e, "S_exit": S_x, "realized": S_x / S_e - 1,
                        "implied_move": implied,
                        "implied_scaled": implied * np.sqrt(held / dte_sessions) if dte_sessions else np.nan}
                for otm in otm_pcts:
                    rows.append(dict(base, otm=otm, **strategy_pnl(m_e, m_x, S_e, S_x, otm)))
    if not rows:
        return pd.DataFrame(columns=["ticker", "event_date", "t_0", "bucket", "expiry", "entry",
                                     "entry_date", "horizon", "exit_date", "sessions_held", "dte_sessions",
                                     "S_entry", "S_exit", "realized", "implied_move", "implied_scaled",
                                     "otm", *STRATEGIES, "ratio"])
    res = pd.DataFrame(rows)
    res["ratio"] = res["realized"].abs() / res["implied_scaled"]
    return res

def pnl_path(pe: PricedEvent, strategy: str, entry: str = ENTRY, otm: float = OTM_PCT) -> pd.Series:
    """The strategy's P&L per $1 spot on every session from entry to expiry."""
    e_day = pe.t_pre if entry == "pre" else pe.t_0
    m_e = pe.marks(e_day)
    S_e = pe.synthetic_spot(e_day, m_e)
    days = CAL[(CAL >= e_day) & (CAL <= min(pe.expiry_session, LAST_SESSION))]
    out = {}
    for d in days:
        m = pe.marks(d)
        out[sessions_between(e_day, d)] = strategy_pnl(m_e, m, S_e, pe.synthetic_spot(d, m), otm)[strategy]
    return pd.Series(out, name=f"{pe.event_date.date()}")

def run_study(tag: str, start: str, end: str, universe: list[str] = TOP_100, buckets: dict = EXPIRY_BUCKETS,
              max_events: int | None = None, label: str = None) -> dict:
    """The whole pipeline on a fresh window. Returns the events, priced legs, long results and the scoreboard."""
    ev = build_events(tag, start, end, universe)
    if ev.empty:
        raise ValueError(f"No 8-K events for {tag!r} in {start}..{end}")
    ev["event_date"] = ev["filing_date"]
    if max_events:
        ev = ev.head(max_events).copy()
    pr, drops = price_events(ev, buckets, label=label or f"{tag} {start}..{end}")
    if not pr:
        raise ValueError(f"No events could be priced for {tag!r} in {start}..{end}")
    res = evaluate(pr)
    if res.empty:
        raise ValueError(f"No evaluated horizons for {tag!r} in {start}..{end}")
    from .risk_management import scoreboard
    return {"events": ev, "priced": pr, "dropped": drops, "results": res, "board": scoreboard(res)}
