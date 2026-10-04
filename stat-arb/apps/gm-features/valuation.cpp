#include "valuation.hpp"

#include <cmath>

namespace gm::features {
namespace {

// A Parquet double column carries an absent source field as NaN. ADR-019
// forbids NaN as a sentinel, so it is converted back into an explicit status
// at the boundary rather than allowed to propagate into a coordinate, where
// it would poison the covariance of every window containing that day.
//
// Checked per COORDINATE rather than across the whole row: the fields differ
// between the three yields, and an issuer missing one of them is not thereby
// missing the others (see the ValuationYields comment).
bool finite(double v) { return std::isfinite(v); }

} // namespace

std::optional<std::size_t> select_as_of(const std::vector<FundamentalsRow>& rows,
                                        std::string_view ticker, std::string_view as_of) {
    std::optional<std::size_t> best;
    for (std::size_t i = 0; i < rows.size(); ++i) {
        const FundamentalsRow& row = rows[i];
        if (row.ticker != ticker) continue;

        // The rule the whole file exists for: published on or before `as_of`.
        // Deliberately NOT `period_end <= as_of` - see the header comment and
        // README.md. Dates are strict ISO-8601 strings, so lexical ordering is
        // chronological ordering, which is how every other stage in this
        // pipeline compares dates.
        if (row.available_date > as_of) continue;

        if (!best) {
            best = i;
            continue;
        }
        const FundamentalsRow& incumbent = rows[*best];
        // Greatest period_end first; available_date only as a tie-break, so a
        // restatement displaces the figure it restates but never displaces a
        // later period that has already been published.
        const bool newer_period = row.period_end > incumbent.period_end;
        const bool same_period_newer_filing = row.period_end == incumbent.period_end &&
                                              row.available_date > incumbent.available_date;
        if (newer_period || same_period_newer_filing) best = i;
    }
    // Both comparisons are strict, so the outcome is independent of the order
    // of `rows`. The one exception is two rows agreeing on BOTH dates while
    // disagreeing on their figures, which is malformed input rather than a
    // restatement; the lower index wins, deterministically, and the condition
    // is worth catching in the ingest stage instead of resolving here.
    return best;
}

ValuationPoint compute_valuation_yields(const FundamentalsRow& fundamentals, double close_price) {
    ValuationPoint out;

    // Market cap is required by ALL three coordinates - two divide by it and
    // the third has it inside enterprise value - so this one really is a
    // row-level condition.
    if (!finite(close_price) || !finite(fundamentals.shares_outstanding)) {
        out.status = ValuationStatus::kNonPositiveMarketCap;
        out.earnings_status = YieldStatus::kMissingInput;
        out.ebitda_ev_status = YieldStatus::kMissingInput;
        out.fcf_status = YieldStatus::kMissingInput;
        return out;
    }
    // Unadjusted close times as-reported share count. Using adjclose here
    // would be wrong by every split since the filing (see header).
    const double market_cap = close_price * fundamentals.shares_outstanding;
    if (!(close_price > 0.0) || !(fundamentals.shares_outstanding > 0.0) ||
        !(market_cap > 0.0)) {
        out.status = ValuationStatus::kNonPositiveMarketCap;
        out.earnings_status = YieldStatus::kMissingInput;
        out.ebitda_ev_status = YieldStatus::kMissingInput;
        out.fcf_status = YieldStatus::kMissingInput;
        return out;
    }

    // ---- E/P -------------------------------------------------------------
    if (finite(fundamentals.net_income_ttm)) {
        out.yields.earnings_yield = fundamentals.net_income_ttm / market_cap;
    } else {
        out.earnings_status = YieldStatus::kMissingInput;
    }

    // ---- FCF/P -----------------------------------------------------------
    if (finite(fundamentals.free_cash_flow_ttm)) {
        out.yields.fcf_yield = fundamentals.free_cash_flow_ttm / market_cap;
    } else {
        out.fcf_status = YieldStatus::kMissingInput;
    }

    // ---- EBITDA/EV -------------------------------------------------------
    // The weak axis, and the only one with a denominator that can go
    // non-positive. Both of its failure modes are per-coordinate.
    if (!finite(fundamentals.ebitda_ttm) || !finite(fundamentals.total_debt) ||
        !finite(fundamentals.cash_and_equivalents)) {
        out.ebitda_ev_status = YieldStatus::kMissingInput;
    } else {
        const double enterprise_value =
            market_cap + fundamentals.total_debt - fundamentals.cash_and_equivalents;
        // EV <= 0 means the company trades below its net cash. Dividing by it
        // would flip the sign of the coordinate, and a sign-flipped coordinate
        // is not an outlier a robust estimator can absorb. Excluded, not
        // clamped: the counts are published instead (ADR-022).
        //
        // This no longer discards the other two coordinates with it, which
        // the previous version did - E/P and FCF/P do not involve enterprise
        // value at all and are unaffected by its sign.
        if (!(enterprise_value > 0.0)) {
            out.ebitda_ev_status = YieldStatus::kNonPositiveDenominator;
        } else {
            // A small-but-positive enterprise value is deliberately left alone,
            // however large the resulting yield. FastMCD downstream exists to
            // ignore a minority of extreme points; flooring the denominator to
            // keep the number tidy would be the eigenvalue-floor mistake in a
            // new place.
            out.yields.ebitda_ev_yield = fundamentals.ebitda_ttm / enterprise_value;
        }
    }

    out.status = out.yields.any() ? ValuationStatus::kOk : ValuationStatus::kNoYieldComputable;
    return out;
}

ValuationPanel compute_valuation_panel(const std::vector<FundamentalsRow>& fundamentals,
                                       const std::vector<std::string>& price_tickers,
                                       const std::vector<std::string>& price_dates,
                                       const std::vector<double>& price_close) {
    ValuationPanel panel;
    // The three price vectors are parallel columns of one Parquet table. A
    // length mismatch is a caller defect, not a data condition, and indexing
    // on regardless is how an out-of-bounds read gets shipped.
    if (price_tickers.size() != price_dates.size() ||
        price_tickers.size() != price_close.size()) {
        return panel;
    }

    // Grouped once so each as-of scan covers one issuer's filings rather than
    // the whole table. std::map keeps iteration order deterministic (ADR-003),
    // and push_back preserves the input order within a ticker, which
    // select_as_of does not depend on but which keeps this reproducible.
    std::map<std::string, std::vector<FundamentalsRow>> by_ticker;
    for (const FundamentalsRow& row : fundamentals) by_ticker[row.ticker].push_back(row);

    for (std::size_t i = 0; i < price_tickers.size(); ++i) {
        const std::string& ticker = price_tickers[i];
        const std::string& date = price_dates[i];

        const auto group = by_ticker.find(ticker);
        if (group == by_ticker.end()) {
            // No filings at all for this issuer: indistinguishable, from this
            // day's point of view, from having none published yet.
            ++panel.status_counts[ValuationStatus::kNoFundamentalsAvailable];
            continue;
        }

        const auto chosen = select_as_of(group->second, ticker, date);
        if (!chosen) {
            ++panel.status_counts[ValuationStatus::kNoFundamentalsAvailable];
            continue;
        }

        const ValuationPoint point =
            compute_valuation_yields(group->second[*chosen], price_close[i]);
        ++panel.status_counts[point.status];
        ++panel.yield_counts["earnings_yield"][point.earnings_status];
        ++panel.yield_counts["ebitda_ev_yield"][point.ebitda_ev_status];
        ++panel.yield_counts["fcf_yield"][point.fcf_status];
        if (point.status == ValuationStatus::kOk) panel.yields[ticker][date] = point.yields;
    }
    return panel;
}

std::string_view to_string(ValuationStatus status) {
    switch (status) {
        case ValuationStatus::kOk:
            return "ok";
        case ValuationStatus::kNoFundamentalsAvailable:
            return "no_fundamentals_available";
        case ValuationStatus::kNonPositiveMarketCap:
            return "non_positive_market_cap";
        case ValuationStatus::kNoYieldComputable:
            return "no_yield_computable";
    }
    return "unknown";
}

std::string_view to_string(YieldStatus status) {
    switch (status) {
        case YieldStatus::kOk:
            return "ok";
        case YieldStatus::kMissingInput:
            return "missing_input";
        case YieldStatus::kNonPositiveDenominator:
            return "non_positive_denominator";
    }
    return "unknown";
}

} // namespace gm::features
