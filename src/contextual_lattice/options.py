"""Bounded, exploratory audit of selected option contracts and stock movement.

CBBO minute marks are sampled observations, not fresh quote updates or fills.
No implied volatility, executable premium, or option profit is inferred here.
"""
from __future__ import annotations

import math

import pandas as pd

MIN_DISTINCT_EVENTS = 20


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _quote_mid(quote: dict | None, session: str) -> float | None:
    if quote is None:
        return None
    fields = ("bid", "ask", "mid", "bid_size", "ask_size", "minutes_before_1600")
    if not all(_finite(quote.get(field)) for field in fields):
        return None
    bid, ask, mid = (float(quote[field]) for field in ("bid", "ask", "mid"))
    if not (0 < bid <= ask and math.isclose(mid, (bid + ask) / 2, abs_tol=1e-6)):
        return None
    if (float(quote["bid_size"]) < 1 or float(quote["ask_size"]) < 1
            or not 0 <= float(quote["minutes_before_1600"]) <= 5):
        return None
    try:
        instant = pd.Timestamp(quote["mark_time_utc"])
        if instant.tzinfo is None:
            return None
        local = instant.tz_convert("America/New_York")
        near_close = ((local.hour == 15 and 55 <= local.minute <= 59)
                      or (local.hour == 16 and local.minute == 0))
        if local.strftime("%Y-%m-%d") != session or not near_close:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return mid


def _exact_scores(events: pd.DataFrame, scores: pd.DataFrame) -> dict[tuple[str, str], float]:
    fixed = scores[(scores["view"] == "B") & (scores["estimator"] == "mahalanobis")].copy()
    fixed["date"] = pd.to_datetime(fixed["date"]).dt.strftime("%Y-%m-%d")
    keys = set(zip(events["ticker"], events["t_pre"]))
    fixed = fixed[[ (row.ticker, row.date) in keys for row in fixed.itertuples() ]]
    if fixed.duplicated(["ticker", "date"]).any():
        raise ValueError("ambiguous exact pre-event Lattice score")
    return {(str(row.ticker), str(row.date)): float(row.depth)
            for row in fixed.itertuples() if _finite(row.depth)}


def build_audit(events: pd.DataFrame, contracts: pd.DataFrame, quotes: pd.DataFrame,
                prices: pd.DataFrame, scores: pd.DataFrame,
                predictions: pd.DataFrame | None = None) -> pd.DataFrame:
    """One attempted row per selected event/expiry; retain failed gates."""
    if events["event_id"].duplicated().any():
        raise ValueError("duplicate event identity")
    if quotes.duplicated(["contract_ticker", "session"]).any():
        raise ValueError("ambiguous option contract/session mark")
    if prices.duplicated(["ticker", "date"]).any():
        raise ValueError("ambiguous stock ticker/session mark")
    score_by_key = _exact_scores(events, scores)
    quote_by_key = quotes.set_index(["contract_ticker", "session"]).to_dict("index")
    price_groups = {str(key): group.sort_values("date").set_index("date")
                    for key, group in prices.groupby("ticker")}
    forecast_by_key: dict[tuple[str, str], float] = {}
    if predictions is not None:
        needed = {"ticker", "decision_date", "predicted_abs_return", "status"}
        if not needed.issubset(predictions.columns):
            raise ValueError("equity predictions require ticker,decision_date,predicted_abs_return,status")
        if predictions.duplicated(["ticker", "decision_date"]).any():
            raise ValueError("ambiguous equity prediction")
        forecast_by_key = {(str(r.ticker), str(r.decision_date)): float(r.predicted_abs_return)
                           for r in predictions.itertuples()
                           if str(r.status) in {"forecast", "predicted", "eligible", "evaluated"}
                           and _finite(r.predicted_abs_return)}
    rows = []
    for event in events.to_dict("records"):
        ticker, event_id = str(event["ticker"]), str(event["event_id"])
        entry = str(event["t_0"])
        price_panel = price_groups.get(ticker)
        exit_date = None
        adjusted_abs = None
        native_close_entry = None
        if price_panel is not None and entry in price_panel.index:
            future = price_panel.index[price_panel.index > entry]
            if len(future):
                exit_date = str(future[0])
                p0, p1 = price_panel.loc[entry], price_panel.loc[exit_date]
                if _finite(p0["adjclose"]) and _finite(p1["adjclose"]) and p0["adjclose"] > 0 and p1["adjclose"] > 0:
                    adjusted_abs = abs(math.log(float(p1["adjclose"]) / float(p0["adjclose"])))
                if "close" in price_panel.columns and _finite(p0["close"]) and p0["close"] > 0:
                    native_close_entry = float(p0["close"])
        event_contracts = contracts[contracts["event_id"] == event_id]
        buckets = sorted(event_contracts["bucket"].dropna().unique()) or [None]
        for bucket in buckets:
            reasons = []
            score = score_by_key.get((ticker, str(event["t_pre"])))
            if score is None:
                reasons.append("missing_exact_pre_score")
            chronology_ok = str(event["t_pre"]) < str(event["event_date"]) < entry
            if not chronology_ok:
                reasons.append("event_chronology_unverified")
            if exit_date is None:
                reasons.append("missing_next_stock_session")
            elif adjusted_abs is None:
                reasons.append("invalid_adjusted_stock_close")
            legs = event_contracts[event_contracts["bucket"] == bucket]
            pair = {}
            for code in ("C_K", "P_K"):
                matches = legs[legs["leg_code"] == code]
                if len(matches) == 1:
                    pair[code] = matches.iloc[0]
            terms_ok = len(pair) == 2
            if terms_ok:
                call, put = pair["C_K"], pair["P_K"]
                terms_ok = (str(call["contract_type"]) == "call"
                            and str(put["contract_type"]) == "put"
                            and str(call["selection_date"]) == str(event["t_pre"])
                            and str(put["selection_date"]) == str(event["t_pre"])
                            and str(call["expiration_date"]) == str(put["expiration_date"])
                            and exit_date is not None
                            and str(call["expiration_date"]) > exit_date
                            and _finite(call["strike"]) and _finite(put["strike"])
                            and float(call["strike"]) == float(put["strike"])
                            and _finite(call["shares_per_contract"])
                            and _finite(put["shares_per_contract"])
                            and float(call["shares_per_contract"]) == 100
                            and float(put["shares_per_contract"]) == 100)
            if not terms_ok:
                reasons.append("missing_or_inconsistent_atm_pair_terms")
            entry_mid = exit_mid = None
            if terms_ok:
                values = {}
                for code, leg in pair.items():
                    symbol = str(leg["contract_ticker"])
                    for session, label in ((entry, "entry"), (exit_date, "exit")):
                        values[(code, label)] = _quote_mid(quote_by_key.get((symbol, session)), session)
                if any(values[(code, "entry")] is None for code in pair):
                    reasons.append("invalid_entry_quote")
                else:
                    entry_mid = sum(values[(code, "entry")] for code in pair)
                if any(values[(code, "exit")] is None for code in pair):
                    reasons.append("invalid_exit_quote")
                else:
                    exit_mid = sum(values[(code, "exit")] for code in pair)
            paired = (chronology_ok and adjusted_abs is not None
                      and entry_mid is not None and exit_mid is not None)
            prediction = forecast_by_key.get((ticker, entry))
            if prediction is None:
                reasons.append("no_clock_qualified_movement_forecast")
            rows.append(dict(event_id=event_id, ticker=ticker, bucket=bucket,
                             decision_date=entry, exit_date=exit_date, score_depth=score,
                             prediction=prediction, status="descriptive_mark_pair" if paired else "incomplete_mark_pair",
                             abstention_reason=";".join(dict.fromkeys(reasons)) or "forecast_timing_unverified",
                             target_observed=adjusted_abs is not None,
                             adjusted_abs_log_return=adjusted_abs,
                             native_close_entry=native_close_entry,
                             unadjusted_spot_entry=None,
                             straddle_mid_entry=entry_mid, straddle_mid_exit=exit_mid,
                             straddle_mid_change=(exit_mid-entry_mid if paired else None),
                             option_premium_status="blocked",
                             pricing_blockers="no_verified_quote_update_freshness;underlying_not_synchronized;rates_dividends_exercise_and_lifecycle_unverified;no_executable_fills"))
    return pd.DataFrame(rows)


def summarize_audit(rows: pd.DataFrame, matched_summary: dict | None = None) -> dict:
    descriptive = rows[rows["status"] == "descriptive_mark_pair"]
    n = int(descriptive["event_id"].nunique())
    reasons: dict[str, int] = {}
    if "abstention_reason" in rows:
        for reason_list in rows["abstention_reason"].dropna().astype(str):
            for reason in reason_list.split(";"):
                if reason:
                    reasons[reason] = reasons.get(reason, 0) + 1
    source_n = None
    if matched_summary is not None:
        source_n = matched_summary.get("coverage", {}).get("primary_distinct_event_ids")
        if not isinstance(source_n, int):
            raise ValueError("matched summary lacks original primary distinct event count")
    gate_n = n if source_n is None else min(n, source_n)
    association_status = "inconclusive" if gate_n < MIN_DISTINCT_EVENTS else "exploratory_descriptive"
    return {"status": association_status, "attempted_rows": int(len(rows)),
            "attempted_distinct_events": int(rows["event_id"].nunique()),
            "distinct_descriptive_events": n, "source_primary_distinct_events": source_n,
            "target_observed_rows": int(rows["target_observed"].fillna(False).sum()) if "target_observed" in rows else 0,
            "prediction_rows": int(rows["prediction"].notna().sum()) if "prediction" in rows else 0,
            "abstention_reason_counts": reasons,
            "minimum_distinct_events": MIN_DISTINCT_EVENTS,
            "association_status": association_status,
            "association_reason": "insufficient_independent_events" if gate_n < MIN_DISTINCT_EVENTS else "fixed_selected_contracts_only",
            "option_premium_status": "blocked", "implied_volatility_status": "blocked",
            "economic_profit_claim": False,
            "interpretation": "Selected fixed contracts and sampled close marks; no unbiased chain universe, synchronized surface, executable fills, or untouched holdout."}
