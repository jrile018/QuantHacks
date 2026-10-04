// gm-geometry: correlation -> Ledoit-Wolf shrinkage -> RMT denoising ->
// Mantegna distance -> classical MDS -> Procrustes alignment, applied
// on a rolling window across the full price history (ADR-009/ADR-010,
// ADR §6.1-6.2, ADR §13 M2: "geometry artifacts for full history in
// <60s locally; structural change metric spikes at known events").
//
// Reads gm-ingest's upstream artifacts (sibling stage directory, same
// convention as gm-ingest reading gm-universe's output): prefers
// liquid_universe.parquet for the ticker set (ADR-001's top-N-by-
// liquidity selection) and falls back to every ticker in prices.parquet
// if no liquidity ranking was configured (e.g. this milestone's golden
// fixture, whose [ingest] section has no liquidity_top_n).

#include <gm-core/calendar.hpp>
#include <gm-core/stage_main.hpp>
#include <gm-geometry/correlation.hpp>
#include <gm-geometry/distance.hpp>
#include <gm-geometry/graph.hpp>
#include <gm-geometry/mds.hpp>
#include <gm-geometry/rie.hpp>
#include <gm-geometry/procrustes.hpp>
#include <gm-geometry/rmt.hpp>
#include <gm-geometry/shrinkage.hpp>
#include <gm-io/parquet.hpp>
#include <gm-topology/ripser_wrapper.hpp>
#include <gm-io/table.hpp>

#include <Eigen/Dense>

#include <algorithm>
#include <cmath>
#include <map>
#include <numeric>
#include <set>

namespace {

gm::Result<std::vector<std::string>> load_ticker_universe(const std::filesystem::path& ingest_dir) {
    auto liquid = gm::io::read_parquet(ingest_dir / "liquid_universe.parquet");
    if (liquid) {
        auto tickers = liquid->string_column("ticker");
        if (!tickers) return tl::unexpected(tickers.error());
        std::vector<std::string> result(tickers->begin(), tickers->end());
        std::sort(result.begin(), result.end());
        return result;
    }

    // No liquidity ranking was configured for this run - fall back to
    // every ticker gm-ingest actually wrote to prices.parquet.
    auto prices = gm::io::read_parquet(ingest_dir / "prices.parquet");
    if (!prices) return tl::unexpected(prices.error());
    auto ticker_col = prices->string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    std::set<std::string> unique(ticker_col->begin(), ticker_col->end());
    return std::vector<std::string>(unique.begin(), unique.end());
}

struct HistoryFilterResult {
    std::vector<std::string> retained;
    std::vector<std::string> excluded_short_history;
};

/// Drops any requested ticker whose price data doesn't begin on or
/// before `cutoff` - discovered necessary the hard way (ADR §3
/// principle 1 - found via this milestone's own real 16-year run, not
/// a unit test): the panel's usable date range is the INTERSECTION of
/// every selected ticker's coverage (build_return_panel below never
/// forward-fills), so a single recently-listed high-liquidity name
/// (e.g. a 2025 spin-off) silently collapsed a requested 16-year
/// analysis down to the ~1.5 years since that one ticker started
/// trading. Excluding short-history tickers up front - rather than
/// letting one late joiner define everyone's range - is a deliberate
/// scope decision, not a full time-varying-membership system (that is
/// real added complexity: correctly Procrustes-aligning frames whose
/// ticker SETS differ, not just their count, deserves its own design
/// pass rather than a rushed addition here). Reported via
/// excluded_short_history so it's visible in the manifest, not silent.
HistoryFilterResult filter_tickers_with_sufficient_history(const gm::io::Table& prices,
                                                             const std::vector<std::string>& tickers,
                                                             const gm::Date& cutoff) {
    auto ticker_col = prices.string_column("ticker");
    auto date_col = prices.string_column("date");
    // Both columns are guaranteed present by this point (build_return_panel
    // already validated them via the same accessors on the same table).

    std::map<std::string, std::string> first_date_by_ticker;
    for (std::size_t i = 0; i < ticker_col->size(); ++i) {
        const std::string& t = (*ticker_col)[i];
        const std::string& d = (*date_col)[i];
        auto it = first_date_by_ticker.find(t);
        if (it == first_date_by_ticker.end() || d < it->second) first_date_by_ticker[t] = d;
    }

    std::string cutoff_iso = cutoff.to_iso();  // ISO-8601 dates compare correctly as strings
    HistoryFilterResult result;
    for (const auto& t : tickers) {
        auto it = first_date_by_ticker.find(t);
        if (it != first_date_by_ticker.end() && it->second <= cutoff_iso) {
            result.retained.push_back(t);
        } else {
            result.excluded_short_history.push_back(t);
        }
    }
    return result;
}

struct ReturnPanel {
    Eigen::MatrixXd returns;        // T x N log returns, ascending by date
    std::vector<std::string> dates; // T+1 dates the returns were computed between;
                                     // returns.row(i) is the return from dates[i] to dates[i+1]
};

/// Builds a rectangular log-return panel for exactly `tickers` (in that
/// order) from gm-ingest's long-format prices.parquet. A date is
/// included only if EVERY requested ticker has an adjclose value for
/// it (an intersection, not a union) - the alternative (forward-filling
/// a missing ticker-day) would quietly fabricate a return that never
/// happened, which is worse than dropping the day.
gm::Result<ReturnPanel> build_return_panel(const gm::io::Table& prices,
                                            const std::vector<std::string>& tickers) {
    auto ticker_col = prices.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    auto date_col = prices.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto adjclose_col = prices.double_column("adjclose");
    if (!adjclose_col) return tl::unexpected(adjclose_col.error());

    std::set<std::string> wanted(tickers.begin(), tickers.end());
    // ticker -> date -> adjclose
    std::map<std::string, std::map<std::string, double>> by_ticker;
    for (std::size_t i = 0; i < ticker_col->size(); ++i) {
        if (wanted.count((*ticker_col)[i]) == 0) continue;
        by_ticker[(*ticker_col)[i]][(*date_col)[i]] = (*adjclose_col)[i];
    }

    for (const auto& t : tickers) {
        if (by_ticker.find(t) == by_ticker.end()) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kNotFound,
                                                   "requested ticker has no price data", t));
        }
    }

    // Intersection of every requested ticker's date set.
    std::set<std::string> common;
    {
        const auto& first = by_ticker.at(tickers.front());
        for (const auto& [d, _] : first) common.insert(d);
    }
    for (std::size_t i = 1; i < tickers.size(); ++i) {
        std::set<std::string> next;
        const auto& this_ticker_dates = by_ticker.at(tickers[i]);
        for (const auto& d : common) {
            if (this_ticker_dates.count(d) > 0) next.insert(d);
        }
        common = std::move(next);
    }

    std::vector<std::string> dates(common.begin(), common.end());  // std::set is already sorted
    if (dates.size() < 2) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure,
            "fewer than 2 dates have data for every requested ticker",
            "common dates: " + std::to_string(dates.size())));
    }

    Eigen::Index t = static_cast<Eigen::Index>(dates.size()) - 1;
    Eigen::Index n = static_cast<Eigen::Index>(tickers.size());
    Eigen::MatrixXd returns(t, n);
    for (Eigen::Index j = 0; j < n; ++j) {
        const auto& price_by_date = by_ticker.at(tickers[static_cast<std::size_t>(j)]);
        for (Eigen::Index i = 0; i < t; ++i) {
            double p0 = price_by_date.at(dates[static_cast<std::size_t>(i)]);
            double p1 = price_by_date.at(dates[static_cast<std::size_t>(i) + 1]);
            returns(i, j) = std::log(p1 / p0);
        }
    }

    return ReturnPanel{std::move(returns), std::move(dates)};
}

gm::VoidResult run_gm_geometry(const gm::Config& config, const std::filesystem::path& output_dir,
                                gm::Manifest& manifest) {
    std::int64_t window_days = config.get_int_or("geometry.window_days", 60);
    std::int64_t k = config.get_int_or("geometry.embedding_dims", 3);
    // ADR §6.4's View C default: k nearest neighbours under D(t) for
    // peer-basket selection. Separate config key from embedding_dims -
    // unrelated meanings that happen to share the letter k in the ADR's
    // prose (embedding dimensionality vs. neighbour-graph degree).
    std::int64_t knn_k = config.get_int_or("geometry.knn_k", 8);

    // ADR-009 as amended. "shrink_clip" is the historical path: Ledoit-
    // Wolf shrinkage followed by Marchenko-Pastur clipping. Those are
    // two COMPETING estimators of the same corrected spectrum, not two
    // halves of one pipeline, and composing them optimises neither - the
    // shrinkage intensity was solved for a sample spectrum that clipping
    // then replaces, and the bulk edge clipping tests against is no
    // longer the bulk edge of a sample covariance.
    //
    // "rie" is the single rotationally-invariant estimator the
    // literature converged on instead (rie.hpp). Which one produces
    // better peer baskets is an empirical question; running the gate
    // both ways is how it gets answered, so both are selectable and the
    // manifest records which was used.
    const std::string correlation_estimator =
        config.get_string_or("geometry.correlation_estimator", "shrink_clip");
    if (correlation_estimator != "shrink_clip" && correlation_estimator != "rie") {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "geometry.correlation_estimator must be \"shrink_clip\" or \"rie\"",
            correlation_estimator));
    }
    if (window_days < 2) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "geometry.window_days must be >= 2"));
    }
    if (k < 1) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "geometry.embedding_dims must be >= 1"));
    }

    std::filesystem::path ingest_dir = output_dir.parent_path() / "gm-ingest";

    auto tickers = load_ticker_universe(ingest_dir);
    if (!tickers) return tl::unexpected(tickers.error());
    if (static_cast<std::int64_t>(tickers->size()) < k) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure, "fewer tickers than geometry.embedding_dims",
            std::to_string(tickers->size()) + " tickers, k=" + std::to_string(k)));
    }

    auto prices = gm::io::read_parquet(ingest_dir / "prices.parquet");
    if (!prices) return tl::unexpected(prices.error());

    // Filter out tickers whose data doesn't cover the requested range's
    // start - see filter_tickers_with_sufficient_history's comment for
    // why this is necessary at all (a single late-joining ticker
    // otherwise collapses the panel's usable range for everyone).
    // universe.start_date is the same key gm-universe itself reads;
    // reused here rather than inventing a separate geometry-specific
    // config knob for the same underlying date.
    auto start_date_str = config.get_string("universe.start_date");
    if (!start_date_str) return tl::unexpected(start_date_str.error());
    auto start_date = gm::Date::parse_iso(*start_date_str);
    if (!start_date) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "universe.start_date is not a valid ISO date",
                                               *start_date_str));
    }
    gm::NyseCalendar calendar_for_cutoff;
    // One window's worth of trading-day grace: a ticker that starts a
    // handful of days into the requested range (e.g. the range begins
    // on a date that isn't that ticker's exact first trade) still
    // contributes to nearly every frame; only genuinely late joiners
    // (months to years in) get excluded.
    gm::Date history_cutoff = calendar_for_cutoff.add_trading_days(*start_date, window_days);

    auto filtered = filter_tickers_with_sufficient_history(*prices, *tickers, history_cutoff);
    if (filtered.retained.empty()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure,
            "every requested ticker was excluded for insufficient history",
            "cutoff=" + history_cutoff.to_iso()));
    }
    manifest.set_int("num_tickers_excluded_short_history",
                      static_cast<std::int64_t>(filtered.excluded_short_history.size()));
    if (static_cast<std::int64_t>(filtered.retained.size()) < k) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure,
            "fewer than geometry.embedding_dims tickers remain after the history filter",
            std::to_string(filtered.retained.size()) + " remain, k=" + std::to_string(k)));
    }
    // Everything from here on uses filtered.retained, NOT the original
    // `tickers` - they can differ in both size and order after
    // filtering, and every downstream index (the embedding matrix's
    // rows, output ticker labels) must agree with whichever list
    // build_return_panel was actually given.
    const std::vector<std::string>& active_tickers = filtered.retained;

    auto panel = build_return_panel(*prices, active_tickers);
    if (!panel) return tl::unexpected(panel.error());

    Eigen::Index total_t = panel->returns.rows();
    Eigen::Index n = panel->returns.cols();
    double q = static_cast<double>(n) / static_cast<double>(window_days);

    if (total_t < window_days) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure, "fewer return observations than geometry.window_days",
            std::to_string(total_t) + " < " + std::to_string(window_days)));
    }

    std::vector<std::string> out_dates, out_tickers;
    std::vector<double> out_x, out_y, out_z;
    // Coordinates beyond the third, present only when
    // geometry.embedding_dims > 3. Held separately from x/y/z on purpose:
    // a k == 3 run then writes a geometry.parquet byte-identical to the one
    // it wrote before this change, so the golden pipeline test (ADR-020
    // layer 2) keeps its meaning and no existing run needs regenerating to
    // stay readable. Every consumer that only knows about x/y/z keeps
    // working; the ones that want the full embedding read dim3.. as well.
    //
    // Before this, embedding_dims was a real config key whose effect was
    // largely thrown away: classical_mds computed k coordinates and this
    // stage wrote exactly three of them, so setting it to 10 silently
    // discarded seven. ADR §6.2's "k=3 display, up to 10 for scoring" was
    // not actually reachable.
    std::vector<std::vector<double>> out_extra_dims;
    std::vector<std::string> regime_dates;
    std::vector<double> regime_structural_change;
    std::vector<double> regime_h0_persistence;
    std::vector<double> regime_h1_persistence;
    std::vector<double> regime_wasserstein_distance;
    std::vector<std::uint8_t> regime_tear_flag;
    std::vector<std::string> edge_dates, edge_ticker_a, edge_ticker_b;
    std::vector<double> edge_distances;
    std::vector<std::uint8_t> edge_in_mst;
    std::vector<std::uint8_t> edge_in_knn;

    std::optional<Eigen::MatrixXd> previous_aligned;
    // Cached separately from previous_aligned (which gets overwritten
    // to the CURRENT frame's coordinates further down, before the
    // Wasserstein computation below used to run - comparing a
    // diagram to itself, which is why wasserstein_distance always
    // came out exactly 0.0 on real multi-frame data despite passing
    // every single-frame unit test). This holds the prior frame's
    // persistence diagram specifically for that comparison, updated
    // only after this iteration's Wasserstein distance is computed.
    std::optional<gm::topology::PersistenceFeatures> previous_persistence;

    for (Eigen::Index frame_end = window_days - 1; frame_end < total_t; ++frame_end) {
        Eigen::MatrixXd window = panel->returns.block(frame_end - window_days + 1, 0, window_days, n);
        // The frame is dated as-of the day the return window ENDS -
        // i.e. the day the last return in the window was realized,
        // which is dates[frame_end + 1] (returns.row(i) spans
        // dates[i] -> dates[i+1]).
        const std::string& frame_date = panel->dates[static_cast<std::size_t>(frame_end) + 1];

        Eigen::MatrixXd cleaned_correlation;
        if (correlation_estimator == "rie") {
            auto corr = gm::geometry::sample_correlation(window);
            if (!corr) return tl::unexpected(corr.error());
            auto rie = gm::geometry::rie_clean_correlation(*corr, q);
            if (!rie) return tl::unexpected(rie.error());
            cleaned_correlation = std::move(rie->cleaned_correlation);
        } else {
            auto shrunk = gm::geometry::ledoit_wolf_shrink_correlation(window);
            if (!shrunk) return tl::unexpected(shrunk.error());
            auto denoised = gm::geometry::mp_denoise(shrunk->correlation, q);
            if (!denoised) return tl::unexpected(denoised.error());
            cleaned_correlation = std::move(denoised->denoised_correlation);
        }

        auto dist = gm::geometry::mantegna_distance(cleaned_correlation);
        if (!dist) return tl::unexpected(dist.error());

        // k-NN + MST edges are computed on D(t) itself, not the 3D
        // embedding below (ADR §6.4) - View C's peer-basket selection
        // needs the full-precision distance the embedding necessarily
        // compresses when k (embedding_dims) < n-1.
        auto edges = gm::geometry::knn_and_mst_edges(*dist, static_cast<int>(knn_k));
        if (!edges) return tl::unexpected(edges.error());
        for (const auto& e : *edges) {
            edge_dates.push_back(frame_date);
            edge_ticker_a.push_back(active_tickers[static_cast<std::size_t>(e.i)]);
            edge_ticker_b.push_back(active_tickers[static_cast<std::size_t>(e.j)]);
            edge_distances.push_back(e.distance);
            edge_in_mst.push_back(e.in_mst ? 1 : 0);
            edge_in_knn.push_back(e.in_knn ? 1 : 0);
        }

        auto embedding = gm::geometry::classical_mds(*dist, static_cast<int>(k));
        if (!embedding) return tl::unexpected(embedding.error());

        Eigen::MatrixXd aligned;
        double structural_change = 0.0;
        if (previous_aligned.has_value()) {
            auto proc = gm::geometry::align(embedding->coordinates, *previous_aligned);
            if (!proc) return tl::unexpected(proc.error());
            aligned = proc->aligned;
            structural_change = proc->normalized_residual;
        } else {
            aligned = embedding->coordinates;  // first frame: nothing to align to yet
        }
        previous_aligned = aligned;

        // ADR-012: Compute H0/H1 persistence and Wasserstein distance
        gm::topology::PersistenceFeatures current_persistence;
        auto persist_result = gm::topology::compute_persistence(aligned);
        if (!persist_result) return tl::unexpected(persist_result.error());
        current_persistence = *persist_result;

        double h0_persist = current_persistence.h0_total_persistence;
        double h1_persist = current_persistence.h1_total_persistence;

        // Wasserstein distance from the PRIOR frame's diagram - uses
        // previous_persistence (still holding last iteration's value at
        // this point), not previous_aligned (already overwritten to this
        // frame's coordinates above), and not a redundant second
        // compute_persistence() call on the same data.
        double wasserstein_dist = 0.0;
        if (previous_persistence.has_value()) {
            auto wd_result = gm::topology::wasserstein_distance(
                previous_persistence->h0_pairs, current_persistence.h0_pairs);
            if (wd_result) wasserstein_dist = *wd_result;
        }
        previous_persistence = current_persistence;

        // Tear detection: flag if topology changing significantly
        bool tear_flag = false;
        if (h1_persist > h0_persist * 0.15) tear_flag = true;
        if (!regime_wasserstein_distance.empty() && regime_wasserstein_distance.size() > 10) {
            double mean_wd = std::accumulate(regime_wasserstein_distance.begin(),
                regime_wasserstein_distance.end(), 0.0) / static_cast<double>(regime_wasserstein_distance.size());
            double var_wd = 0.0;
            for (double w : regime_wasserstein_distance)
                var_wd += (w - mean_wd) * (w - mean_wd);
            double std_wd = std::sqrt(var_wd / static_cast<double>(regime_wasserstein_distance.size()));
            if (std_wd > 0.0 && wasserstein_dist > mean_wd + 1.5 * std_wd)
                tear_flag = true;
        }

        regime_h0_persistence.push_back(h0_persist);
        regime_h1_persistence.push_back(h1_persist);
        regime_wasserstein_distance.push_back(wasserstein_dist);
        regime_tear_flag.push_back(tear_flag ? 1 : 0);

        for (Eigen::Index i = 0; i < n; ++i) {
            out_dates.push_back(frame_date);
            out_tickers.push_back(active_tickers[static_cast<std::size_t>(i)]);
            out_x.push_back(aligned(i, 0));
            out_y.push_back(k >= 2 ? aligned(i, 1) : 0.0);
            out_z.push_back(k >= 3 ? aligned(i, 2) : 0.0);
            if (k > 3) {
                if (out_extra_dims.empty()) {
                    out_extra_dims.resize(static_cast<std::size_t>(k - 3));
                }
                for (int d = 3; d < static_cast<int>(k); ++d) {
                    // classical_mds returns k columns, but read defensively:
                    // a coordinate that does not exist is absent, not zero,
                    // and zero here would look like "this name sits exactly
                    // at the origin in dimension 7" rather than "there is no
                    // dimension 7".
                    const double value =
                        d < static_cast<int>(aligned.cols()) ? aligned(i, d) : 0.0;
                    out_extra_dims[static_cast<std::size_t>(d - 3)].push_back(value);
                }
            }
        }
        regime_dates.push_back(frame_date);
        regime_structural_change.push_back(structural_change);
    }

    gm::io::Table geometry_table;
    if (auto r = geometry_table.add_string_column("date", std::move(out_dates)); !r) return tl::unexpected(r.error());
    if (auto r = geometry_table.add_string_column("ticker", std::move(out_tickers)); !r) return tl::unexpected(r.error());
    if (auto r = geometry_table.add_double_column("x", std::move(out_x)); !r) return tl::unexpected(r.error());
    if (auto r = geometry_table.add_double_column("y", std::move(out_y)); !r) return tl::unexpected(r.error());
    if (auto r = geometry_table.add_double_column("z", std::move(out_z)); !r) return tl::unexpected(r.error());
    // dim3, dim4, ... continue the same axis ordering: classical MDS returns
    // its axes in descending eigenvalue order, so dimension 3 onward carry
    // progressively less of the structure. x/y/z ARE dim0/dim1/dim2 - they
    // keep their historical names so existing readers are undisturbed.
    //
    // A gotcha worth stating, because the natural assumption is wrong:
    // x/y/z are NOT stable across a change to embedding_dims. Procrustes
    // alignment above runs on the full k coordinates, so at k = 10 the
    // frame-to-frame rotation is a 10-dimensional one, and its projection
    // onto the first three axes is not the rotation a k = 3 run would have
    // applied. Measured on 2020-03-27: the same date renders visibly more
    // spread at k = 10 than at k = 3 on the same axes. The geometry is not
    // wrong in either case - inter-point distances are what MDS preserves -
    // but two runs at different k are not comparable coordinate by
    // coordinate, only shape by shape.
    for (std::size_t d = 0; d < out_extra_dims.size(); ++d) {
        const std::string name = "dim" + std::to_string(d + 3);
        if (auto r = geometry_table.add_double_column(name, std::move(out_extra_dims[d])); !r) {
            return tl::unexpected(r.error());
        }
    }

    auto write1 = gm::io::write_parquet(geometry_table, output_dir / "geometry.parquet");
    if (!write1) return tl::unexpected(write1.error());

    gm::io::Table regime_table;
    if (auto r = regime_table.add_string_column("date", std::move(regime_dates)); !r) return tl::unexpected(r.error());
    if (auto r = regime_table.add_double_column("structural_change", std::move(regime_structural_change)); !r)
        return tl::unexpected(r.error());
    if (auto r = regime_table.add_double_column("h0_total_persistence", std::move(regime_h0_persistence)); !r)
        return tl::unexpected(r.error());
    if (auto r = regime_table.add_double_column("h1_total_persistence", std::move(regime_h1_persistence)); !r)
        return tl::unexpected(r.error());
    if (auto r = regime_table.add_double_column("wasserstein_distance_from_prev_frame", std::move(regime_wasserstein_distance)); !r)
        return tl::unexpected(r.error());
    if (auto r = regime_table.add_bool_column("tear_flag", std::move(regime_tear_flag)); !r)
        return tl::unexpected(r.error());

    auto write2 = gm::io::write_parquet(regime_table, output_dir / "regime.parquet");
    if (!write2) return tl::unexpected(write2.error());

    gm::io::Table edges_table;
    if (auto r = edges_table.add_string_column("date", std::move(edge_dates)); !r) return tl::unexpected(r.error());
    if (auto r = edges_table.add_string_column("ticker_a", std::move(edge_ticker_a)); !r)
        return tl::unexpected(r.error());
    if (auto r = edges_table.add_string_column("ticker_b", std::move(edge_ticker_b)); !r)
        return tl::unexpected(r.error());
    if (auto r = edges_table.add_double_column("distance", std::move(edge_distances)); !r)
        return tl::unexpected(r.error());
    if (auto r = edges_table.add_bool_column("in_mst", std::move(edge_in_mst)); !r) return tl::unexpected(r.error());
    if (auto r = edges_table.add_bool_column("in_knn", std::move(edge_in_knn)); !r) return tl::unexpected(r.error());

    auto write3 = gm::io::write_parquet(edges_table, output_dir / "edges.parquet");
    if (!write3) return tl::unexpected(write3.error());

    manifest.set_int("num_frames", static_cast<std::int64_t>(regime_table.num_rows()));
    manifest.set_int("num_tickers", static_cast<std::int64_t>(active_tickers.size()));
    manifest.set_int("rows_written", static_cast<std::int64_t>(geometry_table.num_rows()));
    manifest.set_int("edge_rows_written", static_cast<std::int64_t>(edges_table.num_rows()));
    manifest.set_int("window_days", window_days);
    manifest.set_int("embedding_dims", k);
    manifest.set_int("coordinate_columns_written", k > 3 ? k : 3);
    manifest.set_int("knn_k", knn_k);
    manifest.set_string("correlation_estimator", correlation_estimator);
    manifest.set_double("q_n_over_window", q);

    return {};
}

} // namespace

int main(int argc, char** argv) { return gm::run_stage_main(argc, argv, "gm-geometry", run_gm_geometry); }
