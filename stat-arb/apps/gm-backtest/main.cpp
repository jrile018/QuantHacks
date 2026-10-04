// gm-backtest: the ADR §6.5 walk-forward trade simulation (ADR §13 M5:
// "Walk-forward engine, cost model, DSR ... deflated, cost-netted
// walk-forward results with machine-counted trials").
//
// For each excursion gm-signals detected (a View C z-score crossing
// episode), applies EVERY ADR §6.5 entry condition at its start_date:
//   1. View C: already satisfied by construction (excursions.parquet
//      only exists where |z| already crossed z_entry) - PLUS half-life
//      in the tradable band (min/max_half_life_days), checked here.
//   1b. ADR-012's topology veto: gm-signals tags every spreads.parquet
//      row with tear_flag (gm-geometry's regime.parquet, via Ripser
//      persistent homology) rather than dropping tear-day rows itself -
//      an excursion whose ENTRY day is tear-flagged is rejected HERE
//      (rejected_tear_veto), the same place View A's and View B's vetoes
//      below are enforced, entry-gated only, exactly like those two (a
//      position already open when a later day tears is not force-closed;
//      see the tear-veto design note in this file's git history / the
//      M6 audit for why entry-only is the reading of ADR-012 taken
//      here). Checked immediately after the spread lookup below since
//      tear_flag is a property of that same spreads.parquet row - keeping
//      this separate from rejected_no_spread_data (a DIFFERENT failure
//      mode: a genuine cross-stage inconsistency where excursions.parquet
//      references a (ticker, date) gm-signals never computed at all) is
//      the specific fix for the M6 audit finding: 819 tear-vetoed
//      candidates were previously miscounted into rejected_no_spread_data,
//      making a real data-integrity counter permanently nonzero for a
//      deliberate policy decision instead of an actual bug.
//   2. View B: outside its own surface (gm-boundaries' scores.parquet,
//      view="B", the Mahalanobis estimator specifically - ADR-007's
//      "statistical anchor").
//   3. View A: the frame's structural-change metric below a veto
//      threshold (a data-driven quantile of its own full-history
//      distribution, not a hardcoded constant - gm-geometry's
//      regime.parquet).
//   4. No SEC 8-K filing inside the EXPECTED holding horizon
//      (start_date to start_date + horizon_multiplier*half_life) -
//      fetched directly here via gm::signals::fetch_filing_dates
//      (the SAME library gm-report uses, NOT gm-report's derived
//      excursions_tagged.parquet: gm-backtest runs BEFORE gm-report in
//      gm-run's fixed stage order, so depending on gm-report's output
//      would violate ADR-006's one-way data flow. Both stages
//      independently call the same underlying fetch, cached, so
//      whichever runs second gets a cache hit rather than a wasted
//      re-fetch - and checking against the EXPECTED horizon here is
//      actually a more precise match to ADR §6.5's literal wording
//      than gm-report's realized-excursion-span proxy).
//   5. Liquidity/borrow feasibility - a documented simplification:
//      always satisfied (no live liquidity/borrow feed exists yet;
//      the universe is already liquidity-screened at ADR-001's stage).
//
// For each candidate that survives ALL five conditions, its P&L series
// is NOT taken from gm-signals' spreads.parquet spread column directly
// - that column is refit fresh every single day (a new causal window,
// and potentially a different peer-basket NEIGHBOUR SET entirely, since
// gm-geometry's k-NN graph itself changes day to day), so differencing
// it across days does not represent one held position's mark-to-market
// P&L; it can silently mix real price movement with the reference
// basket changing out from under the position. Found the hard way on
// the real 16-year run: several unrelated tickers' spreads jumped
// simultaneously on one date, traced to a wholesale k-NN neighbour-set
// swap that day, not any real market move (see git history). Instead,
// build_fixed_basket_series() reconstructs a FIXED-basket spread series
// per candidate using the entry-day weights (gm-signals' baskets.parquet)
// held constant across the whole holding period, applied to raw prices
// (gm-ingest's prices.parquet) - exactly what a real held position's
// P&L requires.
//
// Eligible candidates are handed to gm::backtest::simulate_portfolio
// for a daily equal-weighted return series, then scored with
// gm::backtest::sample_moments and gm::backtest::deflated_sharpe_ratio
// (N=1 for this single default-parameter run - the real multi-trial
// DSR is gm-sweep's job, once it exists, using the trial count and
// Sharpe variance it tracks).

#include <gm-backtest/deflated_sharpe.hpp>
#include <gm-backtest/trade_simulation.hpp>
#include <gm-core/stage_main.hpp>
#include <gm-io/http_cache.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>
#include <gm-signals/earnings.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <map>
#include <set>
#include <vector>

namespace {

/// ticker -> date -> ln(adjclose), the same convention gm-signals'
/// own load_log_prices uses - needed here to reconstruct a FIXED-basket
/// spread series per candidate (see the header comment above and the
/// git history on why gm-signals' own spreads.parquet spread column
/// cannot be differenced across days to get a held position's P&L).
using LogPriceMap = std::map<std::string, std::map<std::string, double>>;

gm::Result<LogPriceMap> load_log_prices(const gm::io::Table& prices) {
    auto ticker_col = prices.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto date_col = prices.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto adjclose_col = prices.double_column("adjclose");
    if (!adjclose_col) return tl::unexpected(adjclose_col.error());

    LogPriceMap result;
    for (std::size_t i = 0; i < ticker_col->size(); ++i) {
        double p = (*adjclose_col)[i];
        if (!(p > 0.0)) continue;
        result[(*ticker_col)[i]][(*date_col)[i]] = std::log(p);
    }
    return result;
}

struct BasketLeg {
    std::string neighbor_ticker;
    double weight;
};

/// ticker -> entry_date -> that day's fitted peer-basket legs
/// (gm-signals' baskets.parquet). Keyed by entry_date, not just
/// ticker, because the SAME ticker can have different baskets locked
/// in at different entry dates over a long history.
using BasketsByTickerDate = std::map<std::string, std::map<std::string, std::vector<BasketLeg>>>;

gm::Result<BasketsByTickerDate> load_baskets(const gm::io::Table& t) {
    auto date_col = t.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_col = t.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto neighbor_col = t.string_column("neighbor_ticker");
    if (!neighbor_col) return tl::unexpected(neighbor_col.error());
    auto weight_col = t.double_column("weight");
    if (!weight_col) return tl::unexpected(weight_col.error());

    BasketsByTickerDate result;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        result[(*ticker_col)[i]][(*date_col)[i]].push_back(BasketLeg{(*neighbor_col)[i], (*weight_col)[i]});
    }
    return result;
}

/// Builds the FIXED-basket spread series for one candidate, held over
/// its own [entry_date, exit_date]: spread(date) = ln P_target(date) -
/// sum(w_j * ln P_j(date)), using `legs` (the basket locked in AT
/// ENTRY) applied to every subsequent date's RAW prices - the entry-day
/// weights never change over the holding period, unlike gm-signals' own
/// daily-refit spread column. Walks the target's OWN price date
/// sequence (not calendar arithmetic); a date is included only if the
/// target AND every neighbour leg has a price for it (a partial gap on
/// one neighbour drops just that date, not the whole candidate).
std::map<std::string, double> build_fixed_basket_series(const std::string& target_ticker,
                                                          const std::string& entry_date,
                                                          const std::string& exit_date,
                                                          const std::vector<BasketLeg>& legs,
                                                          const LogPriceMap& log_prices) {
    std::map<std::string, double> result;
    auto target_it = log_prices.find(target_ticker);
    if (target_it == log_prices.end()) return result;

    std::vector<const std::map<std::string, double>*> neighbor_maps;
    for (const auto& leg : legs) {
        auto it = log_prices.find(leg.neighbor_ticker);
        if (it == log_prices.end()) return result; // a leg with no price data at all - can't build any of this series
        neighbor_maps.push_back(&it->second);
    }

    auto lo = target_it->second.lower_bound(entry_date);
    auto hi = target_it->second.upper_bound(exit_date);
    for (auto it = lo; it != hi; ++it) {
        const std::string& date = it->first;
        double s = it->second;
        bool complete = true;
        for (std::size_t j = 0; j < legs.size(); ++j) {
            auto np = neighbor_maps[j]->find(date);
            if (np == neighbor_maps[j]->end()) {
                complete = false;
                break;
            }
            s -= legs[j].weight * np->second;
        }
        if (complete) result[date] = s;
    }
    return result;
}

struct SpreadPoint {
    double z;
    double spread;
    double half_life;
    int n_neighbors;
    bool tear_flag; // ADR-012: this date's topology-tear flag, carried
                     // through from gm-signals' spreads.parquet (which
                     // gm-geometry's regime.parquet sourced it from).
};

using SpreadsByTickerDate = std::map<std::string, std::map<std::string, SpreadPoint>>;

gm::Result<SpreadsByTickerDate> load_spreads(const gm::io::Table& t) {
    auto ticker_col = t.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto date_col = t.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto z_col = t.double_column("z");
    if (!z_col) return tl::unexpected(z_col.error());
    auto spread_col = t.double_column("spread");
    if (!spread_col) return tl::unexpected(spread_col.error());
    auto half_life_col = t.double_column("half_life");
    if (!half_life_col) return tl::unexpected(half_life_col.error());
    auto n_col = t.int64_column("n_neighbors");
    if (!n_col) return tl::unexpected(n_col.error());
    auto tear_flag_col = t.bool_column("tear_flag");
    if (!tear_flag_col) return tl::unexpected(tear_flag_col.error());

    SpreadsByTickerDate result;
    for (std::size_t i = 0; i < ticker_col->size(); ++i) {
        result[(*ticker_col)[i]][(*date_col)[i]] = SpreadPoint{(*z_col)[i], (*spread_col)[i], (*half_life_col)[i],
                                                                 static_cast<int>((*n_col)[i]),
                                                                 (*tear_flag_col)[i] != 0};
    }
    return result;
}

using ViewBByTickerDate = std::map<std::string, std::map<std::string, bool>>;

gm::Result<ViewBByTickerDate> load_view_b(const gm::io::Table& t) {
    auto date_col = t.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_col = t.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto view_col = t.string_column("view");
    if (!view_col) return tl::unexpected(view_col.error());
    auto estimator_col = t.string_column("estimator");
    if (!estimator_col) return tl::unexpected(estimator_col.error());
    auto inside_col = t.bool_column("inside");
    if (!inside_col) return tl::unexpected(inside_col.error());

    ViewBByTickerDate result;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        if ((*view_col)[i] != "B" || (*estimator_col)[i] != "mahalanobis") continue;
        result[(*ticker_col)[i]][(*date_col)[i]] = (*inside_col)[i];
    }
    return result;
}

/// ticker -> date -> whether View D placed the name INSIDE its own
/// valuation boundary that day. Same shape and same estimator choice as
/// load_view_b, deliberately: the two are read side by side and a
/// difference in estimator between them would be an unexplained
/// asymmetry rather than a decision.
gm::Result<ViewBByTickerDate> load_view_d(const gm::io::Table& t) {
    auto date_col = t.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_col = t.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto view_col = t.string_column("view");
    if (!view_col) return tl::unexpected(view_col.error());
    auto estimator_col = t.string_column("estimator");
    if (!estimator_col) return tl::unexpected(estimator_col.error());
    auto inside_col = t.bool_column("inside");
    if (!inside_col) return tl::unexpected(inside_col.error());

    ViewBByTickerDate result;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        if ((*view_col)[i] != "D" || (*estimator_col)[i] != "mahalanobis") continue;
        result[(*ticker_col)[i]][(*date_col)[i]] = (*inside_col)[i];
    }
    return result;
}

/// ticker -> date -> earnings yield, from gm-features' valuation.parquet.
///
/// std::map rather than a hash: the trailing-median lookup below walks a
/// date range, which needs ordered iteration, and ADR-003 wants
/// deterministic order regardless.
using YieldByTickerDate = std::map<std::string, std::map<std::string, double>>;

gm::Result<YieldByTickerDate> load_earnings_yield(const gm::io::Table& t) {
    auto date_col = t.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_col = t.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto ep_col = t.double_column("earnings_yield");
    if (!ep_col) return tl::unexpected(ep_col.error());

    YieldByTickerDate result;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        // An absent coordinate arrives as NaN; skipped rather than stored,
        // so the median below is over observations that exist.
        if (!std::isfinite((*ep_col)[i])) continue;
        result[(*ticker_col)[i]][(*date_col)[i]] = (*ep_col)[i];
    }
    return result;
}

/// The median earnings yield for `ticker` over the `lookback` observations
/// STRICTLY BEFORE `as_of`, and the value on `as_of` itself.
///
/// Strictly before matters: including the entry day in its own reference
/// median drags the median toward the value being tested, which shrinks
/// exactly the signal the gate is looking for - the same self-inclusion
/// error View B's window is written to avoid.
struct YieldContext {
    bool valid = false;
    double current = 0.0;
    double trailing_median = 0.0;
};

YieldContext yield_context(const YieldByTickerDate& yields, const std::string& ticker,
                           const std::string& as_of, int lookback) {
    YieldContext out;
    const auto ticker_it = yields.find(ticker);
    if (ticker_it == yields.end()) return out;
    const auto& series = ticker_it->second;

    const auto today = series.find(as_of);
    if (today == series.end()) return out;
    out.current = today->second;

    std::vector<double> prior;
    prior.reserve(static_cast<std::size_t>(lookback));
    // Walk backwards from the entry date, exclusive.
    for (auto it = today; it != series.begin() && static_cast<int>(prior.size()) < lookback;) {
        --it;
        prior.push_back(it->second);
    }
    // A median over a handful of points is not a reference distribution.
    if (prior.size() < static_cast<std::size_t>(std::max(2, lookback / 4))) return out;

    std::sort(prior.begin(), prior.end());
    const std::size_t mid = prior.size() / 2;
    out.trailing_median =
        prior.size() % 2 == 1 ? prior[mid] : 0.5 * (prior[mid - 1] + prior[mid]);
    out.valid = true;
    return out;
}

gm::Result<std::map<std::string, double>> load_regime(const gm::io::Table& t) {
    auto date_col = t.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto sc_col = t.double_column("structural_change");
    if (!sc_col) return tl::unexpected(sc_col.error());

    std::map<std::string, double> result;
    for (std::size_t i = 0; i < date_col->size(); ++i) result[(*date_col)[i]] = (*sc_col)[i];
    return result;
}

double quantile_of(std::vector<double> values, double q) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    std::size_t idx = static_cast<std::size_t>(q * static_cast<double>(values.size() - 1));
    return values[idx];
}

struct ExcursionRow {
    std::string ticker, start_date, end_date;
};

gm::Result<std::vector<ExcursionRow>> load_excursions(const gm::io::Table& t) {
    auto ticker_col = t.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto start_col = t.string_column("start_date");
    if (!start_col) return tl::unexpected(start_col.error());
    auto end_col = t.string_column("end_date");
    if (!end_col) return tl::unexpected(end_col.error());

    std::vector<ExcursionRow> result;
    for (std::size_t i = 0; i < ticker_col->size(); ++i) {
        result.push_back(ExcursionRow{(*ticker_col)[i], (*start_col)[i], (*end_col)[i]});
    }
    return result;
}

/// Steps forward `n_trading_days` from `from_date` in `ticker`'s OWN
/// date sequence (not calendar arithmetic - weekends/holidays are not
/// trading days), capping at the last date the ticker actually has
/// data for if the horizon would run past the end of history.
std::string horizon_date(const std::map<std::string, SpreadPoint>& ticker_dates, const std::string& from_date,
                          int n_trading_days) {
    auto it = ticker_dates.find(from_date);
    if (it == ticker_dates.end()) return from_date; // shouldn't happen; defensive fallback
    for (int i = 0; i < n_trading_days && std::next(it) != ticker_dates.end(); ++i) ++it;
    return it->first;
}

gm::VoidResult run_gm_backtest(const gm::Config& config, const std::filesystem::path& output_dir,
                                gm::Manifest& manifest) {
    std::error_code ec;
    std::filesystem::create_directories(output_dir, ec);
    if (ec) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to create output directory", output_dir.string()));
    }

    std::filesystem::path signals_dir = output_dir.parent_path() / "gm-signals";
    std::filesystem::path boundaries_dir = output_dir.parent_path() / "gm-boundaries";
    std::filesystem::path geometry_dir = output_dir.parent_path() / "gm-geometry";
    std::filesystem::path universe_dir = output_dir.parent_path() / "gm-universe";
    std::filesystem::path ingest_dir = output_dir.parent_path() / "gm-ingest";

    auto excursions_table = gm::io::read_parquet(signals_dir / "excursions.parquet");
    if (!excursions_table) return tl::unexpected(excursions_table.error());
    auto spreads_table = gm::io::read_parquet(signals_dir / "spreads.parquet");
    if (!spreads_table) return tl::unexpected(spreads_table.error());
    auto baskets_table = gm::io::read_parquet(signals_dir / "baskets.parquet");
    if (!baskets_table) return tl::unexpected(baskets_table.error());
    auto scores_table = gm::io::read_parquet(boundaries_dir / "scores.parquet");
    if (!scores_table) return tl::unexpected(scores_table.error());
    auto regime_table = gm::io::read_parquet(geometry_dir / "regime.parquet");
    if (!regime_table) return tl::unexpected(regime_table.error());
    auto universe_table = gm::io::read_parquet(universe_dir / "universe.parquet");
    if (!universe_table) return tl::unexpected(universe_table.error());
    auto prices_table = gm::io::read_parquet(ingest_dir / "prices.parquet");
    if (!prices_table) return tl::unexpected(prices_table.error());

    auto excursions = load_excursions(*excursions_table);
    if (!excursions) return tl::unexpected(excursions.error());
    auto spreads = load_spreads(*spreads_table);
    if (!spreads) return tl::unexpected(spreads.error());
    auto baskets = load_baskets(*baskets_table);
    if (!baskets) return tl::unexpected(baskets.error());
    // ADR-022's valuation gate. "off" by default so no existing run
    // silently changes its answer.
    //
    //   off               no valuation condition (the historical behaviour)
    //   cheap             the name's earnings yield at entry must exceed its
    //                     own trailing median - the price fell without the
    //                     earnings falling with it
    //   diverged_and_cheap   as above, AND View D must place the name
    //                     OUTSIDE its own valuation boundary, so the move
    //                     has to be large enough to be unusual at all
    const std::string valuation_gate = config.get_string_or("backtest.valuation_gate", "off");
    if (valuation_gate != "off" && valuation_gate != "cheap" &&
        valuation_gate != "diverged_and_cheap") {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "backtest.valuation_gate must be off, cheap or diverged_and_cheap",
            valuation_gate));
    }
    const std::int64_t valuation_lookback =
        config.get_int_or("backtest.valuation_gate_lookback_days", 252);

    auto view_b = load_view_b(*scores_table);
    if (!view_b) return tl::unexpected(view_b.error());

    // Only loaded when the gate is on: a run with the gate off must not
    // fail because an upstream stage it does not use produced nothing.
    ViewBByTickerDate view_d;
    YieldByTickerDate earnings_yields;
    if (valuation_gate != "off") {
        auto loaded_d = load_view_d(*scores_table);
        if (!loaded_d) return tl::unexpected(loaded_d.error());
        view_d = std::move(*loaded_d);

        const auto valuation_path =
            output_dir.parent_path() / "gm-features" / "valuation.parquet";
        if (!std::filesystem::exists(valuation_path)) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kNotFound,
                "backtest.valuation_gate is on but there is no valuation.parquet upstream",
                "run gm-ingest with fetch_fundamentals = true, then gm-features"));
        }
        auto valuation_table = gm::io::read_parquet(valuation_path);
        if (!valuation_table) return tl::unexpected(valuation_table.error());
        auto loaded_yields = load_earnings_yield(*valuation_table);
        if (!loaded_yields) return tl::unexpected(loaded_yields.error());
        earnings_yields = std::move(*loaded_yields);
    }
    auto regime = load_regime(*regime_table);
    if (!regime) return tl::unexpected(regime.error());
    auto log_prices = load_log_prices(*prices_table);
    if (!log_prices) return tl::unexpected(log_prices.error());

    auto uni_ticker = universe_table->string_column("ticker");
    if (!uni_ticker) return tl::unexpected(uni_ticker.error());
    auto uni_cik = universe_table->int64_column("cik");
    if (!uni_cik) return tl::unexpected(uni_cik.error());
    std::map<std::string, std::int64_t> cik_by_ticker;
    for (std::size_t i = 0; i < uni_ticker->size(); ++i) cik_by_ticker.try_emplace((*uni_ticker)[i], (*uni_cik)[i]);

    std::int64_t min_half_life = config.get_int_or("backtest.min_half_life_days", 3);
    std::int64_t max_half_life = config.get_int_or("backtest.max_half_life_days", 30);
    double veto_percentile = config.get_double_or("backtest.structural_change_veto_percentile", 0.95);


    double cost_bps_per_leg = config.get_double_or("backtest.cost_bps_per_leg", 5.0);
    double horizon_multiplier = config.get_double_or("backtest.horizon_multiplier", 3.0);
    std::string cache_dir = config.get_string_or("backtest.sec_cache_dir", "data/raw/sec_submissions");

    std::vector<double> all_regime_values;
    all_regime_values.reserve(regime->size());
    for (const auto& [date, sc] : *regime) all_regime_values.push_back(sc);
    double veto_threshold = quantile_of(all_regime_values, veto_percentile);

    // Fetch 8-K dates only for tickers that actually have excursions -
    // same HttpCache directory gm-report uses by default, so whichever
    // of the two stages runs second in a given invocation gets a cache
    // hit rather than a redundant live fetch.
    std::set<std::string> tickers_with_excursions;
    for (const auto& e : *excursions) tickers_with_excursions.insert(e.ticker);

    gm::io::HttpCache http_cache(cache_dir);
    std::map<std::string, std::vector<std::string>> filing_dates_by_ticker;
    for (const auto& ticker : tickers_with_excursions) {
        auto cik_it = cik_by_ticker.find(ticker);
        if (cik_it == cik_by_ticker.end()) continue;
        auto filings = gm::signals::fetch_filing_dates(http_cache, cik_it->second, {"8-K"});
        if (!filings) continue; // a single ticker's fetch failing shouldn't halt the whole backtest
        std::vector<std::string> dates;
        dates.reserve(filings->size());
        for (const auto& f : *filings) dates.push_back(f.date);
        std::sort(dates.begin(), dates.end());
        filing_dates_by_ticker[ticker] = std::move(dates);
    }

    std::int64_t rejected_no_spread_data = 0;
    std::int64_t rejected_tear_veto = 0;
    std::int64_t rejected_half_life_band = 0;
    std::int64_t rejected_view_b = 0;
    std::int64_t rejected_view_a_veto = 0;
    std::int64_t rejected_earnings = 0;
    std::int64_t rejected_no_basket_weights = 0;
    std::int64_t rejected_empty_fixed_series = 0;
    // Split three ways rather than one, because they call for different
    // responses: no coverage at all is a data problem, "not cheap" is the
    // gate doing its job, and "not unusual" is the boundary doing its job.
    std::int64_t rejected_valuation_no_data = 0;
    std::int64_t rejected_valuation_not_cheap = 0;
    std::int64_t rejected_valuation_not_diverged = 0;

    std::vector<gm::backtest::TradeCandidate> candidates;

    for (const auto& exc : *excursions) {
        auto ticker_spreads_it = spreads->find(exc.ticker);
        if (ticker_spreads_it == spreads->end()) {
            ++rejected_no_spread_data;
            continue;
        }
        auto point_it = ticker_spreads_it->second.find(exc.start_date);
        if (point_it == ticker_spreads_it->second.end()) {
            ++rejected_no_spread_data;
            continue;
        }
        const SpreadPoint& entry_point = point_it->second;

        // ADR-012: entry-day topology veto - see the file header's "1b"
        // and gm-signals' tear_flag_by_date comment for the full
        // rationale. Deliberately its own counter, separate from
        // rejected_no_spread_data above (a genuine cross-stage
        // inconsistency, not a policy decision) and checked BEFORE the
        // other entry conditions since ADR-012 frames a tear as
        // invalidating the signal itself ("the definition of normal is
        // actively invalid"), not as one veto among equals.
        if (entry_point.tear_flag) {
            ++rejected_tear_veto;
            continue;
        }

        if (entry_point.half_life < static_cast<double>(min_half_life) ||
            entry_point.half_life > static_cast<double>(max_half_life)) {
            ++rejected_half_life_band;
            continue;
        }

        auto vb_ticker_it = view_b->find(exc.ticker);
        bool view_b_outside = false;
        if (vb_ticker_it != view_b->end()) {
            auto vb_date_it = vb_ticker_it->second.find(exc.start_date);
            if (vb_date_it != vb_ticker_it->second.end()) view_b_outside = !vb_date_it->second;
        }
        if (!view_b_outside) {
            ++rejected_view_b;
            continue;
        }

        auto regime_it = regime->find(exc.start_date);
        if (regime_it == regime->end() || regime_it->second >= veto_threshold) {
            ++rejected_view_a_veto;
            continue;
        }

        // ADR-022's valuation gate. See the config comment above for the
        // modes and the loader comment for why direction has to be tested
        // explicitly rather than read off View D's inside/outside alone.
        if (valuation_gate != "off") {
            const YieldContext yc = yield_context(earnings_yields, exc.ticker, exc.start_date,
                                                   static_cast<int>(valuation_lookback));
            if (!yc.valid) {
                ++rejected_valuation_no_data;
                continue;
            }
            // Cheaper than its own recent normal: the price fell and the
            // earnings did not fall with it.
            if (!(yc.current > yc.trailing_median)) {
                ++rejected_valuation_not_cheap;
                continue;
            }
            if (valuation_gate == "diverged_and_cheap") {
                const auto vd_ticker_it = view_d.find(exc.ticker);
                bool view_d_outside = false;
                if (vd_ticker_it != view_d.end()) {
                    const auto vd_date_it = vd_ticker_it->second.find(exc.start_date);
                    if (vd_date_it != vd_ticker_it->second.end()) {
                        view_d_outside = !vd_date_it->second;
                    }
                }
                if (!view_d_outside) {
                    ++rejected_valuation_not_diverged;
                    continue;
                }
            }
        }

        int horizon_days = static_cast<int>(std::ceil(horizon_multiplier * entry_point.half_life));
        std::string horizon_exit = horizon_date(ticker_spreads_it->second, exc.start_date, horizon_days);
        std::string exit_date = std::min(exc.end_date, horizon_exit);

        auto filing_it = filing_dates_by_ticker.find(exc.ticker);
        bool had_earnings_in_horizon = false;
        if (filing_it != filing_dates_by_ticker.end()) {
            auto lb = std::lower_bound(filing_it->second.begin(), filing_it->second.end(), exc.start_date);
            if (lb != filing_it->second.end() && *lb <= horizon_exit) had_earnings_in_horizon = true;
        }
        if (had_earnings_in_horizon) {
            ++rejected_earnings;
            continue;
        }

        auto basket_ticker_it = baskets->find(exc.ticker);
        if (basket_ticker_it == baskets->end()) {
            ++rejected_no_basket_weights;
            continue;
        }
        auto basket_date_it = basket_ticker_it->second.find(exc.start_date);
        if (basket_date_it == basket_ticker_it->second.end() || basket_date_it->second.empty()) {
            ++rejected_no_basket_weights;
            continue;
        }

        // The FIXED-basket spread series for this candidate, held over
        // its own [start_date, exit_date] using the entry-day weights -
        // see the file header and build_fixed_basket_series' own
        // comment for why this replaces spreads.parquet's own
        // daily-refit spread column for P&L purposes.
        auto fixed_series =
            build_fixed_basket_series(exc.ticker, exc.start_date, exit_date, basket_date_it->second, *log_prices);
        if (fixed_series.size() < 2) {
            ++rejected_empty_fixed_series;
            continue;
        }

        candidates.push_back(gm::backtest::TradeCandidate{exc.ticker, exc.start_date, exit_date,
                                                            /*long_the_spread=*/entry_point.z < 0.0,
                                                            /*num_legs=*/1 + entry_point.n_neighbors,
                                                            std::move(fixed_series)});
    }

    auto portfolio = gm::backtest::simulate_portfolio(candidates, cost_bps_per_leg);
    if (!portfolio) return tl::unexpected(portfolio.error());

    gm::io::Table daily_table;
    if (auto r = daily_table.add_string_column("date", portfolio->dates); !r) return tl::unexpected(r.error());
    if (auto r = daily_table.add_double_column("return", portfolio->daily_returns); !r)
        return tl::unexpected(r.error());
    if (auto r = daily_table.add_int64_column("num_open_positions", portfolio->num_open_positions); !r)
        return tl::unexpected(r.error());

    auto write1 = gm::io::write_parquet(daily_table, output_dir / "daily_returns.parquet");
    if (!write1) return tl::unexpected(write1.error());

    nlohmann::json results;
    results["excursions_total"] = excursions->size();
    results["candidates_eligible"] = candidates.size();
    results["rejected_no_spread_data"] = rejected_no_spread_data;
    results["rejected_tear_veto"] = rejected_tear_veto;
    results["rejected_half_life_band"] = rejected_half_life_band;
    results["rejected_view_b"] = rejected_view_b;
    results["rejected_view_a_veto"] = rejected_view_a_veto;
    results["rejected_earnings_in_horizon"] = rejected_earnings;
    results["rejected_no_basket_weights"] = rejected_no_basket_weights;
    results["rejected_empty_fixed_series"] = rejected_empty_fixed_series;
    results["valuation_gate"] = valuation_gate;
    if (valuation_gate != "off") {
        results["valuation_gate_lookback_days"] = valuation_lookback;
        // Split three ways because they call for different responses: no
        // coverage is a data problem, "not cheap" is the gate doing its
        // job, "not diverged" is the boundary doing its job.
        results["rejected_valuation_no_data"] = rejected_valuation_no_data;
        results["rejected_valuation_not_cheap"] = rejected_valuation_not_cheap;
        results["rejected_valuation_not_diverged"] = rejected_valuation_not_diverged;
    }
    results["structural_change_veto_threshold"] = veto_threshold;
    results["trading_days_with_positions"] = portfolio->dates.size();

    if (portfolio->daily_returns.size() >= 2) {
        auto moments = gm::backtest::sample_moments(portfolio->daily_returns);
        if (!moments) return tl::unexpected(moments.error());

        double sum = 0.0;
        for (double r : portfolio->daily_returns) sum += r;
        double mean = sum / static_cast<double>(portfolio->daily_returns.size());
        double sum_sq_dev = 0.0;
        for (double r : portfolio->daily_returns) sum_sq_dev += (r - mean) * (r - mean);
        double sample_variance = sum_sq_dev / static_cast<double>(portfolio->daily_returns.size() - 1);
        double sample_std = std::sqrt(sample_variance);

        double sharpe = sample_std > 0.0 ? mean / sample_std : 0.0;
        double annualized_sharpe = sharpe * std::sqrt(252.0);

        auto sr0 = gm::backtest::expected_max_sharpe(0.0, /*n_trials=*/1);
        if (!sr0) return tl::unexpected(sr0.error());
        auto dsr = gm::backtest::deflated_sharpe_ratio(
            sharpe, *sr0, static_cast<int>(portfolio->daily_returns.size()), moments->skewness, moments->kurtosis);

        results["mean_daily_return"] = mean;
        results["sample_std_daily_return"] = sample_std;
        results["sharpe_ratio_daily"] = sharpe;
        results["sharpe_ratio_annualized"] = annualized_sharpe;
        results["skewness"] = moments->skewness;
        results["kurtosis"] = moments->kurtosis;
        results["deflated_sharpe_ratio"] = dsr ? nlohmann::json(*dsr) : nlohmann::json(nullptr);
        results["n_trials"] = 1;
        results["dsr_note"] =
            "N=1 (this single default-parameter run) - the real multi-trial DSR requires gm-sweep";

        manifest.set_double("sharpe_ratio_annualized", annualized_sharpe);
        if (dsr) manifest.set_double("deflated_sharpe_ratio", *dsr);
    } else {
        results["sharpe_ratio_daily"] = nullptr;
        results["note"] = "fewer than 2 days with open positions - not enough data for Sharpe/DSR";
    }

    std::filesystem::path results_path = output_dir / "backtest_results.json";
    std::ofstream results_out(results_path, std::ios::binary | std::ios::trunc);
    if (!results_out) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to write backtest results", results_path.string()));
    }
    results_out << results.dump(2);

    manifest.set_int("excursions_total", static_cast<std::int64_t>(excursions->size()));
    manifest.set_int("candidates_eligible", static_cast<std::int64_t>(candidates.size()));
    manifest.set_int("trading_days_with_positions", static_cast<std::int64_t>(portfolio->dates.size()));
    manifest.set_double("structural_change_veto_threshold", veto_threshold);
    manifest.set_double("cost_bps_per_leg", cost_bps_per_leg);
    manifest.set_int("min_half_life_days", min_half_life);
    manifest.set_int("max_half_life_days", max_half_life);
    manifest.set_string("valuation_gate", valuation_gate);

    return {};
}

} // namespace

int main(int argc, char** argv) {
    return gm::run_stage_main(argc, argv, "gm-backtest", run_gm_backtest);
}
