#include <gm-signals/earnings.hpp>

#include <nlohmann/json.hpp>

#include <cstdio>

namespace gm::signals {

namespace {

std::string zero_padded_cik(std::int64_t cik) {
    char buf[16];
    std::snprintf(buf, sizeof(buf), "%010lld", static_cast<long long>(cik));
    return std::string{buf};
}

} // namespace

Result<std::vector<FilingDate>> extract_filings(const nlohmann::json& node,
                                                 const std::set<std::string>& form_types) {
    std::vector<FilingDate> result;
    try {
        if (!node.contains("form") || !node.contains("filingDate")) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                                   "SEC submissions object missing form/filingDate"));
        }
        const auto& forms = node.at("form");
        const auto& dates = node.at("filingDate");
        if (forms.size() != dates.size()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure, "SEC submissions form/filingDate arrays have mismatched length",
                std::to_string(forms.size()) + " vs " + std::to_string(dates.size())));
        }
        for (std::size_t i = 0; i < forms.size(); ++i) {
            std::string form = forms[i].get<std::string>();
            if (!form_types.empty() && form_types.count(form) == 0) continue;
            result.push_back(FilingDate{dates[i].get<std::string>(), std::move(form)});
        }
    } catch (const nlohmann::json::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "SEC submissions object has an unexpected shape", e.what()));
    }
    return result;
}

Result<std::vector<FilingDate>> fetch_filing_dates(gm::io::HttpCache& cache, std::int64_t cik,
                                                    const std::vector<std::string>& form_types) {
    std::set<std::string> wanted(form_types.begin(), form_types.end());
    std::string padded = zero_padded_cik(cik);

    std::string primary_url = "https://data.sec.gov/submissions/CIK" + padded + ".json";
    auto primary_entry = cache.get(primary_url, "sec_submissions_CIK" + padded);
    if (!primary_entry) return tl::unexpected(primary_entry.error());
    auto primary_body = primary_entry->read_body();
    if (!primary_body) return tl::unexpected(primary_body.error());

    nlohmann::json doc;
    std::vector<std::string> pagination_files;
    try {
        doc = nlohmann::json::parse(*primary_body);
        if (!doc.contains("/filings/recent"_json_pointer)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure, "SEC submissions response has no filings.recent",
                "CIK " + padded));
        }
        if (doc.contains("/filings/files"_json_pointer)) {
            for (const auto& file_entry : doc.at("/filings/files"_json_pointer)) {
                pagination_files.push_back(file_entry.at("name").get<std::string>());
            }
        }
    } catch (const nlohmann::json::parse_error& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "SEC submissions response is not valid JSON",
                                               "CIK " + padded + ": " + e.what()));
    } catch (const nlohmann::json::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "SEC submissions response has an unexpected shape",
                                               "CIK " + padded + ": " + e.what()));
    }

    std::vector<FilingDate> result;
    auto recent = extract_filings(doc.at("/filings/recent"_json_pointer), wanted);
    if (!recent) return tl::unexpected(recent.error());
    result.insert(result.end(), recent->begin(), recent->end());

    // Older filings live in separately-paginated files SEC references
    // by name (e.g. "CIK0000320193-submissions-001.json") - "recent"
    // alone can start as late as 2015 for a name with a long filing
    // history, silently missing everything from ADR-002's 2010 start
    // date onward without this follow-up.
    for (const auto& file_name : pagination_files) {
        std::string url = "https://data.sec.gov/submissions/" + file_name;
        auto entry = cache.get(url, "sec_submissions_page_" + file_name);
        if (!entry) return tl::unexpected(entry.error());
        auto body = entry->read_body();
        if (!body) return tl::unexpected(body.error());

        nlohmann::json page_doc;
        try {
            page_doc = nlohmann::json::parse(*body);
        } catch (const nlohmann::json::parse_error& e) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                                   "SEC submissions pagination file is not valid JSON",
                                                   file_name + ": " + e.what()));
        }
        auto page_filings = extract_filings(page_doc, wanted);
        if (!page_filings) return tl::unexpected(page_filings.error());
        result.insert(result.end(), page_filings->begin(), page_filings->end());
    }

    return result;
}

} // namespace gm::signals
