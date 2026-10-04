#pragma once

// SEC XBRL fundamentals with real publication dates (ADR-022; ADR.md 6.6).
//
// Reads data.sec.gov/api/xbrl/companyfacts/CIK##########.json - the ADR
// section 7.3 primary source - and turns it into the two-date records the
// point-in-time rule needs. Follows the gm-signals/earnings.hpp split
// exactly: all JSON-shape handling lives in pure functions testable against
// hand-written fixtures, and only fetch_company_facts touches the network.
//
// FINDING: available_date CAN BE REPORTED, NOT ESTIMATED
// -----------------------------------------------------
// README.md says free fundamental sources record period_end but generally
// not available_date, and that the estimated case is therefore the norm.
// That is not true of this source. Every XBRL fact entry carries a `filed`
// field - the actual EDGAR submission date of the filing that reported it:
//
//   {"start":"2022-09-25","end":"2023-09-30","val":96995000000,
//    "accn":"0000320193-23-000106","form":"10-K","filed":"2023-11-03"}
//
// So `filed` IS available_date, measured rather than assumed, and a run
// built on this source records fundamentals_availability = "reported".
// `filed` is also conservative in the right direction: companies usually
// press-release earnings days-to-weeks BEFORE the 10-Q reaches EDGAR, so
// using it means the backtest sees the numbers slightly later than the
// market did, which is the pessimistic side README.md asks for.
//
// EVERY VINTAGE IS KEPT. THIS IS NOT AN OPTIMISATION OVERSIGHT.
// ------------------------------------------------------------
// The same period is reported many times: once in its own filing, then
// again as a comparative column in later filings, and again if it is
// restated. Apple's FY2022 net income appears with filed dates of
// 2022-10-28, 2023-11-03 and 2024-11-01.
//
// extract_facts deliberately does NOT collapse those to one row. Keeping
// only the latest vintage looks like harmless deduplication and is in fact
// look-ahead bias: a backtest simulating 2023 would read the FY2022 figure
// as restated in 2024. The whole point of carrying two dates is that the
// answer depends on WHEN you ask, so the table has to hold every answer and
// let the as-of selection pick. (Caught here by measurement, on a probe that
// had made exactly this mistake.)
//
// TTM MUST BE CONSTRUCTED - THERE IS NO Q4 FILING
// -----------------------------------------------
// US filers do not file a Q4 10-Q; the fourth quarter exists only implicitly
// inside the 10-K. Measured on Apple: the `fp` field takes the values Q1,
// Q2, Q3 and FY, never Q4, and FY2023 net income of 96,995m compares with
// only 74,039m across the three reported quarters. So "sum the last four
// quarterly entries" - the obvious implementation - is wrong at every fiscal
// year end, and wrong silently.
//
// What XBRL does report directly is year-to-date cumulative figures at each
// quarter (1, 2 and 3 quarters long) plus the annual figure. assemble_ttm
// therefore uses the roll-forward identity:
//
//     TTM = FY(prior year) + YTD(current, q quarters)
//                          - YTD(prior year, same q quarters)
//
// verified against an independent second construction (derive the implied
// prior Q4 from FY minus its own 9-month YTD, then accumulate) on all 49
// computable dates of Apple's history, with zero disagreements.
//
// A TTM figure becomes available when its LAST component does, which in
// practice is the filing that reported the current YTD - so each YTD vintage
// yields one TTM row, and a restatement of a component yields another.

#include <gm-core/error.hpp>
#include <gm-io/http_cache.hpp>

#include <nlohmann/json_fwd.hpp>

#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace gm::data {

/// One XBRL fact exactly as SEC reported it, with no deduplication applied.
struct XbrlFact {
    std::string period_start;    ///< empty for an instant (balance-sheet item)
    std::string period_end;      ///< SEC "end"
    std::string available_date;  ///< SEC "filed" - the EDGAR submission date
    std::string form;            ///< "10-K", "10-Q", "10-K/A", "8-K", ...
    std::string accession;       ///< SEC "accn", for provenance
    double value{};
};

/// Pulls every fact for one taxonomy/tag/unit out of a companyfacts document,
/// in document order, keeping all vintages. A tag that is absent is NOT an
/// error - filers use different tags for the same concept - so this returns
/// an empty vector and lets the caller try the next candidate. A malformed
/// entry is an error, because that means the document shape is not what this
/// code understands.
///
/// `unit` is the key under "units", e.g. "USD" or "shares".
[[nodiscard]] Result<std::vector<XbrlFact>> extract_facts(const nlohmann::json& companyfacts,
                                                           std::string_view taxonomy,
                                                           std::string_view tag,
                                                           std::string_view unit);

/// How many fiscal quarters a duration fact spans, rounded to the nearest
/// quarter; 0 for an instant, and 0 if either date fails to parse. Rounded
/// because fiscal quarters are 13-week periods of uneven length, so an exact
/// day count discriminates nothing useful.
[[nodiscard]] int quarters_spanned(const XbrlFact& fact);

/// A trailing-twelve-month figure and the date it became knowable.
struct TtmPoint {
    std::string period_end;      ///< end of the twelve-month window
    std::string available_date;  ///< when the last component was filed
    double value{};
};

/// Builds every TTM vintage derivable from `facts` using the roll-forward
/// identity in the header comment. Facts that cannot be placed - a YTD
/// figure whose prior fiscal year is not in the data, an interim period from
/// before the first annual report - are skipped rather than guessed at.
///
/// Returns kValidationFailure if there is no annual figure at all, since
/// without one no twelve-month window can be anchored.
///
/// Output is sorted by (period_end, available_date) with exact duplicates
/// removed; comparative re-reporting produces genuinely identical rows.
[[nodiscard]] Result<std::vector<TtmPoint>> assemble_ttm(const std::vector<XbrlFact>& facts);

/// For a balance-sheet item (an instant), the index of the fact describing
/// the most recent instant published on or before `as_of`; ties on the
/// instant broken by the later filing, so a restatement wins once published.
/// The same two-date rule as gm::features::select_as_of, over instants.
///
/// Returns nullopt when nothing has been published yet.
[[nodiscard]] std::optional<std::size_t> latest_instant_as_of(const std::vector<XbrlFact>& facts,
                                                               std::string_view as_of);

// ---------------------------------------------------------------------------
// CONCEPT RESOLUTION: EBITDA AND ENTERPRISE VALUE ARE NOT XBRL CONCEPTS
// ---------------------------------------------------------------------------
//
// Net income has a tag. EBITDA does not - it has to be assembled from an
// operating-income subtotal plus depreciation and amortisation, and each of
// those appears under several different tags depending on the filer. There
// is no combined total-debt tag either. So every field below the first is a
// CHAIN of candidate tags, tried in order, plus an assembly rule.
//
// The chains below were measured, not guessed. Downloading companyfacts for
// 40 S&P 500 issuers sampled across the alphabet and counting how many have
// each tag at all:
//
//   concept                    best single tag        chain     missing
//   net income                 NetIncomeLoss 39/40     40/40    -
//   operating income           OperatingIncomeLoss     34/40    C COP DHI EMR FOX STT
//   depreciation+amortisation  DDA 29/40               40/40    -
//   operating cash flow        NCPBUIOA 40/40          40/40    -
//   capital expenditure        PTAPPE 32/40            39/40    APA
//   long-term debt             LongTermDebt 32/40      35/40    AKAM BRK.B DHI GM TTD
//   short-term debt            LTDebtCurrent 25/40     32/40    (8 issuers)
//   cash and equivalents       CCEACV 38/40            39/40    FDXF
//   short-term investments     ShortTermInvestments    24/40    (16 issuers)
//   share count                WANOSOB 40/40           40/40    -
//
// Two conclusions follow, and both are design decisions rather than
// implementation details:
//
// 1. REQUIRED vs OPTIONAL absence are different things. An issuer that
//    reports no ShortTermInvestments tag almost certainly HAS no marketable
//    securities - nobody files a zero, they omit the line - so reading
//    absence as zero is correct. An issuer with no cash tag is a gap, and
//    reading THAT as zero would fabricate a number. The same distinction
//    applies to short-term debt (optional) versus long-term debt (required).
//    Every zero substitution is counted and published; see
//    FundamentalsBuild::substituted_zero.
//
// 2. Composed per yield, the honest coverage is:
//
//      E/P        40/40 issuers (100%)
//      FCF/P      39/40 issuers  (98%)   - APA reports no capex tag
//      EBITDA/EV  29/40 issuers  (72%)
//
//    and the eleven EBITDA/EV misses are mostly STRUCTURAL rather than data
//    gaps. Citigroup and State Street have no operating-income subtotal
//    because a bank's income statement is not built that way, and EBITDA is
//    close to meaningless for a bank regardless. This is why
//    gm::features::ValuationYields makes each coordinate independently
//    optional: rejecting those issuers outright would discard two perfectly
//    good coordinates for the sake of a third that does not apply to them.

/// One candidate tag: where to look and in what unit.
struct TagCandidate {
    std::string_view taxonomy;  ///< "us-gaap" or "dei"
    std::string_view tag;
    std::string_view unit;      ///< "USD" or "shares"
};

/// An accounting concept and the tags real filers use for it, best first.
struct ConceptChain {
    std::string_view name;                     ///< snake_case, used as a manifest key
    std::vector<TagCandidate> candidates;
    /// True when absence most likely means the issuer HAS none of this, so
    /// zero is the correct reading rather than a guess. See the note above.
    bool absence_means_zero{false};
    /// Components to ADD when no single candidate above resolved, used where
    /// an issuer reports the parts but not the total. ALL of them must be
    /// present or the concept is absent: summing a subset produces a
    /// plausible number that is quietly too small, which is worse than no
    /// number at all. Measured need: three of twelve issuers in the first
    /// real run reported no depreciation-and-amortisation aggregate.
    std::vector<TagCandidate> sum_components;
};

/// The flow concepts (income statement, cash-flow statement). These are
/// reported year-to-date and get turned into TTM by assemble_ttm.
[[nodiscard]] const std::vector<ConceptChain>& flow_concepts();

/// The instant concepts (balance sheet, share count), read as-of a date.
[[nodiscard]] const std::vector<ConceptChain>& instant_concepts();

/// Which candidate actually resolved, and the facts it yielded.
struct ResolvedConcept {
    std::string tag_used;  ///< "us-gaap:NetIncomeLoss"; empty when none matched
    std::vector<XbrlFact> facts;
};

/// Tries each candidate in order and returns the first that yields any facts.
/// An entirely absent concept is NOT an error - that is the normal state for
/// several concepts at several issuers, and is what absence_means_zero and
/// the coverage counters exist to describe.
[[nodiscard]] Result<ResolvedConcept> resolve_concept(const nlohmann::json& companyfacts,
                                                       const ConceptChain& chain);

/// One row of fundamentals.parquet for one issuer, before the ticker is
/// attached. Fields that could not be assembled are NaN, which the consumer
/// (gm::features::compute_valuation_yields) turns back into an explicit
/// per-coordinate status - NaN never reaches a coordinate.
struct FundamentalsRecord {
    std::string period_end;
    std::string available_date;
    double net_income_ttm{};
    double ebitda_ttm{};
    double free_cash_flow_ttm{};
    double total_debt{};
    double cash_and_equivalents{};
    double shares_outstanding{};
};

struct FundamentalsBuild {
    std::vector<FundamentalsRecord> rows;
    /// concept name -> the tag that resolved, or "" when none did. Published
    /// so a reader can see WHICH tag produced a number rather than trusting
    /// that some tag did.
    std::map<std::string, std::string> tag_used;
    /// concept name -> how many rows read an absent optional concept as zero
    /// because the issuer reports that concept NOWHERE. A permanent property
    /// of the filer: it holds none of this.
    std::map<std::string, std::int64_t> substituted_zero;
    /// concept name -> how many rows read it as zero because nothing had been
    /// published by that row's available_date, even though the issuer does
    /// report it elsewhere. A property of early history, not of the filer,
    /// and counted apart because the two call for different responses.
    std::map<std::string, std::int64_t> substituted_zero_not_yet_published;
    /// field name -> how many rows assembled it from a figure describing an
    /// EARLIER period than the row's own period_end. Not an error - it is the
    /// most recent figure that was public at the time, which is what an
    /// analyst would use - but it means two coordinates on that row can
    /// describe different periods, and that is worth being able to see.
    std::map<std::string, std::int64_t> stale_component;
};

/// Assembles every point-in-time fundamentals vintage derivable from one
/// issuer's companyfacts document.
///
/// Rows are anchored on the net-income TTM vintages, because net income is
/// the one concept present for every issuer measured and because each TTM
/// vintage corresponds to one filing - which is exactly the granularity
/// `available_date` needs. Balance-sheet items are then read as of that
/// vintage's own available_date, never later, so a row never contains a
/// number published after the date it claims to be knowable on.
///
/// Returns kValidationFailure only when no net-income TTM can be built at
/// all; every other absence produces NaN in the affected field and a count.
[[nodiscard]] Result<FundamentalsBuild> build_fundamentals(const nlohmann::json& companyfacts);

/// Fetches a company's raw companyfacts JSON through the mandatory cache
/// (ADR-015). Returns the response body; the caller parses it once and calls
/// extract_facts per tag. Deliberately not returning a parsed document, so
/// this header needs only nlohmann's forward declarations.
[[nodiscard]] Result<std::string> fetch_company_facts(gm::io::HttpCache& cache, std::int64_t cik);

} // namespace gm::data
