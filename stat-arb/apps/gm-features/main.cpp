#include "centrality.hpp"
#include "market_model.hpp"
#include "returns.hpp"
#include "valuation.hpp"

#include <gm-core/stage_main.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>

#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <vector>

namespace {

/// Reads gm-ingest's fundamentals.parquet, joins it to the price panel under
/// the point-in-time rule, and writes valuation.parquet.
///
/// A run whose ingest stage did not fetch fundamentals simply has no such
/// file, and that is not an error: valuation is opt-in, and every stage
/// downstream treats an absent valuation.parquet as "no View D", not as a
/// failure. Saying so here rather than upstream keeps the decision in one
/// place.
gm::VoidResult write_valuation(const std::filesystem::path& output_dir, gm::Manifest& manifest) {
    const std::filesystem::path ingest_dir = output_dir.parent_path() / "gm-ingest";
    const std::filesystem::path fundamentals_path = ingest_dir / "fundamentals.parquet";
    if (!std::filesystem::exists(fundamentals_path)) {
        manifest.set_string("valuation", "skipped (no fundamentals.parquet upstream)");
        return {};
    }

    auto fundamentals_table = gm::io::read_parquet(fundamentals_path);
    if (!fundamentals_table) return tl::unexpected(fundamentals_table.error());

    auto f_ticker = fundamentals_table->string_column("ticker");
    if (!f_ticker) return tl::unexpected(f_ticker.error());
    auto f_period_end = fundamentals_table->string_column("period_end");
    if (!f_period_end) return tl::unexpected(f_period_end.error());
    auto f_available = fundamentals_table->string_column("available_date");
    if (!f_available) return tl::unexpected(f_available.error());
    auto f_ni = fundamentals_table->double_column("net_income_ttm");
    if (!f_ni) return tl::unexpected(f_ni.error());
    auto f_ebitda = fundamentals_table->double_column("ebitda_ttm");
    if (!f_ebitda) return tl::unexpected(f_ebitda.error());
    auto f_fcf = fundamentals_table->double_column("free_cash_flow_ttm");
    if (!f_fcf) return tl::unexpected(f_fcf.error());
    auto f_debt = fundamentals_table->double_column("total_debt");
    if (!f_debt) return tl::unexpected(f_debt.error());
    auto f_cash = fundamentals_table->double_column("cash_and_equivalents");
    if (!f_cash) return tl::unexpected(f_cash.error());
    auto f_shares = fundamentals_table->double_column("shares_outstanding");
    if (!f_shares) return tl::unexpected(f_shares.error());

    std::vector<gm::features::FundamentalsRow> rows;
    rows.reserve(f_ticker->size());
    for (std::size_t i = 0; i < f_ticker->size(); ++i) {
        gm::features::FundamentalsRow row;
        row.ticker = (*f_ticker)[i];
        row.period_end = (*f_period_end)[i];
        row.available_date = (*f_available)[i];
        row.net_income_ttm = (*f_ni)[i];
        row.ebitda_ttm = (*f_ebitda)[i];
        row.free_cash_flow_ttm = (*f_fcf)[i];
        row.total_debt = (*f_debt)[i];
        row.cash_and_equivalents = (*f_cash)[i];
        row.shares_outstanding = (*f_shares)[i];
        rows.push_back(std::move(row));
    }

    auto prices = gm::io::read_parquet(ingest_dir / "prices.parquet");
    if (!prices) return tl::unexpected(prices.error());
    auto p_ticker = prices->string_column("ticker");
    if (!p_ticker) return tl::unexpected(p_ticker.error());
    auto p_date = prices->string_column("date");
    if (!p_date) return tl::unexpected(p_date.error());
    // The UNADJUSTED close, deliberately - a reported share count is not
    // split-adjusted, so multiplying it by adjclose gives a market cap wrong
    // by every split since the filing. See valuation.hpp.
    auto p_close = prices->double_column("close");
    if (!p_close) return tl::unexpected(p_close.error());

    const auto panel = gm::features::compute_valuation_panel(rows, *p_ticker, *p_date, *p_close);

    std::vector<std::string> out_date, out_ticker;
    std::vector<double> out_ep, out_ebitda_ev, out_fcf;
    constexpr double kAbsent = std::numeric_limits<double>::quiet_NaN();
    for (const auto& [ticker, series] : panel.yields) {
        for (const auto& [date, y] : series) {
            out_date.push_back(date);
            out_ticker.push_back(ticker);
            out_ep.push_back(y.earnings_yield.value_or(kAbsent));
            out_ebitda_ev.push_back(y.ebitda_ev_yield.value_or(kAbsent));
            out_fcf.push_back(y.fcf_yield.value_or(kAbsent));
        }
    }
    const std::size_t rows_out = out_date.size();

    gm::io::Table table;
    if (auto r = table.add_string_column("date", std::move(out_date)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_string_column("ticker", std::move(out_ticker)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("earnings_yield", std::move(out_ep)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("ebitda_ev_yield", std::move(out_ebitda_ev)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_double_column("fcf_yield", std::move(out_fcf)); !r) return tl::unexpected(r.error());

    auto write = gm::io::write_parquet(table, output_dir / "valuation.parquet");
    if (!write) return tl::unexpected(write.error());

    manifest.set_string("valuation", "enabled");
    manifest.set_int("valuation_rows", static_cast<std::int64_t>(rows_out));
    // Every ticker-day is accounted for in exactly one status, and every
    // coordinate in exactly one per-axis outcome. Published because coverage
    // that has to be inferred from missing rows is not coverage.
    nlohmann::json statuses = nlohmann::json::object();
    for (const auto& [status, count] : panel.status_counts) {
        statuses[std::string{gm::features::to_string(status)}] = count;
    }
    manifest.set_json("valuation_status_counts", statuses);
    nlohmann::json axes = nlohmann::json::object();
    for (const auto& [axis, counts] : panel.yield_counts) {
        nlohmann::json entry = nlohmann::json::object();
        for (const auto& [status, count] : counts) {
            entry[std::string{gm::features::to_string(status)}] = count;
        }
        axes[axis] = entry;
    }
    manifest.set_json("valuation_axis_counts", axes);

    spdlog::info("gm-features: valuation {} ticker-days with at least one coordinate", rows_out);
    return {};
}

gm::VoidResult run_gm_features(const gm::Config& config, const std::filesystem::path& output_dir,
                           gm::Manifest& manifest) {
    std::filesystem::path universe_dir = output_dir.parent_path() / "gm-universe";
    std::filesystem::path universe_path = universe_dir / "universe.parquet";

    if (!std::filesystem::exists(universe_path)) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kNotFound,
            "Missing upstream universe.parquet",
            universe_path.string()));
    }

    auto universe_table = gm::io::read_parquet(universe_path);
    if (!universe_table) return tl::unexpected(universe_table.error());

    auto dates_col = universe_table->string_column("date");
    if (!dates_col) return tl::unexpected(dates_col.error());
    auto tickers_col = universe_table->string_column("ticker");
    if (!tickers_col) return tl::unexpected(tickers_col.error());
    auto sectors_col = universe_table->string_column("gics_sector");
    if (!sectors_col) return tl::unexpected(sectors_col.error());

    // Point-in-time sector co-membership centrality (ADR section 7.4): a
    // genuine function of (ticker, date), computed independently per
    // date from only that date's actual members - see
    // gm::features::compute_pit_sector_centrality doc comment. This
    // replaces the earlier all-time-static version that used the
    // whole file's ticker set and max sector size for every row
    // regardless of date (measured look-ahead bias vs a point-in-time
    // computation: up to +95.9% on 2010-01-04 Communication Services).
    std::vector<double> out_etf_co_membership =
        gm::features::compute_pit_sector_centrality(*dates_col, *tickers_col, *sectors_col);

    // Diagnostics for the earliest date only, to make the PIT fix
    // independently checkable from the run log without re-deriving it.
    {
        std::map<std::string, std::set<std::string>> sector_members_first_date;
        const std::string& first_date = *std::min_element(dates_col->begin(), dates_col->end());
        for (std::size_t i = 0; i < dates_col->size(); ++i) {
            if ((*dates_col)[i] == first_date) sector_members_first_date[(*sectors_col)[i]].insert((*tickers_col)[i]);
        }
        std::size_t names_that_day = 0, max_sector = 0;
        for (const auto& [sector, members] : sector_members_first_date) {
            names_that_day += members.size();
            max_sector = std::max(max_sector, members.size());
        }
        spdlog::info("gm-features: PIT sector distribution on earliest date {} ({} names, max sector size {}):",
                     first_date, names_that_day, max_sector);
        for (const auto& [sector, members] : sector_members_first_date) {
            spdlog::info("  {}: {} constituents (centrality {:.6f})", sector, members.size(),
                         static_cast<double>(members.size()) / (1.0 + static_cast<double>(max_sector)));
        }
        manifest.set_int("pit_first_date_universe_size", static_cast<std::int64_t>(names_that_day));
        manifest.set_int("pit_first_date_max_sector_size", static_cast<std::int64_t>(max_sector));
        manifest.set_string("pit_first_date", first_date);
    }

    // Trailing 5/21/63-day cumulative returns (ADR-015 upstream
    // prices.parquet, sibling artifact to universe.parquet, same
    // pattern). Real implementation, not a NaN placeholder: a
    // (ticker, date) with insufficient trailing history legitimately
    // has no value (NaN), which is different from every row being NaN.
    std::filesystem::path prices_path = output_dir.parent_path() / "gm-ingest" / "prices.parquet";
    if (!std::filesystem::exists(prices_path)) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kNotFound,
            "Missing upstream prices.parquet",
            prices_path.string()));
    }
    auto prices_table = gm::io::read_parquet(prices_path);
    if (!prices_table) return tl::unexpected(prices_table.error());

    auto price_tickers = prices_table->string_column("ticker");
    if (!price_tickers) return tl::unexpected(price_tickers.error());
    auto price_dates = prices_table->string_column("date");
    if (!price_dates) return tl::unexpected(price_dates.error());
    auto price_adjclose = prices_table->double_column("adjclose");
    if (!price_adjclose) return tl::unexpected(price_adjclose.error());

    auto returns_5d_by_ticker_date =
        gm::features::compute_trailing_returns(*price_tickers, *price_dates, *price_adjclose, 5);
    auto returns_21d_by_ticker_date =
        gm::features::compute_trailing_returns(*price_tickers, *price_dates, *price_adjclose, 21);
    auto returns_63d_by_ticker_date =
        gm::features::compute_trailing_returns(*price_tickers, *price_dates, *price_adjclose, 63);

    auto lookup_return = [](const std::map<std::string, std::map<std::string, double>>& by_ticker,
                             const std::string& ticker, const std::string& date) -> double {
        auto ticker_it = by_ticker.find(ticker);
        if (ticker_it == by_ticker.end()) return std::numeric_limits<double>::quiet_NaN();
        auto date_it = ticker_it->second.find(date);
        if (date_it == ticker_it->second.end()) return std::numeric_limits<double>::quiet_NaN();
        return date_it->second;
    };

    std::vector<std::string> out_dates;
    std::vector<std::string> out_tickers;
    std::vector<double> out_returns_5d, out_returns_21d, out_returns_63d;
    std::vector<double> out_beta, out_idio_vol;

    // The market model, computed once for the whole panel rather than per
    // row: the index is a property of each DATE across all names, so
    // building it inside the row loop would rebuild it once per ticker.
    const std::int64_t market_model_window =
        config.get_int_or("features.market_model_window_days", 252);
    const auto daily_returns = gm::features::compute_daily_returns(
        *price_tickers, *price_dates, *price_adjclose);
    const auto index_returns = gm::features::equal_weighted_index(daily_returns);
    const auto market_models = gm::features::compute_market_model(
        daily_returns, index_returns, static_cast<int>(market_model_window));
    std::int64_t beta_present = 0;
    out_dates.reserve(dates_col->size());
    out_tickers.reserve(dates_col->size());
    out_returns_5d.reserve(dates_col->size());
    out_returns_21d.reserve(dates_col->size());
    out_returns_63d.reserve(dates_col->size());

    std::int64_t returns_5d_present = 0, returns_21d_present = 0, returns_63d_present = 0;

    for (std::size_t i = 0; i < dates_col->size(); ++i) {
        const auto& ticker = (*tickers_col)[i];
        const auto& date = (*dates_col)[i];

        out_dates.push_back(date);
        out_tickers.push_back(ticker);

        double r5 = lookup_return(returns_5d_by_ticker_date, ticker, date);
        double r21 = lookup_return(returns_21d_by_ticker_date, ticker, date);
        double r63 = lookup_return(returns_63d_by_ticker_date, ticker, date);
        if (!std::isnan(r5)) ++returns_5d_present;
        if (!std::isnan(r21)) ++returns_21d_present;
        if (!std::isnan(r63)) ++returns_63d_present;
        out_returns_5d.push_back(r5);
        out_returns_21d.push_back(r21);
        out_returns_63d.push_back(r63);

        // Absent where there is not enough paired history, or where the
        // index did not move in the window - NaN in the column, which the
        // consumer reads as absent, never as a value.
        double beta = std::numeric_limits<double>::quiet_NaN();
        double idio = std::numeric_limits<double>::quiet_NaN();
        const auto mm_ticker = market_models.find(ticker);
        if (mm_ticker != market_models.end()) {
            const auto mm_date = mm_ticker->second.find(date);
            if (mm_date != mm_ticker->second.end()) {
                beta = mm_date->second.beta;
                idio = mm_date->second.idiosyncratic_volatility;
                ++beta_present;
            }
        }
        out_beta.push_back(beta);
        out_idio_vol.push_back(idio);
    }

    std::int64_t rows_written = static_cast<std::int64_t>(out_dates.size());

    // Sector distribution for logging/manifest (the all-time count here
    // is a diagnostic only - it never feeds the centrality computation
    // above, only these summary stats).
    std::set<std::string> unique_tickers_all_time(tickers_col->begin(), tickers_col->end());
    std::set<std::string> unique_sectors(sectors_col->begin(), sectors_col->end());

    gm::io::Table table;
    if (auto r = table.add_string_column("date", std::move(out_dates)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_string_column("ticker", std::move(out_tickers)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_double_column("etf_co_membership", std::move(out_etf_co_membership)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_double_column("returns_5d", std::move(out_returns_5d)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_double_column("returns_21d", std::move(out_returns_21d)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_double_column("returns_63d", std::move(out_returns_63d)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_double_column("beta", std::move(out_beta)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_double_column("idiosyncratic_volatility",
                                          std::move(out_idio_vol)); !r)
        return tl::unexpected(r.error());
    // beta and idiosyncratic_volatility, now real (market_model.hpp).
    // They were deliberately absent rather than shipped as all-NaN
    // placeholders, which is why adding them needs no caveat about the
    // artifact's history: nobody was ever given a fake column to trust.
    //
    // The index is equal-weighted and built from this panel - see
    // market_model.hpp for why, in short: a value-weighted index needs a
    // point-in-time share count whose coverage does not reach the start of
    // the price window, so beta would move as coverage arrived rather than
    // as the stock did.
    //
    // A (ticker, date) without enough paired history, or in a window where
    // the index never moved, has NO market model - and is written as NaN
    // here, the same absent-value convention the trailing returns beside
    // it use.

    auto write_result = gm::io::write_parquet(table, output_dir / "features.parquet");
    if (!write_result) return tl::unexpected(write_result.error());

    manifest.set_int("rows_written", rows_written);
    manifest.set_int("unique_tickers", static_cast<std::int64_t>(unique_tickers_all_time.size()));
    manifest.set_int("num_gics_sectors", static_cast<std::int64_t>(unique_sectors.size()));
    manifest.set_int("returns_5d_present", returns_5d_present);
    manifest.set_int("returns_21d_present", returns_21d_present);
    manifest.set_int("returns_63d_present", returns_63d_present);
    manifest.set_int("beta_present", beta_present);
    manifest.set_int("market_model_window_days", market_model_window);
    manifest.set_int("index_days", static_cast<std::int64_t>(index_returns.size()));
    manifest.set_string("note",
        "M6 ETF co-membership via GICS sector, computed point-in-time per (ticker, date). "
        "returns_5d/21d/63d are real trailing adjclose returns from prices.parquet. "
        "beta and idiosyncratic_volatility are a real market-model regression against an "
        "equal-weighted index built from this panel; absent where history is insufficient.");

    if (auto r = write_valuation(output_dir, manifest); !r) return tl::unexpected(r.error());

    spdlog::info("gm-features: {} rows, {} unique tickers (all-time), {} GICS sectors, "
                 "returns_5d present {}/{}, returns_21d present {}/{}, returns_63d present {}/{}",
                 rows_written, unique_tickers_all_time.size(), unique_sectors.size(),
                 returns_5d_present, rows_written, returns_21d_present, rows_written,
                 returns_63d_present, rows_written);
    return {};
}

} // namespace

int main(int argc, char** argv) {
    return gm::run_stage_main(argc, argv, "gm-features", run_gm_features);
}
