"""Build daily, next-day-usable ClinicalTrials.gov history features.

Input is ct_changes.csv from 27b_ct_changes.py. This script refuses partial
history, existing output files, and failed time safety checks.
"""

import argparse
import bisect
import json
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd


ACTIVE = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"}
COLUMNS = [
    "ch_n_active_known", "ch_n_ph2_known", "ch_n_ph3_known", "ch_n_pc_next90",
    "ch_n_pc_next180", "ch_dsl_next_pc", "ch_n_slip_90", "ch_n_slip_365",
    "ch_slip_days_sum_180", "ch_n_pull_in_90", "ch_share_active_slipped_365",
    "ch_n_status_to_active_not_recruiting_180", "ch_n_status_to_terminated_90",
    "ch_n_suspended_90", "ch_n_withdrawn_90", "ch_n_status_change_30",
    "ch_n_results_posted_90", "ch_n_results_overdue", "ch_n_enroll_change_90",
    "ch_enroll_chg_pct_sum_180", "ch_n_outcome_change_365", "ch_n_site_change_90",
    "ch_n_events_30", "ch_n_events_90", "ch_dsl_any_change", "ch_n_registered_late",
]


def parsed(field, value):
    if pd.isna(value):
        return None
    if field in ("enrollment", "primary_outcomes"):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {} if field == "enrollment" else []
    if field in ("arm_count", "intervention_count", "sites_count"):
        try:
            return int(value)
        except ValueError:
            return 0
    if field == "why_stopped":
        return str(value).lower() == "true"
    return str(value)


def as_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return pd.Timestamp(value + "-01" if len(value) == 7 else value)
    except ValueError:
        return None


def build_index(frame):
    histories = {}
    events_by_ticker = defaultdict(list)
    for nct, group in frame.groupby("nct_id", sort=False):
        group = group.sort_values(["version_date", "version_number"])
        ticker = group.ticker.iloc[0]
        state = {}
        timeline = []
        for (day, version), items in group.groupby(["version_date", "version_number"], sort=True):
            for row in items.itertuples(index=False):
                state[row.state_field] = parsed(row.state_field, row.new_value)
                event = {"nct": nct, "ticker": ticker, "date": pd.Timestamp(str(day)),
                         "kind": row.change_type, "initial": bool(row.initial),
                         "old": parsed(row.state_field, row.old_value),
                         "new": parsed(row.state_field, row.new_value),
                         "days_shifted": pd.to_numeric(row.days_shifted, errors="coerce")}
                events_by_ticker[ticker].append(event)
            timeline.append((pd.Timestamp(str(day)), state.copy()))
        histories[nct] = (ticker, [x[0] for x in timeline], [x[1] for x in timeline])
    by_ticker = defaultdict(list)
    for nct, (ticker, dates, states) in histories.items():
        by_ticker[ticker].append((nct, dates, states))
    for ticker in events_by_ticker:
        events_by_ticker[ticker].sort(key=lambda e: e["date"])
    return by_ticker, events_by_ticker


def compute_row(ticker, day, trials, events):
    current = []
    for nct, dates, states in trials.get(ticker, []):
        pos = bisect.bisect_left(dates, day) - 1
        if pos >= 0:
            state = states[pos]
            if state.get("study_first_posted") and as_date(state["study_first_posted"]) < day:
                current.append((nct, state))
    active = [(nct, s) for nct, s in current if s.get("overall_status") in ACTIVE]
    pcs = [(nct, as_date(s.get("primary_completion"))) for nct, s in active]
    ahead = [d for _, d in pcs if d is not None and d >= day]
    past = [e for e in events.get(ticker, []) if e["date"] < day]
    def recent(days, kind=None, condition=None):
        subset = [e for e in past if e["date"] >= day - timedelta(days=days)
                  and (kind is None or e["kind"] == kind)]
        return [e for e in subset if condition(e)] if condition else subset
    slips_90 = recent(90, "primary_completion_date_change", lambda e: not e["initial"] and pd.notna(e["days_shifted"]) and e["days_shifted"] > 0)
    slips_365 = recent(365, "primary_completion_date_change", lambda e: not e["initial"] and pd.notna(e["days_shifted"]) and e["days_shifted"] > 0)
    enroll_180 = recent(180, "enrollment_change", lambda e: not e["initial"])
    def enrollment_pct(event):
        old, new = event["old"], event["new"]
        if not isinstance(old, dict) or not isinstance(new, dict) or not old.get("count"):
            return 0.0
        return (new.get("count", 0) - old["count"]) / old["count"]
    first_late = 0
    overdue = 0
    for _, state in current:
        first, start = as_date(state.get("study_first_posted")), as_date(state.get("start"))
        first_late += int(first is not None and start is not None and (first - start).days > 90)
        pc = as_date(state.get("primary_completion"))
        results = as_date(state.get("results_first_posted"))
        overdue += int(pc is not None and pc < day - timedelta(days=365) and (results is None or results >= day))
    val = {
        "ch_n_active_known": len(active),
        "ch_n_ph2_known": sum("PHASE2" in s.get("phase", "") for _, s in active),
        "ch_n_ph3_known": sum("PHASE3" in s.get("phase", "") for _, s in active),
        "ch_n_pc_next90": sum((d - day).days <= 90 for d in ahead),
        "ch_n_pc_next180": sum((d - day).days <= 180 for d in ahead),
        "ch_dsl_next_pc": min(((d - day).days for d in ahead), default=np.nan),
        "ch_n_slip_90": len({e["nct"] for e in slips_90}),
        "ch_n_slip_365": len({e["nct"] for e in slips_365}),
        "ch_slip_days_sum_180": sum(e["days_shifted"] for e in recent(180, "primary_completion_date_change") if not e["initial"] and pd.notna(e["days_shifted"]) and e["days_shifted"] > 0),
        "ch_n_pull_in_90": len({e["nct"] for e in recent(90, "primary_completion_date_change") if not e["initial"] and pd.notna(e["days_shifted"]) and e["days_shifted"] < 0}),
        "ch_share_active_slipped_365": len({e["nct"] for e in slips_365} & {n for n, _ in active}) / len(active) if active else np.nan,
        "ch_n_status_to_active_not_recruiting_180": len(recent(180, "status_change", lambda e: not e["initial"] and e["new"] == "ACTIVE_NOT_RECRUITING")),
        "ch_n_status_to_terminated_90": len(recent(90, "status_change", lambda e: not e["initial"] and e["new"] == "TERMINATED")),
        "ch_n_suspended_90": len(recent(90, "status_change", lambda e: not e["initial"] and e["new"] == "SUSPENDED")),
        "ch_n_withdrawn_90": len(recent(90, "status_change", lambda e: not e["initial"] and e["new"] == "WITHDRAWN")),
        "ch_n_status_change_30": len(recent(30, "status_change", lambda e: not e["initial"])),
        "ch_n_results_posted_90": len(recent(90, "results_first_posted", lambda e: not e["initial"] and bool(e["new"]))),
        "ch_n_results_overdue": overdue,
        "ch_n_enroll_change_90": len(recent(90, "enrollment_change", lambda e: not e["initial"])),
        "ch_enroll_chg_pct_sum_180": sum(enrollment_pct(e) for e in enroll_180),
        "ch_n_outcome_change_365": len(recent(365, "primary_outcome_change", lambda e: not e["initial"])),
        "ch_n_site_change_90": len(recent(90, "sites_count_change", lambda e: not e["initial"])),
        "ch_n_events_30": len(recent(30, condition=lambda e: not e["initial"])),
        "ch_n_events_90": len(recent(90, condition=lambda e: not e["initial"])),
        "ch_dsl_any_change": (day - past[-1]["date"]).days if past else np.nan,
        "ch_n_registered_late": first_late,
    }
    return val


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    fds = args.data / "fds"
    paths = [fds / "fds_trialhist.csv", fds / "fds_trialhist_missing.csv", fds / "fds_trialhist_dictionary.csv"]
    if any(path.exists() for path in paths):
        raise SystemExit("Refusing to edit an existing output file")
    raw = pd.read_csv(args.data / "raw" / "ct_changes.csv", keep_default_na=False)
    base = pd.read_csv(fds / "fds_features.csv", usecols=["cik", "date"])
    lookup = pd.read_csv(fds / "fds_lookup_cik_ticker.csv")
    c2t = dict(zip(lookup.cik.astype(int), lookup.ticker.astype(str)))
    trials, events = build_index(raw)
    rows = []
    for row in base.itertuples(index=False):
        day = pd.Timestamp(str(int(row.date)))
        rows.append(compute_row(c2t.get(int(row.cik)), day, trials, events))
    out = pd.concat([base, pd.DataFrame(rows, columns=COLUMNS)], axis=1)
    assert len(out) == len(base) and out[["cik", "date"]].equals(base)
    assert not out.duplicated(["cik", "date"]).any()
    assert np.isfinite(out[COLUMNS].to_numpy(dtype=float)[~out[COLUMNS].isna().to_numpy()]).all()
    print(f"Rows and unique keys match fds_features.csv: {len(out)}")
    print("No infinite feature values: true")
    rng = np.random.default_rng(0)
    mismatch = 0
    for index in rng.choice(len(out), size=300, replace=False):
        row = out.iloc[index]
        column = COLUMNS[int(rng.integers(len(COLUMNS)))]
        ticker = c2t.get(int(row.cik))
        day = pd.Timestamp(str(int(row.date)))
        # Rebuild the index from a direct raw CSV filter for this one company-day.
        sample = raw[(raw.ticker == ticker) & (raw.version_date.astype(int) < int(row.date))]
        slow_trials, slow_events = build_index(sample) if len(sample) else ({}, {})
        expected = compute_row(ticker, day, slow_trials, slow_events)[column]
        got = row[column]
        mismatch += not (pd.isna(expected) and pd.isna(got) or pd.notna(expected) and pd.notna(got) and abs(expected - got) < 1e-8)
    print(f"Independent slow recount mismatches (300 random cells): {mismatch}")
    assert mismatch == 0
    mismatch = 0
    for index in rng.choice(len(out), size=200, replace=False):
        row = out.iloc[index]
        ticker = c2t.get(int(row.cik))
        day = pd.Timestamp(str(int(row.date)))
        clipped = raw[(raw.ticker == ticker) & (raw.version_date.astype(int) < int(row.date))]
        small_trials, small_events = build_index(clipped) if len(clipped) else ({}, {})
        expected = compute_row(ticker, day, small_trials, small_events)
        for column in COLUMNS:
            got, want = row[column], expected[column]
            mismatch += not (pd.isna(got) and pd.isna(want) or pd.notna(got) and pd.notna(want) and abs(got - want) < 1e-8)
    print(f"Delete-future mismatches (200 rows, all columns): {mismatch}")
    assert mismatch == 0
    missing = base.copy()
    for col in COLUMNS:
        missing[col] = np.where(out[col].notna(), 0, 6).astype("int8")
    dictionary = pd.DataFrame([(col, "trial_history", "days" if "dsl" in col else "fraction" if "share" in col or "pct" in col else "count",
                                col.removeprefix("ch_").replace("_", " ") + "; registry versions usable on the calendar day after posting") for col in COLUMNS],
                              columns=["column", "block", "unit", "description"])
    print("Coverage per column:")
    for col in COLUMNS:
        print(f"{col}: {out[col].notna().mean():.3f}")
    print("Audit of 10 random trials:")
    for nct in rng.choice(raw.nct_id.unique(), size=min(10, raw.nct_id.nunique()), replace=False):
        group = raw[raw.nct_id == nct]
        print(f"{nct}: " + "; ".join(f"{date}: {','.join(changes.change_type)}" for date, changes in group.groupby("version_date")))
    out.to_csv(paths[0], index=False, float_format="%.8g")
    missing.to_csv(paths[1], index=False)
    dictionary.to_csv(paths[2], index=False)
    print("Saved " + ", ".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
