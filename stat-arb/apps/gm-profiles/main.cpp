// gm-profiles: SEC company profile fetching for the Learn panel (ADR §8.2, M6).
// Reads gm-universe's universe.parquet to get ticker/CIK pairs, fetches company
// profiles from SEC EDGAR's submissions JSON API, and generates meta/profiles.json
// with SIC codes, descriptions, and links.

#include <gm-core/stage_main.hpp>
#include <gm-io/http_cache.hpp>
#include <gm-io/parquet.hpp>
#include <gm-profiles/profiles.hpp>

#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <map>

namespace {

gm::VoidResult run_gm_profiles(const gm::Config& config, const std::filesystem::path& output_dir,
                                gm::Manifest& manifest) {
    // This stage never created its own output directory (unlike every
    // other stage app, e.g. gm-signals) - confirmed by an actual real
    // run against the real universe: SEC fetching genuinely succeeded
    // (259s of real EDGAR calls), but the final profiles.json write
    // failed with kIoFailure because output_dir didn't exist yet.
    std::error_code ec;
    std::filesystem::create_directories(output_dir, ec);
    if (ec) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to create output directory", output_dir.string()));
    }

    // Sibling stage directory, same output_dir.parent_path()/"gm-<stage>"
    // convention gm-signals/gm-boundaries/gm-geometry already use for
    // reading upstream artifacts (see e.g. apps/gm-signals/main.cpp) -
    // works against the real config/params.toml with no extra setup,
    // unlike the old required-but-absent upstream.universe_parquet key.
    // An explicit config override is still honored first, for anyone
    // who wants to point this stage at a universe.parquet living
    // somewhere else (e.g. a hand-built fixture).
    std::filesystem::path upstream_path;
    auto upstream_override = config.get_string("upstream.universe_parquet");
    if (upstream_override) {
        upstream_path = *upstream_override;
    } else {
        upstream_path = output_dir.parent_path() / "gm-universe" / "universe.parquet";
    }
    if (!std::filesystem::exists(upstream_path)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNotFound,
                                               "upstream universe.parquet not found",
                                               upstream_path.string()));
    }

    // Read universe.parquet to get unique ticker/CIK pairs
    auto universe_table = gm::io::read_parquet(upstream_path);
    if (!universe_table) return tl::unexpected(universe_table.error());

    auto tickers_col = universe_table->string_column("ticker");
    if (!tickers_col) return tl::unexpected(tickers_col.error());
    auto ciks_col = universe_table->int64_column("cik");
    if (!ciks_col) return tl::unexpected(ciks_col.error());

    // Map unique CIK -> ticker (use the first occurrence of each CIK)
    std::map<std::int64_t, std::string> cik_to_ticker;
    for (std::size_t i = 0; i < tickers_col->size(); ++i) {
        std::int64_t cik = (*ciks_col)[i];
        if (cik_to_ticker.find(cik) == cik_to_ticker.end()) {
            cik_to_ticker[cik] = (*tickers_col)[i];
        }
    }

    // Initialize HTTP cache for SEC fetching
    auto cache_dir = config.get_string_or("http_cache.directory", "data/raw/profiles_cache");
    gm::io::HttpCache cache(cache_dir);

    // Fetch profiles for each unique CIK
    std::map<std::string, nlohmann::json> profiles_by_ticker;
    std::int64_t success_count = 0;
    std::int64_t fail_count = 0;

    for (const auto& [cik, ticker] : cik_to_ticker) {
        auto profile = gm::profiles::fetch_company_profile(cache, ticker, cik);
        if (!profile) {
            // Log the error but continue
            fail_count++;
            continue;
        }

        // Build JSON object for this profile. Canonical profiles.json
        // schema (must match gm::view::TickerProfile in
        // apps/gm-view/data_loader.hpp exactly - field names AND
        // types): ticker, company_name, sic_code (STRING - SIC codes
        // are conventionally treated as codes, not numbers, and a
        // string survives a leading-zero code without loss),
        // sic_description, edgar_url. CompanyProfile::sic_code is
        // int64_t (it comes off SEC's JSON as a bare number), so it's
        // converted to a string here at the one point that matters.
        nlohmann::json profile_json;
        profile_json["ticker"] = profile->ticker;
        profile_json["company_name"] = profile->company_name;
        profile_json["sic_code"] = std::to_string(profile->sic_code);
        profile_json["sic_description"] = profile->sic_description;
        profile_json["edgar_url"] = profile->edgar_url;

        profiles_by_ticker[ticker] = profile_json;
        success_count++;
    }

    // Build final profiles object - indexed by ticker for fast lookup by the viewer
    nlohmann::json profiles_data = nlohmann::json::object();
    for (const auto& [ticker, profile_json] : profiles_by_ticker) {
        profiles_data[ticker] = profile_json;
    }

    // Write meta/profiles.json - ADR §8.2's artifact contract documents
    // this artifact as living at runs/<run_id>/meta/profiles.json, a
    // sibling of every stage's own output_dir (run_dir/gm-<stage>/),
    // not nested inside this stage's own output_dir - matching the
    // file-header comment above and how the viewer (data_loader.cpp)
    // looks for it: run_dir / "meta" / "profiles.json".
    auto meta_dir = output_dir.parent_path() / "meta";
    std::filesystem::create_directories(meta_dir, ec);
    if (ec) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to create meta directory", meta_dir.string()));
    }
    auto output_file = meta_dir / "profiles.json";
    std::ofstream out(output_file);
    if (!out) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "Failed to open profiles.json for writing",
                            output_file.string()));
    }
    out << profiles_data.dump(2);
    if (!out) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "Failed to write profiles.json",
                            output_file.string()));
    }
    out.close();

    manifest.set_int("unique_ciks", static_cast<std::int64_t>(cik_to_ticker.size()));
    manifest.set_int("profiles_fetched", success_count);
    manifest.set_int("profiles_failed", fail_count);

    return {};
}

}  // namespace

int main(int argc, char** argv) {
    return gm::run_stage_main(argc, argv, "gm-profiles", run_gm_profiles);
}
