"""Build point in time estimates of baby shelf capacity."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


SOURCE = [
    "cik", "date", "fin_mktcap_m", "fin_float_m", "fin_liq_m",
    "fin_burn_q_m", "fin_stockproc_ttm_m", "fil_s3_n365",
    "fil_p424b_n365",
]


def missing_from(out, values, *codes):
    """Use the largest input reason, or 7 when all inputs have code 0."""
    bad = values.isna().to_numpy()
    if not bad.any():
        return
    worst = np.maximum.reduce([c.to_numpy(dtype=np.int8) for c in codes])
    out[bad] = np.where(worst[bad] == 0, 7, worst[bad])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    folder = args.data / "fds"
    x = pd.read_csv(folder / "fds_features.csv", usecols=SOURCE)
    m = pd.read_csv(folder / "fds_missing.csv", usecols=SOURCE)
    assert x[["cik", "date"]].equals(m[["cik", "date"]]), "Missing codes do not align"
    assert not x.duplicated(["cik", "date"]).any(), "Duplicate input key"
    assert x[["cik", "date"]].equals(x.sort_values(["cik", "date"])[["cik", "date"]].reset_index(drop=True)), "Input must be sorted"

    out = x[["cik", "date"]].copy()
    reasons = out.copy()
    group = x.groupby("cik", sort=False)
    cap = group["fin_mktcap_m"].transform(lambda s: s.rolling(60, min_periods=20).max())
    out["sh_float_hi60_m"] = cap
    code = np.zeros(len(x), dtype=np.int8)
    insufficient = cap.isna().to_numpy()
    rolling_n = group["fin_mktcap_m"].transform(lambda s: s.rolling(60, min_periods=1).count()).to_numpy()
    assert (rolling_n[insufficient] < 20).all()
    code[insufficient] = 4
    reasons["sh_float_hi60_m"] = code

    baby = pd.Series(np.where(cap.notna(), (cap < 75).astype(float), np.nan), index=x.index)
    out["sh_baby"] = baby
    code = np.zeros(len(x), dtype=np.int8)
    missing_from(code, baby, reasons.sh_float_hi60_m)
    reasons["sh_baby"] = code

    with np.errstate(divide="ignore", invalid="ignore"):
        distance = np.log(cap.where(cap > 0) / 75)
    out["sh_dist_to_75"] = distance
    code = np.zeros(len(x), dtype=np.int8)
    missing_from(code, distance, reasons.sh_float_hi60_m)
    reasons["sh_dist_to_75"] = code

    is_baby = baby.eq(1)
    not_baby = baby.eq(0)
    shelf_cap = (cap / 3).where(is_baby)
    out["sh_cap_12m_m"] = shelf_cap
    code = np.where(not_baby, 6, 0).astype(np.int8)
    missing_from(code, shelf_cap, reasons.sh_baby)
    code[not_baby.to_numpy()] = 6
    reasons["sh_cap_12m_m"] = code

    used = x.fin_stockproc_ttm_m.clip(lower=0)
    out["sh_used_12m_m"] = used
    code = np.zeros(len(x), dtype=np.int8)
    missing_from(code, used, m.fin_stockproc_ttm_m)
    reasons["sh_used_12m_m"] = code

    room = (shelf_cap - used).clip(lower=0).where(is_baby)
    out["sh_room_m"] = room
    code = np.where(not_baby, 6, 0).astype(np.int8)
    missing_from(code, room, reasons.sh_cap_12m_m, reasons.sh_used_12m_m)
    code[not_baby.to_numpy()] = 6
    reasons["sh_room_m"] = code

    positive_cash_flow = x.fin_burn_q_m.isna() & m.fin_burn_q_m.eq(6)
    burn = x.fin_burn_q_m.mask(positive_cash_flow, 0)
    need = (4 * burn - x.fin_liq_m).clip(lower=0)
    out["sh_need_12m_m"] = need
    code = np.where(positive_cash_flow & need.notna(), 6, 0).astype(np.int8)
    missing_from(code, need, m.fin_burn_q_m, m.fin_liq_m)
    reasons["sh_need_12m_m"] = code

    eligible = is_baby & need.gt(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = (room / need).where(eligible).clip(0, 20)
        to_mcap = (room / x.fin_mktcap_m.where(x.fin_mktcap_m > 0)).where(is_baby)
    out["sh_room_to_need"] = ratio
    code = np.where(not_baby | (is_baby & need.eq(0)), 6, 0).astype(np.int8)
    missing_from(code, ratio, reasons.sh_room_m, reasons.sh_need_12m_m, reasons.sh_baby)
    code[(not_baby | (is_baby & need.eq(0))).to_numpy()] = 6
    reasons["sh_room_to_need"] = code
    out["sh_room_to_mcap"] = to_mcap
    code = np.where(not_baby, 6, 0).astype(np.int8)
    missing_from(code, to_mcap, reasons.sh_room_m, m.fin_mktcap_m, reasons.sh_baby)
    code[not_baby.to_numpy()] = 6
    reasons["sh_room_to_mcap"] = code

    out["sh_squeeze"] = (eligible & room.lt(need)).astype(np.int8)
    out["sh_has_s3"] = x.fil_s3_n365.gt(0).astype(np.int8)
    out["sh_has_424b"] = x.fil_p424b_n365.gt(0).astype(np.int8)
    for name in ("sh_squeeze", "sh_has_s3", "sh_has_424b"):
        reasons[name] = np.zeros(len(x), dtype=np.int8)

    with np.errstate(divide="ignore", invalid="ignore"):
        raw_ratio = x.fin_float_m / x.fin_mktcap_m.where(x.fin_mktcap_m > 0)
    valid_ratio = raw_ratio.between(0.05, 1.2)
    out["sh_float_ratio"] = raw_ratio.where(valid_ratio)
    code = np.where(~valid_ratio, 5, 0).astype(np.int8)
    missing_from(code, out.sh_float_ratio, m.fin_float_m, m.fin_mktcap_m)
    code[(~valid_ratio & raw_ratio.notna()).to_numpy()] = 5
    reasons["sh_float_ratio"] = code

    months = baby.groupby(x.cik, sort=False).transform(lambda s: s.rolling(252, min_periods=60).sum())
    out["sh_months_baby"] = months
    code = np.zeros(len(x), dtype=np.int8)
    bad = months.isna().to_numpy()
    code[bad] = 4
    enough_rows = x.groupby("cik", sort=False).cumcount().to_numpy() >= 59
    prior_code = reasons.sh_baby.groupby(x.cik, sort=False).transform(lambda s: s.rolling(252, min_periods=1).max()).fillna(0).to_numpy(dtype=np.int8)
    code[bad & enough_rows] = np.where(prior_code[bad & enough_rows] == 0, 7, prior_code[bad & enough_rows])
    reasons["sh_months_baby"] = code

    assert len(out) == len(x) and len(reasons) == len(x), "Row count changed"
    assert not out.duplicated(["cik", "date"]).any(), "Duplicate output key"
    assert np.isfinite(out.drop(columns=["cik", "date"]).to_numpy(dtype=float)[out.drop(columns=["cik", "date"]).notna().to_numpy()]).all(), "Infinite output"

    positions = {cik: positions.to_numpy() for cik, positions in x.groupby("cik", sort=False).groups.items()}
    rng = np.random.default_rng(0)

    def slow_hi(row):
        company = positions[x.at[row, "cik"]]
        earlier = company[company <= row]
        vals = x.fin_mktcap_m.iloc[earlier[-60:]].dropna()
        return vals.max() if len(vals) >= 20 else np.nan

    sample = rng.choice(len(x), size=300, replace=False)
    diffs = []
    for row in sample:
        expected = slow_hi(int(row))
        actual = cap.iloc[row]
        assert (pd.isna(expected) and pd.isna(actual)) or abs(expected - actual) < 1e-6, "Independent rolling check failed"
        if not pd.isna(expected):
            diffs.append(abs(expected - actual))
    print(f"Independent 300-row check: max absolute difference {max(diffs, default=0):.6g}")

    sample = rng.choice(len(x), size=200, replace=False)
    for row in sample:
        row = int(row)
        company = positions[x.at[row, "cik"]]
        cut = company[company <= row]
        truncated = x.fin_mktcap_m.iloc[cut]
        after_deletion = truncated.rolling(60, min_periods=20).max().iloc[-1]
        actual = cap.iloc[row]
        assert (pd.isna(after_deletion) and pd.isna(actual)) or abs(after_deletion - actual) < 1e-6, "Look-ahead check failed"
    print("Look-ahead 200-row deletion check: passed")

    descriptions = [
        ("sh_float_hi60_m", "USD millions", "Highest market cap in the last 60 company rows, an upper bound on float under the baby shelf rule because affiliate holdings are assumed to be zero."),
        ("sh_baby", "flag", "One when the estimated upper bound on float is below the baby shelf rule threshold of 75 million dollars."),
        ("sh_dist_to_75", "log ratio", "Log of the estimated upper bound on float divided by the baby shelf rule threshold of 75 million dollars."),
        ("sh_cap_12m_m", "USD millions", "One third of the estimated upper bound on float for companies inside the baby shelf rule."),
        ("sh_used_12m_m", "USD millions", "Nonnegative common stock proceeds over 12 months used as a rough measure of baby shelf rule capacity already used."),
        ("sh_room_m", "USD millions", "Estimated remaining baby shelf rule capacity after rough prior stock proceeds are removed."),
        ("sh_need_12m_m", "USD millions", "Cash gap over 12 months based on four quarters of burn less current liquidity."),
        ("sh_room_to_need", "ratio", "Estimated baby shelf rule room divided by the cash gap, clipped from zero to 20."),
        ("sh_room_to_mcap", "ratio", "Estimated baby shelf rule room divided by current market cap."),
        ("sh_squeeze", "flag", "One when the baby shelf rule room is smaller than the positive cash gap."),
        ("sh_has_s3", "flag", "One when an S-3 filing occurred in the last 365 days."),
        ("sh_has_424b", "flag", "One when a 424B prospectus filing occurred in the last 365 days."),
        ("sh_float_ratio", "ratio", "Reported public float divided by market cap when the ratio is between 0.05 and 1.2."),
        ("sh_months_baby", "market days", "Number of the last 252 company rows inside the estimated baby shelf rule zone."),
    ]
    dictionary = pd.DataFrame([(name, "shelf", unit, desc) for name, unit, desc in descriptions], columns=["column", "block", "unit", "description"])
    assert list(out.columns[2:]) == dictionary.column.tolist(), "Dictionary does not match output"
    assert reasons.columns.tolist() == out.columns.tolist(), "Missing codes do not match output"
    assert reasons.iloc[:, 2:].isin(range(8)).all().all(), "Invalid missing code"
    out.to_csv(folder / "fds_shelf.csv", index=False, float_format="%.6g")
    reasons.to_csv(folder / "fds_shelf_missing.csv", index=False)
    dictionary.to_csv(folder / "fds_shelf_dictionary.csv", index=False)

    print(f"Rows: {len(out):,}; unique keys: {len(out):,}; infinite values: 0")
    print("Coverage:")
    print(out.iloc[:, 2:].notna().mean().to_string(float_format=lambda v: f"{v:.4f}"))
    print("Baby shelf share by year:")
    years = out.date.astype(str).str[:4]
    print(out.sh_baby.eq(1).groupby(years).mean().to_string(float_format=lambda v: f"{v:.4f}"))
    print("Main columns:")
    print(out[["sh_float_hi60_m", "sh_cap_12m_m", "sh_room_m", "sh_need_12m_m", "sh_room_to_need", "sh_squeeze"]].describe().to_string(float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
