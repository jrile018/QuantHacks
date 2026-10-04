"""Command-line entry point for a reproducible 8-K study window."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import requests

from .capital_liquidity import plan_trade
from .config import (BASELINE_BUCKET, COST_HAIRCUT, ENTRY, EVENT_TAG, MAX_VOLUME_PARTICIPATION,
                     OTM_PCT, RISK_FRACTION, STRATEGIES, STUDY_END, STUDY_START)
from .implementation import option_bar_rows, option_leg_rows, run_study


ROOT = Path(__file__).resolve().parents[1]


def hash_sources(paths: list[Path]) -> str:
    """Fingerprint source and dependencies, ignoring platform line endings."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def capacity_table(priced, capital: float, risk_fraction: float, participation: float,
                   cost_haircut: float, entry: str = ENTRY, otm: float = OTM_PCT) -> pd.DataFrame:
    """One sizing row per priced event, expiry bucket, and strategy."""
    rows = []
    for pe in priced:
        day = pe.t_0 if entry == "post" else pe.t_pre
        marks = pe.marks(day)
        spot = pe.synthetic_spot(day, marks)
        volumes = {name: leg.volume_on(day) for name, leg in pe.legs.items()}
        for strategy in STRATEGIES:
            base = {"ticker": pe.ticker, "event_date": pe.event_date, "entry_date": day,
                    "bucket": pe.bucket, "strategy": strategy}
            try:
                row = plan_trade(strategy=strategy, spot=spot, strikes=pe.strikes, marks=marks,
                                 volumes=volumes, capital=capital, risk_fraction=risk_fraction,
                                 participation=participation, cost_haircut=cost_haircut, otm=otm)
                rows.append({**base, **row, "reason": ""})
            except (KeyError, ValueError) as exc:
                rows.append({**base, "reason": str(exc)})
    return pd.DataFrame(rows)


def write_outputs(study: dict, capacity: pd.DataFrame, output_dir: Path, manifest: dict) -> None:
    """Write the study tables and settings needed to reproduce them."""
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = (("events", study["events"]), ("dropped", study["dropped"]),
                        ("results", study["results"]), ("scoreboard", study["board"]),
                        ("capacity", capacity),
                        ("option_legs", option_leg_rows(study["events"], study["priced"])),
                        ("option_bars", option_bar_rows(study["priced"])))
    exported = {}
    for name, table in tables:
        path = output_dir / f"{name}.csv"
        table.to_csv(path, index=False)
        exported[name] = {"rows": len(table), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {**manifest, "exported_tables": exported}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the modular Massive 8-K options study")
    parser.add_argument("--tag", default=EVENT_TAG, help="exact tertiary disclosure category")
    parser.add_argument("--start", default=STUDY_START, help="filing window start (YYYY-MM-DD)")
    parser.add_argument("--end", default=STUDY_END, help="filing window end (YYYY-MM-DD)")
    parser.add_argument("--max-events", type=int, default=None, help="small smoke run when testing access")
    parser.add_argument("--capital", type=float, default=100_000, help="available cash for one event")
    parser.add_argument("--risk-fraction", type=float, default=RISK_FRACTION)
    parser.add_argument("--participation", type=float, default=MAX_VOLUME_PARTICIPATION)
    parser.add_argument("--cost-haircut", type=float, default=COST_HAIRCUT)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if pd.Timestamp(args.start) > pd.Timestamp(args.end):
        print("start must be on or before end", file=sys.stderr)
        return 2
    if args.max_events is not None and args.max_events <= 0:
        print("max-events must be positive", file=sys.stderr)
        return 2
    try:
        study = run_study(args.tag, args.start, args.end, max_events=args.max_events)
        capacity = capacity_table(study["priced"], args.capital, args.risk_fraction,
                                  args.participation, args.cost_haircut)
        manifest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source": "Massive 8-K disclosures and option chains",
                    "source_sha256": hash_sources([ROOT / "run_all.py", ROOT / "requirements.txt",
                                                   *sorted((ROOT / "src").glob("*.py"))]),
                    "python_version": sys.version.split()[0],
                    "pandas_version": pd.__version__, "numpy_version": np.__version__,
                    "requests_version": requests.__version__,
                    "tag": args.tag, "start": args.start, "end": args.end,
                    "max_events": args.max_events, "capital": args.capital,
                    "risk_fraction": args.risk_fraction, "participation": args.participation,
                    "cost_haircut": args.cost_haircut, "entry": ENTRY,
                    "timing_rule": "post=first session strictly after filing_date; pre=last session strictly before filing_date",
                    "otm": OTM_PCT, "baseline_bucket": BASELINE_BUCKET,
                    "event_count": len(study["events"]), "priced_count": len(study["priced"])}
        write_outputs(study, capacity, args.output_dir, manifest)
    except (ValueError, KeyError, RuntimeError) as exc:
        print(f"Study could not run: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote study tables and manifest to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
