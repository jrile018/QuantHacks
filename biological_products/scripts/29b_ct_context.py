"""Pre-specified context splits for trial slips and recruiting completion.

Run after 29_ct_event_study.py. Every listed group is printed, including empty
groups. Group definitions use only registry versions posted before usable day.
"""

import argparse
import bisect
import importlib.util
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


GROUPS = {
    "1 runway": ["after cash end", "on or before cash end", "unknown"],
    "2 phase": ["Phase 3 or 2/3", "earlier phase", "unknown"],
    "2 active count": ["one", "two or more", "zero"],
    "3 slip size": ["under 30", "30 to 180", "over 180", "unknown"],
    "4 repeat": ["first", "second or later", "unknown"],
    "5 enrollment edit": ["up", "down", "not changed"],
    "5 outcome edit": ["changed", "not changed"],
    "6 enrollment pace": ["low under 0.8", "high at least 0.8", "unknown"],
}


def load_merge_module():
    path = Path(__file__).resolve().parent / "28_merge_ct_history.py"
    spec = importlib.util.spec_from_file_location("ct_merge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def block_t(frame, column):
    grouped = frame.groupby(["ticker", "month"])[column].mean().dropna().to_numpy()
    if len(grouped) < 2 or grouped.std(ddof=1) == 0:
        return np.nan
    return grouped.mean() / (grouped.std(ddof=1) / math.sqrt(len(grouped)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    raw = args.data / "raw"
    study_path = raw / "ct_event_study.csv"
    if not study_path.exists():
        raise SystemExit("Missing ct_event_study.csv; run 29_ct_event_study.py after the history pull")
    events = pd.read_csv(study_path)
    changes = pd.read_csv(raw / "ct_changes.csv", keep_default_na=False)
    merge = load_merge_module()
    trials, indexed_events = merge.build_index(changes)
    features = pd.read_csv(args.data / "fds" / "fds_features.csv",
                           usecols=["cik", "date", "fin_runway_q", "fin_liq_m"])
    lookup = pd.read_csv(args.data / "fds" / "fds_lookup_cik_ticker.csv")
    t2c = dict(zip(lookup.ticker.astype(str), lookup.cik.astype(int)))
    feature_index = {}
    for cik, group in features.groupby("cik"):
        group = group.sort_values("date")
        feature_index[int(cik)] = (group.date.astype(int).tolist(), group)
    change_index = {(nct, int(ver)): group for (nct, ver), group in changes.groupby(["nct_id", "version_number"])}
    slips = changes[(changes.change_type == "primary_completion_date_change") & (changes.initial.astype(int) == 0)].copy()
    slips["days_shifted"] = pd.to_numeric(slips.days_shifted, errors="coerce")
    slips = slips[slips.days_shifted > 0]
    slip_order = defaultdict(dict)
    for nct, group in slips.sort_values(["version_date", "version_number"]).groupby("nct_id"):
        for number, row in enumerate(group.itertuples(index=False), start=1):
            slip_order[nct][int(row.version_number)] = number
    records = []
    for row in events.itertuples(index=False):
        is_slip = row.event_type == "primary_completion_date_change" and pd.notna(row.days_shifted) and row.days_shifted > 0
        is_active = row.event_type == "status_to_active_not_recruiting"
        if not (is_slip or is_active):
            continue
        usable = pd.Timestamp(row.usable)
        edits = change_index.get((row.nct_id, int(row.version_number)), pd.DataFrame())
        state = None
        for nct, dates, states in trials.get(row.ticker, []):
            if nct == row.nct_id:
                pos = bisect.bisect_left(dates, usable) - 1
                state = states[pos] if pos >= 0 else None
                break
        state = state or {}
        current_pc = merge.as_date(state.get("primary_completion"))
        if is_slip:
            matching = edits[edits.change_type == "primary_completion_date_change"]
            new_pc = merge.as_date(matching.new_value.iloc[0]) if len(matching) else current_pc
        else:
            new_pc = current_pc
        cik = t2c.get(row.ticker)
        keys, group = feature_index.get(cik, ([], None))
        pos = bisect.bisect_right(keys, int(usable.strftime("%Y%m%d"))) - 1
        runway = group.iloc[pos].fin_runway_q if pos >= 0 else np.nan
        liquidity = group.iloc[pos].fin_liq_m if pos >= 0 else np.nan
        if new_pc is None or pd.isna(runway) or pd.isna(liquidity) or liquidity <= 0 or runway < 0:
            cash_group = "unknown"
        else:
            cash_end = usable + pd.Timedelta(days=float(runway) * 91)
            cash_group = "after cash end" if new_pc > cash_end else "on or before cash end"
        phase = state.get("phase", "")
        phase_group = "Phase 3 or 2/3" if "PHASE3" in phase else "earlier phase" if phase else "unknown"
        active_count = merge.compute_row(row.ticker, usable, trials, indexed_events)["ch_n_active_known"]
        active_group = "zero" if active_count == 0 else "one" if active_count == 1 else "two or more"
        shift = row.days_shifted
        slip_group = "under 30" if shift < 30 else "30 to 180" if shift <= 180 else "over 180"
        repeat_number = slip_order[row.nct_id].get(int(row.version_number))
        repeat_group = "first" if repeat_number == 1 else "second or later" if repeat_number else "unknown"
        enrollment = edits[edits.change_type == "enrollment_change"] if len(edits) else pd.DataFrame()
        if len(enrollment):
            old = merge.parsed("enrollment", enrollment.old_value.iloc[0])
            new = merge.parsed("enrollment", enrollment.new_value.iloc[0])
            old_count = old.get("count") if isinstance(old, dict) else None
            new_count = new.get("count") if isinstance(new, dict) else None
            enroll_group = "up" if old_count is not None and new_count is not None and new_count > old_count else "down" if old_count is not None and new_count is not None and new_count < old_count else "not changed"
        else:
            enroll_group = "not changed"
        outcome_group = "changed" if len(edits) and (edits.change_type == "primary_outcome_change").any() else "not changed"
        # Only previously posted actual and estimated values can establish pace.
        previous_enrollment = changes[(changes.nct_id == row.nct_id) &
                                      ((changes.version_date.astype(int) < int(usable.strftime("%Y%m%d")))) &
                                      (changes.change_type == "enrollment_change")].sort_values(["version_date", "version_number"])
        target = actual = None
        for change in previous_enrollment.itertuples(index=False):
            info = merge.parsed("enrollment", change.new_value)
            if isinstance(info, dict) and info.get("count") is not None:
                if info.get("type") == "ESTIMATED":
                    target = info["count"]
                if info.get("type") == "ACTUAL":
                    actual = info["count"]
        pace = actual / target if actual is not None and target and target > 0 else None
        pace_group = "unknown" if pace is None else "low under 0.8" if pace < 0.8 else "high at least 0.8"
        records.append(dict(ticker=row.ticker, nct_id=row.nct_id, event_type="slip" if is_slip else "to active not recruiting",
                            month=row.month, abn5=row.abn5, abn20=row.abn20,
                            **{"1 runway": cash_group, "2 phase": phase_group, "2 active count": active_group,
                               "3 slip size": slip_group if is_slip else "not applicable",
                               "4 repeat": repeat_group if is_slip else "not applicable",
                               "5 enrollment edit": enroll_group, "5 outcome edit": outcome_group,
                               "6 enrollment pace": pace_group}))
    result = pd.DataFrame(records)
    print("Pre-specified context groups. Month-only completion dates use day 1.")
    print("Enrollment pace: last posted ACTUAL count / last posted ESTIMATED count; low is below 0.8. Unknown means both were not available.")
    groups_tested = 0
    for event_type in ("slip", "to active not recruiting"):
        subset = result[result.event_type == event_type] if not result.empty else pd.DataFrame()
        companies = subset.ticker.nunique() if len(subset) else 0
        print(f"EVENT {event_type}: {len(subset)} events, {companies} companies")
        if event_type != "slip" and (len(subset) < 20 or companies < 8):
            print("Status move context groups: too small to read; still printing all pre-specified splits")
        for split, labels in GROUPS.items():
            print(f"SPLIT {split}")
            if event_type != "slip" and split in ("3 slip size", "4 repeat"):
                print("not applicable to a status move")
                continue
            for label in labels:
                group = subset[subset[split] == label] if len(subset) else pd.DataFrame()
                n, firms = len(group), group.ticker.nunique() if len(group) else 0
                if n:
                    groups_tested += 1
                note = "too small to read" if n < 20 or firms < 8 else "readable sample"
                mean5 = group.abn5.mean() if n else np.nan
                mean20 = group.abn20.mean() if n else np.nan
                median5 = group.abn5.median() if n else np.nan
                median20 = group.abn20.median() if n else np.nan
                positive5 = (group.abn5 > 0).mean() if n else np.nan
                positive20 = (group.abn20 > 0).mean() if n else np.nan
                t5 = block_t(group, "abn5") if n else np.nan
                t20 = block_t(group, "abn20") if n else np.nan
                print(f"{label} | n {n} | companies {firms} | mean5 {mean5:+.4f} | median5 {median5:+.4f} | positive5 {positive5:.3f} | t5 {t5:+.2f} | mean20 {mean20:+.4f} | median20 {median20:+.4f} | positive20 {positive20:.3f} | t20 {t20:+.2f} | {note}")
    print(f"Nonempty groups examined: {groups_tested}. A simple Bonferroni screen would use p < {0.05/groups_tested:.4g} rather than 0.05 for each group." if groups_tested else "Nonempty groups examined: 0")


if __name__ == "__main__":
    main()
