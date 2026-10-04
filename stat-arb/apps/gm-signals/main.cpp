// gm-signals: peer baskets, OU fitting, excursion tracking (ADR §6.4-6.5,
// ADR §13 M4: "Peer baskets (OSQP), OU fitting, excursion tracking ...
// a defensible out-of-sample answer to 'do excursions revert?'").
//
// For each ticker, at each date with sufficient trailing history:
//   1. Look up that ticker's k-nearest-neighbour set as of that date
//      from gm-geometry's edges.parquet (in_knn=true rows only - NOT
//      in_mst, which can include bridge edges that aren't genuine
//      neighbour relationships; see graph.hpp).
//   2. Fit peer-basket weights (gm::signals::fit_peer_basket_weights)
//      on a trailing window of RETURNS ending YESTERDAY - strictly
//      before today, mirroring View B's causality discipline (ADR §6.4)
//      rather than View A's fit-and-score-the-same-frame pattern. Using
//      today's own return to fit the very model that scores today would
//      be a real look-ahead flaw for a signal ADR §6.5 means to trade.
//   3. Build the spread level series s(tau) = ln P_i(tau) - sum(w_j *
//      ln P_j(tau)) over that same trailing (pre-today) window, fit an
//      OU process to it, then compute TODAY's spread s(t) with the
//      already-fit weights and score it against the already-fit OU
//      model - today's price is used only as the point being scored,
//      never as training data.
//   4. Once every date's z-score is computed, run excursion detection
//      per ticker over its full z-score history.
//
// Writes spreads.parquet (date, ticker, z, spread, half_life,
// n_neighbors), baskets.parquet (date, ticker, neighbor_ticker, weight -
// the entry-day peer-basket weights a downstream consumer needs to
// reconstruct a FIXED-basket spread series for a held position, since
// spreads.parquet's own `spread` column is refit fresh every day and
// is only valid for THAT day's z-score, not for computing a held
// position's P&L across multiple days), and excursions.parquet
// (ticker, start_date, end_date, peak_depth, reverted, duration_days).

#include <gm-boundaries/mahalanobis.hpp>
#include <gm-core/stage_main.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>
#include <gm-signals/excursion.hpp>
#include <gm-signals/ou_fit.hpp>
#include <gm-signals/peer_basket.hpp>

#include <Eigen/Dense>

#include <algorithm>
#include <cmath>
#include <map>
#include <optional>
#include <set>
#include <vector>

namespace {

/// ticker -> date -> ln(adjclose). A flat map-of-maps rather than a
/// rectangular panel (unlike gm-geometry's build_return_panel): View C
/// works per-ticker against a per-ticker-chosen neighbour set that
/// changes day to day, so there is no single shared date x ticker grid
/// worth materializing up front the way there is for the frame-wide
/// correlation/embedding pipeline.
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
        if (!(p > 0.0)) continue; // a non-positive price has no logarithm; skip rather than fabricate one
        result[(*ticker_col)[i]][(*date_col)[i]] = std::log(p);
    }
    return result;
}

/// date -> ticker -> its k-NN neighbour tickers as of that date
/// (in_knn=true rows only, from gm-geometry's edges.parquet - see the
/// file header on why in_mst is the wrong column to filter on here).
using KnnMap = std::map<std::string, std::map<std::string, std::vector<std::string>>>;

/// The set of tickers gm-geometry actually carried through its
/// liquidity-and-history filtering (ADR-001/ADR-016) - every ticker
/// that appears in at least one in_knn edge. gm-ingest's prices.parquet
/// covers a much larger candidate universe (every ticker considered
/// before that filtering), so iterating log_prices' own keys directly
/// would walk hundreds of tickers gm-geometry never admitted, each one
/// contributing nothing but skip-counted no-op iterations across their
/// entire multi-year history - wasted computation, and a
/// rows_skipped_incomplete figure dominated by "this ticker was never
/// in scope" rather than genuine data gaps within the real universe.
gm::Result<std::set<std::string>> load_active_universe(const gm::io::Table& edges) {
    auto ticker_a_col = edges.string_column("ticker_a");
    if (!ticker_a_col) return tl::unexpected(ticker_a_col.error());
    auto ticker_b_col = edges.string_column("ticker_b");
    if (!ticker_b_col) return tl::unexpected(ticker_b_col.error());
    auto in_knn_col = edges.bool_column("in_knn");
    if (!in_knn_col) return tl::unexpected(in_knn_col.error());

    std::set<std::string> result;
    for (std::size_t i = 0; i < ticker_a_col->size(); ++i) {
        if (!(*in_knn_col)[i]) continue;
        result.insert((*ticker_a_col)[i]);
        result.insert((*ticker_b_col)[i]);
    }
    return result;
}

gm::Result<KnnMap> load_knn_neighbors(const gm::io::Table& edges) {
    auto date_col = edges.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_a_col = edges.string_column("ticker_a");
    if (!ticker_a_col) return tl::unexpected(ticker_a_col.error());
    auto ticker_b_col = edges.string_column("ticker_b");
    if (!ticker_b_col) return tl::unexpected(ticker_b_col.error());
    auto in_knn_col = edges.bool_column("in_knn");
    if (!in_knn_col) return tl::unexpected(in_knn_col.error());

    KnnMap result;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        if (!(*in_knn_col)[i]) continue;
        const std::string& date = (*date_col)[i];
        const std::string& a = (*ticker_a_col)[i];
        const std::string& b = (*ticker_b_col)[i];
        // edges.parquet stores each unordered pair once (i<j
        // canonical ordering, graph.hpp) - both endpoints must see the
        // other as a neighbour here, since the graph itself is
        // undirected by construction.
        result[date][a].push_back(b);
        result[date][b].push_back(a);
    }
    return result;
}

struct SpreadRow {
    std::string date;
    std::string ticker;
    double z;
    double spread;
    double half_life;
    int n_neighbors;
    std::vector<std::string> neighbor_tickers; // parallel to neighbor_weights
    std::vector<double> neighbor_weights;
};

/// Computes ticker `target`'s spread and z-score at date index `t`
/// (into `target_dates`, its own chronological date list), using the
/// trailing `window` prior dates [t-window, t) for fitting - see the
/// file header for why today (index t) is excluded from every fit.
/// Returns std::nullopt (not an error) when data is incomplete for
/// this particular (ticker, date) - e.g. a neighbour missing a price on
/// one of the window dates - since that is an expected, non-fatal gap
/// in a 16-year multi-ticker panel, not a validation failure that
/// should halt the whole stage.
std::optional<SpreadRow> compute_spread_row(const std::string& target, const std::vector<std::string>& target_dates,
                                             std::size_t t, const std::vector<std::string>& neighbors,
                                             const LogPriceMap& log_prices, std::size_t window,
                                             double ridge_lambda) {
    const auto& target_prices = log_prices.at(target);

    // The causal fit window is the `window` dates strictly before
    // today: target_dates[t-window .. t-1].
    std::vector<std::string> fit_dates(target_dates.begin() + static_cast<std::ptrdiff_t>(t - window),
                                        target_dates.begin() + static_cast<std::ptrdiff_t>(t));

    Eigen::VectorXd target_returns(static_cast<Eigen::Index>(window) - 1);
    for (std::size_t i = 0; i + 1 < fit_dates.size(); ++i) {
        auto p0 = target_prices.find(fit_dates[i]);
        auto p1 = target_prices.find(fit_dates[i + 1]);
        if (p0 == target_prices.end() || p1 == target_prices.end()) return std::nullopt;
        target_returns(static_cast<Eigen::Index>(i)) = p1->second - p0->second;
    }

    std::vector<const std::map<std::string, double>*> neighbor_price_maps;
    for (const auto& nb : neighbors) {
        auto it = log_prices.find(nb);
        if (it == log_prices.end()) return std::nullopt;
        neighbor_price_maps.push_back(&it->second);
    }
    const auto k = static_cast<Eigen::Index>(neighbors.size());

    Eigen::MatrixXd neighbor_returns(static_cast<Eigen::Index>(window) - 1, k);
    for (Eigen::Index j = 0; j < k; ++j) {
        const auto& nb_prices = *neighbor_price_maps[static_cast<std::size_t>(j)];
        for (std::size_t i = 0; i + 1 < fit_dates.size(); ++i) {
            auto p0 = nb_prices.find(fit_dates[i]);
            auto p1 = nb_prices.find(fit_dates[i + 1]);
            if (p0 == nb_prices.end() || p1 == nb_prices.end()) return std::nullopt;
            neighbor_returns(static_cast<Eigen::Index>(i), j) = p1->second - p0->second;
        }
    }

    auto weights = gm::signals::fit_peer_basket_weights(target_returns, neighbor_returns, ridge_lambda);
    if (!weights) return std::nullopt;

    // Spread LEVEL series over the same fit_dates window (all strictly
    // before today), for the OU fit.
    Eigen::VectorXd spread_window(static_cast<Eigen::Index>(fit_dates.size()));
    for (std::size_t i = 0; i < fit_dates.size(); ++i) {
        auto tp = target_prices.find(fit_dates[i]);
        if (tp == target_prices.end()) return std::nullopt;
        double s = tp->second;
        for (Eigen::Index j = 0; j < k; ++j) {
            auto np = neighbor_price_maps[static_cast<std::size_t>(j)]->find(fit_dates[i]);
            if (np == neighbor_price_maps[static_cast<std::size_t>(j)]->end()) return std::nullopt;
            s -= (*weights)(j) * np->second;
        }
        spread_window(static_cast<Eigen::Index>(i)) = s;
    }

    auto ou = gm::signals::fit_ou(spread_window, /*dt=*/1.0);
    if (!ou) return std::nullopt;

    // Today's spread, scored against the pre-fit model - the only place
    // today's own price is used.
    const std::string& today = target_dates[t];
    auto tp_today = target_prices.find(today);
    if (tp_today == target_prices.end()) return std::nullopt;
    double s_today = tp_today->second;
    for (Eigen::Index j = 0; j < k; ++j) {
        auto np = neighbor_price_maps[static_cast<std::size_t>(j)]->find(today);
        if (np == neighbor_price_maps[static_cast<std::size_t>(j)]->end()) return std::nullopt;
        s_today -= (*weights)(j) * np->second;
    }

    auto z = gm::signals::ou_zscore(*ou, s_today);
    if (!z) return std::nullopt;

    std::vector<double> weight_values(weights->data(), weights->data() + weights->size());
    return SpreadRow{today,      target,  *z, s_today, ou->half_life, static_cast<int>(k),
                      neighbors, std::move(weight_values)};
}

/// One ticker's View C rows: the boundary on (z, z-dot) that ADR 6.4
/// specifies, fitted to the trailing window of this name's own
/// (z, z-dot) pairs and scoring today's pair against it.
///
/// z-dot is the one-step change in z. A threshold on |z| alone cannot
/// tell "two standard deviations out and still widening" from "two out
/// and snapping back", and those are opposite trades; the second
/// coordinate is what separates them.
///
/// Strictly causal, exactly as View B is: the window ends the day BEFORE
/// the point being scored, so a pair never helps build the cloud it is
/// measured against.
struct ViewCRows {
    std::vector<std::string> dates, tickers, views, estimators;
    std::vector<double> depths, pvalues;
    std::vector<std::uint8_t> insides;
    std::int64_t fit_failures = 0;
};

void score_view_c(const std::vector<std::string>& dates, const std::vector<double>& z,
                  const std::string& ticker, std::int64_t lookback, double alpha,
                  ViewCRows& out) {
    if (z.size() < 2) return;

    // (z, z-dot) pairs, one per date from the second onward - the first
    // date has no previous z to difference against.
    std::vector<std::array<double, 2>> pairs;
    std::vector<std::string> pair_dates;
    pairs.reserve(z.size() - 1);
    pair_dates.reserve(z.size() - 1);
    for (std::size_t i = 1; i < z.size(); ++i) {
        if (!std::isfinite(z[i]) || !std::isfinite(z[i - 1])) continue;
        pairs.push_back({z[i], z[i] - z[i - 1]});
        pair_dates.push_back(dates[i]);
    }
    if (static_cast<std::int64_t>(pairs.size()) <= lookback) return;

    for (std::size_t i = static_cast<std::size_t>(lookback); i < pairs.size(); ++i) {
        const std::size_t first = i - static_cast<std::size_t>(lookback);
        Eigen::MatrixXd training(static_cast<Eigen::Index>(lookback), 2);
        for (std::size_t j = first; j < i; ++j) {
            training(static_cast<Eigen::Index>(j - first), 0) = pairs[j][0];
            training(static_cast<Eigen::Index>(j - first), 1) = pairs[j][1];
        }
        Eigen::VectorXd query(2);
        query(0) = pairs[i][0];
        query(1) = pairs[i][1];

        auto fit = gm::boundaries::fit_mahalanobis(training);
        if (!fit) {
            ++out.fit_failures;
            continue;
        }
        auto score = gm::boundaries::score_mahalanobis(*fit, query, alpha);
        if (!score) {
            ++out.fit_failures;
            continue;
        }
        out.dates.push_back(pair_dates[i]);
        out.tickers.push_back(ticker);
        out.views.emplace_back("C");
        out.estimators.emplace_back("mahalanobis");
        out.depths.push_back(score->depth);
        out.pvalues.push_back(score->p_value);
        out.insides.push_back(score->inside ? 1 : 0);
    }
}

gm::VoidResult run_gm_signals(const gm::Config& config, const std::filesystem::path& output_dir,
                               gm::Manifest& manifest) {
    std::error_code ec;
    std::filesystem::create_directories(output_dir, ec);
    if (ec) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to create output directory", output_dir.string()));
    }

    // Sibling stage directories, same convention gm-boundaries and
    // gm-geometry already use for reading upstream artifacts.
    std::filesystem::path ingest_dir = output_dir.parent_path() / "gm-ingest";
    std::filesystem::path geometry_dir = output_dir.parent_path() / "gm-geometry";

    auto prices = gm::io::read_parquet(ingest_dir / "prices.parquet");
    if (!prices) return tl::unexpected(prices.error());
    auto edges = gm::io::read_parquet(geometry_dir / "edges.parquet");
    if (!edges) return tl::unexpected(edges.error());

    // ADR-012: Read regime.parquet to get tear_flag per date. gm-signals
    // does NOT act on this veto itself - it TAGS every spreads.parquet row
    // with the tear_flag of its date and writes every row it computes,
    // full stop. Actually rejecting a tear-day candidate from trading is
    // gm-backtest's job (apps/gm-backtest/main.cpp, alongside View A's and
    // View B's vetoes, into its own rejected_tear_veto counter), for two
    // reasons found the hard way on the real 16-year run:
    //   1. Dropping rows HERE desynced spreads.parquet/baskets.parquet
    //      from excursions.parquet (excursion detection below runs over
    //      the FULL z-score series, tear days included, since a tear day
    //      is real out-of-sample data about whether the spread reverted -
    //      not a reason to pretend the observation never happened). An
    //      excursion starting on a tear day would then find no matching
    //      spreads.parquet row downstream, and gm-backtest's
    //      rejected_no_spread_data counter - documented as catching a
    //      genuine cross-stage inconsistency, not an expected data gap -
    //      silently absorbed 819/7376 (11.1%) of all excursions as if
    //      they were data corruption, when they were a deliberate policy
    //      decision. See git history / ADR.md for the postmortem.
    //   2. ADR-012 vetoes "views B and C" trading signals, i.e. a trading
    //      decision - the same kind of decision View A's structural-change
    //      veto and View B's outside-boundary check already are, and both
    //      of those are enforced in gm-backtest, not here. Tagging here
    //      and enforcing there keeps all four ADR §6.5 entry vetoes in one
    //      place with one counter each, and keeps this stage's own output
    //      a straightforward "here is what the data says" artifact.
    auto regime = gm::io::read_parquet(geometry_dir / "regime.parquet");
    if (!regime) return tl::unexpected(regime.error());
    auto regime_dates_col = regime->string_column("date");
    if (!regime_dates_col) return tl::unexpected(regime_dates_col.error());
    auto tear_flag_col = regime->bool_column("tear_flag");
    if (!tear_flag_col) return tl::unexpected(tear_flag_col.error());

    // Build date -> tear_flag map for O(log n) lookup
    std::map<std::string, bool> tear_flag_by_date;
    for (std::size_t i = 0; i < regime_dates_col->size(); ++i) {
        tear_flag_by_date[(*regime_dates_col)[i]] = (*tear_flag_col)[i];
    }

    auto log_prices = load_log_prices(*prices);
    if (!log_prices) return tl::unexpected(log_prices.error());
    auto knn = load_knn_neighbors(*edges);
    if (!knn) return tl::unexpected(knn.error());
    auto active_universe = load_active_universe(*edges);
    if (!active_universe) return tl::unexpected(active_universe.error());

    std::int64_t window = config.get_int_or("signals.spread_fit_window_days", 60);
    double ridge_lambda = config.get_double_or("signals.ridge_lambda", 1e-6);
    double z_entry = config.get_double_or("signals.z_entry", 2.0);
    double z_exit = config.get_double_or("signals.z_exit", 0.5);

    if (window < 3) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "signals.spread_fit_window_days must be >= 3"));
    }

    std::vector<std::string> out_dates, out_tickers;
    std::vector<double> out_z, out_spread, out_half_life;
    std::vector<std::int64_t> out_n_neighbors;
    std::vector<std::uint8_t> out_tear_flag;

    // Per (date,ticker), one row per basket neighbour: the ENTRY-DAY
    // weights a downstream consumer (gm-backtest) needs to reconstruct
    // a FIXED-basket spread series for a held position - spreads.parquet's
    // own `spread` column is refit fresh every single day (a new causal
    // window, and even a different neighbour SET, since gm-geometry's
    // k-NN graph itself changes day to day), so spread[t]-spread[t-1]
    // does NOT represent one consistent position's mark-to-market P&L;
    // it can silently mix a real price move with an artifact of the
    // reference basket changing out from under the position entirely.
    // Found the hard way on the real 16-year backtest: a single day
    // where several unrelated tickers' spreads jumped ~2 in log-space
    // simultaneously - traced to a wholesale k-NN neighbour-set swap on
    // that date (see the git history for the specific case), not any
    // real market move.
    std::vector<std::string> basket_dates, basket_tickers, basket_neighbor_tickers;
    std::vector<double> basket_weights;

    // ticker -> chronological z-score series, kept alongside the dates
    // they correspond to - needed to run excursion detection per
    // ticker once every date's z is computed.
    std::map<std::string, std::vector<std::string>> zscore_dates_by_ticker;
    std::map<std::string, std::vector<double>> zscore_series_by_ticker;

    std::int64_t rows_skipped_incomplete = 0;
    // ADR-012: count of computed rows whose date is tear-flagged - a
    // visible, attributable record of the veto's reach at this stage.
    // Not a rejection count (gm-backtest's rejected_tear_veto is the
    // trading-relevant one, since it only counts EXCURSION-START-day tear
    // flags); this is the broader "how much of the raw signal surface did
    // ADR-012 touch" figure.
    std::int64_t rows_tear_flagged = 0;

    for (const auto& ticker : *active_universe) {
        auto price_it = log_prices->find(ticker);
        if (price_it == log_prices->end()) {
            // A ticker gm-geometry admitted but gm-ingest's price map has
            // no entry for at all would be a real cross-stage inconsistency
            // (not an expected data gap) - counted rather than silently
            // dropped, but this should not happen in practice since
            // gm-geometry's universe is itself derived from prices.parquet.
            ++rows_skipped_incomplete;
            continue;
        }
        const auto& date_price_map = price_it->second;

        std::vector<std::string> dates;
        dates.reserve(date_price_map.size());
        for (const auto& [d, _] : date_price_map) dates.push_back(d); // std::map keys are already sorted

        if (static_cast<std::int64_t>(dates.size()) <= window) continue; // not enough history for even one fit

        for (std::size_t t = static_cast<std::size_t>(window); t < dates.size(); ++t) {
            const std::string& date = dates[t];
            auto date_it = knn->find(date);
            if (date_it == knn->end()) {
                ++rows_skipped_incomplete;
                continue;
            }
            auto ticker_it = date_it->second.find(ticker);
            if (ticker_it == date_it->second.end() || ticker_it->second.empty()) {
                ++rows_skipped_incomplete;
                continue;
            }

            auto row = compute_spread_row(ticker, dates, t, ticker_it->second, *log_prices,
                                           static_cast<std::size_t>(window), ridge_lambda);
            if (!row) {
                ++rows_skipped_incomplete;
                continue;
            }

            // ADR-012: TAG this row with its date's tear_flag - do not drop
            // it. See the tear_flag_by_date comment above for why the
            // actual trading veto is enforced in gm-backtest instead.
            auto tear_it = tear_flag_by_date.find(row->date);
            bool tear = (tear_it != tear_flag_by_date.end() && tear_it->second);
            if (tear) ++rows_tear_flagged;

            out_dates.push_back(row->date);
            out_tickers.push_back(row->ticker);
            out_z.push_back(row->z);
            out_spread.push_back(row->spread);
            out_half_life.push_back(row->half_life);
            out_n_neighbors.push_back(row->n_neighbors);
            out_tear_flag.push_back(tear ? 1 : 0);

            for (std::size_t j = 0; j < row->neighbor_tickers.size(); ++j) {
                basket_dates.push_back(row->date);
                basket_tickers.push_back(row->ticker);
                basket_neighbor_tickers.push_back(row->neighbor_tickers[j]);
                basket_weights.push_back(row->neighbor_weights[j]);
            }

            zscore_dates_by_ticker[ticker].push_back(row->date);
            zscore_series_by_ticker[ticker].push_back(row->z);
        }
    }

    gm::io::Table spreads_table;
    if (auto r = spreads_table.add_string_column("date", std::move(out_dates)); !r) return tl::unexpected(r.error());
    if (auto r = spreads_table.add_string_column("ticker", std::move(out_tickers)); !r)
        return tl::unexpected(r.error());
    if (auto r = spreads_table.add_double_column("z", std::move(out_z)); !r) return tl::unexpected(r.error());
    if (auto r = spreads_table.add_double_column("spread", std::move(out_spread)); !r)
        return tl::unexpected(r.error());
    if (auto r = spreads_table.add_double_column("half_life", std::move(out_half_life)); !r)
        return tl::unexpected(r.error());
    if (auto r = spreads_table.add_int64_column("n_neighbors", std::move(out_n_neighbors)); !r)
        return tl::unexpected(r.error());
    // ADR-012: this date's tear_flag (gm-geometry's regime.parquet),
    // carried through so gm-backtest can enforce the veto itself (see the
    // tear_flag_by_date comment above) without re-reading regime.parquet
    // and without any row here ever going missing relative to
    // excursions.parquet's z-score-derived rows.
    if (auto r = spreads_table.add_bool_column("tear_flag", std::move(out_tear_flag)); !r)
        return tl::unexpected(r.error());

    auto write1 = gm::io::write_parquet(spreads_table, output_dir / "spreads.parquet");
    if (!write1) return tl::unexpected(write1.error());

    gm::io::Table baskets_table;
    if (auto r = baskets_table.add_string_column("date", std::move(basket_dates)); !r)
        return tl::unexpected(r.error());
    if (auto r = baskets_table.add_string_column("ticker", std::move(basket_tickers)); !r)
        return tl::unexpected(r.error());
    if (auto r = baskets_table.add_string_column("neighbor_ticker", std::move(basket_neighbor_tickers)); !r)
        return tl::unexpected(r.error());
    if (auto r = baskets_table.add_double_column("weight", std::move(basket_weights)); !r)
        return tl::unexpected(r.error());

    auto write_baskets = gm::io::write_parquet(baskets_table, output_dir / "baskets.parquet");
    if (!write_baskets) return tl::unexpected(write_baskets.error());

    // Excursion detection, per ticker, over its own chronological
    // z-score history built above.
    std::vector<std::string> exc_tickers, exc_start_dates, exc_end_dates;
    std::vector<double> exc_peak_depths;
    std::vector<std::uint8_t> exc_reverted;
    std::vector<std::int64_t> exc_duration_days;

    // ADR 6.4's View C boundary. Written as its own artifact rather than
    // into gm-boundaries' scores.parquet because that stage runs before
    // this one and the z-series does not exist yet when it does - but with
    // the SAME schema, so a consumer reads both identically.
    const std::int64_t view_c_lookback = config.get_int_or("signals.view_c_lookback_days", 120);
    const double view_c_alpha = config.get_double_or("signals.view_c_alpha", 0.05);
    ViewCRows view_c;
    if (view_c_lookback >= 3) {
        for (const auto& [ticker, series] : zscore_series_by_ticker) {
            const auto dates_it = zscore_dates_by_ticker.find(ticker);
            if (dates_it == zscore_dates_by_ticker.end()) continue;
            score_view_c(dates_it->second, series, ticker, view_c_lookback, view_c_alpha, view_c);
        }
    }

    for (const auto& [ticker, dates] : zscore_dates_by_ticker) {
        const auto& series = zscore_series_by_ticker.at(ticker);
        Eigen::VectorXd z_vec = Eigen::Map<const Eigen::VectorXd>(series.data(), static_cast<Eigen::Index>(series.size()));

        auto excursions = gm::signals::detect_excursions(z_vec, z_entry, z_exit);
        if (!excursions) return tl::unexpected(excursions.error());

        for (const auto& e : *excursions) {
            exc_tickers.push_back(ticker);
            exc_start_dates.push_back(dates[e.start_index]);
            exc_end_dates.push_back(dates[e.end_index]);
            exc_peak_depths.push_back(e.peak_depth);
            exc_reverted.push_back(e.reverted ? 1 : 0);
            exc_duration_days.push_back(static_cast<std::int64_t>(e.end_index - e.start_index));
        }
    }

    gm::io::Table excursions_table;
    if (auto r = excursions_table.add_string_column("ticker", std::move(exc_tickers)); !r)
        return tl::unexpected(r.error());
    if (auto r = excursions_table.add_string_column("start_date", std::move(exc_start_dates)); !r)
        return tl::unexpected(r.error());
    if (auto r = excursions_table.add_string_column("end_date", std::move(exc_end_dates)); !r)
        return tl::unexpected(r.error());
    if (auto r = excursions_table.add_double_column("peak_depth", std::move(exc_peak_depths)); !r)
        return tl::unexpected(r.error());
    if (auto r = excursions_table.add_bool_column("reverted", std::move(exc_reverted)); !r)
        return tl::unexpected(r.error());
    if (auto r = excursions_table.add_int64_column("duration_days", std::move(exc_duration_days)); !r)
        return tl::unexpected(r.error());

    auto write2 = gm::io::write_parquet(excursions_table, output_dir / "excursions.parquet");
    if (!write2) return tl::unexpected(write2.error());

    manifest.set_int("active_universe_size", static_cast<std::int64_t>(active_universe->size()));
    manifest.set_int("rows_written", static_cast<std::int64_t>(spreads_table.num_rows()));
    manifest.set_int("basket_rows_written", static_cast<std::int64_t>(baskets_table.num_rows()));
    manifest.set_int("rows_skipped_incomplete", rows_skipped_incomplete);
    // View C's boundary scores, same schema as gm-boundaries' scores.parquet.
    gm::io::Table view_c_table;
    if (auto r = view_c_table.add_string_column("date", std::move(view_c.dates)); !r) return tl::unexpected(r.error());
    if (auto r = view_c_table.add_string_column("ticker", std::move(view_c.tickers)); !r) return tl::unexpected(r.error());
    if (auto r = view_c_table.add_string_column("view", std::move(view_c.views)); !r) return tl::unexpected(r.error());
    if (auto r = view_c_table.add_string_column("estimator", std::move(view_c.estimators)); !r) return tl::unexpected(r.error());
    if (auto r = view_c_table.add_double_column("depth", std::move(view_c.depths)); !r) return tl::unexpected(r.error());
    if (auto r = view_c_table.add_double_column("pvalue", std::move(view_c.pvalues)); !r) return tl::unexpected(r.error());
    if (auto r = view_c_table.add_bool_column("inside", std::move(view_c.insides)); !r) return tl::unexpected(r.error());
    auto write_view_c = gm::io::write_parquet(view_c_table, output_dir / "view_c_scores.parquet");
    if (!write_view_c) return tl::unexpected(write_view_c.error());

    manifest.set_int("view_c_rows", static_cast<std::int64_t>(view_c_table.num_rows()));
    manifest.set_int("view_c_lookback_days", view_c_lookback);
    // A fit can fail on a degenerate window - a stretch where z barely
    // moved leaves z-dot with no spread at all. Counted so a run that
    // silently produced almost nothing is distinguishable from one that
    // had nothing to produce.
    manifest.set_int("view_c_fit_failures", view_c.fit_failures);

    manifest.set_int("rows_tear_flagged", rows_tear_flagged);
    manifest.set_int("excursions_written", static_cast<std::int64_t>(excursions_table.num_rows()));
    manifest.set_int("spread_fit_window_days", window);
    manifest.set_double("ridge_lambda", ridge_lambda);
    manifest.set_double("z_entry", z_entry);
    manifest.set_double("z_exit", z_exit);

    return {};
}

} // namespace

int main(int argc, char** argv) {
    return gm::run_stage_main(argc, argv, "gm-signals", run_gm_signals);
}
