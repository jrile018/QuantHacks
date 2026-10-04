#pragma once

// Point-in-time relative valuation coordinates (ADR-022; ADR.md 6.6).
//
// This is the first non-price information in the pipeline. It produces the
// three coordinates View D fits its ellipsoid to, per ticker per day:
//
//     E/P        earnings yield
//     EBITDA/EV  operating yield on enterprise value
//     FCF/P      free-cash-flow yield
//
// WHY YIELDS AND NOT MULTIPLES
// ----------------------------
// P/E diverges as E approaches zero and flips sign across zero earnings.
// Feeding an unbounded, sign-flipping coordinate into a covariance estimate
// is the same near-degeneracy the FastMCD conditioning work spent three
// rounds on, and the right place to fix it is here, in the choice of
// coordinate, not downstream in the estimator that has to swallow it. E/P
// passes smoothly through zero: a company earning nothing has an earnings
// yield of zero, which is both finite and true.
//
// WHERE THAT ARGUMENT DOES NOT HOLD, AND WHAT IS DONE ABOUT IT
// ------------------------------------------------------------
// It holds for E/P and FCF/P, whose denominator is market capitalisation
// and therefore strictly positive. It does NOT hold for EBITDA/EV:
// enterprise value is market cap + debt - cash, which goes negative for a
// company trading below its net cash. So the third coordinate can still
// flip sign, and ADR-022's own justification does not cover it.
//
// Two separate problems live in that denominator and they get different
// treatment:
//
//   EV small but positive -> the coordinate gets large, and that is FINE.
//     It is left alone. View D fits each ticker's own history with FastMCD,
//     whose entire purpose is to ignore a minority of extreme points, so a
//     brief episode of a genuinely enormous yield is exactly the
//     contamination the estimator is built for. Clamping it would be the
//     eigenvalue-floor mistake in a new location.
//
//   EV <= 0 -> the coordinate flips SIGN, and robustness does not help.
//     A sign-flipped value is not an outlier, it is a different quantity
//     pointing the wrong way, and no amount of robust estimation recovers
//     from including it. That ticker-day is reported as
//     kNonPositiveEnterpriseValue and carries no coordinate at all: not
//     floored, not imputed, not silently zero. The counts travel out in
//     ValuationPanel::status_counts so the stage can publish coverage as a
//     dataset statistic, which is how ADR-016 already handles price
//     retrievability.
//
// POINT-IN-TIME IS THE WHOLE POINT
// --------------------------------
// Every fundamentals row carries two dates: `period_end`, the period the
// figures describe, and `available_date`, the day they were published. A
// computation simulating day D may read only rows with
// `available_date <= D`. Never `period_end <= D` - a company's Q1 describes
// the quarter ending 31 March but is not published until May, so joining on
// period_end trades on 31 March using numbers nobody could see until May.
// That failure is silent: the equity curve improves rather than breaking.
// See README.md, "Data discipline: point-in-time, or it does not ship".
//
// PRICE BASIS
// -----------
// Market capitalisation is computed from the UNADJUSTED close, not from
// `adjclose`. This is deliberate and is the easy mistake to make here,
// because every other feature in this stage uses adjclose: adjclose is
// back-adjusted for splits and dividends while a reported share count is
// not, so multiplying the two gives a market cap that is wrong by every
// split since. Aggregate dollar figures throughout - dollar earnings
// against dollar market cap - so no per-share adjustment basis has to be
// reconciled at all.

#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace gm::features {

/// One row of `fundamentals.parquet`. Dates are ISO "YYYY-MM-DD" strings, as
/// everywhere else in this project's artifacts, so lexical comparison is
/// chronological comparison. All figures are trailing-twelve-month totals in
/// dollars except the balance-sheet items and the share count, which are
/// as-of `period_end`.
struct FundamentalsRow {
    std::string ticker;
    std::string period_end;      ///< the period the figures are about
    std::string available_date;  ///< the day the figures were published
    double net_income_ttm{};
    double ebitda_ttm{};
    double free_cash_flow_ttm{};
    double total_debt{};
    double cash_and_equivalents{};
    double shares_outstanding{};
};

/// The as-of rule. Among `rows` belonging to `ticker` whose `available_date`
/// is on or before `as_of`, returns the index of the one with the greatest
/// `period_end`; ties on `period_end` are broken by the greatest
/// `available_date`, so a restatement supersedes the figure it restates only
/// once the restatement itself has been published.
///
/// Returns nullopt when nothing has been published yet - an absent value,
/// never a NaN or a zero standing in for one (ADR-019).
///
/// Independent of the order of `rows`.
[[nodiscard]] std::optional<std::size_t> select_as_of(const std::vector<FundamentalsRow>& rows,
                                                      std::string_view ticker,
                                                      std::string_view as_of);

/// Why a ticker-day has no valuation coordinates AT ALL. Conditions that
/// affect one coordinate but not the others are not in here - see
/// ValuationYields.
enum class ValuationStatus {
    kOk = 0,                   ///< at least one coordinate was computed
    kNoFundamentalsAvailable,  ///< nothing published as of that day yet
    kNonPositiveMarketCap,     ///< close price or share count non-positive
    kNoYieldComputable,        ///< market cap fine, every coordinate's inputs absent
};

/// The three coordinates, each independently present or absent.
///
/// Absent is per-COORDINATE and not per-row, which matters more than it
/// looks. Measured across 40 real S&P issuers' SEC filings, E/P is
/// derivable for 40, FCF/P for 39, and EBITDA/EV for only 29. The eleven
/// misses are mostly structural rather than data gaps: a bank does not
/// report an operating-income subtotal, because that is not how a bank's
/// income statement is built, and EBITDA is close to meaningless for one
/// anyway. Rejecting those rows outright - which an all-or-nothing rule
/// does - would discard two perfectly good coordinates for the sake of a
/// third that is undefined for that issuer, for 28% of the sample.
struct ValuationYields {
    std::optional<double> earnings_yield;   ///< E/P
    std::optional<double> ebitda_ev_yield;  ///< EBITDA/EV
    std::optional<double> fcf_yield;        ///< FCF/P

    [[nodiscard]] bool any() const noexcept {
        return earnings_yield.has_value() || ebitda_ev_yield.has_value() ||
               fcf_yield.has_value();
    }
};

/// Why one coordinate is absent. Counted per coordinate so coverage is a
/// published number per axis rather than one blended figure that hides
/// which axis is the weak one.
enum class YieldStatus {
    kOk = 0,
    kMissingInput,             ///< a field this coordinate needs is absent in the source
    kNonPositiveDenominator,   ///< EBITDA/EV only: EV <= 0; see the header comment
};

struct ValuationPoint {
    ValuationStatus status{ValuationStatus::kOk};
    /// Each coordinate is meaningful iff it has a value. Present only when
    /// `status == kOk`; a row-level failure leaves all three absent.
    ValuationYields yields{};
    /// Per-coordinate outcome, in the fixed order E/P, EBITDA/EV, FCF/P.
    YieldStatus earnings_status{YieldStatus::kOk};
    YieldStatus ebitda_ev_status{YieldStatus::kOk};
    YieldStatus fcf_status{YieldStatus::kOk};
};

/// The three coordinates for one ticker on one day.
/// `close_price` is that day's UNADJUSTED close (see header).
[[nodiscard]] ValuationPoint compute_valuation_yields(const FundamentalsRow& fundamentals,
                                                      double close_price);

struct ValuationPanel {
    /// [ticker][date] -> yields. A ticker-day with no coordinate has no
    /// entry, matching how compute_trailing_returns reports insufficient
    /// history. std::map for deterministic iteration order (ADR-003).
    std::map<std::string, std::map<std::string, ValuationYields>> yields;
    /// How many ticker-days landed in each status, including kOk. Intended
    /// for the stage manifest, so coverage is a published number rather than
    /// something a reader has to infer from missing rows.
    std::map<ValuationStatus, std::int64_t> status_counts;
    /// Per-coordinate outcome counts, keyed "earnings_yield",
    /// "ebitda_ev_yield", "fcf_yield". Counted only for ticker-days that got
    /// as far as having a market cap, so these are about the coordinate and
    /// not about the row. Reported separately from status_counts because one
    /// blended coverage figure would hide which axis is the weak one - and
    /// measured on real filings, one of the three clearly is.
    std::map<std::string, std::map<YieldStatus, std::int64_t>> yield_counts;
};

/// Applies the as-of rule and the yield computation across a whole price
/// panel. The three price vectors are parallel columns of `prices.parquet`
/// and must be the same length; `price_close` is the UNADJUSTED close.
[[nodiscard]] ValuationPanel compute_valuation_panel(
    const std::vector<FundamentalsRow>& fundamentals,
    const std::vector<std::string>& price_tickers, const std::vector<std::string>& price_dates,
    const std::vector<double>& price_close);

/// Stable snake_case name for a status, for manifest keys and log lines.
[[nodiscard]] std::string_view to_string(ValuationStatus status);
[[nodiscard]] std::string_view to_string(YieldStatus status);

} // namespace gm::features
