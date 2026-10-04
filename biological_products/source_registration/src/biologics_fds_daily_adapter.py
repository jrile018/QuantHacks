"""Describe and validate biologics-fds-daily CSV files (headers and keys only).

It does not extract, fetch or interpret values. Keys are cik (int) and
date (int YYYYMMDD).
"""

import csv
from datetime import datetime
from pathlib import Path

SOURCE_ID = "biologics-fds-daily"
ADAPTER_VERSION = "1"
KEYED_FILES = ("fds_features.csv", "fds_missing.csv", "fds_labels.csv")


def describe_csv(path):
    """Return header and row count of a CSV file."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            raise ValueError(f"{path}: empty CSV")
        rows = sum(1 for _ in reader)
    return {"path": str(path), "columns": header, "rows": rows,
            "adapter_version": ADAPTER_VERSION}


def validate_keys(path):
    """Check cik/date columns; return a list of error strings (empty if valid)."""
    errors = []
    seen = set()
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "cik" not in reader.fieldnames or "date" not in reader.fieldnames:
            return [f"{path}: cik and date columns are required"]
        for number, row in enumerate(reader, 2):
            cik, date = row["cik"], row["date"]
            if not cik.isdigit():
                errors.append(f"{path}:{number}: cik must be an integer")
            try:
                if len(date) != 8 or not date.isdigit():
                    raise ValueError
                datetime.strptime(date, "%Y%m%d")
            except ValueError:
                errors.append(f"{path}:{number}: date must be YYYYMMDD")
            if (cik, date) in seen:
                errors.append(f"{path}:{number}: duplicate (cik, date)")
            seen.add((cik, date))
    return errors


def validate_folder(folder):
    """Validate the keyed files present in a folder; missing files are reported."""
    folder = Path(folder)
    errors = []
    for name in KEYED_FILES:
        path = folder / name
        if not path.is_file():
            errors.append(f"{path}: missing")
        else:
            errors.extend(validate_keys(path))
    return errors
