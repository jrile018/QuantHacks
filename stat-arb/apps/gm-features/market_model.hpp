#pragma once

// The market-model regression: beta and idiosyncratic volatility.
//
// These two features have been documented as deliberately absent since the
// feature store was written - "a real, larger undertaking (needs an index
// return series this stage does not currently build)". They were left out
// rather than shipped as all-NaN columns, which was the right call and is
// why this can be added now without anyone having to distrust an existing
// column.
//
// WHICH INDEX
// -----------
// EQUAL-weighted, built from the panel itself, not a value-weighted index
// and not an external series. Three reasons, in order of how much they
// matter:
//
//   1. A value-weighted index needs market capitalisation for every name
//      on every day, which needs a point-in-time share count. That exists
//      now (gm-data's fundamentals reader) but only for issuers with SEC
//      XBRL coverage, which does not reach the start of the price window -
//      so a value-weighted index would silently change composition as
//      coverage arrives, and beta would move for reasons that have nothing
//      to do with the stock.
//   2. An external index series is a second data source with its own
//      point-in-time problems, and the panel is what the rest of the
//      geometry is built from. Regressing against something the geometry
//      does not know about would make beta answer a different question
//      from every other feature here.
//   3. Equal weighting is the same choice ADR 6.2 already makes when it
//      talks about the market mode of the correlation matrix.
//
// The index return on day t is the MEAN of that day's available returns,
// which means it is defined per day over whatever names traded, not over a
// fixed membership. That is deliberate: the universe is point-in-time, and
// a fixed-membership index would need names that had not listed yet.
//
// CAUSALITY
// ---------
// The regression window ends on the day being described, inclusive. This
// is a descriptive feature of the trailing window, not a forecast, and it
// uses only returns observable by that date - the same rule the trailing
// returns beside it follow.

#include <map>
#include <string>
#include <vector>

namespace gm::features {

struct MarketModel {
    /// Slope of the regression of the ticker's return on the index return
    /// over the trailing window.
    double beta{};
    /// Standard deviation of the regression residuals, annualised by
    /// sqrt(252). The part of the name's movement the market does not
    /// explain, which is the part a relative-value strategy trades.
    double idiosyncratic_volatility{};
    /// How many paired observations the fit used. Published so a beta from
    /// the shortest acceptable window is distinguishable from one with the
    /// full window behind it.
    int observations{};
};

/// Daily simple returns per ticker, from adjusted close, for every
/// (ticker, date) with a prior bar for that ticker.
[[nodiscard]] std::map<std::string, std::map<std::string, double>> compute_daily_returns(
    const std::vector<std::string>& price_tickers, const std::vector<std::string>& price_dates,
    const std::vector<double>& price_adjclose);

/// The equal-weighted index return per date: the mean of that date's
/// available ticker returns. A date with fewer than `min_names` returns
/// has no entry - a two-stock "index" is not one.
[[nodiscard]] std::map<std::string, double> equal_weighted_index(
    const std::map<std::string, std::map<std::string, double>>& returns_by_ticker,
    int min_names = 5);

/// Market model per (ticker, date) over the trailing `window` days,
/// inclusive of `date`.
///
/// A (ticker, date) with fewer than `window / 2` paired observations has
/// NO entry, the same convention compute_trailing_returns uses for
/// insufficient history: an absent value the caller represents as NaN,
/// never a placeholder for something unimplemented.
///
/// Returns nothing for a window where the index return has zero variance -
/// beta would be a division by zero, and a fabricated slope through a
/// degenerate regression is exactly the kind of plausible wrong number
/// this project refuses to ship.
[[nodiscard]] std::map<std::string, std::map<std::string, MarketModel>> compute_market_model(
    const std::map<std::string, std::map<std::string, double>>& returns_by_ticker,
    const std::map<std::string, double>& index_returns, int window);

} // namespace gm::features
