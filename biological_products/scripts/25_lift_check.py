"""Compare added feature blocks with a walk forward offering model."""

import argparse
import os
from pathlib import Path

os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score


SETTINGS = dict(max_depth=3, learning_rate=0.05, max_iter=200,
                min_samples_leaf=200, l2_regularization=5.0, random_state=0)
TARGET = "y_8k_next5_offer"


def auc(y, p):
    return roc_auc_score(y, p) if np.unique(y).size == 2 else np.nan


def traded_slice(frame, probability):
    liquid = frame.loc[(frame.px_adv20_usd_m >= 1) & (frame.px_close_real >= 1),
                       ["date", "cik", TARGET]].copy()
    liquid["probability"] = probability.loc[liquid.index].to_numpy()
    liquid = liquid.sort_values(["date", "probability", "cik"], ascending=[True, False, True])
    rank = liquid.groupby("date", sort=False).cumcount()
    daily_size = liquid.groupby("date", sort=False)["cik"].transform("size")
    selected = liquid.loc[rank < np.ceil(daily_size * 0.02)]
    base = liquid[TARGET].mean()
    precision = selected[TARGET].mean()
    return precision, precision / base if base > 0 else np.nan, len(selected), base


class ExtraOnlyView:
    """Keep baseline columns fixed while permuting added columns."""

    def __init__(self, model, fixed, base_cols, extra_cols):
        self.model = model
        self.fixed = fixed
        self.base_cols = base_cols
        self.extra_cols = extra_cols

    def fit(self, extra, y=None):
        return self

    def predict_proba(self, extra):
        full = self.fixed.copy()
        for col in self.extra_cols:
            full[col] = extra[col].to_numpy()
        return self.model.predict_proba(full[self.base_cols + self.extra_cols])


def resolve_extra(value, folder):
    if value.endswith(".csv") or "/" in value or "\\" in value:
        path = Path(value)
        if not path.exists():
            path = folder / path.name
    else:
        path = folder / f"fds_{value}.csv"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--extra", nargs="+", required=True, help="Block names or CSV paths")
    args = parser.parse_args()
    folder = args.data / "fds"
    paths = [resolve_extra(value, folder) for value in args.extra]
    names = [p.stem.removeprefix("fds_") for p in paths]
    output_name = "_".join(names)

    features = pd.read_csv(folder / "fds_features.csv")
    options = pd.read_csv(folder / "fds_options.csv")
    labels = pd.read_csv(folder / "fds_labels.csv", usecols=["cik", "date", TARGET])
    assert not features.duplicated(["cik", "date"]).any()
    assert not options.duplicated(["cik", "date"]).any()
    assert not labels.duplicated(["cik", "date"]).any()
    base_cols = [c for c in features.columns if c not in ("cik", "date")]
    base_cols += [c for c in options.columns if c not in ("cik", "date")]
    assert len(base_cols) == len(set(base_cols)), "Baseline column collision"
    data = features.merge(options, on=["cik", "date"], how="left", validate="one_to_one")
    data = data.merge(labels, on=["cik", "date"], how="left", validate="one_to_one")
    data = data.loc[data[TARGET].notna()].copy()

    extra_cols = []
    for path in paths:
        extra = pd.read_csv(path)
        assert {"cik", "date"}.issubset(extra.columns), f"Missing keys in {path}"
        assert not extra.duplicated(["cik", "date"]).any(), f"Duplicate keys in {path}"
        cols = [c for c in extra.columns if c not in ("cik", "date")]
        assert not set(cols).intersection(base_cols + extra_cols), f"Column collision in {path}"
        extra_cols.extend(cols)
        data = data.merge(extra, on=["cik", "date"], how="left", validate="one_to_one")
    assert extra_cols, "No added features"
    all_cols = base_cols + extra_cols
    data = data.replace([np.inf, -np.inf], np.nan).copy()
    data["d"] = pd.to_datetime(data.date.astype(str), format="%Y%m%d")
    data = data.sort_values(["d", "cik"]).reset_index(drop=True)
    pred_base = pd.Series(np.nan, index=data.index)
    pred_extra = pd.Series(np.nan, index=data.index)
    quarterly = []
    importance_jobs = []
    quarters = pd.period_range("2025Q1", "2026Q3", freq="Q")

    print(f"Rows with labels: {len(data):,}; baseline columns: {len(base_cols)}; added columns: {len(extra_cols)}")
    print("Quarter | train | test | baseline AUC | extended AUC | baseline slice precision | extended slice precision | baseline lift | extended lift | baseline slice rows | extended slice rows")
    for quarter in quarters:
        start, end = quarter.start_time, quarter.end_time
        train = data.d < start - pd.Timedelta(days=7)
        test = (data.d >= start) & (data.d <= end)
        if not test.any() or train.sum() < 5000:
            continue
        y_train = data.loc[train, TARGET].astype(np.int8)
        y_test = data.loc[test, TARGET].astype(np.int8)
        baseline = HistGradientBoostingClassifier(**SETTINGS)
        extended = HistGradientBoostingClassifier(**SETTINGS)
        baseline.fit(data.loc[train, base_cols], y_train)
        extended.fit(data.loc[train, all_cols], y_train)
        pred_base.loc[test] = baseline.predict_proba(data.loc[test, base_cols])[:, 1]
        pred_extra.loc[test] = extended.predict_proba(data.loc[test, all_cols])[:, 1]
        b_auc = auc(y_test, pred_base.loc[test])
        e_auc = auc(y_test, pred_extra.loc[test])
        b_precision, b_lift, b_n, _ = traded_slice(data.loc[test], pred_base)
        e_precision, e_lift, e_n, _ = traded_slice(data.loc[test], pred_extra)
        quarterly.append(dict(quarter=str(quarter), train_rows=int(train.sum()), test_rows=int(test.sum()),
                              baseline_auc=b_auc, extended_auc=e_auc,
                              baseline_slice_precision=b_precision, extended_slice_precision=e_precision,
                              baseline_lift=b_lift, extended_lift=e_lift,
                              baseline_slice_rows=b_n, extended_slice_rows=e_n))
        print(f"{quarter} | {train.sum():,} | {test.sum():,} | {b_auc:.4f} | {e_auc:.4f} | {b_precision:.4f} | {e_precision:.4f} | {b_lift:.3f} | {e_lift:.3f} | {b_n} | {e_n}")
        if quarter in quarters[-2:]:
            importance_jobs.append((str(quarter), extended, data.loc[test, all_cols].copy(), y_test.copy()))

    tested = pred_base.notna() & pred_extra.notna()
    y = data.loc[tested, TARGET].astype(np.int8)
    b_pooled = auc(y, pred_base.loc[tested])
    e_pooled = auc(y, pred_extra.loc[tested])
    b_precision, b_lift, b_n, liquid_base = traded_slice(data.loc[tested], pred_base)
    e_precision, e_lift, e_n, _ = traded_slice(data.loc[tested], pred_extra)
    print(f"Pooled AUC: baseline {b_pooled:.4f}; extended {e_pooled:.4f}; difference {e_pooled - b_pooled:+.4f}")
    print(f"Liquid base rate: {liquid_base:.4f}")
    print(f"Traded slice: baseline precision {b_precision:.4f}, lift {b_lift:.3f}, rows {b_n}; extended precision {e_precision:.4f}, lift {e_lift:.3f}, rows {e_n}")

    test_frame = data.loc[tested, ["date", TARGET]].copy()
    test_frame["baseline"] = pred_base.loc[tested].to_numpy()
    test_frame["extended"] = pred_extra.loc[tested].to_numpy()
    test_frame = test_frame.reset_index(drop=True)
    day_groups = [np.flatnonzero(test_frame.date.to_numpy() == date) for date in test_frame.date.unique()]
    yy = test_frame[TARGET].to_numpy(dtype=np.int8)
    bb = test_frame.baseline.to_numpy()
    ee = test_frame.extended.to_numpy()
    rng = np.random.default_rng(0)
    differences = []
    for _ in range(500):
        picked = rng.integers(len(day_groups), size=len(day_groups))
        rows = np.concatenate([day_groups[i] for i in picked])
        if np.unique(yy[rows]).size == 2:
            differences.append(auc(yy[rows], ee[rows]) - auc(yy[rows], bb[rows]))
    low, high = np.percentile(differences, [5, 95])
    print(f"Date bootstrap, 500 resamples: 90% interval for extended minus baseline pooled AUC [{low:+.4f}, {high:+.4f}]")

    rng = np.random.default_rng(0)
    importance = []
    for quarter, model, X_test, y_test in importance_jobs:
        if len(X_test) > 10000:
            take = np.sort(rng.choice(len(X_test), size=10000, replace=False))
            X_test, y_test = X_test.iloc[take], y_test.iloc[take]
        view = ExtraOnlyView(model, X_test, base_cols, extra_cols)
        result = permutation_importance(view, X_test[extra_cols], y_test,
                                        scoring=lambda est, xx, yy: auc(yy, est.predict_proba(xx)[:, 1]),
                                        n_repeats=3, random_state=0, n_jobs=1)
        importance.append(result.importances_mean)
        print(f"Permutation sample {quarter}: {len(X_test):,} rows")
    if importance:
        scores = pd.Series(np.mean(importance, axis=0), index=extra_cols).sort_values(ascending=False)
        print("Added column permutation importance, mean AUC decrease in last two quarters:")
        print(scores.head(10).to_string(float_format=lambda v: f"{v:+.5f}"))

    destination = folder / f"lift_check_{output_name}.csv"
    pd.DataFrame(quarterly).to_csv(destination, index=False, float_format="%.6g")
    print(f"Saved {destination}")


if __name__ == "__main__":
    main()
