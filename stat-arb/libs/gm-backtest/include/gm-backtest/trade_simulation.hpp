#pragma once

// Walk-forward portfolio simulation (ADR §6.5 signal, ADR-014 walk-
// forward discipline). Deliberately split from apps/gm-backtest/main.cpp
// the same way every other stage in this codebase splits math from
// I/O: this module takes ALREADY-FILTERED trade candidates (the
// eligibility logic - Views A/B/C, earnings, tradable half-life band -
// lives in the stage app, which is where the multi-source parquet
// joins naturally belong) and turns them into a daily portfolio return
// series, so the actual simulation math is testable against small
// hand-built fixtures independent of any real data file.

#include <gm-core/error.hpp>

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace gm::backtest {

struct TradeCandidate {
    std::string ticker;      // identity only (logging/labeling) - NOT used to look anything up
    std::string entry_date;  // inclusive
    std::string exit_date;   // inclusive; must be >= entry_date
    bool long_the_spread;    // true if entry z < 0 (spread below its mean, expect it to rise)
    int num_legs;            // 1 (the target) + number of peer-basket neighbours, for cost scaling

    // date -> spread level, computed by the CALLER using this trade's
    // OWN entry-day peer-basket weights held FIXED across the entire
    // holding period (NOT gm-signals' spreads.parquet spread column,
    // which is refit fresh every day and is only valid for scoring
    // that single day's z - see the file header on why differencing it
    // across days does not represent one held position's P&L). Every
    // candidate carries its own series rather than sharing one
    // ticker-keyed lookup across all candidates, because the SAME
    // ticker can have multiple trades over a long history with
    // DIFFERENT baskets locked in at different entry dates - a shared
    // per-ticker lookup cannot represent that without an ambiguous
    // synthetic key, so each candidate is simply self-contained
    // instead.
    std::map<std::string, double> spread_series;
};

struct PortfolioResult {
    std::vector<std::string> dates;             // every date at least one position had a return contribution
    std::vector<double> daily_returns;           // equal-weighted average across that day's open positions
    std::vector<std::int64_t> num_open_positions; // how many positions contributed to that day's average
};

/// For each candidate, walks its OWN spread_series between entry_date
/// and exit_date (using whatever actual trading days that series
/// contains - not calendar arithmetic) and computes a daily return
/// contribution of +/-(spread[t] - spread[t-1]) depending on
/// long_the_spread. Round-trip transaction cost (`cost_bps_per_leg` *
/// num_legs * 2, entry and exit) is deducted as a lump sum split evenly
/// across the entry day and the exit day's contribution for that
/// position - costs are incurred at trade time, not smoothly amortized
/// across the holding period.
///
/// A candidate whose spread_series has fewer than 2 observations in
/// [entry_date, exit_date] (nothing to compute a return between)
/// contributes no days and is otherwise silently skipped - not a
/// validation failure, since a single-day candidate the data has no
/// continuation for is an expected data-boundary case, not a bug in
/// the study itself.
[[nodiscard]] Result<PortfolioResult> simulate_portfolio(const std::vector<TradeCandidate>& candidates,
                                                          double cost_bps_per_leg);

} // namespace gm::backtest
