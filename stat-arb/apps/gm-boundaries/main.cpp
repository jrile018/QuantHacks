// gm-boundaries: fits and scores the two boundary views ADR-006/ADR-011
// call for in phase 1 - View A (market, per-frame) and View B (self,
// per-ticker causal history) - against gm-geometry's embeddings, using
// both estimators from gm-boundaries-lib (Mahalanobis + KDE) per view.
//
// Mesh export (surfaces/*.gmmesh, ADR §8.2) is opt-in via
// boundaries.write_meshes, defaulting OFF, because writing a mesh for
// every one of several thousand frames is real cost that most runs do
// not need - the scores themselves, which are the analytical deliverable
// ADR-011 cares about, do not depend on meshes existing at all.
//
// This note previously described that flag as though it worked. It did
// not: no code read boundaries.write_meshes, no writer existed, and the
// manifest line reporting the setting was a hardcoded string saying
// "disabled". The consequence was that the boundary SURFACE - the lumpy
// non-convex envelope ADR-011 specifies and the entire visual point of
// gm-view - could not be produced at all, by any configuration. The flag
// is now real. Three knobs:
//
//   boundaries.write_meshes         bool, default false
//   boundaries.mesh_resolution      int,  default 32 (grid cells per axis)
//   boundaries.mesh_frame_stride    int,  default 1 (export every Nth frame)
//   boundaries.view_b_mesh_tickers  array of ticker strings, default empty
//   boundaries.view_b_mesh_stride   int,  default 1 (every Nth dated point)
//
// The stride exists because resolution and frame count multiply: a full
// 4129-frame run at resolution 32 is thousands of files, and looking at
// one year in the viewer does not require meshing all sixteen.
//
// The two views produce two different SHAPES, which is why both are
// exported and why they are named apart on disk:
//
//   {date}_A.gmmesh            the market's envelope on that date -
//                              fitted to every ticker present, so it is a
//                              blob enclosing the cross-section.
//   {date}_B_{ticker}.gmmesh   ONE ticker's envelope around its own
//                              trailing history - fitted to a path
//                              through space, so it is a tube.
//
// View B meshes are opt-in per ticker rather than for all of them,
// because they multiply by ticker as well as by date: 81 names x 4129
// dates is roughly a third of a million files, which is not a default
// anyone wants. Naming the handful being looked at costs nothing and
// makes the size of the output predictable from the config alone.
//
// One property of the View B tube is easy to misread and worth stating
// where it is produced: its training window is strictly PRIOR history,
// excluding the very date it is named for (ADR-011's causality rule). So
// the current point legitimately can, and when something interesting is
// happening does, sit OUTSIDE its own tube. That is the finding, not a
// rendering fault.

#include <gm-boundaries/kde.hpp>
#include <gm-boundaries/mahalanobis.hpp>
#include <gm-boundaries/fastmcd.hpp>
#include <gm-boundaries/marching_tetrahedra.hpp>
#include <gm-core/stage_main.hpp>
#include <gm-io/mesh.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>

#include <Eigen/Dense>

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <vector>

namespace {

/// One ticker's position on one date, in however many dimensions
/// gm-geometry actually wrote. Previously three named doubles, which made
/// the entire stage silently three-dimensional: geometry.embedding_dims
/// could say 10 and every fit here would still be over x/y/z alone.
struct FramePoint {
    std::string date;
    std::vector<double> coords;

    [[nodiscard]] std::size_t dims() const noexcept { return coords.size(); }
};

/// ticker -> its embedding history, sorted ascending by date (from
/// geometry.parquet, which is itself frame-ordered but this re-sorts
/// per-ticker defensively rather than assuming the upstream ordering).
using HistoryByTicker = std::map<std::string, std::vector<FramePoint>>;

/// date -> the tickers present in that frame with their coordinates.
using PointsByDate = std::map<std::string, std::vector<std::pair<std::string, FramePoint>>>;

gm::Result<std::pair<HistoryByTicker, PointsByDate>> load_geometry(const gm::io::Table& geometry) {
    auto date_col = geometry.string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_col = geometry.string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());
    // x/y/z ARE dimensions 0/1/2 - they keep those names for the readers
    // that predate higher-dimensional embeddings. Anything past the third
    // arrives as dim3, dim4, ... and is discovered by probing rather than
    // declared, so this stage reads whatever gm-geometry wrote without
    // needing its config repeated here (and without silently ignoring
    // columns, which is the failure this replaces).
    std::vector<std::vector<double>> columns;
    for (const char* name : {"x", "y", "z"}) {
        auto col = geometry.double_column(name);
        if (!col) return tl::unexpected(col.error());
        columns.push_back(std::move(*col));
    }
    for (int d = 3;; ++d) {
        auto col = geometry.double_column("dim" + std::to_string(d));
        if (!col) break; // no more dimensions in this artifact
        columns.push_back(std::move(*col));
    }
    const std::size_t dims = columns.size();
    for (const auto& column : columns) {
        if (column.size() != date_col->size()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kValidationFailure,
                "geometry coordinate columns have inconsistent lengths",
                std::to_string(column.size()) + " vs " + std::to_string(date_col->size())));
        }
    }

    HistoryByTicker by_ticker;
    PointsByDate by_date;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        FramePoint fp;
        fp.date = (*date_col)[i];
        fp.coords.reserve(dims);
        for (std::size_t d = 0; d < dims; ++d) fp.coords.push_back(columns[d][i]);
        by_ticker[(*ticker_col)[i]].push_back(fp);
        by_date[(*date_col)[i]].push_back({(*ticker_col)[i], fp});
    }
    for (auto& [ticker, history] : by_ticker) {
        std::sort(history.begin(), history.end(),
                  [](const FramePoint& a, const FramePoint& b) { return a.date < b.date; });
    }
    return std::make_pair(std::move(by_ticker), std::move(by_date));
}

Eigen::MatrixXd points_to_matrix(const std::vector<FramePoint>& points) {
    if (points.empty()) return Eigen::MatrixXd(0, 0);
    const auto dims = static_cast<Eigen::Index>(points.front().dims());
    Eigen::MatrixXd m(static_cast<Eigen::Index>(points.size()), dims);
    for (std::size_t i = 0; i < points.size(); ++i) {
        for (Eigen::Index d = 0; d < dims; ++d) {
            m(static_cast<Eigen::Index>(i), d) =
                points[i].coords[static_cast<std::size_t>(d)];
        }
    }
    return m;
}

Eigen::VectorXd point_to_vector(const FramePoint& point) {
    Eigen::VectorXd v(static_cast<Eigen::Index>(point.dims()));
    for (std::size_t d = 0; d < point.dims(); ++d) {
        v(static_cast<Eigen::Index>(d)) = point.coords[d];
    }
    return v;
}

/// Appends one (date, ticker, view, estimator, depth, pvalue, inside)
/// row per estimator that successfully scored - Mahalanobis and KDE are
/// independent fits (ADR-007: "disagreement between the two is a
/// first-class output"), so a failure in one (e.g. KDE needs only 2
/// points, Mahalanobis needs k+1=4) does not block the other from
/// being reported.
struct ScoreRows {
    std::vector<std::string> dates, tickers, views, estimators;
    std::vector<double> depths, pvalues;
    std::vector<std::uint8_t> insides;

    // A skipped estimator (degenerate MAD, too few points for k+1,
    // near-singular covariance) is expected occasionally and by design
    // does not halt the stage (ADR-007: the two estimators are
    // independent). But "occasionally" and "systematically" look
    // identical from scores.parquet alone - a bug that made every
    // single Mahalanobis fit fail would silently just produce a
    // KDE-only scores.parquet with no error anywhere. These counters
    // make that distinction visible in the manifest instead of
    // requiring an outside cross-check against the expected row count
    // (view_a_frames_scored/view_b_points_scored * 2 estimators).
    std::size_t mahalanobis_failures = 0;
    std::size_t kde_failures = 0;
    std::size_t fastmcd_failures = 0;

    // Where each estimator first failed, and why. A count alone says a
    // problem exists; this says where to look. Kept as the FIRST rather
    // than the last so it is stable across runs that differ only in how
    // far they got.
    std::string first_mahalanobis_failure;
    std::string first_kde_failure;
    std::string first_fastmcd_failure;

    static std::string where(const std::string& date, const std::string& ticker, const char* view,
                             const std::string& reason) {
        return date + " " + view + "/" + ticker + ": " + reason;
    }

    void add(const std::string& date, const std::string& ticker, const char* view,
             const char* estimator, double depth, double pvalue, bool inside) {
        dates.push_back(date);
        tickers.push_back(ticker);
        views.push_back(view);
        estimators.push_back(estimator);
        depths.push_back(depth);
        pvalues.push_back(pvalue);
        insides.push_back(inside ? 1 : 0);
    }
};

/// Extracts a boundary surface from `training` and writes it as a
/// .gmmesh at `out_path`, so gm-view has an envelope to draw around the
/// point cloud rather than only the points.
///
/// The isosurface is the KDE level set: the same `level` the scores are
/// computed against, so the drawn surface is literally the boundary the
/// "inside/outside" column refers to, not a separate cosmetic shape that
/// could drift away from it.
///
/// View-agnostic on purpose. A View A frame and a View B trailing window
/// are both just "a set of points to enclose", and giving each its own
/// copy of this would let the two surfaces drift apart in exactly the way
/// the paragraph above promises they will not.
gm::VoidResult export_boundary_mesh(const Eigen::MatrixXd& training,
                                     const std::filesystem::path& out_path, double alpha,
                                     int resolution) {
    // A drawable surface is three-dimensional by definition, so when the
    // embedding has more dimensions than that this fits the FIRST THREE
    // only. Those are the dominant MDS axes (classical MDS returns axes in
    // descending eigenvalue order), so it is the most faithful three-
    // dimensional shadow available - but it is a shadow.
    //
    // Consequence worth stating rather than hiding: with k > 3 the drawn
    // surface is NOT the boundary the scores refer to. A point can sit
    // inside this shape on screen and still score outside, because its
    // unusualness lives in a dimension the picture does not have. That
    // disagreement is information, not a bug - it says "this name looks
    // ordinary from here, and is not" - and the manifest records the two
    // dimensionalities so a reader can tell when it is possible.
    const Eigen::MatrixXd display_training =
        training.cols() > 3 ? Eigen::MatrixXd(training.leftCols(3)) : training;

    auto fit = gm::boundaries::fit_kde(display_training, alpha);
    if (!fit) return tl::unexpected(fit.error());

    // Sample box: the cloud's own extent, padded by three bandwidths per
    // axis. Beyond three bandwidths a Gaussian kernel contributes
    // essentially nothing, so the level set is guaranteed to close inside
    // the box instead of being clipped flat against its walls - which
    // would produce a surface with a hole in it and look like a
    // rendering bug rather than a sampling one.
    std::array<double, 3> lo{};
    std::array<double, 3> hi{};
    for (int k = 0; k < 3; ++k) {
        const double pad = 3.0 * fit->bandwidth(k);
        lo[static_cast<std::size_t>(k)] = display_training.col(k).minCoeff() - pad;
        hi[static_cast<std::size_t>(k)] = display_training.col(k).maxCoeff() + pad;
    }

    const gm::boundaries::KdeFit& kde = *fit;
    auto field = [&kde](double x, double y, double z) {
        Eigen::Vector3d point(x, y, z);
        auto density = gm::boundaries::kde_density(kde, point);
        // A density evaluation cannot meaningfully fail for a finite
        // point against a fitted model. Treating an unexpected failure as
        // zero density (definitively outside) keeps the isosurface
        // well-defined rather than leaving an unexplained hole in it.
        return density ? *density : 0.0;
    };

    auto mesh = gm::boundaries::marching_tetrahedra(field, lo, hi, resolution, fit->level);
    if (!mesh) return tl::unexpected(mesh.error());

    gm::io::MeshData out;
    out.vertices = mesh->vertices;
    out.triangles = mesh->triangles;
    return gm::io::write_gmmesh(out, out_path);
}

/// Counters for one view's mesh export, so a run that quietly produced
/// nothing is distinguishable from one that had nothing to produce.
struct MeshCounters {
    std::int64_t written = 0;
    std::int64_t failures = 0;
    std::string first_error;

    void record(const gm::VoidResult& result, const std::string& what) {
        if (result) {
            ++written;
        } else {
            ++failures;
            if (first_error.empty()) first_error = what + ": " + result.error().message;
        }
    }
};

/// The tickers named in boundaries.view_b_mesh_tickers.
///
/// Returns an error rather than an empty set when the key holds anything
/// that is not an array of strings. A misspelled or mistyped entry here
/// would otherwise export zero surfaces and report success, which is the
/// precise shape of bug the counters in this stage exist to prevent -
/// and it would be discovered only by someone opening the viewer and
/// finding no tube.
gm::Result<std::set<std::string>> read_view_b_mesh_tickers(const gm::Config& config) {
    std::set<std::string> wanted;
    const auto* boundaries = config.raw()["boundaries"].as_table();
    if (boundaries == nullptr) return wanted;
    const auto* node = boundaries->get("view_b_mesh_tickers");
    if (node == nullptr) return wanted;
    const auto* array = node->as_array();
    if (array == nullptr) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "boundaries.view_b_mesh_tickers must be an array of ticker strings",
            "e.g. view_b_mesh_tickers = [\"AAPL\", \"MSFT\"]"));
    }
    for (const auto& element : *array) {
        const auto* value = element.as_string();
        if (value == nullptr) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument,
                "boundaries.view_b_mesh_tickers contains a non-string entry",
                "every element must be a ticker symbol in quotes"));
        }
        const std::string ticker = value->get();
        // A ticker is going into a filename. No real symbol contains a
        // path separator, but a config typo that did would write outside
        // surfaces/ - refuse rather than resolve it.
        if (ticker.empty() || ticker.find('/') != std::string::npos ||
            ticker.find('\\') != std::string::npos || ticker == "." || ticker == "..") {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "boundaries.view_b_mesh_tickers entry is not a "
                                                   "usable ticker symbol",
                                                   ticker));
        }
        wanted.insert(ticker);
    }
    return wanted;
}

void score_both_estimators(ScoreRows& rows, const Eigen::MatrixXd& training, const Eigen::VectorXd& query,
                            const std::string& date, const std::string& ticker, const char* view,
                            double alpha) {
    auto maha_fit = gm::boundaries::fit_mahalanobis(training);
    if (maha_fit) {
        auto score = gm::boundaries::score_mahalanobis(*maha_fit, query, alpha);
        if (score) {
            rows.add(date, ticker, view, "mahalanobis", score->depth, score->p_value, score->inside);
        } else {
            ++rows.mahalanobis_failures;
            if (rows.first_mahalanobis_failure.empty()) {
                rows.first_mahalanobis_failure =
                    ScoreRows::where(date, ticker, view, score.error().message);
            }
        }
    } else {
        ++rows.mahalanobis_failures;
        if (rows.first_mahalanobis_failure.empty()) {
            rows.first_mahalanobis_failure =
                ScoreRows::where(date, ticker, view, maha_fit.error().message);
        }
    }

    auto kde_fit = gm::boundaries::fit_kde(training, alpha);
    if (kde_fit) {
        auto score = gm::boundaries::score_kde(*kde_fit, query);
        // KDE has no p-value in the parametric sense; store NaN rather
        // than a fabricated number, so a consumer can tell the two
        // estimators apart rather than mistaking a placeholder for a
        // real probability.
        if (score) {
            rows.add(date, ticker, view, "kde", score->depth, std::numeric_limits<double>::quiet_NaN(),
                      score->inside);
        } else {
            ++rows.kde_failures;
            if (rows.first_kde_failure.empty()) {
                rows.first_kde_failure = ScoreRows::where(date, ticker, view, score.error().message);
            }
        }
    } else {
        ++rows.kde_failures;
        if (rows.first_kde_failure.empty()) {
            rows.first_kde_failure = ScoreRows::where(date, ticker, view, kde_fit.error().message);
        }
    }

    auto mcd_fit = gm::boundaries::fit_fastmcd(training);
    if (mcd_fit) {
        auto score = gm::boundaries::score_fastmcd(*mcd_fit, query, alpha);
        if (score) {
            rows.add(date, ticker, view, "fastmcd", score->depth, score->p_value, score->inside);
        } else {
            ++rows.fastmcd_failures;
            if (rows.first_fastmcd_failure.empty()) {
                rows.first_fastmcd_failure =
                    ScoreRows::where(date, ticker, view, score.error().message);
            }
        }
    } else {
        ++rows.fastmcd_failures;
        if (rows.first_fastmcd_failure.empty()) {
            rows.first_fastmcd_failure =
                ScoreRows::where(date, ticker, view, mcd_fit.error().message);
        }
    }
}

/// Which valuation coordinates View D is fitted in.
///
/// Configurable, and defaulting to the two that are nearly always
/// derivable, because the third is not. Measured on a real run: of the
/// ticker-days that have a market capitalisation at all, E/P is present for
/// 100%, FCF/P for 94%, and EBITDA/EV for 57% - the last because enterprise
/// value needs a debt and cash position that a good many issuers either
/// report under tags outside the chain or, for banks, structure entirely
/// differently.
///
/// A boundary has to be fitted in ONE space, so every point in the cloud
/// must carry every configured axis. Adding EBITDA/EV therefore does not
/// enrich the fit - it shrinks the cross-section it is fitted to, by a lot.
/// That is a trade worth making deliberately and not by default, so the
/// count of ticker-days it costs is published either way.
gm::Result<std::vector<std::string>> read_view_d_axes(const gm::Config& config) {
    static const std::vector<std::string> kKnown = {"earnings_yield", "ebitda_ev_yield",
                                                     "fcf_yield"};
    std::vector<std::string> axes;
    const auto* boundaries = config.raw()["boundaries"].as_table();
    const toml::node* node = boundaries != nullptr ? boundaries->get("view_d_axes") : nullptr;
    if (node == nullptr) return std::vector<std::string>{"earnings_yield", "fcf_yield"};

    const auto* array = node->as_array();
    if (array == nullptr) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "boundaries.view_d_axes must be an array of coordinate names",
            R"(e.g. view_d_axes = ["earnings_yield", "fcf_yield"])"));
    }
    for (const auto& element : *array) {
        const auto* value = element.as_string();
        if (value == nullptr) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "boundaries.view_d_axes has a non-string entry"));
        }
        const std::string axis = value->get();
        if (std::find(kKnown.begin(), kKnown.end(), axis) == kKnown.end()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument, "unknown View D axis", axis));
        }
        if (std::find(axes.begin(), axes.end(), axis) != axes.end()) {
            // A repeated axis makes the covariance exactly singular, which
            // fails deep inside an estimator with a message about
            // conditioning rather than about the config that caused it.
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "boundaries.view_d_axes repeats an axis", axis));
        }
        axes.push_back(axis);
    }
    if (axes.empty()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "boundaries.view_d_axes is empty"));
    }
    return axes;
}

/// Fits and scores View D against gm-features' valuation.parquet.
///
/// A run without that artifact simply has no View D - valuation is opt-in
/// upstream - and that is recorded, not treated as a failure.
gm::VoidResult score_view_d(const gm::Config& config, const std::filesystem::path& output_dir,
                             ScoreRows& rows, gm::Manifest& manifest, double alpha,
                             std::int64_t lookback) {
    const auto valuation_path =
        output_dir.parent_path() / "gm-features" / "valuation.parquet";
    if (!std::filesystem::exists(valuation_path)) {
        manifest.set_string("view_d", "skipped (no valuation.parquet upstream)");
        return {};
    }

    auto axes = read_view_d_axes(config);
    if (!axes) return tl::unexpected(axes.error()); // already validated up front

    auto table = gm::io::read_parquet(valuation_path);
    if (!table) return tl::unexpected(table.error());
    auto date_col = table->string_column("date");
    if (!date_col) return tl::unexpected(date_col.error());
    auto ticker_col = table->string_column("ticker");
    if (!ticker_col) return tl::unexpected(ticker_col.error());

    std::vector<std::vector<double>> axis_cols;
    for (const std::string& axis : *axes) {
        auto col = table->double_column(axis);
        if (!col) return tl::unexpected(col.error());
        axis_cols.push_back(std::move(*col));
    }

    // ticker -> its valuation history, ascending by date.
    std::map<std::string, std::vector<FramePoint>> by_ticker;
    std::int64_t dropped_incomplete = 0;
    for (std::size_t i = 0; i < date_col->size(); ++i) {
        FramePoint fp;
        fp.date = (*date_col)[i];
        fp.coords.reserve(axis_cols.size());
        bool complete = true;
        for (const auto& col : axis_cols) {
            const double v = col[i];
            // An absent coordinate arrives as NaN from the Parquet column.
            // The whole ticker-day is dropped rather than imputed: a fitted
            // cloud with an invented point in it is worse than a smaller one,
            // and the count says how much smaller.
            if (!std::isfinite(v)) {
                complete = false;
                break;
            }
            fp.coords.push_back(v);
        }
        if (!complete) {
            ++dropped_incomplete;
            continue;
        }
        by_ticker[(*ticker_col)[i]].push_back(std::move(fp));
    }
    for (auto& [ticker, history] : by_ticker) {
        std::sort(history.begin(), history.end(),
                  [](const FramePoint& a, const FramePoint& b) { return a.date < b.date; });
    }

    // Same causal rule as View B: the trailing window of this name's own
    // prior valuation history, never including today's own point.
    std::int64_t points_scored = 0;
    std::int64_t tickers_too_short = 0;
    // |correlation| between the first two axes, per window. Collected
    // because the axes are not as independent as having two of them
    // suggests: E/P and FCF/P share a denominator, so between filings they
    // are exactly proportional. How close to collinear that leaves a real
    // window is a measurement, and it decides how much a second axis is
    // actually buying.
    std::vector<double> axis_correlations;
    for (const auto& [ticker, history] : by_ticker) {
        if (static_cast<std::int64_t>(history.size()) <= lookback) {
            ++tickers_too_short;
            continue;
        }
        for (std::size_t i = static_cast<std::size_t>(lookback); i < history.size(); ++i) {
            std::vector<FramePoint> window(
                history.begin() + static_cast<std::ptrdiff_t>(i - static_cast<std::size_t>(lookback)),
                history.begin() + static_cast<std::ptrdiff_t>(i));
            Eigen::MatrixXd training = points_to_matrix(window);
            Eigen::VectorXd query = point_to_vector(history[i]);

            if (training.cols() >= 2 && training.rows() > 2) {
                const Eigen::VectorXd a = training.col(0);
                const Eigen::VectorXd b = training.col(1);
                const Eigen::VectorXd ca = a.array() - a.mean();
                const Eigen::VectorXd cb = b.array() - b.mean();
                const double denom = ca.norm() * cb.norm();
                if (denom > 0.0) axis_correlations.push_back(std::abs(ca.dot(cb) / denom));
            }

            const std::size_t before = rows.dates.size();
            score_both_estimators(rows, training, query, history[i].date, ticker, "D", alpha);
            if (rows.dates.size() > before) ++points_scored;
        }
    }

    manifest.set_string("view_d", "enabled");
    std::string axis_list;
    for (const std::string& axis : *axes) {
        if (!axis_list.empty()) axis_list += ",";
        axis_list += axis;
    }
    manifest.set_string("view_d_axes", axis_list);
    manifest.set_int("view_d_dims", static_cast<std::int64_t>(axes->size()));
    manifest.set_int("view_d_points_scored", points_scored);
    manifest.set_int("view_d_tickers", static_cast<std::int64_t>(by_ticker.size()));
    // How much the axis choice costs. Reported rather than left implicit,
    // because adding an axis shrinks this cross-section and the shrinkage is
    // the whole trade-off.
    manifest.set_int("view_d_ticker_days_dropped_incomplete", dropped_incomplete);
    manifest.set_int("view_d_tickers_history_too_short", tickers_too_short);

    if (!axis_correlations.empty()) {
        std::sort(axis_correlations.begin(), axis_correlations.end());
        const auto at = [&](double q) {
            const auto idx = static_cast<std::size_t>(q * static_cast<double>(
                                                           axis_correlations.size() - 1));
            return axis_correlations[idx];
        };
        // A median close to 1.0 means the two axes are, most of the time,
        // one axis - so View D is effectively one-dimensional however many
        // columns it was fitted with, and the estimator failures below are
        // the honest consequence rather than a numerical accident.
        manifest.set_double("view_d_axis_abs_correlation_median", at(0.5));
        manifest.set_double("view_d_axis_abs_correlation_p10", at(0.10));
        manifest.set_double("view_d_axis_abs_correlation_p90", at(0.90));
        std::int64_t above_099 = 0;
        for (double c : axis_correlations) {
            if (c > 0.99) ++above_099;
        }
        manifest.set_int("view_d_windows_abs_correlation_above_0_99", above_099);
        manifest.set_int("view_d_windows_measured",
                          static_cast<std::int64_t>(axis_correlations.size()));
    }
    return {};
}

gm::VoidResult run_gm_boundaries(const gm::Config& config, const std::filesystem::path& output_dir,
                                  gm::Manifest& manifest) {
    double alpha = config.get_double_or("boundaries.alpha", 0.05);
    std::int64_t view_b_lookback = config.get_int_or("boundaries.view_b_lookback_days", 60);
    const bool write_meshes = config.get_bool_or("boundaries.write_meshes", false);
    const std::int64_t mesh_resolution = config.get_int_or("boundaries.mesh_resolution", 32);
    const std::int64_t mesh_frame_stride = config.get_int_or("boundaries.mesh_frame_stride", 1);
    const std::int64_t view_b_mesh_stride = config.get_int_or("boundaries.view_b_mesh_stride", 1);
    auto view_b_mesh_tickers = read_view_b_mesh_tickers(config);
    if (!view_b_mesh_tickers) return tl::unexpected(view_b_mesh_tickers.error());
    if (write_meshes && (mesh_resolution < 1 || mesh_resolution > 512)) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "boundaries.mesh_resolution must be between 1 and 512",
            std::to_string(mesh_resolution)));
    }
    if (write_meshes && mesh_frame_stride < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "boundaries.mesh_frame_stride must be at least 1",
                                               std::to_string(mesh_frame_stride)));
    }
    if (write_meshes && view_b_mesh_stride < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "boundaries.view_b_mesh_stride must be at least 1",
                                               std::to_string(view_b_mesh_stride)));
    }
    // Validated here rather than where it is used, for the same reason the
    // View B ticker list is: score_view_d runs after View A and View B have
    // scored every point, so a typo in an axis name would otherwise fail the
    // run twenty minutes in, having already done all the work it is about to
    // throw away.
    if (auto axes = read_view_d_axes(config); !axes) return tl::unexpected(axes.error());

    if (!write_meshes && !view_b_mesh_tickers->empty()) {
        // Naming tickers to mesh and leaving the master switch off is a
        // config that asks for surfaces and silently gets none. Say so
        // instead of running for twenty minutes and producing an empty
        // surfaces directory.
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "boundaries.view_b_mesh_tickers is set but boundaries.write_meshes is false",
            "set write_meshes = true, or remove view_b_mesh_tickers"));
    }

    // Which views to score. Defaults to all of them; exists so that
    // investigating one view does not cost the other two. A View A question
    // takes about two minutes to answer and about twenty if View B has to be
    // recomputed on the way past, and that difference decides whether the
    // question gets asked at all.
    const std::string views = config.get_string_or("boundaries.views", "ABD");
    for (char c : views) {
        if (c != 'A' && c != 'B' && c != 'D') {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument,
                "boundaries.views may contain only the letters A, B and D",
                views));
        }
    }
    const bool score_a = views.find('A') != std::string::npos;
    const bool score_b = views.find('B') != std::string::npos;
    const bool score_d = views.find('D') != std::string::npos;

    std::filesystem::path geometry_dir = output_dir.parent_path() / "gm-geometry";
    auto geometry = gm::io::read_parquet(geometry_dir / "geometry.parquet");
    if (!geometry) return tl::unexpected(geometry.error());

    auto loaded = load_geometry(*geometry);
    if (!loaded) return tl::unexpected(loaded.error());
    auto& [by_ticker, by_date] = *loaded;

    // Checked here rather than at the View B loop it feeds, because that
    // loop runs after View A has scored every frame: a misspelled symbol
    // would otherwise fail the run ten minutes in, having already done all
    // the work it was going to throw away. A ticker can be absent for dull
    // reasons (delisted before the window, wrong share class) and for
    // interesting ones, but either way the run should say so immediately.
    if (!score_b) view_b_lookback = std::numeric_limits<std::int64_t>::max();
    const std::set<std::string>& view_b_wanted = *view_b_mesh_tickers;
    for (const auto& wanted : view_b_wanted) {
        if (by_ticker.find(wanted) == by_ticker.end()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kValidationFailure,
                "boundaries.view_b_mesh_tickers names a ticker absent from this run's geometry",
                wanted));
        }
    }

    ScoreRows rows;
    std::int64_t view_a_frames_scored = 0, view_b_points_scored = 0;
    MeshCounters view_a_meshes;
    MeshCounters view_b_meshes;
    std::int64_t frame_index = 0;
    // How many dimensions the fits actually used, discovered from the
    // artifact rather than assumed, and published so a reader never has to
    // infer it (this stage having silently been 3-D regardless of config is
    // exactly what that inference used to get wrong).
    std::size_t scored_dims = 0;
    for (const auto& [date, ticker_points] : by_date) {
        if (!ticker_points.empty()) {
            scored_dims = ticker_points.front().second.dims();
            break;
        }
    }
    // View A: per frame, fit to every ticker present that frame, score
    // every ticker in that same frame against its own frame's fit.
    for (const auto& [date, ticker_points] : by_date) {
        if (!score_a && !write_meshes) break;
        std::vector<FramePoint> frame_points;
        frame_points.reserve(ticker_points.size());
        for (const auto& [ticker, fp] : ticker_points) frame_points.push_back(fp);
        Eigen::MatrixXd training = points_to_matrix(frame_points);

        bool any_scored = false;
        if (score_a) {
            for (const auto& [ticker, fp] : ticker_points) {
                Eigen::VectorXd query = point_to_vector(fp);
                std::size_t rows_before = rows.dates.size();
                score_both_estimators(rows, training, query, date, ticker, "A", alpha);
                if (rows.dates.size() > rows_before) any_scored = true;
            }
        }
        if (any_scored) ++view_a_frames_scored;

        if (write_meshes && (frame_index % mesh_frame_stride) == 0) {
            // A frame whose surface cannot be extracted does not halt the
            // stage - the scores are the deliverable and they are already
            // computed. But a run that silently produced zero meshes while
            // reporting success is exactly the failure this stage's other
            // counters exist to prevent, so the count and the first
            // message both reach the manifest.
            view_a_meshes.record(export_boundary_mesh(training,
                                                       output_dir / "surfaces" /
                                                           (date + "_A.gmmesh"),
                                                       alpha, static_cast<int>(mesh_resolution)),
                                  date);
        }
        ++frame_index;
    }

    // View B: per ticker, strictly causal - the trailing
    // view_b_lookback_days of THAT TICKER's own prior history (never
    // including today's own point), scoring today's point against it.
    for (const auto& [ticker, history] : by_ticker) {
        // Counted per ticker, so the stride means "every Nth dated point
        // of THIS name" rather than drifting with whatever came before it
        // alphabetically.
        std::int64_t view_b_index = 0;
        for (std::size_t i = static_cast<std::size_t>(view_b_lookback); i < history.size(); ++i) {
            std::vector<FramePoint> window(history.begin() + static_cast<std::ptrdiff_t>(i - static_cast<std::size_t>(view_b_lookback)),
                                            history.begin() + static_cast<std::ptrdiff_t>(i));
            Eigen::MatrixXd training = points_to_matrix(window);
            Eigen::VectorXd query = point_to_vector(history[i]);

            std::size_t rows_before = rows.dates.size();
            score_both_estimators(rows, training, query, history[i].date, ticker, "B", alpha);
            if (rows.dates.size() > rows_before) ++view_b_points_scored;

            // The tube, for the named tickers only. `training` here is the
            // same matrix the scores above were computed from, so the
            // surface written and the inside/outside verdict recorded are
            // the same fit rather than two fits that happen to agree.
            if (write_meshes && view_b_wanted.count(ticker) != 0 &&
                (view_b_index % view_b_mesh_stride) == 0) {
                view_b_meshes.record(
                    export_boundary_mesh(training,
                                          output_dir / "surfaces" /
                                              (history[i].date + "_B_" + ticker + ".gmmesh"),
                                          alpha, static_cast<int>(mesh_resolution)),
                    history[i].date + " " + ticker);
            }
            ++view_b_index;
        }
    }

    // View D: the same causal question in valuation space rather than
    // embedding space (ADR-022). Scored into the same table under view "D",
    // because a consumer comparing "unusual in price geometry" against
    // "unusual in valuation" wants one table, not two.
    if (score_d) {
        if (auto r = score_view_d(config, output_dir, rows, manifest, alpha,
                                   config.get_int_or("boundaries.view_b_lookback_days", 60));
            !r) {
            return tl::unexpected(r.error());
        }
    } else {
        manifest.set_string("view_d", "skipped (boundaries.views excludes D)");
    }

    // Read out before the vectors below are moved-from into the Table -
    // these two counters are plain integers, unaffected by those moves,
    // but capturing them into locals here keeps that fact from having
    // to be re-verified by whoever edits this function next.
    std::size_t mahalanobis_failures = rows.mahalanobis_failures;
    std::size_t kde_failures = rows.kde_failures;
    std::size_t fastmcd_failures = rows.fastmcd_failures;
    std::string first_mahalanobis_failure = rows.first_mahalanobis_failure;
    std::string first_kde_failure = rows.first_kde_failure;
    std::string first_fastmcd_failure = rows.first_fastmcd_failure;

    gm::io::Table scores;
    if (auto r = scores.add_string_column("date", std::move(rows.dates)); !r) return tl::unexpected(r.error());
    if (auto r = scores.add_string_column("ticker", std::move(rows.tickers)); !r) return tl::unexpected(r.error());
    if (auto r = scores.add_string_column("view", std::move(rows.views)); !r) return tl::unexpected(r.error());
    if (auto r = scores.add_string_column("estimator", std::move(rows.estimators)); !r) return tl::unexpected(r.error());
    if (auto r = scores.add_double_column("depth", std::move(rows.depths)); !r) return tl::unexpected(r.error());
    if (auto r = scores.add_double_column("pvalue", std::move(rows.pvalues)); !r) return tl::unexpected(r.error());
    if (auto r = scores.add_bool_column("inside", std::move(rows.insides)); !r) return tl::unexpected(r.error());

    auto write = gm::io::write_parquet(scores, output_dir / "scores.parquet");
    if (!write) return tl::unexpected(write.error());

    manifest.set_int("rows_written", static_cast<std::int64_t>(scores.num_rows()));
    manifest.set_int("embedding_dims_scored", static_cast<std::int64_t>(scored_dims));
    manifest.set_string("views_scored", views);
    manifest.set_int("view_a_frames_scored", view_a_frames_scored);
    manifest.set_int("view_b_points_scored", view_b_points_scored);
    manifest.set_double("alpha", alpha);
    manifest.set_int("view_b_lookback_days", view_b_lookback);
    if (write_meshes) {
        manifest.set_string("mesh_export", "enabled");
        manifest.set_int("mesh_dims", 3);
        if (scored_dims > 3) {
            manifest.set_string("mesh_projection_note",
                                 "surfaces are the first three embedding dimensions; scores use " +
                                     std::to_string(scored_dims));
        }
        manifest.set_int("meshes_written", view_a_meshes.written);
        manifest.set_int("mesh_failures", view_a_meshes.failures);
        manifest.set_int("mesh_resolution", mesh_resolution);
        manifest.set_int("mesh_frame_stride", mesh_frame_stride);
        if (!view_a_meshes.first_error.empty()) {
            manifest.set_string("mesh_first_error", view_a_meshes.first_error);
        }
        // View B's counters are reported separately from View A's, not
        // summed into them: the two are different shapes fitted to
        // different training sets, and one silently failing while the
        // other succeeded would vanish inside a total.
        manifest.set_int("view_b_meshes_written", view_b_meshes.written);
        manifest.set_int("view_b_mesh_failures", view_b_meshes.failures);
        manifest.set_int("view_b_mesh_stride", view_b_mesh_stride);
        std::string wanted_list;
        for (const auto& ticker : view_b_wanted) {
            if (!wanted_list.empty()) wanted_list += ",";
            wanted_list += ticker;
        }
        manifest.set_string("view_b_mesh_tickers", wanted_list);
        if (!view_b_meshes.first_error.empty()) {
            manifest.set_string("view_b_mesh_first_error", view_b_meshes.first_error);
        }
    } else {
        manifest.set_string("mesh_export", "disabled (boundaries.write_meshes = false)");
    }
    // Expected row count is (view_a_frames_scored + view_b_points_scored)
    // * 2 estimators; these counters make the gap between that and
    // rows_written attributable, instead of requiring the reader to
    // reconstruct it by hand. Zero here (the common case) is itself
    // useful confirmation, not just an absence of information.
    manifest.set_int("mahalanobis_failures", static_cast<std::int64_t>(mahalanobis_failures));
    manifest.set_int("kde_failures", static_cast<std::int64_t>(kde_failures));
    manifest.set_int("fastmcd_failures", static_cast<std::int64_t>(fastmcd_failures));
    if (!first_mahalanobis_failure.empty()) {
        manifest.set_string("mahalanobis_first_failure", first_mahalanobis_failure);
    }
    if (!first_kde_failure.empty()) manifest.set_string("kde_first_failure", first_kde_failure);
    if (!first_fastmcd_failure.empty()) {
        manifest.set_string("fastmcd_first_failure", first_fastmcd_failure);
    }

    return {};
}

} // namespace

int main(int argc, char** argv) {
    return gm::run_stage_main(argc, argv, "gm-boundaries", run_gm_boundaries);
}
