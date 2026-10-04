"""Offline research probe for periodic net-return shape and formula diagnostics.

This module accepts caller-supplied observations. It is not a ledger adapter,
an eligibility decision, a calibrated inference method, or a performance report.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence as SequenceABC
from datetime import datetime, timedelta
from decimal import Decimal
from math import isfinite, sqrt
from types import MappingProxyType
from typing import Mapping, Sequence


CONTRACT_VERSION = "offline-net-return-probe-v1"
LIMITATION = "prototype_synthetic_only_diagnostic_only"


@dataclass(frozen=True)
class ProbeResult:
    contract_version: str
    status: str
    n_periods: int
    reasons: tuple[str, ...]
    user_reportable: bool
    ci95: None
    diagnostics: Mapping[str, float | None]
    provenance: Mapping[str, object]


def _freeze(value: object) -> object:
    """Copy caller data so later mutations cannot rewrite this receipt."""
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("provenance keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise ValueError("provenance contains unsupported or nonfinite value")


def _series(value: object) -> bool:
    return isinstance(value, SequenceABC) and not isinstance(value, (str, bytes, bytearray))


def _utc_dates(values: Sequence[object]) -> tuple[list[datetime], bool]:
    parsed: list[datetime] = []
    valid = True
    for value in values:
        if not isinstance(value, str):
            valid = False
            continue
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            valid = False
            continue
        if date.tzinfo is None or date.utcoffset() != timedelta(0):
            valid = False
            continue
        parsed.append(date)
    return parsed, valid


def _numbers(values: Sequence[object]) -> tuple[list[float], bool]:
    numbers: list[float] = []
    valid = True
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            valid = False
            continue
        try:
            number = float(value)
        except (ValueError, OverflowError):
            valid = False
            continue
        if not isfinite(number):
            valid = False
            continue
        numbers.append(number)
    return numbers, valid


def assess_panel(
    timestamps: Sequence[object],
    expected_calendar: Sequence[object],
    net_returns: Sequence[object],
    reference_returns: Sequence[object],
    *,
    reference_kind: str,
    periods_per_year: object,
    provenance: Mapping[str, object],
    marks_complete: object,
    costs_complete: object,
    flows_reconciled: object,
    timing_verified: object,
) -> ProbeResult:
    """Check a supplied panel without promoting it to economic evidence."""
    reasons: list[str] = [LIMITATION, "inference_method_not_implemented", "calibration_pending"]
    supplied = {
        "timestamps": timestamps,
        "expected_calendar": expected_calendar,
        "net_returns": net_returns,
        "reference_returns": reference_returns,
    }
    series: dict[str, Sequence[object]] = {}
    for name, value in supplied.items():
        if _series(value):
            series[name] = value  # type: ignore[assignment]
        else:
            reasons.append("invalid_" + name)
            series[name] = ()
    timestamps = series["timestamps"]
    expected_calendar = series["expected_calendar"]
    net_returns = series["net_returns"]
    reference_returns = series["reference_returns"]
    count = len(net_returns)
    if len({len(timestamps), len(expected_calendar), count, len(reference_returns)}) != 1:
        reasons.append("length_mismatch")

    dates, dates_valid = _utc_dates(timestamps)
    calendar, calendar_valid = _utc_dates(expected_calendar)
    if not dates_valid or not calendar_valid:
        reasons.append("invalid_timestamp")
    if len(dates) != len(set(dates)):
        reasons.append("duplicate_timestamp")
    if any(left >= right for left, right in zip(dates, dates[1:])):
        reasons.append("nonmonotone_timestamp")
    if dates_valid and calendar_valid and dates != calendar:
        reasons.append("calendar_mismatch")
    if calendar_valid and any(left >= right for left, right in zip(calendar, calendar[1:])):
        reasons.append("invalid_expected_calendar")

    returns, returns_valid = _numbers(net_returns)
    reference, reference_valid = _numbers(reference_returns)
    if not returns_valid:
        reasons.append("invalid_net_return")
    if not reference_valid:
        reasons.append("invalid_reference_return")
    if reference_kind not in ("observed_series", "declared_zero"):
        reasons.append("invalid_reference_kind")
    if reference_kind == "declared_zero" and reference_valid and any(value != 0.0 for value in reference):
        reasons.append("declared_zero_mismatch")
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year <= 0:
        reasons.append("invalid_periods_per_year")
    if not isinstance(provenance, Mapping) or not provenance:
        reasons.append("missing_provenance")
        frozen_provenance: Mapping[str, object] = MappingProxyType({})
    else:
        try:
            frozen_provenance = _freeze(provenance)  # type: ignore[assignment]
        except (ValueError, RecursionError):
            reasons.append("invalid_provenance")
            frozen_provenance = MappingProxyType({})
    for name, value in (
        ("marks_complete", marks_complete),
        ("costs_complete", costs_complete),
        ("flows_reconciled", flows_reconciled),
        ("timing_verified", timing_verified),
    ):
        if value is not True:
            reasons.append(name + "_unresolved")
    if count < 2:
        reasons.append("insufficient_periods")
    if returns_valid and any(value <= -1.0 for value in returns):
        reasons.append("bankruptcy_or_ruin")

    diagnostics: dict[str, float | None] = {
        "mean_excess_return": None,
        "sample_variance": None,
        "sample_sd": None,
        "period_sharpe": None,
        "annualized_conventional_sharpe": None,
    }
    structural_reasons = reasons[3:]
    if not structural_reasons:
        try:
            excess = [net - ref for net, ref in zip(returns, reference)]
            if not all(isfinite(value) for value in excess):
                raise ArithmeticError
            mean = sum(excess) / count
            variance = sum((value - mean) ** 2 for value in excess) / (count - 1)
            if not isfinite(mean) or not isfinite(variance):
                raise ArithmeticError
            diagnostics["mean_excess_return"] = mean
            diagnostics["sample_variance"] = variance
            if variance == 0.0:
                reasons.append("undefined_variance")
            else:
                sd = sqrt(variance)
                sharpe = mean / sd
                annualized = sharpe * sqrt(periods_per_year)
                if not all(isfinite(value) for value in (sd, sharpe, annualized)):
                    raise ArithmeticError
                diagnostics["sample_sd"] = sd
                diagnostics["period_sharpe"] = sharpe
                diagnostics["annualized_conventional_sharpe"] = annualized
        except (ArithmeticError, OverflowError, ZeroDivisionError):
            reasons.append("numerical_diagnostic_unavailable")
            diagnostics = dict.fromkeys(diagnostics)
    status = "diagnostic_only" if len(reasons) == 3 else "unavailable"
    return ProbeResult(
        CONTRACT_VERSION, status, count, tuple(reasons), False, None,
        MappingProxyType(diagnostics), frozen_provenance,
    )
