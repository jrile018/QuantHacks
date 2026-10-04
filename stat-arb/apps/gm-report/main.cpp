// gm-report: the ADR-013 reversion study - "the gate."
//
// WHAT THIS STAGE ANSWERS, AND IN WHAT ORDER
// ------------------------------------------
// 1. Do flagged excursions come back within H days?   (Kaplan-Meier)
// 2. Do they come back MORE than comparable unflagged
//    names on the same day?                           (matched control)
// 3. Is any of that more than sampling noise, once
//    episodes from one name and one month are not
//    counted as independent facts?                    (clustered SE)
// 4. Does the answer survive treating a takeover as a
//    takeover rather than as missing data?            (Aalen-Johansen)
// 5. Is any of it money, rather than an indicator
//    crossing back over its own denominator?          (realised return)
//
// Question 1 alone was the whole of this stage for a long time, and it
// is the one that means the least. Two earlier versions got progressively
// less wrong:
//
//   - The first reported the fraction of excursions whose `reverted`
//     flag was true. That flag means "closed before the price series ran
//     out", with no horizon at all, so over sixteen years it read 99.8%
//     in every bucket - overall, in every depth quartile, with earnings
//     and without. A figure that flat across every conditioning variable
//     is a property of the definition, not a fact about markets.
//
//   - The second restored the horizon (survival.hpp) and the buckets
//     separated sharply. But a base rate is still not an edge. Anything
//     that has moved a long way tends to move back some of it, so "68%
//     revert within 20 days" remained equally consistent with the
//     boundary carrying information and with it carrying none.
//
// Questions 2 through 5 are what this version adds. The headline number
// is no longer a rate; it is a DIFFERENCE against matched controls, with
// a standard error that respects how few independent observations 7,110
// episodes really are.
//
// THE OUTCOME IS A RETURN, NOT AN INDICATOR
// -----------------------------------------
// A z-score can cross back under its exit threshold because its own
// rolling denominator moved, without any price having done anything a
// position could have captured. So the matched comparison is run on the
// basket-relative log return over the forward window, holding the ENTRY-
// DAY basket weights fixed (spreads.parquet's own `spread` is refit
// daily against a neighbour set that itself changes, so differencing it
// mixes real moves with the reference basket changing underfoot - see
// the gm-signals header for the day this was found the hard way).
//
// Costs are subtracted from both arms at the same rate. They cancel in
// the difference by construction; they are there so the LEVEL is honest
// rather than to move the contrast.
//
// SIGN CONVENTION
// ---------------
// Both arms are signed by -sign(prior basket-relative move), never by
// -sign(z). Using z would score the treated arm with a rule the control
// arm cannot be given, which is exactly the asymmetry a matched design
// exists to avoid. The treated arm's own -sign(z) figure is reported
// separately, so the choice can be inspected rather than trusted.
//
// WHAT IS STILL NOT ANSWERED HERE
// -------------------------------
// Position sizing, capacity, borrow, and portfolio construction. This
// stage says whether the flag carries information; it does not say
// whether a book built on it makes money (ADR Sec13 M5, not M4).

#include <gm-core/stage_main.hpp>
#include <gm-io/http_cache.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>
#include <gm-signals/cluster.hpp>
#include <gm-signals/competing_risks.hpp>
#include <gm-signals/earnings.hpp>
#include <gm-signals/matching.hpp>
#include <gm-signals/survival.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();

/// ticker -> date -> ln(adjclose). Same shape gm-signals uses, and for
/// the same reason: the basket behind any one (date, ticker) is chosen
/// per ticker and changes day to day, so there is no shared grid worth
/// materializing.
using LogPriceMap = std::map<std::string, std::map<std::string, double>>;

/// "date|ticker" -> the entry-day basket, as (neighbour, weight).
using BasketMap = std::map<std::string, std::vector<std::pair<std::string, double>>>;

std::string key_of(const std::string& date, const std::string& ticker) { return date + "|" + ticker; }

/// "YYYY-MM-DD" -> "YYYY-MM". The calendar clustering dimension.
std::string month_of(const std::string& date) { return date.size() >= 7 ? date.substr(0, 7) : date; }

struct RevertBucket {
    std::string label;
    std::int64_t count = 0;
    std::int64_t reverted_count = 0;
    [[nodiscard]] double reversion_rate() const {
        return count > 0 ? static_cast<double>(reverted_count) / static_cast<double>(count) : 0.0;
    }
};

/// One (date, ticker) row, with everything the matched study needs.
struct PanelRow {
    std::string date;
    std::string ticker;
    std::string sector;
    double z = kNaN;
    double prior_rel_ret = kNaN;   // trailing basket-relative move
    double raw_prior_ret = kNaN;   // trailing raw return (features.parquet)
    double idio_vol = kNaN;
    double beta = kNaN;
    std::vector<double> fwd_rel_ret;  // one per horizon, NaN where unavailable
    bool treated = false;             // an excursion started on this day
    bool control_eligible = false;
    double peak_depth = kNaN;         // treated rows only, for the selection table
};

/// Basket-relative log return between two dates, holding the basket
/// weights fixed at their entry-day values. Absent (rather than
/// approximated) if any leg is missing a bar - a basket silently
/// renormalized over whichever neighbours happened to trade is not the
/// basket the position was actually against.
std::optional<double> relative_return(const LogPriceMap& prices, const std::string& ticker,
                                       const std::vector<std::pair<std::string, double>>& basket,
                                       const std::string& from_date, const std::string& to_date) {
    const auto tick_it = prices.find(ticker);
    if (tick_it == prices.end()) return std::nullopt;
    const auto from_it = tick_it->second.find(from_date);
    const auto to_it = tick_it->second.find(to_date);
    if (from_it == tick_it->second.end() || to_it == tick_it->second.end()) return std::nullopt;

    double out = to_it->second - from_it->second;
    for (const auto& [neighbour, weight] : basket) {
        const auto nb_it = prices.find(neighbour);
        if (nb_it == prices.end()) return std::nullopt;
        const auto nf = nb_it->second.find(from_date);
        const auto nt = nb_it->second.find(to_date);
        if (nf == nb_it->second.end() || nt == nb_it->second.end()) return std::nullopt;
        out -= weight * (nt->second - nf->second);
    }
    return out;
}

nlohmann::json balance_json(const std::vector<std::string>& names, const std::vector<double>& before,
                             const std::vector<double>& after) {
    nlohmann::json out = nlohmann::json::array();
    for (std::size_t j = 0; j < names.size(); ++j) {
        out.push_back({{"covariate", names[j]},
                        {"standardized_diff_before", j < before.size() ? before[j] : 0.0},
                        {"standardized_diff_after", j < after.size() ? after[j] : 0.0}});
    }
    return out;
}

gm::VoidResult run_gm_report(const gm::Config& config, const std::filesystem::path& output_dir,
                             gm::Manifest& manifest) {
    std::error_code ec;
    std::filesystem::create_directories(output_dir, ec);
    if (ec) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                               "failed to create output directory", output_dir.string()));
    }

    const std::filesystem::path base = output_dir.parent_path();
    const std::filesystem::path signals_dir = base / "gm-signals";
    const std::filesystem::path universe_dir = base / "gm-universe";
    const std::filesystem::path ingest_dir = base / "gm-ingest";
    const std::filesystem::path features_dir = base / "gm-features";

    auto excursions = gm::io::read_parquet(signals_dir / "excursions.parquet");
    if (!excursions) return tl::unexpected(excursions.error());
    auto spreads = gm::io::read_parquet(signals_dir / "spreads.parquet");
    if (!spreads) return tl::unexpected(spreads.error());
    auto universe = gm::io::read_parquet(universe_dir / "universe.parquet");
    if (!universe) return tl::unexpected(universe.error());

    auto exc_ticker = excursions->string_column("ticker");
    if (!exc_ticker) return tl::unexpected(exc_ticker.error());
    auto exc_start = excursions->string_column("start_date");
    if (!exc_start) return tl::unexpected(exc_start.error());
    auto exc_end = excursions->string_column("end_date");
    if (!exc_end) return tl::unexpected(exc_end.error());
    auto exc_peak = excursions->double_column("peak_depth");
    if (!exc_peak) return tl::unexpected(exc_peak.error());
    auto exc_reverted = excursions->bool_column("reverted");
    if (!exc_reverted) return tl::unexpected(exc_reverted.error());
    // The horizon itself. Without it every question below collapses into
    // "did it ever", which is the bug this stage was fixed for.
    auto exc_duration = excursions->int64_column("duration_days");
    if (!exc_duration) return tl::unexpected(exc_duration.error());

    // ticker -> CIK, first occurrence (constant per ticker across
    // universe.parquet's point-in-time membership rows), and likewise
    // for GICS sector. Sector is treated as static per name: it does
    // change on rare reclassification, and taking the first observation
    // keeps the matching stratum from drifting mid-study, which would
    // silently split one name across two strata.
    auto uni_ticker = universe->string_column("ticker");
    if (!uni_ticker) return tl::unexpected(uni_ticker.error());
    auto uni_cik = universe->int64_column("cik");
    if (!uni_cik) return tl::unexpected(uni_cik.error());
    auto uni_sector = universe->string_column("gics_sector");
    if (!uni_sector) return tl::unexpected(uni_sector.error());
    std::map<std::string, std::int64_t> cik_by_ticker;
    std::map<std::string, std::string> sector_by_ticker;
    for (std::size_t i = 0; i < uni_ticker->size(); ++i) {
        cik_by_ticker.try_emplace((*uni_ticker)[i], (*uni_cik)[i]);
        if (!(*uni_sector)[i].empty()) sector_by_ticker.try_emplace((*uni_ticker)[i], (*uni_sector)[i]);
    }

    // ---------------------------------------------------------------
    // 8-K tagging (unchanged): did news land inside the episode's span?
    // ---------------------------------------------------------------
    std::set<std::string> tickers_with_excursions(exc_ticker->begin(), exc_ticker->end());

    const std::string cache_dir = config.get_string_or("report.sec_cache_dir", "data/raw/sec_submissions");
    gm::io::HttpCache http_cache(cache_dir);

    std::map<std::string, std::vector<std::string>> filing_dates_by_ticker;
    std::int64_t tickers_missing_cik = 0;
    std::int64_t tickers_fetch_failed = 0;
    for (const auto& ticker : tickers_with_excursions) {
        auto cik_it = cik_by_ticker.find(ticker);
        if (cik_it == cik_by_ticker.end()) {
            ++tickers_missing_cik;
            continue;
        }
        auto filings = gm::signals::fetch_filing_dates(http_cache, cik_it->second, {"8-K"});
        if (!filings) {
            // A single ticker's fetch failing (network hiccup, an unusual
            // CIK) should not halt the whole study - it just means that
            // ticker's excursions can't be earnings-tagged, and is counted
            // so the gap is visible in the manifest rather than silently
            // absorbed.
            ++tickers_fetch_failed;
            continue;
        }
        std::vector<std::string> dates;
        dates.reserve(filings->size());
        for (const auto& f : *filings) dates.push_back(f.date);
        std::sort(dates.begin(), dates.end());
        filing_dates_by_ticker[ticker] = std::move(dates);
    }

    std::vector<std::uint8_t> had_earnings(exc_ticker->size(), 0);
    for (std::size_t i = 0; i < exc_ticker->size(); ++i) {
        auto it = filing_dates_by_ticker.find((*exc_ticker)[i]);
        if (it == filing_dates_by_ticker.end()) continue;
        const auto& dates = it->second;
        auto lb = std::lower_bound(dates.begin(), dates.end(), (*exc_start)[i]);
        if (lb != dates.end() && *lb <= (*exc_end)[i]) had_earnings[i] = 1;
    }

    // ---------------------------------------------------------------
    // Depth buckets (unchanged)
    // ---------------------------------------------------------------
    std::vector<double> sorted_depths(exc_peak->begin(), exc_peak->end());
    std::sort(sorted_depths.begin(), sorted_depths.end());
    auto quantile = [&](double q) -> double {
        if (sorted_depths.empty()) return 0.0;
        const std::size_t idx = static_cast<std::size_t>(q * static_cast<double>(sorted_depths.size() - 1));
        return sorted_depths[idx];
    };
    const double q25 = quantile(0.25), q50 = quantile(0.50), q75 = quantile(0.75);

    auto depth_bucket_label = [&](double depth) -> std::string {
        if (depth < q25) return "q1_shallowest";
        if (depth < q50) return "q2";
        if (depth < q75) return "q3";
        return "q4_deepest";
    };

    const std::vector<std::int64_t> horizons{5, 10, 20, 40, 60};

    // ---------------------------------------------------------------
    // Price panel and baskets, for the realised-return outcome.
    // Restricted to the tickers that actually appear in spreads (the
    // ~79-name active universe) plus their neighbours: prices.parquet
    // carries the whole ~900-name candidate pool and loading all of it
    // would be several hundred megabytes of map nobody reads.
    // ---------------------------------------------------------------
    auto spd_date = spreads->string_column("date");
    if (!spd_date) return tl::unexpected(spd_date.error());
    auto spd_ticker = spreads->string_column("ticker");
    if (!spd_ticker) return tl::unexpected(spd_ticker.error());
    auto spd_z = spreads->double_column("z");
    if (!spd_z) return tl::unexpected(spd_z.error());

    BasketMap baskets;
    std::set<std::string> needed_tickers(spd_ticker->begin(), spd_ticker->end());
    {
        auto basket_tbl = gm::io::read_parquet(signals_dir / "baskets.parquet");
        if (!basket_tbl) return tl::unexpected(basket_tbl.error());
        auto b_date = basket_tbl->string_column("date");
        if (!b_date) return tl::unexpected(b_date.error());
        auto b_ticker = basket_tbl->string_column("ticker");
        if (!b_ticker) return tl::unexpected(b_ticker.error());
        auto b_neighbour = basket_tbl->string_column("neighbor_ticker");
        if (!b_neighbour) return tl::unexpected(b_neighbour.error());
        auto b_weight = basket_tbl->double_column("weight");
        if (!b_weight) return tl::unexpected(b_weight.error());
        for (std::size_t i = 0; i < b_date->size(); ++i) {
            baskets[key_of((*b_date)[i], (*b_ticker)[i])].emplace_back((*b_neighbour)[i], (*b_weight)[i]);
            needed_tickers.insert((*b_neighbour)[i]);
        }
    }

    LogPriceMap log_prices;
    {
        auto prices = gm::io::read_parquet(ingest_dir / "prices.parquet");
        if (!prices) return tl::unexpected(prices.error());
        auto p_ticker = prices->string_column("ticker");
        if (!p_ticker) return tl::unexpected(p_ticker.error());
        auto p_date = prices->string_column("date");
        if (!p_date) return tl::unexpected(p_date.error());
        auto p_adj = prices->double_column("adjclose");
        if (!p_adj) return tl::unexpected(p_adj.error());
        for (std::size_t i = 0; i < p_ticker->size(); ++i) {
            if (!needed_tickers.count((*p_ticker)[i])) continue;
            const double px = (*p_adj)[i];
            if (!(px > 0.0)) continue;  // no logarithm; skip rather than fabricate
            log_prices[(*p_ticker)[i]][(*p_date)[i]] = std::log(px);
        }
    }

    // Per-ticker trading calendar and a date -> position index, so a
    // horizon of H means H of THAT NAME'S trading days.
    std::map<std::string, std::vector<std::string>> calendar;
    std::map<std::string, std::map<std::string, std::size_t>> calendar_index;
    for (const auto& [ticker, series] : log_prices) {
        auto& cal = calendar[ticker];
        cal.reserve(series.size());
        for (const auto& [d, px] : series) {
            (void)px;
            calendar_index[ticker][d] = cal.size();
            cal.push_back(d);
        }
    }

    // The panel's own last trading day, used to tell "the data ended"
    // from "this name's series ended" for the competing-risks split.
    std::string panel_last_date;
    for (const auto& [ticker, cal] : calendar) {
        (void)ticker;
        if (!cal.empty() && cal.back() > panel_last_date) panel_last_date = cal.back();
    }

    // ---------------------------------------------------------------
    // Covariates from gm-features. Optional: if the stage did not run,
    // the matched study degrades to the covariates it does have and
    // SAYS SO, rather than reporting a same-looking number computed on
    // fewer things.
    // ---------------------------------------------------------------
    struct Cov {
        double raw_prior_ret = kNaN;
        double idio_vol = kNaN;
        double beta = kNaN;
    };
    std::map<std::string, Cov> covariates;
    std::vector<std::string> covariates_unavailable;
    bool have_features = false;
    {
        auto features = gm::io::read_parquet(features_dir / "features.parquet");
        if (features) {
            auto f_date = features->string_column("date");
            auto f_ticker = features->string_column("ticker");
            auto f_ret = features->double_column("returns_21d");
            auto f_vol = features->double_column("idiosyncratic_volatility");
            auto f_beta = features->double_column("beta");
            if (f_date && f_ticker && f_ret && f_vol && f_beta) {
                have_features = true;
                for (std::size_t i = 0; i < f_date->size(); ++i) {
                    if (!needed_tickers.count((*f_ticker)[i])) continue;
                    Cov c;
                    c.raw_prior_ret = (*f_ret)[i];
                    c.idio_vol = (*f_vol)[i];
                    c.beta = (*f_beta)[i];
                    covariates[key_of((*f_date)[i], (*f_ticker)[i])] = c;
                }
            }
        }
    }
    if (!have_features) {
        covariates_unavailable.insert(covariates_unavailable.end(),
                                       {"returns_21d", "idiosyncratic_volatility", "beta"});
    }
    // Market capitalisation needs ingest.fetch_fundamentals, which is off
    // by default (one SEC request per issuer, 10-40 MB each). Named here
    // rather than quietly omitted - see BLOCKED.md entry 4.
    if (!std::filesystem::exists(features_dir / "valuation.parquet")) {
        covariates_unavailable.push_back("log_market_cap");
    }

    // ---------------------------------------------------------------
    // Which rows are treated, and which are eligible controls.
    // ---------------------------------------------------------------
    std::map<std::string, double> excursion_start_depth;
    std::map<std::string, std::vector<std::pair<std::string, std::string>>> spans_by_ticker;
    for (std::size_t i = 0; i < exc_ticker->size(); ++i) {
        excursion_start_depth.try_emplace(key_of((*exc_start)[i], (*exc_ticker)[i]), (*exc_peak)[i]);
        spans_by_ticker[(*exc_ticker)[i]].emplace_back((*exc_start)[i], (*exc_end)[i]);
    }

    // A control must not itself be dislocated. Two conditions, and both
    // matter: a small |z| on a day that happens to sit in the middle of
    // an open episode is not an undislocated name, it is a dislocated
    // one on its way back.
    const double control_z_max = config.get_double_or("report.control_z_max", 1.0);
    const double caliper = config.get_double_or("report.match_caliper", 0.25);
    const double cost_bps = config.get_double_or("report.round_trip_cost_bps", 10.0);
    const double cost = cost_bps / 10000.0;
    const std::int64_t prior_window = config.get_int_or("report.prior_move_window_days", 21);
    const std::int64_t delisting_gap_days = config.get_int_or("report.delisting_gap_days", 10);

    std::vector<PanelRow> panel;
    panel.reserve(spd_date->size());
    std::int64_t rows_without_basket = 0, rows_without_prior = 0;

    for (std::size_t i = 0; i < spd_date->size(); ++i) {
        PanelRow row;
        row.date = (*spd_date)[i];
        row.ticker = (*spd_ticker)[i];
        row.z = (*spd_z)[i];
        const std::string k = key_of(row.date, row.ticker);

        auto sec_it = sector_by_ticker.find(row.ticker);
        row.sector = sec_it == sector_by_ticker.end() ? std::string{"UNKNOWN"} : sec_it->second;

        const auto depth_it = excursion_start_depth.find(k);
        row.treated = depth_it != excursion_start_depth.end();
        if (row.treated) row.peak_depth = depth_it->second;

        bool inside_episode = false;
        auto span_it = spans_by_ticker.find(row.ticker);
        if (span_it != spans_by_ticker.end()) {
            for (const auto& [s, e] : span_it->second) {
                if (row.date >= s && row.date <= e) {
                    inside_episode = true;
                    break;
                }
            }
        }
        row.control_eligible = !row.treated && !inside_episode && std::abs(row.z) <= control_z_max;

        if (!row.treated && !row.control_eligible) {
            continue;  // neither arm; nothing downstream reads it
        }

        auto basket_it = baskets.find(k);
        if (basket_it == baskets.end()) {
            ++rows_without_basket;
            continue;
        }
        const auto& basket = basket_it->second;

        auto cov_it = covariates.find(k);
        if (cov_it != covariates.end()) {
            row.raw_prior_ret = cov_it->second.raw_prior_ret;
            row.idio_vol = cov_it->second.idio_vol;
            row.beta = cov_it->second.beta;
        }

        const auto cal_it = calendar_index.find(row.ticker);
        if (cal_it == calendar_index.end()) continue;
        const auto pos_it = cal_it->second.find(row.date);
        if (pos_it == cal_it->second.end()) continue;
        const std::size_t pos = pos_it->second;
        const auto& cal = calendar.at(row.ticker);

        if (pos >= static_cast<std::size_t>(prior_window)) {
            const auto prior = relative_return(log_prices, row.ticker, basket,
                                                cal[pos - static_cast<std::size_t>(prior_window)], row.date);
            if (prior) row.prior_rel_ret = *prior;
        }
        if (std::isnan(row.prior_rel_ret)) {
            // The prior move is both a covariate and the sign of the
            // outcome. Without it the row cannot be in either arm.
            ++rows_without_prior;
            continue;
        }

        row.fwd_rel_ret.assign(horizons.size(), kNaN);
        for (std::size_t h = 0; h < horizons.size(); ++h) {
            const std::size_t target = pos + static_cast<std::size_t>(horizons[h]);
            if (target >= cal.size()) continue;
            const auto fwd = relative_return(log_prices, row.ticker, basket, row.date, cal[target]);
            if (fwd) row.fwd_rel_ret[h] = *fwd;
        }
        panel.push_back(std::move(row));
    }

    // ---------------------------------------------------------------
    // Matching
    // ---------------------------------------------------------------
    // The outcome, defined identically for both arms. -sign(prior
    // basket-relative move): a name that fell relative to its peers is
    // expected to come back up. A zero prior move carries no direction,
    // so that row is dropped rather than assigned one.
    auto signed_outcome = [&](const PanelRow& r, std::size_t h) -> double {
        const double fwd = r.fwd_rel_ret.empty() ? kNaN : r.fwd_rel_ret[h];
        if (std::isnan(fwd)) return kNaN;
        if (r.prior_rel_ret == 0.0) return kNaN;
        const double direction = r.prior_rel_ret > 0.0 ? -1.0 : 1.0;
        return direction * fwd - cost;
    };

    // ---------------------------------------------------------------
    // TWO SPECIFICATIONS, AND WHY BOTH ARE HERE
    //
    // The objection this study exists to answer is regression to the
    // mean: anything that has moved a long way tends to give some of it
    // back, so a flagged name reverting proves nothing on its own. The
    // confounder in that sentence is the ABSOLUTE move. The PEER-
    // RELATIVE move is not a confounder at all - it is the treatment.
    // Being far from your peers is what the boundary detects.
    //
    //   PRIMARY controls the absolute move (returns_21d), volatility and
    //   beta, within the same day and sector. Treated and control have
    //   both moved similarly in absolute terms; only one of them moved
    //   away from its peers. This is the contrast that separates "the
    //   geometry knows something" from "it went down a lot".
    //
    //   OVER-CONTROLLED additionally matches on the peer-relative move
    //   itself. That partials out most of the treatment, so its estimate
    //   is a deliberate lower bound rather than the answer - reported
    //   because a difference that survives even this is hard to argue
    //   with, and because the two together show how much of the effect
    //   lives in the peer-relative dimension.
    //
    // The first version of this stage ran only the over-controlled
    // specification, by accident rather than by choice. It matched 11%
    // of treated units and produced a balance table that was already
    // near zero before matching - both symptoms of controlling away the
    // variable under test.
    // ---------------------------------------------------------------
    auto run_specification = [&](const std::string& spec_name, bool control_relative_move,
                                  double spec_caliper,
                                  const std::string& reading) -> gm::Result<nlohmann::json> {
        std::vector<std::string> covariate_names;
        if (have_features) {
            covariate_names.insert(covariate_names.end(),
                                    {"returns_21d", "idiosyncratic_volatility", "beta"});
        }
        if (control_relative_move) {
            covariate_names.push_back("prior_relative_return_" + std::to_string(prior_window) + "d");
        }
        if (covariate_names.empty()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kValidationFailure,
                "no matching covariates available: gm-features did not run and the relative-move "
                "specification is disabled",
                spec_name));
        }

        std::vector<gm::signals::MatchUnit> units;
        std::vector<std::size_t> unit_row;  // MatchUnit id -> index into `panel`
        for (std::size_t i = 0; i < panel.size(); ++i) {
            const auto& r = panel[i];
            std::vector<double> cov;
            if (have_features) {
                if (std::isnan(r.raw_prior_ret) || std::isnan(r.idio_vol) || std::isnan(r.beta)) continue;
                cov.insert(cov.end(), {r.raw_prior_ret, r.idio_vol, r.beta});
            }
            if (control_relative_move) cov.push_back(r.prior_rel_ret);
            gm::signals::MatchUnit u;
            u.id = units.size();
            u.stratum = r.date + "|" + r.sector;
            u.treated = r.treated;
            u.covariates = std::move(cov);
            units.push_back(std::move(u));
            unit_row.push_back(i);
        }

        gm::signals::MatchOptions match_options;
        match_options.caliper = spec_caliper;
        auto match = gm::signals::match_on_covariates(units, match_options);
        if (!match) return tl::unexpected(match.error());

        nlohmann::json matched = nlohmann::json::object();
        matched["how_to_read"] = reading;
        matched["covariates_used"] = covariate_names;
        matched["covariates_unavailable"] = covariates_unavailable;
        matched["caliper_pooled_sd"] = spec_caliper;
        matched["control_z_max"] = control_z_max;
        matched["round_trip_cost_bps"] = cost_bps;
        matched["stratum"] = "date|gics_sector (exact)";
        matched["treated_total"] = match->treated_total;
        matched["treated_matched"] = match->treated_matched;
        matched["match_rate"] = match->match_rate();
        matched["controls_available"] = match->controls_available;
        matched["unmatched_no_controls_in_stratum"] = match->treated_unmatched_no_controls;
        matched["unmatched_controls_exhausted"] = match->treated_unmatched_exhausted;
        matched["unmatched_outside_caliper"] = match->treated_unmatched_caliper;
        matched["worst_standardized_diff_after"] = match->worst_balance_after();
        matched["balance"] =
            balance_json(covariate_names, match->standardized_diff_before, match->standardized_diff_after);
        matched["balance_note"] =
            "|standardized difference| below 0.1 after matching is the conventional bar. These are "
            "differences of SIGNED means, so a covariate that is symmetric across the two "
            "directions of dislocation will look balanced before matching whether or not it is; "
            "the magnitude figures below exist because of that.";

        // Which treated units survived matching, by depth. An excursion
        // that could not be matched has not been shown to be like
        // anything, and if the deep ones are systematically the ones
        // that fail then the difference below is being estimated on the
        // shallow tail of the treatment. This table is how that is seen
        // rather than assumed.
        std::map<std::string, std::int64_t> treated_by_depth, matched_by_depth;
        std::set<std::size_t> matched_ids;
        for (const auto& p : match->pairs) matched_ids.insert(p.treated_id);
        double abs_prior_treated = 0.0, abs_prior_control = 0.0;
        std::int64_t abs_prior_n = 0;
        for (std::size_t u = 0; u < units.size(); ++u) {
            if (!units[u].treated) continue;
            const auto& r = panel[unit_row[u]];
            const std::string label = depth_bucket_label(r.peak_depth);
            ++treated_by_depth[label];
            if (matched_ids.count(units[u].id)) ++matched_by_depth[label];
        }
        for (const auto& p : match->pairs) {
            abs_prior_treated += std::abs(panel[unit_row[p.treated_id]].prior_rel_ret);
            abs_prior_control += std::abs(panel[unit_row[p.control_id]].prior_rel_ret);
            ++abs_prior_n;
        }
        nlohmann::json selection = nlohmann::json::array();
        for (const auto& label : {"q1_shallowest", "q2", "q3", "q4_deepest"}) {
            const std::int64_t total = treated_by_depth.count(label) ? treated_by_depth[label] : 0;
            const std::int64_t got = matched_by_depth.count(label) ? matched_by_depth[label] : 0;
            selection.push_back({{"bucket", label},
                                  {"treated", total},
                                  {"matched", got},
                                  {"match_rate", total > 0 ? static_cast<double>(got) /
                                                                  static_cast<double>(total)
                                                            : 0.0}});
        }
        matched["match_rate_by_depth_quartile"] = selection;
        // The magnitude the signed balance table cannot show: how far
        // each arm had actually moved away from its peers.
        matched["mean_abs_prior_relative_move"] = {
            {"treated", abs_prior_n > 0 ? abs_prior_treated / static_cast<double>(abs_prior_n) : 0.0},
            {"control", abs_prior_n > 0 ? abs_prior_control / static_cast<double>(abs_prior_n) : 0.0}};

        nlohmann::json per_horizon = nlohmann::json::array();
        for (std::size_t h = 0; h < horizons.size(); ++h) {
            std::vector<gm::signals::ClusterObservation> obs;
            obs.reserve(match->pairs.size() * 2);
            double treated_z_signed_sum = 0.0;
            std::int64_t treated_z_signed_n = 0;
            for (const auto& pair : match->pairs) {
                const PanelRow& t = panel[unit_row[pair.treated_id]];
                const PanelRow& c = panel[unit_row[pair.control_id]];
                const double yt = signed_outcome(t, h);
                const double yc = signed_outcome(c, h);
                // Both members or neither: dropping one half of a pair
                // reintroduces exactly the imbalance the pairing removed.
                if (std::isnan(yt) || std::isnan(yc)) continue;
                obs.push_back(gm::signals::ClusterObservation{yt, true, t.ticker, month_of(t.date)});
                obs.push_back(gm::signals::ClusterObservation{yc, false, c.ticker, month_of(c.date)});

                if (!std::isnan(t.fwd_rel_ret[h]) && t.z != 0.0) {
                    treated_z_signed_sum += (t.z > 0.0 ? -1.0 : 1.0) * t.fwd_rel_ret[h] - cost;
                    ++treated_z_signed_n;
                }
            }

            nlohmann::json entry;
            entry["horizon_days"] = horizons[h];
            entry["pairs_scored"] = static_cast<std::int64_t>(obs.size() / 2);
            if (obs.size() >= 3) {
                auto diff = gm::signals::clustered_difference(obs);
                if (!diff) return tl::unexpected(diff.error());
                entry["treated_mean_return"] = diff->treated_mean;
                entry["control_mean_return"] = diff->control_mean;
                entry["difference"] = diff->difference;
                entry["se_clustered"] = diff->se_clustered;
                entry["se_iid_for_comparison"] = diff->se_iid;
                entry["t_statistic"] = diff->t_statistic;
                entry["ci_low"] = diff->ci_low;
                entry["ci_high"] = diff->ci_high;
                entry["clusters_ticker"] = diff->clusters_a;
                entry["clusters_month"] = diff->clusters_b;
                entry["min_clusters"] = diff->min_clusters;
                entry["design_effect"] = diff->design_effect;
                entry["effective_n"] = diff->effective_n;
                entry["two_way_variance_adjusted"] = diff->two_way_variance_adjusted;
            } else {
                entry["note"] = "too few matched pairs at this horizon to estimate a difference";
            }
            entry["treated_mean_return_signed_by_z"] =
                treated_z_signed_n > 0
                    ? nlohmann::json(treated_z_signed_sum / static_cast<double>(treated_z_signed_n))
                    : nlohmann::json(nullptr);
            entry["treated_signed_by_z_n"] = treated_z_signed_n;
            per_horizon.push_back(entry);
        }
        matched["by_horizon"] = per_horizon;
        return matched;
    };

    auto primary = run_specification(
        "primary",
        /*control_relative_move=*/false, caliper,
        "PRIMARY. Treated and control moved similarly in absolute terms on the same day in the "
        "same sector; only the treated one moved away from its peers. A difference here is the "
        "geometry adding something beyond 'it went down a lot'.");
    if (!primary) return tl::unexpected(primary.error());
    auto over_controlled = run_specification(
        "over_controlled",
        /*control_relative_move=*/true, caliper,
        "LOWER BOUND, deliberately over-controlled: it additionally matches on the peer-relative "
        "move, which is most of the treatment. Expect a smaller difference and a much lower match "
        "rate. Quote the primary specification; this one is here to be argued with.");
    if (!over_controlled) return tl::unexpected(over_controlled.error());

    // The caliper is a free parameter, and a result that exists only at
    // one setting of a free parameter is not a result. Tightening it buys
    // comparability and costs sample; loosening it does the reverse.
    // Sweeping it here makes that trade part of the artifact rather than
    // something somebody once checked in a shell and did not write down.
    nlohmann::json sensitivity = nlohmann::json::array();
    for (const double c : {0.15, 0.25, 0.50, 1.00}) {
        auto spec = run_specification("sensitivity", /*control_relative_move=*/false, c,
                                       "caliper sensitivity of the primary specification");
        if (!spec) return tl::unexpected(spec.error());
        nlohmann::json row;
        row["caliper_pooled_sd"] = c;
        row["treated_matched"] = (*spec)["treated_matched"];
        row["match_rate"] = (*spec)["match_rate"];
        row["worst_standardized_diff_after"] = (*spec)["worst_standardized_diff_after"];
        nlohmann::json diffs = nlohmann::json::array();
        for (const auto& h : (*spec)["by_horizon"]) {
            if (!h.contains("difference")) continue;
            diffs.push_back({{"horizon_days", h["horizon_days"]},
                              {"difference", h["difference"]},
                              {"t_statistic", h["t_statistic"]},
                              {"ci_low", h["ci_low"]},
                              {"ci_high", h["ci_high"]}});
        }
        row["by_horizon"] = diffs;
        sensitivity.push_back(row);
    }

    // A machine-computed statement of what the primary specification
    // found, so the headline cannot drift away from the numbers
    // underneath it as the panel is re-run.
    double max_abs_t = 0.0;
    std::int64_t significant_positive = 0, significant_negative = 0;
    for (const auto& h : (*primary)["by_horizon"]) {
        if (!h.contains("t_statistic")) continue;
        const double t = h["t_statistic"].get<double>();
        max_abs_t = std::max(max_abs_t, std::abs(t));
        if (t > 1.96) ++significant_positive;
        if (t < -1.96) ++significant_negative;
    }

    nlohmann::json matched = nlohmann::json::object();
    matched["summary"] = {
        {"max_abs_t_primary", max_abs_t},
        {"horizons_with_significant_positive_difference", significant_positive},
        {"horizons_with_significant_negative_difference", significant_negative},
        {"horizons_tested", static_cast<std::int64_t>(horizons.size())},
        {"reading",
         "A POSITIVE difference means flagged excursions reverted MORE than matched controls, "
         "which is what ADR-013 requires. Zero significant positive horizons means the gate is "
         "NOT passed: the base rate in reverted_within_horizon is then regression to the mean, "
         "which the control arm exhibits too."}};
    matched["caliper_sensitivity_primary"] = sensitivity;
    matched["effective_n_note"] =
        "effective_n can exceed the observation count here, and that is not a bug. A matched pair "
        "shares a date, so the market-wide component of both outcomes is common and cancels in "
        "the contrast - the clustering correctly finds the same-day design MORE efficient than "
        "independent sampling would be, not less. Where effective_n falls BELOW the count, the "
        "dependence is real and the naive standard error was overstating the evidence.";
    matched["outcome_definition"] =
        "-sign(prior basket-relative move) x forward basket-relative log return over H trading "
        "days, entry-day basket weights held fixed, minus round-trip cost. Defined identically for "
        "both arms; the treated arm's own -sign(z) version is reported alongside for comparison, "
        "not used in the difference.";
    matched["primary"] = *primary;
    matched["over_controlled"] = *over_controlled;

    // ---------------------------------------------------------------
    // Survival, competing risks, and the legacy horizonless figures.
    // ---------------------------------------------------------------
    // A ticker whose price series stops well before the panel does was
    // almost certainly acquired or delisted; its open episodes can never
    // revert, and Kaplan-Meier must not be told to assume they behave
    // like the survivors. See BLOCKED.md entry 9 for why this is a
    // heuristic and what would replace it.
    // The union of every trading day any name in the panel saw, so
    // "how far short did this name stop" is counted in trading days
    // rather than in calendar days - a name that stopped on 20 December
    // is two weeks short by the calendar and only a handful of bars
    // short in fact.
    std::vector<std::string> union_calendar;
    std::map<std::string, std::size_t> union_index;
    {
        std::set<std::string> all_dates;
        for (const auto& [ticker, cal] : calendar) {
            (void)ticker;
            all_dates.insert(cal.begin(), cal.end());
        }
        union_calendar.assign(all_dates.begin(), all_dates.end());
        for (std::size_t i = 0; i < union_calendar.size(); ++i) union_index[union_calendar[i]] = i;
    }

    std::map<std::string, bool> series_ended_early;
    for (const auto& [ticker, cal] : calendar) {
        bool early = false;
        if (!cal.empty() && !union_calendar.empty()) {
            const auto last_it = union_index.find(cal.back());
            if (last_it != union_index.end()) {
                const std::int64_t missing =
                    static_cast<std::int64_t>(union_calendar.size() - 1 - last_it->second);
                early = missing > delisting_gap_days;
            }
        }
        series_ended_early[ticker] = early;
    }

    RevertBucket overall, with_earnings, without_earnings;
    std::map<std::string, RevertBucket> by_depth_quartile;
    std::map<std::string, RevertBucket> by_depth_quartile_no_earnings;
    std::map<std::string, std::vector<gm::signals::Episode>> episodes;
    std::map<std::string, std::vector<gm::signals::CompetingEpisode>> competing;
    std::map<std::string, std::set<std::string>> tickers_in_bucket, months_in_bucket;
    std::int64_t episodes_competing = 0;

    for (std::size_t i = 0; i < exc_ticker->size(); ++i) {
        const bool reverted = (*exc_reverted)[i] != 0;
        const bool earn = had_earnings[i] != 0;
        const std::string& ticker = (*exc_ticker)[i];

        overall.count++;
        if (reverted) overall.reverted_count++;
        auto& earn_bucket = earn ? with_earnings : without_earnings;
        earn_bucket.count++;
        if (reverted) earn_bucket.reverted_count++;

        const std::string label = depth_bucket_label((*exc_peak)[i]);
        auto& db = by_depth_quartile[label];
        db.label = label;
        db.count++;
        if (reverted) db.reverted_count++;
        if (!earn) {
            auto& db2 = by_depth_quartile_no_earnings[label];
            db2.label = label;
            db2.count++;
            if (reverted) db2.reverted_count++;
        }

        const gm::signals::Episode episode{(*exc_duration)[i], reverted};

        gm::signals::Outcome outcome = gm::signals::Outcome::kCensored;
        if (reverted) {
            outcome = gm::signals::Outcome::kEvent;
        } else {
            auto early_it = series_ended_early.find(ticker);
            if (early_it != series_ended_early.end() && early_it->second) {
                outcome = gm::signals::Outcome::kCompeting;
                ++episodes_competing;
            }
        }
        const gm::signals::CompetingEpisode ce{(*exc_duration)[i], outcome};

        const std::string earn_label = earn ? "with_earnings_or_8k" : "without_earnings_or_8k";
        for (const auto& bucket : {std::string{"overall"}, label, earn_label}) {
            episodes[bucket].push_back(episode);
            competing[bucket].push_back(ce);
            tickers_in_bucket[bucket].insert(ticker);
            months_in_bucket[bucket].insert(month_of((*exc_start)[i]));
        }
    }

    nlohmann::json by_horizon = nlohmann::json::object();
    for (const auto& [bucket, eps] : episodes) {
        auto curve = gm::signals::kaplan_meier(eps);
        if (!curve) return tl::unexpected(curve.error());
        auto cif = gm::signals::aalen_johansen(competing.at(bucket));
        if (!cif) return tl::unexpected(cif.error());

        nlohmann::json entry;
        entry["episodes"] = curve->n();
        entry["reverted"] = curve->events();
        entry["censored"] = curve->censored();
        entry["competing_events_delisted"] = cif->competing();
        // 7,110 episodes are not 7,110 independent facts. These two
        // counts are the cheapest way to see it.
        entry["distinct_tickers"] = static_cast<std::int64_t>(tickers_in_bucket.at(bucket).size());
        entry["distinct_months"] = static_cast<std::int64_t>(months_in_bucket.at(bucket).size());
        entry["median_days_to_reversion"] =
            curve->median_days() ? nlohmann::json(*curve->median_days()) : nlohmann::json(nullptr);

        nlohmann::json points = nlohmann::json::array();
        for (const auto h : horizons) {
            const auto est = curve->at(h);
            const auto inc = cif->at(h);
            points.push_back({{"horizon_days", est.horizon_days},
                               {"reverted_by", est.reverted_by},
                               {"ci_low", est.ci_low},
                               {"ci_high", est.ci_high},
                               {"at_risk_at_horizon", est.at_risk_at_horizon},
                               // Competing risks respected: a name being
                               // acquired can never revert, and its
                               // probability mass must not be handed to
                               // reversion.
                               {"reverted_by_competing_risks", inc.cif_event},
                               {"delisted_by", inc.cif_competing},
                               {"km_overstatement", inc.naive_overstatement}});
        }
        entry["horizons"] = points;
        by_horizon[bucket] = entry;
    }

    // ---------------------------------------------------------------
    // Half-life distribution (unchanged)
    // ---------------------------------------------------------------
    auto half_life_col = spreads->double_column("half_life");
    if (!half_life_col) return tl::unexpected(half_life_col.error());
    std::vector<double> sorted_half_life(half_life_col->begin(), half_life_col->end());
    std::sort(sorted_half_life.begin(), sorted_half_life.end());
    auto hl_quantile = [&](double q) -> double {
        if (sorted_half_life.empty()) return 0.0;
        const std::size_t idx =
            static_cast<std::size_t>(q * static_cast<double>(sorted_half_life.size() - 1));
        return sorted_half_life[idx];
    };

    // ---------------------------------------------------------------
    // excursions_tagged.parquet
    // ---------------------------------------------------------------
    gm::io::Table tagged;
    if (auto r = tagged.add_string_column("ticker", std::vector<std::string>(exc_ticker->begin(),
                                                                              exc_ticker->end()));
        !r)
        return tl::unexpected(r.error());
    if (auto r = tagged.add_string_column("start_date",
                                           std::vector<std::string>(exc_start->begin(), exc_start->end()));
        !r)
        return tl::unexpected(r.error());
    if (auto r =
            tagged.add_string_column("end_date", std::vector<std::string>(exc_end->begin(), exc_end->end()));
        !r)
        return tl::unexpected(r.error());
    if (auto r = tagged.add_double_column("peak_depth", std::vector<double>(exc_peak->begin(), exc_peak->end()));
        !r)
        return tl::unexpected(r.error());
    if (auto r = tagged.add_bool_column("reverted",
                                         std::vector<std::uint8_t>(exc_reverted->begin(), exc_reverted->end()));
        !r)
        return tl::unexpected(r.error());
    if (auto r = tagged.add_bool_column("had_earnings", had_earnings); !r) return tl::unexpected(r.error());
    {
        std::vector<std::uint8_t> competing_flag(exc_ticker->size(), 0);
        for (std::size_t i = 0; i < exc_ticker->size(); ++i) {
            if ((*exc_reverted)[i] != 0) continue;
            auto it = series_ended_early.find((*exc_ticker)[i]);
            competing_flag[i] = (it != series_ended_early.end() && it->second) ? 1 : 0;
        }
        if (auto r = tagged.add_bool_column("censored_by_delisting", competing_flag); !r)
            return tl::unexpected(r.error());
    }
    auto write1 = gm::io::write_parquet(tagged, output_dir / "excursions_tagged.parquet");
    if (!write1) return tl::unexpected(write1.error());

    // ---------------------------------------------------------------
    // reversion_study.json
    // ---------------------------------------------------------------
    nlohmann::json study;
    study["gate_verdict_note"] =
        "The number that decides ADR-013 is matched_control.primary.by_horizon[].difference "
        "together with its clustered interval - NOT reverted_within_horizon, which is a base rate: "
        "it says how often a flagged excursion comes back, not whether it comes back more than a "
        "comparable unflagged name on the same day. Before reading either, read the primary "
        "specification's balance table and its match_rate_by_depth_quartile: an unmatched "
        "excursion has not been shown to be like anything, and if the deep ones are the ones that "
        "fail to match then the difference is being estimated on the shallow tail of the "
        "treatment.";
    study["matched_control"] = matched;
    study["reverted_within_horizon"] = by_horizon;
    study["horizon_note"] =
        "P(reverted by H trading days) per bucket, Kaplan-Meier with Greenwood 95% intervals, "
        "alongside the Aalen-Johansen figure that treats a delisting as a competing risk rather "
        "than as censoring. `km_overstatement` is the difference between them: probability mass "
        "Kaplan-Meier hands to reversion on behalf of episodes that could never revert. The "
        "`ever_reverted` figures below are the horizonless measure this replaced - they read "
        "~0.998 in every bucket because `reverted` means 'closed before the price series ended', "
        "which is very nearly tautological over sixteen years. Kept only so the two can be "
        "compared.";
    study["overall"] = {{"count", overall.count},
                         {"reverted", overall.reverted_count},
                         {"ever_reverted_rate", overall.reversion_rate()}};
    study["with_earnings_or_8k"] = {{"count", with_earnings.count},
                                     {"reverted", with_earnings.reverted_count},
                                     {"ever_reverted_rate", with_earnings.reversion_rate()}};
    study["without_earnings_or_8k"] = {{"count", without_earnings.count},
                                        {"reverted", without_earnings.reverted_count},
                                        {"ever_reverted_rate", without_earnings.reversion_rate()}};
    study["earnings_conditioned_gap"] =
        without_earnings.reversion_rate() - with_earnings.reversion_rate();

    nlohmann::json by_depth = nlohmann::json::array();
    for (const auto& label : {"q1_shallowest", "q2", "q3", "q4_deepest"}) {
        auto it = by_depth_quartile.find(label);
        auto it_no_earn = by_depth_quartile_no_earnings.find(label);
        nlohmann::json entry;
        entry["bucket"] = label;
        entry["count"] = it != by_depth_quartile.end() ? it->second.count : 0;
        entry["reversion_rate"] = it != by_depth_quartile.end() ? it->second.reversion_rate() : 0.0;
        entry["count_excluding_earnings"] =
            it_no_earn != by_depth_quartile_no_earnings.end() ? it_no_earn->second.count : 0;
        entry["reversion_rate_excluding_earnings"] =
            it_no_earn != by_depth_quartile_no_earnings.end() ? it_no_earn->second.reversion_rate() : 0.0;
        by_depth.push_back(entry);
    }
    study["by_peak_depth_quartile"] = by_depth;
    study["peak_depth_quartile_thresholds"] = {{"q25", q25}, {"q50", q50}, {"q75", q75}};
    study["half_life_distribution_days"] = {
        {"p10", hl_quantile(0.10)}, {"median", hl_quantile(0.50)}, {"p90", hl_quantile(0.90)}};
    study["panel"] = {{"rows_considered", static_cast<std::int64_t>(spd_date->size())},
                       {"rows_in_either_arm", static_cast<std::int64_t>(panel.size())},
                       {"rows_dropped_no_basket", rows_without_basket},
                       {"rows_dropped_no_prior_move", rows_without_prior},
                       {"panel_last_date", panel_last_date},
                       {"tickers_series_ended_early",
                        static_cast<std::int64_t>(std::count_if(series_ended_early.begin(),
                                                                 series_ended_early.end(),
                                                                 [](const auto& kv) { return kv.second; }))}};

    const std::filesystem::path study_path = output_dir / "reversion_study.json";
    std::ofstream study_out(study_path, std::ios::binary | std::ios::trunc);
    if (!study_out) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure, "failed to write reversion study",
                                               study_path.string()));
    }
    study_out << study.dump(2);

    manifest.set_int("excursions_studied", overall.count);
    manifest.set_int("tickers_with_excursions", static_cast<std::int64_t>(tickers_with_excursions.size()));
    manifest.set_int("tickers_missing_cik", tickers_missing_cik);
    manifest.set_int("tickers_earnings_fetch_failed", tickers_fetch_failed);
    manifest.set_int("episodes_competing_delisted", episodes_competing);
    manifest.set_int("matched_pairs_primary", (*primary)["treated_matched"].get<std::int64_t>());
    manifest.set_int("treated_total", (*primary)["treated_total"].get<std::int64_t>());
    manifest.set_double("match_rate_primary", (*primary)["match_rate"].get<double>());
    manifest.set_double("worst_standardized_diff_after_primary",
                         (*primary)["worst_standardized_diff_after"].get<double>());
    manifest.set_int("matched_pairs_over_controlled",
                      (*over_controlled)["treated_matched"].get<std::int64_t>());
    manifest.set_double("gate_max_abs_t", max_abs_t);
    manifest.set_int("gate_horizons_significant_positive", significant_positive);
    manifest.set_int("gate_horizons_significant_negative", significant_negative);
    manifest.set_string("gate_verdict", significant_positive > 0
                                             ? "positive_difference_found"
                                             : "not_passed_no_positive_difference");
    manifest.set_double("overall_ever_reverted_rate", overall.reversion_rate());
    manifest.set_string("covariates_unavailable",
                         covariates_unavailable.empty()
                             ? std::string{"none"}
                             : std::accumulate(std::next(covariates_unavailable.begin()),
                                                covariates_unavailable.end(), covariates_unavailable.front(),
                                                [](std::string a, const std::string& b) {
                                                    return std::move(a) + "," + b;
                                                }));

    return {};
}

}  // namespace

int main(int argc, char** argv) {
    return gm::run_stage_main(argc, argv, "gm-report", run_gm_report);
}
