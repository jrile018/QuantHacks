#pragma once

// SEC company profile fetching for the Learn panel (ADR §8.2, M6).
// Fetches from SEC EDGAR's submissions API (data.sec.gov/submissions/CIK##########.json),
// extracts SIC code and company description, and generates meta/profiles.json.
// Uses the same HttpCache pattern as earnings.cpp (ADR-015).

#include <gm-core/error.hpp>
#include <gm-io/http_cache.hpp>

#include <nlohmann/json_fwd.hpp>

#include <cstdint>
#include <map>
#include <string>

namespace gm::profiles {

/// A company profile extracted from SEC EDGAR submissions data.
struct CompanyProfile {
    std::string ticker;           // S&P 500 ticker symbol
    std::string company_name;     // CIK entity name from SEC
    std::int64_t sic_code = 0;    // 4-digit SIC code
    std::string sic_description;  // Human-readable SIC description
    std::string edgar_url;        // URL to EDGAR filing index for this CIK
};

/// Fetches company profile data from SEC EDGAR submissions JSON for a single CIK.
/// Extracts company name, SIC code, SIC description, and generates EDGAR URL.
/// Returns kNotFound if the CIK doesn't exist on SEC EDGAR, kIoFailure on network
/// errors, kParseFailure if the response is malformed.
[[nodiscard]] gm::Result<CompanyProfile> fetch_company_profile(gm::io::HttpCache& cache,
                                                                 const std::string& ticker,
                                                                 std::int64_t cik);

} // namespace gm::profiles
