#pragma once

// SEC 8-K filing dates (ADR-013: "the same [reversion rate], conditioned
// on an earnings date or 8-K inside the window" - an unmasked earnings
// gap is a beautiful, untradeable "dislocation," and the reversion
// study needs to be able to tell those apart from genuine noise-driven
// excursions). Fetches from SEC EDGAR's submissions API
// (data.sec.gov/submissions/CIK##########.json), the ADR's documented
// primary source (Sec7.5).

#include <gm-core/error.hpp>
#include <gm-io/http_cache.hpp>

#include <nlohmann/json_fwd.hpp>

#include <cstdint>
#include <set>
#include <string>
#include <vector>

namespace gm::signals {

struct FilingDate {
    std::string date; // ISO-8601 filing date
    std::string form;  // SEC form type, e.g. "8-K", "10-Q"
};

/// Extracts (form, filingDate) pairs from one SEC submissions-shaped
/// JSON node - the flat, parallel-array "form"/"filingDate" fields SEC
/// uses both for the top-level "filings.recent" object and every
/// paginated historical file (same shape, no extra nesting in the
/// paginated case). Filtered to `form_types` (all forms if empty).
///
/// Exposed publicly (not folded entirely into fetch_filing_dates)
/// specifically so this JSON-shape-handling logic - where the real
/// correctness risk concentrates (mismatched array lengths, missing
/// fields, malformed entries) - is directly unit-testable against
/// hand-crafted JSON fixtures, without requiring a live network call in
/// the fast test suite. All navigation happens inside ONE try/catch
/// internally (ADR-019: no exception crosses a library boundary).
[[nodiscard]] Result<std::vector<FilingDate>> extract_filings(const nlohmann::json& node,
                                                                const std::set<std::string>& form_types);

/// Fetches the COMPLETE filing history for `cik` - not just the most
/// recent ~1000 filings SEC's API returns inline ("filings.recent"),
/// but every additional paginated file it references under
/// "filings.files" too. This matters concretely: for a name with a
/// long filing history, "recent" alone can start as late as 2015,
/// silently missing everything from ADR-002's 2010 start date onward
/// without the pagination follow-up. Every fetch goes through `cache`
/// (mandatory per ADR-015): a CIK's filing history before today only
/// grows, so a cached page stays valid indefinitely.
///
/// `form_types` filters the result (case-sensitive exact match against
/// SEC's own form strings, e.g. {"8-K"}); pass an empty vector for
/// every form type.
[[nodiscard]] Result<std::vector<FilingDate>> fetch_filing_dates(gm::io::HttpCache& cache, std::int64_t cik,
                                                                   const std::vector<std::string>& form_types);

} // namespace gm::signals
