#include <gm-profiles/profiles.hpp>

#include <nlohmann/json.hpp>

#include <cstdio>
#include <stdexcept>

namespace gm::profiles {

namespace {

std::string zero_padded_cik(std::int64_t cik) {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%010lld", static_cast<long long>(cik));
    return std::string{buf};
}

}  // namespace

gm::Result<CompanyProfile> fetch_company_profile(gm::io::HttpCache& cache,
                                                   const std::string& ticker,
                                                   std::int64_t cik) {
    std::string padded = zero_padded_cik(cik);
    std::string primary_url = "https://data.sec.gov/submissions/CIK" + padded + ".json";
    auto primary_entry = cache.get(primary_url, "sec_submissions_CIK" + padded);
    if (!primary_entry) return tl::unexpected(primary_entry.error());

    auto primary_body = primary_entry->read_body();
    if (!primary_body) return tl::unexpected(primary_body.error());

    nlohmann::json doc;
    try {
        doc = nlohmann::json::parse(*primary_body);

        // Check for required fields in the SEC submissions response.
        // The SEC API returns: "cik" (string), "name", "sic" (string!), "sicDescription"
        if (!doc.contains("cik") || !doc.contains("name") ||
            !doc.contains("sic") || !doc.contains("sicDescription")) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure,
                "SEC submissions response missing required fields (cik, name, sic, sicDescription)",
                "ticker " + ticker + ", CIK " + padded));
        }

        CompanyProfile profile;
        profile.ticker = ticker;
        profile.company_name = doc.at("name").get<std::string>();
        
        // SIC is a string in the SEC response, convert it to int64
        std::string sic_str = doc.at("sic").get<std::string>();
        try {
            profile.sic_code = std::stoll(sic_str);
        } catch (const std::exception& e) {
            // std::exception, not std::invalid_argument: stoll also throws
            // out_of_range, and catching only the first let a twenty-digit
            // SIC field propagate an exception across a library boundary,
            // which ADR-019 forbids. The exception's own message says which
            // of the two it was, so it goes into the context rather than
            // being discarded - discarding it was also what made MSVC warn.
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure,
                "SIC code is not a valid number: " + sic_str,
                "ticker " + ticker + ", CIK " + padded + ": " + e.what()));
        }
        
        profile.sic_description = doc.at("sicDescription").get<std::string>();
        profile.edgar_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=" +
                            padded + "&type=&dateb=&owner=include&count=40";

        return profile;

    } catch (const nlohmann::json::parse_error& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "SEC submissions response is not valid JSON",
                                               "ticker " + ticker + ", CIK " + padded + ": " + e.what()));
    } catch (const nlohmann::json::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "SEC submissions response has an unexpected shape",
                                               "ticker " + ticker + ", CIK " + padded + ": " + e.what()));
    }
}

}  // namespace gm::profiles
