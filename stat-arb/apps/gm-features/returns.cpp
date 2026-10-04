#include "returns.hpp"

#include <algorithm>
#include <utility>

namespace gm::features {

std::map<std::string, std::map<std::string, double>> compute_trailing_returns(
    const std::vector<std::string>& price_tickers, const std::vector<std::string>& price_dates,
    const std::vector<double>& price_adjclose, int trading_days_back) {
    // Group into a per-ticker (date, adjclose) series, then sort each by
    // date. gm-ingest already appends each ticker's bars in ascending
    // date order, but sorting explicitly makes this correct regardless
    // of upstream row order rather than assuming it.
    std::map<std::string, std::vector<std::pair<std::string, double>>> series_by_ticker;
    for (std::size_t i = 0; i < price_tickers.size(); ++i) {
        series_by_ticker[price_tickers[i]].emplace_back(price_dates[i], price_adjclose[i]);
    }

    std::map<std::string, std::map<std::string, double>> out;
    for (auto& [ticker, series] : series_by_ticker) {
        std::sort(series.begin(), series.end(),
                  [](const auto& a, const auto& b) { return a.first < b.first; });

        std::map<std::string, double> per_date;
        for (std::size_t t = 0; t < series.size(); ++t) {
            if (static_cast<int>(t) < trading_days_back) continue;
            double prior = series[t - static_cast<std::size_t>(trading_days_back)].second;
            if (prior <= 0.0) continue;  // guard against a bad/zero adjclose, not expected post-ADR-015
            double ret = series[t].second / prior - 1.0;
            per_date[series[t].first] = ret;
        }
        out[ticker] = std::move(per_date);
    }
    return out;
}

} // namespace gm::features
