// gm-ingest: price ingestion, caching, and ADR-015 validation (ADR §7.2,
// §5.4/M1 exit criterion: "validated price panel builds locally;
// coverage stats reported").
//
// Reads gm-universe's upstream artifact (runs/<run_id>/gm-universe/universe.parquet,
// a sibling directory per gm-run's fixed layout - ADR §8.2) to get the
// distinct ticker set and date range, fetches each ticker's daily OHLCV
// history from Yahoo's chart endpoint (promoted to primary during M1,
// see ADR §7.2) through gm-io's mandatory HttpCache, and writes one
// combined validated prices.parquet.
//
// Validation screens actually implemented in M1 (ADR-015's full list is
// larger; what's here is real, not stubbed, and the rest is a
// documented follow-up, not a silent gap):
//   - null bars (Yahoo occasionally has a timestamp with no trade data)
//     are dropped and counted, never silently zero-filled
//   - a day-over-day adjusted-close log return beyond +/-50% rejects
//     that ticker's whole fetch (a jump that large in the split-
//     adjusted series is far more likely a bad tick than a real
//     one-day move) rather than silently including a probable data
//     error
//   - zero-volume trading days are counted and reported, not rejected
//     outright (illiquid names and real halts do have zero-volume days)
//   - gaps of more than 3 trading days between consecutive bars
//     (checked against the NYSE calendar) are counted and reported
//   - retroactive changes: when ingest.compare_against_run names an
//     earlier run, every (ticker, date) present in both panels is
//     compared and any bar whose price moved is counted and reported.
//     Vendors revise history - a late split, a corrected tick, a restated
//     dividend - and when they do, a backtest silently produces a
//     different answer from the one it produced last week with no way to
//     tell whether the strategy changed or the past did.
// NOT yet implemented (tracked, not hidden): two-source cross-validation
// against Tiingo, which needs a second wired-in source and an API key
// this project does not have.

#include <gm-core/calendar.hpp>
#include <gm-core/stage_main.hpp>
#include <gm-data/fundamentals.hpp>
#include <gm-data/revisions.hpp>
#include <gm-data/liquidity.hpp>
#include <gm-io/http_cache.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>

#include <spdlog/spdlog.h>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <map>
#include <set>
#include <utility>

namespace {

using namespace std::chrono;

gm::Date epoch_seconds_to_date(std::int64_t epoch_seconds) {
    auto tp = sys_seconds{seconds{epoch_seconds}};
    return gm::Date{date::floor<date::days>(tp)};
}

std::int64_t date_to_epoch_seconds_midnight_utc(const gm::Date& d) {
    return duration_cast<seconds>(d.sys_days().time_since_epoch()).count();
}

/// One ticker's fetch, parsed and screened. Kept separate from the
/// combined Table assembly below so a single ticker's rejection doesn't
/// require unwinding partially-appended columns in the shared table.
struct TickerBars {
    std::vector<std::string> dates;  // ISO, ascending
    std::vector<double> open, high, low, close, adjclose;
    std::vector<std::int64_t> volume;
    std::int64_t dropped_null_bars = 0;
    std::int64_t zero_volume_days = 0;
    std::int64_t gap_days_over_3 = 0;
};

/// Yahoo's chart endpoint uses a dash for dual-class share tickers
/// (e.g. "BRK-B", "BF-B") where the S&P 500 snapshot - sourced from
/// Wikipedia, ADR §7.1 - uses a dot ("BRK.B", "BF.B"). Found via this
/// milestone's own real 503-ticker coverage report: both dotted names
/// were failing with "missing timestamp/indicators" (BF.B) or an
/// outright 404 (BRK.B), because Yahoo simply doesn't recognize the
/// dotted form as a symbol at all. Translated only for the outbound
/// request URL - `ticker` (the canonical, dotted form) is still what's
/// written to every output column and used as the cache key, so this
/// stays invisible to everything downstream of this one function.
std::string to_yahoo_symbol(const std::string& ticker) {
    std::string yahoo_ticker = ticker;
    std::replace(yahoo_ticker.begin(), yahoo_ticker.end(), '.', '-');
    return yahoo_ticker;
}

gm::Result<TickerBars> fetch_and_screen(gm::io::HttpCache& cache, const gm::NyseCalendar& calendar,
                                         const std::string& ticker, const gm::Date& start,
                                         const gm::Date& end) {
    std::string url = "https://query1.finance.yahoo.com/v8/finance/chart/" + to_yahoo_symbol(ticker) +
                       "?period1=" + std::to_string(date_to_epoch_seconds_midnight_utc(start)) +
                       "&period2=" +
                       std::to_string(date_to_epoch_seconds_midnight_utc(end) + 86400) +
                       "&interval=1d&events=div,splits";
    std::string cache_key = "yahoo_" + ticker + "_" + start.to_iso() + "_" + end.to_iso();
    // Cache key characters must satisfy HttpCache's validate_cache_key
    // (no '/', '\', or ".."); ISO dates and tickers never contain those.

    auto entry = cache.get(url, cache_key);
    if (!entry) return tl::unexpected(entry.error());

    auto body = entry->read_body();
    if (!body) return tl::unexpected(body.error());

    nlohmann::json doc;
    try {
        doc = nlohmann::json::parse(*body);
    } catch (const nlohmann::json::parse_error& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "Yahoo chart response is not valid JSON",
                                               ticker + ": " + e.what()));
    }

    // Everything below navigates and reads `doc` via nlohmann's
    // .at()/.contains()/operator[]/.get<T>(), every one of which can
    // throw (json::out_of_range, json::type_error, ...) if Yahoo's
    // response shape doesn't match what's assumed here - e.g. a ticker
    // it doesn't recognize, or a field the API renames. The whole
    // navigation+extraction pass is one try block for exactly that
    // reason (ADR-019: exceptions must not escape past a stage's error
    // boundary; a per-.at()-call try/catch would be unreadable and easy
    // to miss one of on the next edit - a real bug the M1 code review
    // caught here). `bars` is declared outside the try only because its
    // std::vector<std::string>/double/... members are safe to touch
    // after the block; nothing about their construction can throw a
    // json exception.
    TickerBars bars;
    try {
        // nlohmann::json::find() only searches immediate object keys -
        // it does NOT take a json_pointer for path traversal (that was
        // a real bug here initially, not just the deprecation warning
        // that caught it: .contains()/.at() are the pointer-aware
        // members).
        if (!doc.contains("/chart/result"_json_pointer)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure, "Yahoo chart response has no chart.result", ticker));
        }
        const auto& results = doc.at("/chart/result"_json_pointer);
        if (!results.is_array() || results.empty()) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                                   "Yahoo chart response has an empty result", ticker));
        }
        const auto& result = results[0];

        if (!result.contains("timestamp") || !result.contains("indicators")) {
            return tl::unexpected(
                gm::Error::make(gm::ErrorCode::kParseFailure,
                                 "Yahoo chart result missing timestamp/indicators", ticker));
        }
        const auto& timestamps = result.at("timestamp");
        const auto& quote = result.at("/indicators/quote/0"_json_pointer);
        const auto& adjclose_arr = result.at("/indicators/adjclose/0/adjclose"_json_pointer);

        double prev_adjclose = 0.0;
        bool have_prev = false;
        std::optional<gm::Date> prev_date;

        for (std::size_t i = 0; i < timestamps.size(); ++i) {
            const auto& close_v = quote.at("close")[i];
            const auto& volume_v = quote.at("volume")[i];
            const auto& adjclose_v = adjclose_arr[i];

            if (close_v.is_null() || volume_v.is_null() || adjclose_v.is_null()) {
                ++bars.dropped_null_bars;
                continue;
            }

            double adjclose = adjclose_v.get<double>();

            if (have_prev && prev_adjclose > 0.0) {
                // ADR-015/§7.2 specify a symmetric +/-50% price-ratio
                // bound, not a symmetric bound on the LOG return - those
                // are different things: |log(ratio)| > log(1.5) triggers
                // on any drop beyond -33.3%, not -50%, because a fixed
                // log-return magnitude corresponds to +50% on the
                // upside but only -33.3% on the downside (ratios 1.5 and
                // 1/1.5 aren't symmetric around 1.0 the way +50%/-50%
                // are). Caught by inspecting this milestone's own real
                // rejected-ticker report: WST's genuine -38.2% single-
                // day move (a real, large, legitimate price change) was
                // being rejected by the log-based check even though it
                // is well within the ADR's stated +/-50% tolerance.
                // Comparing the raw ratio against [0.5, 1.5] directly is
                // both correct and simpler than the log formulation.
                double ratio = adjclose / prev_adjclose;
                if (ratio > 1.5 || ratio < 0.5) {
                    return tl::unexpected(gm::Error::make(
                        gm::ErrorCode::kValidationFailure,
                        "adjusted-close day-over-day return exceeds +/-50% (ADR-015 screen)",
                        ticker + " at index " + std::to_string(i) + ": " +
                            std::to_string(prev_adjclose) + " -> " + std::to_string(adjclose)));
                }
            }
            prev_adjclose = adjclose;
            have_prev = true;

            gm::Date bar_date = epoch_seconds_to_date(timestamps[i].get<std::int64_t>());

            if (prev_date.has_value()) {
                std::int64_t gap = calendar.count_trading_days(*prev_date, bar_date) - 1;
                if (gap > 3) ++bars.gap_days_over_3;
            }
            prev_date = bar_date;

            std::int64_t volume = volume_v.get<std::int64_t>();
            if (volume == 0) ++bars.zero_volume_days;

            bars.dates.push_back(bar_date.to_iso());
            bars.open.push_back(quote.at("open")[i].is_null() ? 0.0 : quote.at("open")[i].get<double>());
            bars.high.push_back(quote.at("high")[i].is_null() ? 0.0 : quote.at("high")[i].get<double>());
            bars.low.push_back(quote.at("low")[i].is_null() ? 0.0 : quote.at("low")[i].get<double>());
            bars.close.push_back(close_v.get<double>());
            bars.adjclose.push_back(adjclose);
            bars.volume.push_back(volume);
        }
    } catch (const nlohmann::json::exception& e) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kParseFailure, "Yahoo chart response has an unexpected shape",
            ticker + ": " + e.what()));
    }

    if (bars.dates.empty()) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kValidationFailure, "no usable bars after screening", ticker));
    }

    return bars;
}

/// Fetches, assembles and writes fundamentals.parquet for every ticker in
/// `tickers` that the universe table carries a CIK for.
///
/// One issuer failing does not stop the stage. A company can be missing from
/// SEC's XBRL API for dull reasons (a foreign private issuer filing 20-F, a
/// recent listing, a CIK that has changed) and for interesting ones, and a
/// price panel is still worth having without its fundamentals. What is NOT
/// acceptable is failing quietly: the per-issuer outcome, the tag that won
/// for each concept, and every zero substituted for an absent optional all
/// reach the manifest.
gm::VoidResult ingest_fundamentals(const gm::io::Table& universe_table,
                                    const std::vector<std::string>& tickers,
                                    gm::io::HttpCache& cache,
                                    const std::filesystem::path& output_dir,
                                    gm::Manifest& manifest) {
    auto ticker_col = universe_table.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto cik_col = universe_table.int64_column("cik");
    if (!cik_col) return tl::unexpected(cik_col.error());

    // std::map, not unordered_map: iteration order is part of the artifact
    // (ADR-003), and this decides the row order of fundamentals.parquet.
    std::map<std::string, std::int64_t> cik_of;
    for (std::size_t i = 0; i < ticker_col->size() && i < cik_col->size(); ++i) {
        cik_of.emplace((*ticker_col)[i], (*cik_col)[i]);
    }

    std::vector<std::string> out_ticker, out_period_end, out_available_date;
    std::vector<double> out_net_income, out_ebitda, out_fcf, out_debt, out_cash, out_shares;

    std::int64_t issuers_ok = 0, issuers_no_cik = 0, issuers_fetch_failed = 0,
                 issuers_unassemblable = 0;
    // concept_name -> how many issuers resolved it to each tag, and how many
    // resolved it to nothing. This is the per-field coverage the README asks
    // for, measured on the run rather than quoted from a probe.
    std::map<std::string, std::map<std::string, std::int64_t>> tag_usage;
    std::map<std::string, std::int64_t> concept_absent;
    std::map<std::string, std::int64_t> zero_substitutions;
    std::map<std::string, std::int64_t> zero_not_yet_published;
    std::map<std::string, std::int64_t> stale_component;
    std::vector<std::string> issuer_failures;

    for (const std::string& ticker : tickers) {
        const auto cik = cik_of.find(ticker);
        if (cik == cik_of.end() || cik->second <= 0) {
            ++issuers_no_cik;
            continue;
        }
        auto body = gm::data::fetch_company_facts(cache, cik->second);
        if (!body) {
            ++issuers_fetch_failed;
            issuer_failures.push_back(ticker + ": " + body.error().message);
            continue;
        }
        nlohmann::json doc;
        try {
            doc = nlohmann::json::parse(*body);
        } catch (const std::exception& e) {
            ++issuers_fetch_failed;
            issuer_failures.push_back(std::string{ticker} + ": unparseable companyfacts: " +
                                       e.what());
            continue;
        }

        auto built = gm::data::build_fundamentals(doc);
        if (!built) {
            // Almost always "no net-income TTM could be assembled" - a real
            // condition for an issuer whose XBRL history is too short to
            // anchor a twelve-month window, not a bug.
            ++issuers_unassemblable;
            issuer_failures.push_back(ticker + ": " + built.error().message);
            continue;
        }

        ++issuers_ok;
        for (const auto& [concept_name, tag] : built->tag_used) {
            if (tag.empty()) {
                ++concept_absent[concept_name];
            } else {
                ++tag_usage[concept_name][tag];
            }
        }
        for (const auto& [concept_name, count] : built->substituted_zero) {
            zero_substitutions[concept_name] += count;
        }
        for (const auto& [concept_name, count] : built->substituted_zero_not_yet_published) {
            zero_not_yet_published[concept_name] += count;
        }
        for (const auto& [field, count] : built->stale_component) stale_component[field] += count;
        for (const auto& row : built->rows) {
            out_ticker.push_back(ticker);
            out_period_end.push_back(row.period_end);
            out_available_date.push_back(row.available_date);
            out_net_income.push_back(row.net_income_ttm);
            out_ebitda.push_back(row.ebitda_ttm);
            out_fcf.push_back(row.free_cash_flow_ttm);
            out_debt.push_back(row.total_debt);
            out_cash.push_back(row.cash_and_equivalents);
            out_shares.push_back(row.shares_outstanding);
        }
    }

    const std::size_t rows = out_ticker.size();
    gm::io::Table table;
    if (auto r = table.add_string_column("ticker", std::move(out_ticker)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_string_column("period_end", std::move(out_period_end)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_string_column("available_date", std::move(out_available_date)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("net_income_ttm", std::move(out_net_income)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("ebitda_ttm", std::move(out_ebitda)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("free_cash_flow_ttm", std::move(out_fcf)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("total_debt", std::move(out_debt)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("cash_and_equivalents", std::move(out_cash)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("shares_outstanding", std::move(out_shares)); !r) return tl::unexpected(r.error());

    auto write = gm::io::write_parquet(table, output_dir / "fundamentals.parquet");
    if (!write) return tl::unexpected(write.error());

    manifest.set_string("fundamentals", "enabled");
    // "reported", never "estimated": every available_date here is an actual
    // EDGAR submission date carried in the source, not a lag assumption
    // added by this pipeline. See gm-data/fundamentals.hpp.
    manifest.set_string("fundamentals_availability", "reported");
    manifest.set_int("fundamentals_rows", static_cast<std::int64_t>(rows));
    manifest.set_int("fundamentals_issuers_ok", issuers_ok);
    manifest.set_int("fundamentals_issuers_no_cik", issuers_no_cik);
    manifest.set_int("fundamentals_issuers_fetch_failed", issuers_fetch_failed);
    manifest.set_int("fundamentals_issuers_unassemblable", issuers_unassemblable);

    nlohmann::json coverage = nlohmann::json::object();
    for (const auto& [concept_name, tags] : tag_usage) {
        nlohmann::json entry = nlohmann::json::object();
        std::int64_t resolved = 0;
        for (const auto& [tag, count] : tags) {
            entry[tag] = count;
            resolved += count;
        }
        entry["_resolved_issuers"] = resolved;
        entry["_absent_issuers"] = concept_absent.count(concept_name) ? concept_absent.at(concept_name) : 0;
        coverage[concept_name] = entry;
    }
    for (const auto& [concept_name, count] : concept_absent) {
        if (!coverage.contains(concept_name)) {
            coverage[concept_name] = {{"_resolved_issuers", 0}, {"_absent_issuers", count}};
        }
    }
    manifest.set_json("fundamentals_tag_coverage", coverage);

    // Two different situations, reported apart: the issuer reports this
    // concept nowhere (a permanent property of the filer, where zero is
    // simply correct) versus it does report it but not by that row's
    // available_date (early history, which fills in).
    nlohmann::json zeros = nlohmann::json::object();
    for (const auto& [concept_name, count] : zero_substitutions) zeros[concept_name] = count;
    manifest.set_json("fundamentals_zero_filer_reports_none", zeros);
    nlohmann::json not_yet = nlohmann::json::object();
    for (const auto& [concept_name, count] : zero_not_yet_published) not_yet[concept_name] = count;
    manifest.set_json("fundamentals_zero_not_yet_published", not_yet);
    // Rows whose EBITDA or free cash flow came from a figure describing an
    // earlier period than the row itself - the most recent one that was
    // public at the time. Not an error; visible so it is not a surprise.
    nlohmann::json stale = nlohmann::json::object();
    for (const auto& [field, count] : stale_component) stale[field] = count;
    manifest.set_json("fundamentals_stale_component_rows", stale);

    if (!issuer_failures.empty()) {
        nlohmann::json failures = nlohmann::json::array();
        for (const auto& f : issuer_failures) failures.push_back(f);
        manifest.set_json("fundamentals_issuer_failures", failures);
    }

    spdlog::info(
        "gm-ingest: fundamentals {} rows from {} issuers ({} no CIK, {} fetch failed, {} could "
        "not be assembled)",
        rows, issuers_ok, issuers_no_cik, issuers_fetch_failed, issuers_unassemblable);
    return {};
}

gm::VoidResult run_gm_ingest(const gm::Config& config, const std::filesystem::path& output_dir,
                              gm::Manifest& manifest) {
    std::filesystem::path universe_parquet =
        output_dir.parent_path() / "gm-universe" / "universe.parquet";
    auto universe_table = gm::io::read_parquet(universe_parquet);
    if (!universe_table) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kIoFailure, "failed to read upstream universe.parquet (ran gm-universe first?)",
            universe_parquet.string() + ": " + universe_table.error().to_string()));
    }

    auto ticker_col = universe_table->string_column("ticker");
    auto date_col = universe_table->string_column("date");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    if (!date_col) return tl::unexpected(date_col.error());

    std::set<std::string> unique_tickers(ticker_col->begin(), ticker_col->end());
    gm::Date range_start = *gm::Date::parse_iso(*std::min_element(date_col->begin(), date_col->end()));
    gm::Date range_end = *gm::Date::parse_iso(*std::max_element(date_col->begin(), date_col->end()));

    std::int64_t max_tickers = config.get_int_or("ingest.max_tickers", -1);
    std::vector<std::string> tickers(unique_tickers.begin(), unique_tickers.end());
    if (max_tickers >= 0 && static_cast<std::int64_t>(tickers.size()) > max_tickers) {
        tickers.resize(static_cast<std::size_t>(max_tickers));
    }

    std::string cache_dir = config.get_string_or("ingest.cache_dir", "data/raw/price_cache");
    gm::io::HttpCache cache{cache_dir};
    gm::NyseCalendar calendar;

    gm::io::Table combined;
    std::vector<std::string> all_ticker, all_date;
    std::vector<double> all_open, all_high, all_low, all_close, all_adjclose;
    std::vector<std::int64_t> all_volume;

    std::int64_t tickers_ok = 0, tickers_rejected = 0;
    std::int64_t total_dropped_null = 0, total_zero_volume = 0, total_gaps = 0;
    std::vector<std::string> rejected_tickers;

    for (const auto& ticker : tickers) {
        auto bars = fetch_and_screen(cache, calendar, ticker, range_start, range_end);
        if (!bars) {
            ++tickers_rejected;
            rejected_tickers.push_back(ticker + ": " + bars.error().to_string());
            continue;
        }
        ++tickers_ok;
        total_dropped_null += bars->dropped_null_bars;
        total_zero_volume += bars->zero_volume_days;
        total_gaps += bars->gap_days_over_3;

        for (std::size_t i = 0; i < bars->dates.size(); ++i) {
            all_ticker.push_back(ticker);
            all_date.push_back(bars->dates[i]);
            all_open.push_back(bars->open[i]);
            all_high.push_back(bars->high[i]);
            all_low.push_back(bars->low[i]);
            all_close.push_back(bars->close[i]);
            all_adjclose.push_back(bars->adjclose[i]);
            all_volume.push_back(bars->volume[i]);
        }
    }

    if (tickers_ok == 0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kValidationFailure,
                                               "every ticker was rejected by validation screens; "
                                               "nothing to write"));
    }

    // Table's add_*_column calls are [[nodiscard]] Result<void> (ADR §3
    // principle 1) - every call constructed identically from vectors
    // whose lengths were built in lockstep above, so a failure here
    // would mean a real bug in this function, not a data problem; still
    // checked and propagated rather than ignored.
    if (auto r = combined.add_string_column("ticker", std::move(all_ticker)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_string_column("date", std::move(all_date)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_double_column("open", std::move(all_open)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_double_column("high", std::move(all_high)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_double_column("low", std::move(all_low)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_double_column("close", std::move(all_close)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_double_column("adjclose", std::move(all_adjclose)); !r) return tl::unexpected(r.error());
    if (auto r = combined.add_int64_column("volume", std::move(all_volume)); !r) return tl::unexpected(r.error());

    auto write_result = gm::io::write_parquet(combined, output_dir / "prices.parquet");
    if (!write_result) return tl::unexpected(write_result.error());

    // Liquidity ranking (ADR-001: "top 100 by trailing 60-day median
    // dollar volume") is computed from what was just fetched, not
    // fetched separately - resolves the chicken-and-egg problem (ranking
    // needs prices, but knowing what to fetch would otherwise need
    // ranking) by writing it as a second, derived artifact rather than
    // destructively filtering prices.parquet down before writing it.
    // Optional: a config that only wants the raw validated panel (e.g.
    // this milestone's 10-ticker golden fixture, which has too few
    // names for "top 100" to mean anything) simply omits these keys.
    // Defaults to the full fetched set, and is narrowed to the liquid
    // universe below when one is computed.
    std::vector<std::string> fundamentals_tickers = tickers;

    if (config.has("ingest.liquidity_window_days") || config.has("ingest.liquidity_top_n")) {
        std::int64_t window_days = config.get_int_or("ingest.liquidity_window_days", 60);
        std::int64_t top_n = config.get_int_or("ingest.liquidity_top_n", 100);

        auto ranked = gm::data::rank_by_liquidity(combined, static_cast<int>(window_days),
                                                    static_cast<int>(top_n));
        if (!ranked) return tl::unexpected(ranked.error());

        gm::io::Table liquid;
        std::vector<std::string> liquid_tickers;
        std::vector<double> liquid_medians;
        std::vector<std::int64_t> liquid_bars_used;
        for (const auto& r : *ranked) {
            liquid_tickers.push_back(r.ticker);
            liquid_medians.push_back(r.median_dollar_volume);
            liquid_bars_used.push_back(static_cast<std::int64_t>(r.bars_used));
        }
        if (auto r = liquid.add_string_column("ticker", std::move(liquid_tickers)); !r) return tl::unexpected(r.error());
        if (auto r = liquid.add_double_column("median_dollar_volume", std::move(liquid_medians)); !r) return tl::unexpected(r.error());
        if (auto r = liquid.add_int64_column("bars_used", std::move(liquid_bars_used)); !r) return tl::unexpected(r.error());

        auto liquid_write = gm::io::write_parquet(liquid, output_dir / "liquid_universe.parquet");
        if (!liquid_write) return tl::unexpected(liquid_write.error());

        manifest.set_int("liquid_universe_size", static_cast<std::int64_t>(ranked->size()));
        manifest.set_int("liquidity_window_days", window_days);
        manifest.set_int("liquidity_top_n", top_n);

        // Everything downstream reads the liquid universe, so that is the
        // set worth fetching filings for.
        fundamentals_tickers.clear();
        for (const auto& r : *ranked) fundamentals_tickers.push_back(r.ticker);
    }

    // ---- retroactive-change screen (ADR-015) ----------------------------
    const std::string compare_run = config.get_string_or("ingest.compare_against_run", "");
    if (!compare_run.empty()) {
        const auto prior_prices =
            output_dir.parent_path().parent_path() / compare_run / "gm-ingest" / "prices.parquet";
        if (!std::filesystem::exists(prior_prices)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kNotFound,
                "ingest.compare_against_run names a run with no prices.parquet",
                prior_prices.string()));
        }
        auto prior = gm::io::read_parquet(prior_prices);
        if (!prior) return tl::unexpected(prior.error());
        // Adjusted close: the column every downstream return is computed
        // from, so a revision to it is a revision to everything.
        auto report = gm::data::compare_price_panels(*prior, combined, "adjclose");
        if (!report) return tl::unexpected(report.error());

        manifest.set_string("retroactive_change_check", "enabled");
        manifest.set_string("compared_against_run", compare_run);
        manifest.set_int("bars_compared_against_prior_run", report->compared);
        manifest.set_int("bars_revised_since_prior_run", report->revised);
        manifest.set_int("tickers_with_revised_bars",
                          static_cast<std::int64_t>(report->revised_tickers.size()));
        // New and removed bars are normal - the panel extends daily and
        // the universe turns over - and are reported apart from revisions
        // so a reader never mistakes one for the other.
        manifest.set_int("bars_new_since_prior_run", report->added);
        manifest.set_int("bars_absent_since_prior_run", report->removed);
        if (!report->first_example.empty()) {
            manifest.set_string("first_revised_bar", report->first_example);
        }
        if (report->revised > 0) {
            spdlog::warn(
                "gm-ingest: {} historical bars across {} tickers CHANGED since run {}. Results "
                "built on that run are not reproducible from this one. First: {}",
                report->revised, report->revised_tickers.size(), compare_run,
                report->first_example);
        } else {
            spdlog::info("gm-ingest: {} bars compared against run {}, none revised",
                          report->compared, compare_run);
        }
    } else {
        manifest.set_string("retroactive_change_check",
                             "disabled (ingest.compare_against_run not set)");
    }

    // ---- fundamentals (ADR-022, ADR 7.3) --------------------------------
    // Opt-in: one SEC request per issuer, each document 10-40 MB, and a run
    // that only wants the price panel should not pay for it. Absent the key,
    // nothing here runs and no fundamentals.parquet is written - which
    // downstream stages treat as "no valuation coordinates", not an error.
    //
    // Deliberately placed AFTER the liquidity ranking so it can fetch the ~81
    // names that survive it rather than the ~503-name candidate pool. The
    // pool's other 420 issuers are never read by any later stage, and SEC's
    // bandwidth is a shared resource with a published fair-use policy, not
    // just a local cost.
    if (config.get_bool_or("ingest.fetch_fundamentals", false)) {
        const std::int64_t max_issuers = config.get_int_or("ingest.fundamentals_max_issuers", -1);
        if (max_issuers >= 0 &&
            static_cast<std::int64_t>(fundamentals_tickers.size()) > max_issuers) {
            fundamentals_tickers.resize(static_cast<std::size_t>(max_issuers));
        }
        auto fundamentals_result = ingest_fundamentals(*universe_table, fundamentals_tickers,
                                                        cache, output_dir, manifest);
        if (!fundamentals_result) return tl::unexpected(fundamentals_result.error());
    } else {
        manifest.set_string("fundamentals", "disabled (ingest.fetch_fundamentals = false)");
    }

    manifest.set_int("rows_written", static_cast<std::int64_t>(combined.num_rows()));
    manifest.set_int("tickers_requested", static_cast<std::int64_t>(tickers.size()));
    manifest.set_int("tickers_ok", tickers_ok);
    manifest.set_int("tickers_rejected", tickers_rejected);
    manifest.set_int("dropped_null_bars", total_dropped_null);
    manifest.set_int("zero_volume_days", total_zero_volume);
    manifest.set_int("gaps_over_3_trading_days", total_gaps);
    nlohmann::json rejected_json = nlohmann::json::array();
    for (const auto& r : rejected_tickers) rejected_json.push_back(r);
    manifest.set_json("rejected_tickers", rejected_json);

    return {};
}

} // namespace

int main(int argc, char** argv) { return gm::run_stage_main(argc, argv, "gm-ingest", run_gm_ingest); }
