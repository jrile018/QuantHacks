#pragma once

// Trailing N-trading-day cumulative simple returns, computed per ticker
// from adjusted close, as a genuine implementation (not a NaN
// placeholder). "N trading days" means N bars back in that ticker's own
// price series (adjclose[t]/adjclose[t-N] - 1), matching how
// prices.parquet is already screened/assembled by gm-ingest (ADR-015).

#include <map>
#include <string>
#include <vector>

namespace gm::features {

/// Returns, for every (ticker, date) that had at least `trading_days_back`
/// prior bars for that same ticker, the trailing simple return over that
/// many trading days. A (ticker, date) with insufficient history (new
/// listing, start of series, etc.) has NO entry in the result - that is
/// a legitimate missing value for the caller to represent as NaN, not a
/// placeholder for an unimplemented feature.
[[nodiscard]] std::map<std::string, std::map<std::string, double>> compute_trailing_returns(
    const std::vector<std::string>& price_tickers, const std::vector<std::string>& price_dates,
    const std::vector<double>& price_adjclose, int trading_days_back);

} // namespace gm::features
