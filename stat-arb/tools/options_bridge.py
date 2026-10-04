"""Import a manifested QuantHaxs option study beside Lattice's equity scores.

This is a research-data bridge, not an option pricing or trading stage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Iterator


EVENT_COLUMNS = ("cik", "accession_number", "ticker", "event_date", "t_pre", "t_0")
RESULT_COLUMNS = ("ticker", "event_date", "t_0", "bucket", "entry", "entry_date", "horizon", "otm")
CAPACITY_COLUMNS = ("ticker", "event_date", "entry_date", "bucket", "strategy")
SCORE_COLUMNS = ("date", "ticker", "view", "estimator", "depth", "inside")
ESTIMATORS = ("mahalanobis", "kde", "fastmcd")
SCORE_OUTPUT_COLUMNS = ("score_date",) + tuple(
    name for estimator in ESTIMATORS for name in (f"{estimator}_depth", f"{estimator}_inside")
)


def _read_csv(path: Path, required: tuple[str, ...]) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = set(required) - set(header)
        if missing:
            raise ValueError(f"{path.name} missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"{path.name} has a row with too many fields")
    if any(value is None for row in rows for value in row.values()):
        raise ValueError(f"{path.name} has a row with missing fields")
    return header, rows


def _date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_scores(path: Path) -> Iterator[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = set(SCORE_COLUMNS) - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{path.name} missing columns: {', '.join(sorted(missing))}")
            for row in reader:
                if None in row:
                    raise ValueError(f"{path.name} has a row with too many fields")
                if any(value is None for value in row.values()):
                    raise ValueError(f"{path.name} has a row with missing fields")
                yield row
    elif path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as parquet
        except ImportError as exc:
            raise RuntimeError("Reading Lattice scores.parquet requires pyarrow; install it in the Python environment") from exc
        for batch in parquet.ParquetFile(path).iter_batches(columns=list(SCORE_COLUMNS), batch_size=65536):
            yield from batch.to_pylist()
    else:
        raise ValueError("scores must be a .csv or .parquet file")


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _inside(value: object) -> str:
    normalized = str(value).lower()
    if normalized in ("true", "1"):
        return "1"
    if normalized in ("false", "0"):
        return "0"
    raise ValueError(f"invalid Lattice inside value: {value!r}")


def build_options_artifact(study_dir: Path, output_dir: Path, scores_path: Path | None = None) -> dict:
    """Validate a QuantHaxs run and write event, outcome, capacity, and provenance artifacts."""
    study_dir, output_dir = Path(study_dir), Path(output_dir)
    scores_path = Path(scores_path) if scores_path is not None else None
    source_paths = {name: study_dir / name for name in ("manifest.json", "events.csv", "results.csv", "capacity.csv")}
    for path in source_paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")

    source_manifest = json.loads(source_paths["manifest.json"].read_text(encoding="utf-8"))
    _, source_events = _read_csv(source_paths["events.csv"], EVENT_COLUMNS)
    result_header, source_results = _read_csv(source_paths["results.csv"], RESULT_COLUMNS)
    capacity_header, source_capacity = _read_csv(source_paths["capacity.csv"], CAPACITY_COLUMNS)
    if set(SCORE_OUTPUT_COLUMNS) & set(result_header) or "event_id" in result_header:
        raise ValueError("results.csv has reserved bridge columns")
    if "event_id" in capacity_header:
        raise ValueError("capacity.csv has reserved bridge column event_id")

    events_by_key: dict[tuple[str, str, str], dict] = {}
    events_by_day: dict[tuple[str, str], dict] = {}
    events: list[dict] = []
    for row in source_events:
        ticker = row["ticker"].strip()
        event_date = _date(row["event_date"], "event_date")
        pre = _date(row["t_pre"], "t_pre")
        post = _date(row["t_0"], "t_0")
        if not pre < event_date or not event_date < post:
            raise ValueError(f"event {ticker} has invalid t_pre/event_date/t_0 ordering")
        cik = row["cik"].strip()
        if not cik.isdigit():
            raise ValueError(f"event {ticker} has invalid CIK")
        accession = row["accession_number"].strip()
        if not accession:
            raise ValueError(f"event {ticker} has empty accession_number")
        key = (ticker, row["event_date"], row["t_0"])
        day_key = (ticker, row["event_date"])
        if key in events_by_key or day_key in events_by_day:
            raise ValueError(f"duplicate event: {ticker} {event_date}")
        event = {"event_id": f"CIK:{cik.zfill(10)}:{accession}:{ticker}", "cik": cik.zfill(10),
                 "accession_number": accession, "ticker": ticker, "event_date": row["event_date"],
                 "t_pre": row["t_pre"], "t_0": row["t_0"]}
        events_by_key[key] = event
        events_by_day[day_key] = event
        events.append(event)
    if source_manifest.get("event_count") is not None and source_manifest["event_count"] != len(events):
        raise ValueError("manifest event_count disagrees with events.csv")

    scores: dict[tuple[str, str], dict[str, dict]] = {}
    if scores_path is not None:
        wanted_score_keys = {(event["ticker"], event["t_pre"]) for event in events}
        for row in _read_scores(scores_path):
            if row["view"] != "B":
                continue
            estimator = str(row["estimator"])
            if estimator not in ESTIMATORS:
                continue
            key = (str(row["ticker"]), str(row["date"]))
            if key not in wanted_score_keys:
                continue
            _date(key[1], "score date")
            by_estimator = scores.setdefault(key, {})
            if estimator in by_estimator:
                raise ValueError(f"duplicate score: {key} {estimator}")
            by_estimator[estimator] = row

    outcomes: list[dict] = []
    scored_events: set[str] = set()
    for row in source_results:
        key = (row["ticker"], row["event_date"], row["t_0"])
        event = events_by_key.get(key)
        if event is None:
            raise ValueError(f"result has no matching event: {key}")
        expected_entry = event["t_pre"] if row["entry"] == "pre" else event["t_0"] if row["entry"] == "post" else None
        if row["entry_date"] != expected_entry:
            raise ValueError(f"result has invalid entry_date: {key}")
        score_rows = scores.get((event["ticker"], event["t_pre"]), {})
        added = {"event_id": event["event_id"], "score_date": event["t_pre"] if score_rows else ""}
        for estimator in ESTIMATORS:
            score = score_rows.get(estimator)
            added[f"{estimator}_depth"] = str(score["depth"]) if score and score["depth"] is not None else ""
            added[f"{estimator}_inside"] = _inside(score["inside"]) if score and score["inside"] is not None else ""
        if score_rows:
            scored_events.add(event["event_id"])
        outcomes.append({**row, **added})

    capacity: list[dict] = []
    capacity_entry = source_manifest.get("entry")
    if capacity_entry not in (None, "pre", "post"):
        raise ValueError(f"invalid manifest entry: {capacity_entry!r}")
    for row in source_capacity:
        event = events_by_day.get((row["ticker"], row["event_date"]))
        if event is None:
            raise ValueError(f"capacity row has no matching event: {row['ticker']} {row['event_date']}")
        if capacity_entry:
            allowed_entries = {event["t_pre"] if capacity_entry == "pre" else event["t_0"]}
        else:
            allowed_entries = {event["t_pre"], event["t_0"]}
        if row["entry_date"] not in allowed_entries:
            raise ValueError(f"capacity row has invalid entry_date: {row['ticker']} {row['event_date']}")
        capacity.append({**row, "event_id": event["event_id"]})

    source_hashes = {name: _sha256(path) for name, path in source_paths.items()}
    if scores_path is not None:
        source_hashes["scores"] = _sha256(scores_path)
    summary = {"schema_version": 1, "source": "QuantHaxs manifested Massive 8-K options study",
               "source_tag": source_manifest.get("tag"), "event_rows": len(events), "outcome_rows": len(outcomes),
               "capacity_rows": len(capacity), "scored_events": len(scored_events),
               "score_join": "View B; exact ticker and t_pre session; no forward fill" if scores_path else "not supplied",
               "source_sha256": source_hashes}

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "events.csv", ["event_id", *EVENT_COLUMNS], events)
    _write_csv(output_dir / "outcomes.csv", ["event_id", *result_header, *SCORE_OUTPUT_COLUMNS], outcomes)
    _write_csv(output_dir / "capacity.csv", ["event_id", *capacity_header], capacity)
    (output_dir / "manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True, help="QuantHaxs data/processed/<run> directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="New Lattice runs/<id>/gm-options directory")
    parser.add_argument("--scores", type=Path, help="Optional Lattice gm-boundaries/scores.parquet or CSV export")
    args = parser.parse_args()
    print(json.dumps(build_options_artifact(args.study_dir, args.output_dir, args.scores), indent=2))


if __name__ == "__main__":
    main()
