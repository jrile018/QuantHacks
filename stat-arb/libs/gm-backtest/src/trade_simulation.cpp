#include <gm-backtest/trade_simulation.hpp>

#include <algorithm>

namespace gm::backtest {

Result<PortfolioResult> simulate_portfolio(const std::vector<TradeCandidate>& candidates,
                                            double cost_bps_per_leg) {
    if (cost_bps_per_leg < 0.0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "cost_bps_per_leg must be >= 0"));
    }

    // date -> every position's return contribution on that date, merged
    // across candidates before averaging - a std::map (not
    // unordered_map) so both the per-date list order and the final
    // date iteration order are deterministic (ADR Sec3 principle 2).
    std::map<std::string, std::vector<double>> contributions_by_date;

    for (const auto& c : candidates) {
        if (c.exit_date < c.entry_date) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "trade candidate exit_date precedes entry_date",
                                                   c.ticker + ": " + c.entry_date + " -> " + c.exit_date));
        }
        if (c.num_legs < 1) {
            return tl::unexpected(
                gm::Error::make(gm::ErrorCode::kInvalidArgument, "trade candidate num_legs must be >= 1", c.ticker));
        }

        auto lo = c.spread_series.lower_bound(c.entry_date);
        auto hi = c.spread_series.upper_bound(c.exit_date); // one-past the last date <= exit_date

        std::vector<std::pair<std::string, double>> in_range(lo, hi);
        if (in_range.size() < 2) continue; // nothing to compute a return between - a data-boundary case, not an error

        double total_cost_fraction = (cost_bps_per_leg / 10000.0) * static_cast<double>(c.num_legs) * 2.0;
        std::size_t num_return_days = in_range.size() - 1;
        double cost_per_endpoint = total_cost_fraction / 2.0;

        for (std::size_t i = 1; i < in_range.size(); ++i) {
            double raw_return = in_range[i].second - in_range[i - 1].second;
            double signed_return = c.long_the_spread ? raw_return : -raw_return;

            double cost_today = 0.0;
            if (num_return_days == 1) {
                cost_today = total_cost_fraction; // both entry and exit land on the same single day
            } else if (i == 1) {
                cost_today = cost_per_endpoint; // entry cost, charged on the first day held
            } else if (i == in_range.size() - 1) {
                cost_today = cost_per_endpoint; // exit cost, charged on the last day held
            }

            contributions_by_date[in_range[i].first].push_back(signed_return - cost_today);
        }
    }

    PortfolioResult result;
    result.dates.reserve(contributions_by_date.size());
    result.daily_returns.reserve(contributions_by_date.size());
    result.num_open_positions.reserve(contributions_by_date.size());

    for (const auto& [date, returns] : contributions_by_date) {
        double sum = 0.0;
        for (double r : returns) sum += r;
        result.dates.push_back(date);
        result.daily_returns.push_back(sum / static_cast<double>(returns.size()));
        result.num_open_positions.push_back(static_cast<std::int64_t>(returns.size()));
    }

    return result;
}

} // namespace gm::backtest
