#pragma once

// Liquidity ranking (ADR-001: "top 100 by trailing 60-day median dollar
// volume"). Operates on an already-ingested price panel (gm::io::Table
// with ticker/date/close/volume columns) rather than fetching anything
// itself - this is deliberately a pure function over data gm-ingest
// already produced, not a network-touching stage of its own, so it's
// trivially testable without a live source.

#include <gm-core/error.hpp>
#include <gm-io/table.hpp>

#include <string>
#include <vector>

namespace gm::data {

struct LiquidityRankedTicker {
    std::string ticker;
    double median_dollar_volume;
    std::size_t bars_used;  // how many of the trailing window's bars this ticker actually had
};

/// For each ticker present in `prices`, takes that ticker's most recent
/// `window_days` bars (by date, ascending order within the ticker - the
/// panel need not be pre-sorted), computes each bar's dollar volume
/// (close * volume), and ranks tickers by the median of those values,
/// descending. Returns at most `top_n` entries.
///
/// A ticker with fewer than `window_days` bars available is still
/// ranked (using whatever it has - `bars_used` reports how many), not
/// excluded outright; a newly-listed name with only a few weeks of
/// history genuinely may still be liquid enough to matter, and silently
/// dropping it would bias the universe toward incumbents.
[[nodiscard]] Result<std::vector<LiquidityRankedTicker>> rank_by_liquidity(const gm::io::Table& prices,
                                                                            int window_days, int top_n);

} // namespace gm::data
