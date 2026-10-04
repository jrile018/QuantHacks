#include "market_model.hpp"

#include <cmath>

namespace gm::features {

std::map<std::string, std::map<std::string, double>> compute_daily_returns(
    const std::vector<std::string>& price_tickers, const std::vector<std::string>& price_dates,
    const std::vector<double>& price_adjclose) {
    std::map<std::string, std::map<std::string, double>> out;
    if (price_tickers.size() != price_dates.size() ||
        price_tickers.size() != price_adjclose.size()) {
        // A length mismatch is a caller defect, not a data condition, and
        // indexing on regardless is how an out-of-bounds read ships.
        return out;
    }

    // Grouped by ticker with dates ordered, so "the previous bar" means
    // this ticker's previous bar rather than the previous row of a table
    // whose ordering is not part of its contract.
    std::map<std::string, std::map<std::string, double>> close_by_ticker;
    for (std::size_t i = 0; i < price_tickers.size(); ++i) {
        if (!std::isfinite(price_adjclose[i]) || price_adjclose[i] <= 0.0) continue;
        close_by_ticker[price_tickers[i]][price_dates[i]] = price_adjclose[i];
    }

    for (const auto& [ticker, series] : close_by_ticker) {
        auto prev = series.end();
        for (auto it = series.begin(); it != series.end(); ++it) {
            if (prev != series.end() && prev->second > 0.0) {
                out[ticker][it->first] = it->second / prev->second - 1.0;
            }
            prev = it;
        }
    }
    return out;
}

std::map<std::string, double> equal_weighted_index(
    const std::map<std::string, std::map<std::string, double>>& returns_by_ticker, int min_names) {
    std::map<std::string, double> sum;
    std::map<std::string, int> count;
    for (const auto& [ticker, series] : returns_by_ticker) {
        for (const auto& [date, r] : series) {
            if (!std::isfinite(r)) continue;
            sum[date] += r;
            ++count[date];
        }
    }

    std::map<std::string, double> index;
    for (const auto& [date, total] : sum) {
        const int n = count[date];
        // A handful of names is not an index, and a beta regressed against
        // one would describe those names rather than the market.
        if (n < min_names) continue;
        index[date] = total / static_cast<double>(n);
    }
    return index;
}

std::map<std::string, std::map<std::string, MarketModel>> compute_market_model(
    const std::map<std::string, std::map<std::string, double>>& returns_by_ticker,
    const std::map<std::string, double>& index_returns, int window) {
    std::map<std::string, std::map<std::string, MarketModel>> out;
    if (window < 4) return out;
    const int min_observations = window / 2;

    for (const auto& [ticker, series] : returns_by_ticker) {
        // The ticker's returns as a date-ordered vector, restricted to
        // dates the index also has - a pair needs both halves.
        std::vector<std::string> dates;
        std::vector<double> stock, market;
        dates.reserve(series.size());
        for (const auto& [date, r] : series) {
            const auto idx = index_returns.find(date);
            if (idx == index_returns.end() || !std::isfinite(r) || !std::isfinite(idx->second)) {
                continue;
            }
            dates.push_back(date);
            stock.push_back(r);
            market.push_back(idx->second);
        }

        for (std::size_t i = 0; i < dates.size(); ++i) {
            // Inclusive of i: this describes the window ending today, and
            // uses nothing observed after it.
            const std::size_t first = i + 1 >= static_cast<std::size_t>(window)
                                          ? i + 1 - static_cast<std::size_t>(window)
                                          : 0;
            const std::size_t n = i + 1 - first;
            if (static_cast<int>(n) < min_observations) continue;

            double sum_x = 0.0, sum_y = 0.0;
            for (std::size_t j = first; j <= i; ++j) {
                sum_x += market[j];
                sum_y += stock[j];
            }
            const double mean_x = sum_x / static_cast<double>(n);
            const double mean_y = sum_y / static_cast<double>(n);

            double sxx = 0.0, sxy = 0.0;
            for (std::size_t j = first; j <= i; ++j) {
                const double dx = market[j] - mean_x;
                sxx += dx * dx;
                sxy += dx * (stock[j] - mean_y);
            }
            // A window where the index never moved gives no slope at all.
            // Dividing anyway would fabricate one; ADR-019's rule is that
            // an unavailable value is absent, not invented.
            if (!(sxx > 0.0)) continue;

            const double beta = sxy / sxx;
            const double alpha = mean_y - beta * mean_x;

            double sum_sq_resid = 0.0;
            for (std::size_t j = first; j <= i; ++j) {
                const double resid = stock[j] - (alpha + beta * market[j]);
                sum_sq_resid += resid * resid;
            }
            // n - 2 degrees of freedom: a two-parameter fit. n is at least
            // window/2 >= 2 by the guard above, and window >= 4 makes that
            // at least 2, so this needs n > 2 to be meaningful.
            if (n <= 2) continue;
            const double resid_var = sum_sq_resid / static_cast<double>(n - 2);

            MarketModel m;
            m.beta = beta;
            // Annualised the same way every volatility in this project is:
            // sqrt(252) trading days.
            m.idiosyncratic_volatility = std::sqrt(resid_var) * std::sqrt(252.0);
            m.observations = static_cast<int>(n);
            out[ticker][dates[i]] = m;
        }
    }
    return out;
}

} // namespace gm::features
