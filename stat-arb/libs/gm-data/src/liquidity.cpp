#include <gm-data/liquidity.hpp>

#include <algorithm>
#include <unordered_map>

namespace gm::data {

namespace {

double median_of(std::vector<double> values) {
    std::sort(values.begin(), values.end());
    std::size_t n = values.size();
    if (n == 0) return 0.0;
    if (n % 2 == 1) return values[n / 2];
    return (values[n / 2 - 1] + values[n / 2]) / 2.0;
}

} // namespace

Result<std::vector<LiquidityRankedTicker>> rank_by_liquidity(const gm::io::Table& prices,
                                                               int window_days, int top_n) {
    if (window_days <= 0) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "window_days must be positive"));
    }
    if (top_n <= 0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "top_n must be positive"));
    }

    auto ticker_col = prices.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto date_col = prices.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto close_col = prices.double_column("close");
    if (!close_col) return tl::unexpected(close_col.error());
    auto volume_col = prices.int64_column("volume");
    if (!volume_col) return tl::unexpected(volume_col.error());

    // Group row indices by ticker. ISO-8601 dates sort correctly as
    // plain strings, so sorting each group's indices by date string is
    // enough - no date parsing needed just to rank by recency.
    std::unordered_map<std::string, std::vector<std::size_t>> rows_by_ticker;
    for (std::size_t i = 0; i < ticker_col->size(); ++i) {
        rows_by_ticker[(*ticker_col)[i]].push_back(i);
    }

    std::vector<LiquidityRankedTicker> ranked;
    ranked.reserve(rows_by_ticker.size());

    for (auto& [ticker, indices] : rows_by_ticker) {
        std::sort(indices.begin(), indices.end(), [&](std::size_t a, std::size_t b) {
            return (*date_col)[a] < (*date_col)[b];
        });

        std::size_t take = std::min(indices.size(), static_cast<std::size_t>(window_days));
        std::vector<double> dollar_volumes;
        dollar_volumes.reserve(take);
        for (std::size_t i = indices.size() - take; i < indices.size(); ++i) {
            std::size_t row = indices[i];
            dollar_volumes.push_back((*close_col)[row] * static_cast<double>((*volume_col)[row]));
        }

        ranked.push_back(LiquidityRankedTicker{ticker, median_of(std::move(dollar_volumes)), take});
    }

    // Secondary sort key on ticker name, not just std::stable_sort: the
    // tickers are collected via std::unordered_map iteration above,
    // whose order is itself unspecified and can vary run to run - a
    // stable sort would faithfully preserve that already-nondeterministic
    // order for exact ties, not fix it. Only a real tiebreaker makes
    // "same inputs -> same output" (ADR §3 principle 2) actually hold.
    std::sort(ranked.begin(), ranked.end(), [](const LiquidityRankedTicker& a, const LiquidityRankedTicker& b) {
        if (a.median_dollar_volume != b.median_dollar_volume) {
            return a.median_dollar_volume > b.median_dollar_volume;
        }
        return a.ticker < b.ticker;
    });

    if (ranked.size() > static_cast<std::size_t>(top_n)) {
        ranked.resize(static_cast<std::size_t>(top_n));
    }

    return ranked;
}

} // namespace gm::data
