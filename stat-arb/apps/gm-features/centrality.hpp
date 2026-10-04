#pragma once

// Point-in-time GICS-sector co-membership centrality (ADR section 7.4
// pivot, 2026-08-31): the real, working implementation lives here,
// factored out of apps/gm-features/main.cpp so it can be unit tested
// without going through Parquet I/O. libs/gm-data/etf_holdings.{hpp,cpp}
// was a dead, unreferenced stub for an earlier ETF-holdings-file
// approach that was abandoned in favor of this GICS-sector approach; it
// has been deleted.

#include <string>
#include <vector>

namespace gm::features {

/// Computes a per-(date, ticker) sector co-membership centrality score
/// using ONLY the tickers recorded as members on that row's own date -
/// never data from any other date (point-in-time, no look-ahead).
///
/// `dates`, `tickers`, `sectors` must be the same length: one row per
/// (date, ticker) that was actually a universe member that day, exactly
/// the shape gm-universe's universe.parquet already has (it is NOT a
/// wide table with an in_universe boolean - membership is implicit in
/// row presence).
///
/// For row i: let S = sectors[i], D = dates[i]. Then
///   centrality[i] = (# distinct tickers with sector S on date D)
///                   / (1 + max over all sectors on date D of that
///                      sector's distinct ticker count)
/// Both the numerator and the divisor are recomputed independently for
/// every date, so a ticker's sector centrality on one date can never be
/// influenced by tickers that joined or left the universe on any other
/// date - this is what makes the feature a genuine function of
/// (ticker, date) rather than (ticker) alone with a date column bolted
/// on.
///
/// Returns one centrality value per input row, in input order.
[[nodiscard]] std::vector<double> compute_pit_sector_centrality(
    const std::vector<std::string>& dates, const std::vector<std::string>& tickers,
    const std::vector<std::string>& sectors);

} // namespace gm::features
