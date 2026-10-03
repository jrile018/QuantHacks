"""Explicit cash, option-volume, cost, and risk assumptions for trade capacity."""

import math

from .risk_management import contracts_within_risk_budget


def option_legs(strategy: str, otm: float) -> tuple[str, ...]:
    """Traded option legs, including the ATM pair that represents stock exposure."""
    atm = ("C_K", "P_K")
    call = f"C_U{otm}"
    put = f"P_L{otm}"
    legs = {
        "stock": atm,
        "long_call": ("C_K",),
        "covered_call": atm + (call,),
        "protective_put": atm + (put,),
        "collar": atm + (call, put),
        "cash_secured_put": (put,),
    }
    if strategy not in legs:
        raise ValueError(f"unknown strategy: {strategy}")
    return legs[strategy]


def plan_trade(
    *,
    strategy: str,
    spot: float,
    strikes: dict[str, float],
    marks: dict[str, float],
    volumes: dict[str, float],
    capital: float,
    risk_fraction: float,
    participation: float,
    cost_haircut: float,
    otm: float,
) -> dict[str, float | int]:
    """Size a one-event trade under explicit research assumptions.

    Cash collateral uses a conservative 100-share stock equivalent for strategies
    containing synthetic stock. Volume capacity is a fraction of the least-traded
    required option leg. Costs are a fraction of each premium on each side.
    """
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError("spot must be finite and positive")
    if not math.isfinite(participation) or not 0 <= participation <= 1:
        raise ValueError("participation must be in [0, 1]")
    if not math.isfinite(cost_haircut) or cost_haircut < 0:
        raise ValueError("cost_haircut must be finite and nonnegative")

    legs = option_legs(strategy, otm)
    premiums = [float(marks[name]) for name in legs]
    daily_volumes = [float(volumes[name]) for name in legs]
    if any(not math.isfinite(x) or x < 0 for x in premiums + daily_volumes):
        raise ValueError("marks and volumes must be finite and nonnegative")
    lower_strike = float(strikes[f"L{otm}"])
    otm_call = float(marks.get(f"C_U{otm}", 0.0))
    otm_put = float(marks.get(f"P_L{otm}", 0.0))
    atm_call = float(marks.get("C_K", 0.0))

    if strategy == "long_call":
        capital_per_contract = max_loss = 100 * atm_call
    elif strategy == "cash_secured_put":
        capital_per_contract = 100 * lower_strike
        max_loss = 100 * max(lower_strike - otm_put, 0)
    else:
        purchased_put = otm_put if strategy in ("protective_put", "collar") else 0.0
        sold_call = otm_call if strategy in ("covered_call", "collar") else 0.0
        capital_per_contract = 100 * (spot + purchased_put)
        floor_value = lower_strike if strategy in ("protective_put", "collar") else 0.0
        max_loss = 100 * max(spot - floor_value + purchased_put - sold_call, 0)

    round_trip_cost = 100 * sum(premiums) * cost_haircut * 2
    gross_max_loss = max_loss
    capital_per_contract += round_trip_cost
    max_loss += round_trip_cost
    if capital_per_contract <= 0 or max_loss <= 0:
        raise ValueError("trade must have positive capital and maximum loss")
    capital_contracts = math.floor(capital / capital_per_contract)
    risk_contracts = contracts_within_risk_budget(capital, risk_fraction, max_loss)
    volume_contracts = math.floor(min(daily_volumes) * participation)
    return {
        "capital_per_contract": capital_per_contract,
        "max_loss_per_contract": max_loss,
        "gross_max_loss_per_contract": gross_max_loss,
        "round_trip_cost_per_contract": round_trip_cost,
        "capital_contracts": capital_contracts,
        "risk_contracts": risk_contracts,
        "volume_contracts": volume_contracts,
        "least_leg_volume": min(daily_volumes),
        "capacity_contracts": min(capital_contracts, risk_contracts, volume_contracts),
    }
