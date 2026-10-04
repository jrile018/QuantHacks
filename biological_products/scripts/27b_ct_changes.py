"""Convert complete cached trial versions into posted-date change events.

Requires all NCT files from 27_pull_ct_history.py. Refuses partial history.
Month-only clinical dates use day 1 only for approximate shift arithmetic.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd


FIELDS = {
    "overall_status": "status_change",
    "primary_completion": "primary_completion_date_change",
    "completion": "completion_date_change",
    "enrollment": "enrollment_change",
    "results_first_posted": "results_first_posted",
    "primary_outcomes": "primary_outcome_change",
    "arm_count": "arm_or_intervention_change",
    "intervention_count": "arm_or_intervention_change",
    "sites_count": "sites_count_change",
    "phase": "phase_change",
    "why_stopped": "why_stopped_added",
    "sponsor": "sponsor_change",
    "start": "start_date_change",
}


def date_value(value):
    return (value or {}).get("date", "")


def state(version):
    study = version.get("study", version)
    p = study.get("protocolSection", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    arms = p.get("armsInterventionsModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {})
    outcomes = p.get("outcomesModule", {})
    primary = outcomes.get("primaryOutcomes") or []
    return {
        "overall_status": status.get("overallStatus", ""),
        "primary_completion": date_value(status.get("primaryCompletionDateStruct")),
        "completion": date_value(status.get("completionDateStruct")),
        "enrollment": design.get("enrollmentInfo") or {},
        "results_first_posted": date_value(status.get("resultsFirstPostDateStruct")),
        "primary_outcomes": primary,
        "arm_count": len(arms.get("armGroups") or []),
        "intervention_count": len(arms.get("interventions") or []),
        "sites_count": len(p.get("contactsLocationsModule", {}).get("locations") or []),
        "phase": ",".join(design.get("phases") or []),
        "why_stopped": bool(status.get("whyStopped")),
        "sponsor": (sponsor.get("leadSponsor") or {}).get("name", ""),
        "start": date_value(status.get("startDateStruct")),
        "study_first_posted": date_value(status.get("studyFirstPostDateStruct")),
        "last_update_posted": date_value(status.get("lastUpdatePostDateStruct")),
    }


def norm_date(value):
    if not value:
        return pd.NaT
    try:
        return pd.Timestamp(value + "-01" if len(value) == 7 else value)
    except ValueError:
        return pd.NaT


def event_row(nct, ticker, number, posted, kind, old, new, field, initial):
    def compact(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    days = None
    if field in ("primary_completion", "completion"):
        before, after = norm_date(old), norm_date(new)
        if pd.notna(before) and pd.notna(after):
            days = (after - before).days
    if field == "primary_outcomes":
        old_items = Counter(json.dumps(item, sort_keys=True) for item in old) if isinstance(old, list) else Counter()
        new_items = Counter(json.dumps(item, sort_keys=True) for item in new) if isinstance(new, list) else Counter()
        added = sum((new_items - old_items).values())
        removed = sum((old_items - new_items).values())
    else:
        added = removed = None
    row = dict(nct_id=nct, ticker=ticker, version_number=number + 1,
               version_date=int(posted.replace("-", "")), change_type=kind,
               state_field=field, old_value=compact(old), new_value=compact(new),
               days_shifted=days, initial=int(initial),
               count_added=added, count_removed=removed)
    if field == "overall_status":
        row["status_code"] = str(new).upper()
    if field == "enrollment":
        row["old_enrollment_type"] = old.get("type", "") if isinstance(old, dict) else ""
        row["new_enrollment_type"] = new.get("type", "") if isinstance(new, dict) else ""
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    trials = pd.read_csv(args.data / "raw" / "trials.csv", usecols=["ticker", "nct_id"])
    if trials.nct_id.duplicated().any():
        raise ValueError("Duplicate NCT ids in trials.csv")
    folder = args.data / "raw" / "ct_history"
    missing = [nct for nct in trials.nct_id if not (folder / f"{nct}.json").exists()]
    if missing:
        raise SystemExit(f"Missing complete history for {len(missing)} studies; first: {missing[:5]}")
    rows = []
    for item in trials.itertuples(index=False):
        payload = json.loads((folder / f"{item.nct_id}.json").read_text(encoding="utf-8"))
        numbers = sorted(int(change["version"]) for change in payload["history"]["changes"])
        if not payload.get("completed_utc") or set(numbers) != {int(x) for x in payload["versions"]}:
            raise SystemExit(f"Partial history for {item.nct_id}")
        prior = None
        for number in numbers:
            current = state(payload["versions"][str(number)])
            posted = current["last_update_posted"] or current["study_first_posted"]
            if not posted:
                raise SystemExit(f"No posted date: {item.nct_id} version {number}")
            if prior is None:
                rows.append(event_row(item.nct_id, item.ticker, number, posted,
                                      "study_first_posted", "", current["study_first_posted"],
                                      "study_first_posted", True))
            for field, kind in FIELDS.items():
                old = prior[field] if prior is not None else ""
                new = current[field]
                if old != new and (prior is not None or new not in ("", {}, [], False, 0)):
                    if field == "why_stopped" and not new:
                        continue
                    rows.append(event_row(item.nct_id, item.ticker, number, posted, kind,
                                          old, new, field, prior is None))
            prior = current
    output = args.data / "raw" / "ct_changes.csv"
    if output.exists():
        raise SystemExit(f"Refusing to edit existing file: {output}")
    frame = pd.DataFrame(rows).sort_values(["nct_id", "version_date", "version_number", "change_type"])
    frame.to_csv(output, index=False)
    print(f"Saved {output}; studies {len(trials)}; events {len(frame)}")
    print(frame.change_type.value_counts().to_string())


if __name__ == "__main__":
    main()
