"""Cash accounting and strict quote gates, separate from predictive evidence.

These helpers do not infer fills from bars or interval samples. A caller using
sampled prices must explicitly opt into proxy evidence and retain that status.
Instrument lifecycle, venue definitions, fees and receipt provenance belong to
the audited input adapter; this module never substitutes another instrument.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{name} must be finite')
    return result


def round_trip_cash(entry: float, exit: float, quantity: float, multiplier: float,
                    side: str, costs: float) -> float:
    """Cash gain for one actual contract/share leg, after explicit total costs.

Entry/exit are already the correct execution sides. Prices may be negative
for products that permit them. This is a gain, not a return on margin.
"""
    entry, exit = _finite(entry, 'entry'), _finite(exit, 'exit')
    quantity, multiplier = _finite(quantity, 'quantity'), _finite(multiplier, 'multiplier')
    costs = _finite(costs, 'costs')
    if quantity <= 0 or multiplier <= 0 or costs < 0 or side not in {'long', 'short'}:
        raise ValueError('positive exposure, nonnegative costs and long/short side required')
    return (1 if side == 'long' else -1) * quantity * multiplier * (exit - entry) - costs


def futures_cash_flows(entry: float, exit: float, settlements: Iterable[float],
                       quantity: float, multiplier: float, side: str,
                       costs: float) -> tuple[float, ...]:
    """Reconcile a single held leg across chronological settlement marks.

The first cash flow starts at actual entry, subsequent flows at prior
settlement, and the last at actual exit. Costs appear once. Add actual roll
legs separately; never add a continuous-series roll gap or collateral.
"""
    round_trip_cash(entry, exit, quantity, multiplier, side, costs)
    marks = [_finite(entry, 'entry'), *[_finite(x, 'settlement') for x in settlements],
             _finite(exit, 'exit')]
    flows = [round_trip_cash(a, b, quantity, multiplier, side, 0)
             for a, b in zip(marks, marks[1:])]
    flows[-1] -= float(costs)
    return tuple(flows)


@dataclass(frozen=True)
class Quote:
    instrument_key: str
    event_time: datetime
    available_time: datetime
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    evidence_kind: str = 'update'


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware quote and decision timestamps required')


def executable_price(quote: Quote, order_side: str, quantity: float,
                     cutoff: datetime, max_age_seconds: float, *,
                     allow_sampled_proxy: bool = False) -> float | None:
    """Return side price or an all-or-none nonfill under the declared gate.

Update evidence requires an original quote event timestamp. For interval
data the adapter retains its original interval semantics; enabling a proxy
does not establish update freshness, simultaneous books or an actual fill.
No partial fills are assumed by this conservative initial policy.
"""
    for timestamp in (quote.event_time, quote.available_time, cutoff):
        _aware(timestamp)
    quantity, max_age_seconds = _finite(quantity, 'quantity'), _finite(max_age_seconds, 'max_age')
    if quantity <= 0 or max_age_seconds < 0 or order_side not in {'buy', 'sell'}:
        raise ValueError('valid order side, positive quantity and nonnegative quote age required')
    if not quote.instrument_key:
        raise ValueError('an exact instrument identity is required')
    if quote.evidence_kind not in {'update', 'interval_sample'}:
        raise ValueError('unknown quote evidence kind')
    if quote.evidence_kind == 'interval_sample' and not allow_sampled_proxy:
        return None
    if quote.available_time > cutoff or quote.available_time < quote.event_time:
        return None
    age = (cutoff - quote.event_time).total_seconds()
    if age < 0 or age > max_age_seconds:
        return None
    if not all(math.isfinite(float(x)) for x in (quote.bid, quote.ask, quote.bid_size, quote.ask_size)):
        return None
    if quote.bid > quote.ask:
        return None
    size, price = ((quote.ask_size, quote.ask) if order_side == 'buy'
                   else (quote.bid_size, quote.bid))
    if size <= 0 or size < quantity:
        return None
    return float(price)
