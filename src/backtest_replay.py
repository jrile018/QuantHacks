"""Offline replay of retained selected option legs through the existing study engine."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config, data, implementation, main, risk_management


INPUT_NAMES = ("events.csv", "option_legs.csv", "option_bars.csv")
SOURCE_NAMES = ("src/backtest_replay.py", "src/implementation.py", "src/risk_management.py",
                "src/main.py", "src/capital_liquidity.py", "src/data.py", "src/config.py",
                "requirements.txt", "requirements-notebook-lock.txt", "scripts/reproduce_backtest.py")
ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calendar_hash() -> str:
    dates = "\n".join(data.CAL.strftime("%Y-%m-%d"))
    return hashlib.sha256(dates.encode("ascii")).hexdigest()


def _require_columns(table: pd.DataFrame, required: tuple[str, ...], name: str) -> None:
    missing = set(required) - set(table.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")


def _date_column(table: pd.DataFrame, name: str) -> None:
    try:
        parsed = pd.to_datetime(table[name], format="%Y-%m-%d", errors="raise")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid {name} date") from exc
    if parsed.isna().any():
        raise ValueError(f"missing {name} date")
    table[name] = parsed


def _positive_numbers(table: pd.DataFrame, columns: tuple[str, ...], name: str,
                      *, allow_zero: bool = False) -> None:
    for column in columns:
        try:
            values = pd.to_numeric(table[column], errors="raise")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{name} has invalid {column}") from exc
        if values.isna().any() or not np.isfinite(values).all() or (values < 0 if allow_zero else values <= 0).any():
            raise ValueError(f"{name} has invalid {column}")
        table[column] = values


def _read_snapshot(snapshot_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    settings_path = snapshot_dir / "replay.json"
    if not settings_path.is_file():
        raise ValueError("missing replay.json")
    try:
        receipt = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid replay.json") from exc
    if receipt.get("schema_version") != 1 or receipt.get("provenance", {}).get("kind") not in ("synthetic", "licensed_retained_selected_legs"):
        raise ValueError("unsupported replay schema or provenance")
    hashes = receipt.get("inputs")
    if not isinstance(hashes, dict) or set(hashes) != set(INPUT_NAMES):
        raise ValueError("replay.json must pin the three input SHA256 values")
    for name in INPUT_NAMES:
        path = snapshot_dir / name
        if not path.is_file():
            raise ValueError(f"missing input: {name}")
        expected = hashes[name]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or _sha256(path) != expected:
            raise ValueError(f"input SHA256 mismatch: {name}")
    settings = receipt.get("settings")
    if not isinstance(settings, dict):
        raise ValueError("missing frozen settings")
    frozen = {"horizons": config.HORIZONS, "risk_free": config.RISK_FREE,
              "max_stale_sessions": config.MAX_STALE_SESSIONS,
              "calendar_sha256": _calendar_hash(),
              "calendar_start": data.CAL[0].date().isoformat(),
              "calendar_end": data.CAL[-1].date().isoformat(),
              "baseline_bucket": config.BASELINE_BUCKET, "entry": config.ENTRY}
    for key, current in frozen.items():
        if settings.get(key) != current:
            raise ValueError(f"settings mismatch: {key}")
    if settings.get("otm_pcts") != [0.05]:
        raise ValueError("settings mismatch: otm_pcts must match the selected-leg snapshot")
    for key in ("capital", "risk_fraction", "participation", "cost_haircut"):
        if key not in settings or not isinstance(settings[key], (int, float)) or not np.isfinite(settings[key]):
            raise ValueError(f"invalid frozen setting: {key}")
    if settings["capital"] <= 0 or not 0 < settings["risk_fraction"] <= 1 or not 0 < settings["participation"] <= 1 or not 0 <= settings["cost_haircut"] < 1:
        raise ValueError("invalid frozen sizing settings")
    events = pd.read_csv(snapshot_dir / "events.csv", dtype={"cik": str, "accession_number": str})
    legs = pd.read_csv(snapshot_dir / "option_legs.csv")
    bars = pd.read_csv(snapshot_dir / "option_bars.csv")
    return receipt, events, legs, bars


def _reconstruct(events: pd.DataFrame, legs: pd.DataFrame, bars: pd.DataFrame) -> list[implementation.PricedEvent]:
    _require_columns(events, ("cik", "accession_number", "ticker", "event_date", "t_pre", "t_0"), "events")
    _require_columns(legs, implementation.OPTION_LEG_COLUMNS, "option_legs")
    _require_columns(bars, implementation.OPTION_BAR_COLUMNS, "option_bars")
    if events.empty or legs.empty or bars.empty:
        raise ValueError("snapshot tables must be nonempty")
    for name in ("event_date", "t_pre", "t_0"):
        _date_column(events, name)
    for name in ("expiration_date", "selection_date"):
        _date_column(legs, name)
    _date_column(bars, "session")
    _positive_numbers(legs, ("strike", "spot_pre", "shares_per_contract"), "option_legs")
    _positive_numbers(bars, ("close", "volume"), "option_bars", allow_zero=True)
    if legs.shares_per_contract.ne(100).any():
        raise ValueError("selected legs have unsupported contract multiplier")
    if events[["cik", "accession_number", "ticker"]].isna().any().any() or legs[["contract_ticker", "underlying_ticker", "contract_type", "leg_code"]].isna().any().any():
        raise ValueError("missing event or selected leg identity")
    if bars[["contract_ticker"]].isna().any().any():
        raise ValueError("missing option bar identity")
    if bars.duplicated(["contract_ticker", "session"]).any() or legs.duplicated(["event_id", "bucket", "leg_code"]).any():
        raise ValueError("duplicate selected legs or option bars")
    if not bars.session.isin(data.CAL).all():
        raise ValueError("option bars contain non-calendar sessions")
    event_ids = events.apply(lambda r: f"CIK:{str(r.cik).zfill(10)}:{r.accession_number}:{r.ticker}", axis=1)
    if event_ids.duplicated().any() or set(legs.event_id) != set(event_ids):
        raise ValueError("selected legs do not match event identities")
    bars_by_contract = {ticker: group.sort_values("session").set_index("session")[["close", "volume"]]
                        for ticker, group in bars.groupby("contract_ticker")}
    priced = []
    required = {"C_K", "P_K", "C_U0.05", "P_L0.05"}
    for event_id, event in zip(event_ids, events.itertuples(index=False)):
        if (event.t_pre not in data.CAL or event.t_0 not in data.CAL
                or not event.t_pre < event.event_date < event.t_0
                or event.t_pre != data.session_before(event.event_date)
                or event.t_0 != data.safe_entry_session(event.event_date)):
            raise ValueError("event dates violate the pre/post session rule")
        selected = legs[legs.event_id == event_id]
        for bucket, group in selected.groupby("bucket", sort=True):
            if set(group.leg_code) != required:
                raise ValueError(f"selected legs incomplete or unsupported for {event_id}/{bucket}")
            if bucket not in config.EXPIRY_BUCKETS:
                raise ValueError("selected legs have unknown expiry bucket")
            if group.underlying_ticker.nunique() != 1 or group.underlying_ticker.iloc[0] != event.ticker:
                raise ValueError("selected legs have inconsistent underlying")
            if group.expiration_date.nunique() != 1 or group.selection_date.nunique() != 1 or group.spot_pre.nunique() != 1:
                raise ValueError("selected legs have inconsistent dates or spot")
            expiry, selection = group.expiration_date.iloc[0], group.selection_date.iloc[0]
            if selection != event.t_pre or expiry <= event.t_0 or expiry > data.CAL[-1] or expiry > data.LAST_SESSION:
                raise ValueError("selected legs have invalid selection or unresolved expiry")
            expiry_session = data.CAL[data.CAL.searchsorted(expiry, side="right") - 1]
            strikes = {}
            built = {}
            for leg in group.itertuples(index=False):
                kind, strike_key = (("call", "K") if leg.leg_code == "C_K" else
                                    ("put", "K") if leg.leg_code == "P_K" else
                                    ("call", "U0.05") if leg.leg_code == "C_U0.05" else ("put", "L0.05"))
                if leg.contract_type != kind:
                    raise ValueError("selected legs have incompatible contract type")
                if strike_key in strikes and strikes[strike_key] != leg.strike:
                    raise ValueError("selected legs have inconsistent ATM strike")
                strikes[strike_key] = float(leg.strike)
                if leg.contract_ticker not in bars_by_contract:
                    raise ValueError("selected legs missing option bars")
                contract_bars = bars_by_contract[leg.contract_ticker]
                if contract_bars.index.max() > expiry:
                    raise ValueError("option bar occurs after expiry")
                built[leg.leg_code] = implementation.Leg(leg.contract_ticker, kind, float(leg.strike),
                                                         contract_bars, 100)
            if not strikes["L0.05"] < strikes["K"] < strikes["U0.05"]:
                raise ValueError("selected legs have invalid OTM strikes")
            pe = implementation.PricedEvent(event.ticker, event.event_date, event.t_pre, event.t_0,
                                            bucket, expiry, expiry_session, float(group.spot_pre.iloc[0]),
                                            strikes, built)
            if any(np.isnan(pe.legs[code].mark(day)) for day in (pe.t_pre, pe.t_0) for code in required):
                raise ValueError("selected legs lack valid entry marks")
            priced.append(pe)
    if not priced:
        raise ValueError("no reconstructed priced events")
    return priced


def reproduce(snapshot_dir: Path, output_dir: Path) -> dict:
    """Validate pinned local bytes, then publish a fresh deterministic engineering replay."""
    snapshot_dir, output_dir = Path(snapshot_dir).resolve(), Path(output_dir).resolve()
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    if not snapshot_dir.is_dir():
        raise ValueError(f"missing snapshot directory: {snapshot_dir}")
    if output_dir.is_relative_to(snapshot_dir) or snapshot_dir.is_relative_to(output_dir):
        raise ValueError("snapshot and output directories must be separate")
    receipt, events, legs, bars = _read_snapshot(snapshot_dir)
    priced = _reconstruct(events, legs, bars)
    results = implementation.evaluate(priced, otm_pcts=[0.05])
    if results.empty:
        raise ValueError("replay produced no strategy results")
    board = risk_management.scoreboard(results, bucket=config.BASELINE_BUCKET, entry=config.ENTRY, otm=0.05)
    settings = receipt["settings"]
    capacity = main.capacity_table(priced, settings["capital"], settings["risk_fraction"],
                                   settings["participation"], settings["cost_haircut"],
                                   entry=settings["entry"], otm=0.05)
    source_hashes = {name: _sha256(ROOT / name) for name in SOURCE_NAMES}
    manifest = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "synthetic_engineering_replay" if receipt["provenance"]["kind"] == "synthetic" else "licensed_retained_selected_leg_replay",
                "economic_qualification": "not_established", "provenance": receipt["provenance"],
                "input_sha256": receipt["inputs"], "settings": settings,
                "settings_sha256": _sha256(snapshot_dir / "replay.json"),
                "source_sha256": source_hashes,
                "versions": {"python": sys.version.split()[0], "pandas": pd.__version__,
                             "numpy": np.__version__, "requests": requests.__version__},
                "counts": {"events": len(events), "priced_event_buckets": len(priced),
                           "selected_legs": len(legs), "option_bars": len(bars), "result_rows": len(results)},
                "pnl_basis": "gross unit P&L per $1 synthetic spot; capacity costs shown separately; no portfolio NAV or Sharpe"}
    study = {"events": events, "priced": priced,
             "dropped": pd.DataFrame(columns=["ticker", "t_0", "reason"]),
             "results": results, "board": board}
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".backtest-replay-", dir=output_dir.parent) as stage_name:
        stage = Path(stage_name)
        main.write_outputs(study, capacity, stage, manifest)
        final = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        stage.rename(output_dir)
    return final


def compare_replays(previous_dir: Path, current_dir: Path) -> None:
    """Verify both manifests and scientific table hashes, ignoring run timestamp and location."""
    manifests = []
    for directory in (Path(previous_dir), Path(current_dir)):
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"missing replay manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        exported = manifest.get("exported_tables", {})
        if not exported:
            raise ValueError("missing exported table hashes")
        for name, record in exported.items():
            table_path = directory / f"{name}.csv"
            if not table_path.is_file() or _sha256(table_path) != record.get("sha256"):
                raise ValueError(f"output SHA256 mismatch: {table_path}")
        manifests.append({k: v for k, v in manifest.items() if k != "generated_at_utc"})
    if manifests[0] != manifests[1]:
        raise ValueError("replay manifests or scientific table SHA256 values differ")
