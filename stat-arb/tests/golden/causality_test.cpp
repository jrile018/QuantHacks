// ADR-020 layer 3: View B and View D scores must be CAUSAL.
//
// The property, stated as the ADR states it: recomputing with future data
// truncated changes nothing. A score dated D must depend only on data from
// on or before D, so scoring a panel that ends at D and scoring one that
// runs years past D must agree exactly on every date up to D.
//
// This is the single most load-bearing property in the project and the one
// whose violation is hardest to notice. A look-ahead leak does not crash,
// does not fail a unit test, and does not produce implausible numbers - it
// produces BETTER numbers, and a backtest built on it looks like a
// discovery. Every other guarantee here is checkable by reading the output;
// this one is only checkable by running the thing twice.
//
// Deliberately an integration test against the real binary rather than a
// unit test on a windowing helper. The helper is not what ships; the stage
// is, and the stage is where an innocuous-looking edit (a <= for a <, a
// window built from history.end() rather than from i) puts the future into
// the past.
//
// GM_BOUNDARIES_EXECUTABLE is injected by CMake so this never hardcodes a
// build layout.

#include "run_process.hpp"

#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#if !defined(_WIN32)
#include <sys/wait.h>
#endif

#ifndef GM_BOUNDARIES_EXECUTABLE
#error "GM_BOUNDARIES_EXECUTABLE must be defined by CMake"
#endif

namespace {

/// A deterministic synthetic embedding: `tickers` names over `frames` dates,
/// each wandering on its own smooth path plus a repeatable wobble. Smooth
/// enough that a trailing window is well conditioned, varied enough that a
/// score computed from the wrong window differs from one computed from the
/// right one - which is the whole point of the comparison below.
gm::io::Table synthetic_geometry(int frames, int tickers) {
    std::vector<std::string> dates, names;
    std::vector<double> xs, ys, zs;
    for (int f = 0; f < frames; ++f) {
        // 2020-01-01 plus f days, as an ISO string. Calendar validity does
        // not matter here - the stage compares dates lexically - but real
        // month lengths keep the strings sortable in the obvious way.
        char buf[16];
        std::snprintf(buf, sizeof(buf), "20%02d-%02d-%02d", 20 + f / 336,
                      1 + (f / 28) % 12, 1 + f % 28);
        for (int t = 0; t < tickers; ++t) {
            dates.emplace_back(buf);
            names.push_back("T" + std::to_string(t));
            const double a = 0.11 * static_cast<double>(f) + static_cast<double>(t);
            xs.push_back(std::sin(a) + 0.01 * static_cast<double>(t));
            ys.push_back(std::cos(a * 1.3) - 0.02 * static_cast<double>(t));
            zs.push_back(std::sin(a * 0.7 + static_cast<double>(t)) * 0.5);
        }
    }
    gm::io::Table table;
    REQUIRE(table.add_string_column("date", std::move(dates)).has_value());
    REQUIRE(table.add_string_column("ticker", std::move(names)).has_value());
    REQUIRE(table.add_double_column("x", std::move(xs)).has_value());
    REQUIRE(table.add_double_column("y", std::move(ys)).has_value());
    REQUIRE(table.add_double_column("z", std::move(zs)).has_value());
    return table;
}

/// Writes `table`'s first `keep_frames` dates into a run directory laid out
/// the way gm-boundaries expects, and returns that run's boundaries output
/// directory.
std::filesystem::path make_run(const std::filesystem::path& root, const std::string& name,
                               const gm::io::Table& full, int keep_frames, int tickers) {
    const auto run_dir = root / name;
    std::filesystem::create_directories(run_dir / "gm-geometry");
    std::filesystem::create_directories(run_dir / "gm-boundaries");

    auto dates = full.string_column("date");
    auto names = full.string_column("ticker");
    auto xs = full.double_column("x");
    auto ys = full.double_column("y");
    auto zs = full.double_column("z");
    REQUIRE(dates.has_value());

    const std::size_t keep_rows =
        static_cast<std::size_t>(keep_frames) * static_cast<std::size_t>(tickers);
    gm::io::Table cut;
    REQUIRE(cut.add_string_column("date", {dates->begin(), dates->begin() + static_cast<std::ptrdiff_t>(keep_rows)}).has_value());
    REQUIRE(cut.add_string_column("ticker", {names->begin(), names->begin() + static_cast<std::ptrdiff_t>(keep_rows)}).has_value());
    REQUIRE(cut.add_double_column("x", {xs->begin(), xs->begin() + static_cast<std::ptrdiff_t>(keep_rows)}).has_value());
    REQUIRE(cut.add_double_column("y", {ys->begin(), ys->begin() + static_cast<std::ptrdiff_t>(keep_rows)}).has_value());
    REQUIRE(cut.add_double_column("z", {zs->begin(), zs->begin() + static_cast<std::ptrdiff_t>(keep_rows)}).has_value());

    REQUIRE(gm::io::write_parquet(cut, run_dir / "gm-geometry" / "geometry.parquet").has_value());
    return run_dir / "gm-boundaries";
}

/// (date, ticker, view, estimator) -> inside flag, for every scored row.
std::map<std::string, bool> read_inside(const std::filesystem::path& boundaries_dir) {
    auto table = gm::io::read_parquet(boundaries_dir / "scores.parquet");
    REQUIRE(table.has_value());
    auto date = table->string_column("date");
    auto ticker = table->string_column("ticker");
    auto view = table->string_column("view");
    auto estimator = table->string_column("estimator");
    auto inside = table->bool_column("inside");
    REQUIRE(inside.has_value());

    std::map<std::string, bool> out;
    for (std::size_t i = 0; i < inside->size(); ++i) {
        out[(*date)[i] + "|" + (*ticker)[i] + "|" + (*view)[i] + "|" + (*estimator)[i]] =
            (*inside)[i] != 0;
    }
    return out;
}

/// (date, ticker, view, estimator) -> depth, for every scored row.
///
/// `depth` is distance MINUS the critical distance: negative is inside the
/// boundary, positive is outside. A signed margin, not a magnitude - which
/// matters when writing assertions about it.
std::map<std::string, double> read_depths(const std::filesystem::path& boundaries_dir) {
    auto table = gm::io::read_parquet(boundaries_dir / "scores.parquet");
    REQUIRE(table.has_value());
    auto date = table->string_column("date");
    auto ticker = table->string_column("ticker");
    auto view = table->string_column("view");
    auto estimator = table->string_column("estimator");
    auto depth = table->double_column("depth");
    REQUIRE(depth.has_value());

    std::map<std::string, double> out;
    for (std::size_t i = 0; i < depth->size(); ++i) {
        out[(*date)[i] + "|" + (*ticker)[i] + "|" + (*view)[i] + "|" + (*estimator)[i]] =
            (*depth)[i];
    }
    return out;
}

int run_boundaries(const std::filesystem::path& config, const std::filesystem::path& out_dir,
                   const char* run_id) {
    std::ostringstream cmd;
    cmd << "\"" << GM_BOUNDARIES_EXECUTABLE << "\" --config \"" << config.string()
        << "\" --run-id \"" << run_id << "\" --output-dir \"" << out_dir.string()
        << "\" --manifest-out \"" << (out_dir / "manifest.json").string() << "\"";
#if !defined(_WIN32)
    cmd << " > /dev/null 2>&1";
#else
    cmd << " > NUL 2>&1";
#endif
    return gm::test::run_command(cmd.str());
}

} // namespace

TEST_CASE("View B scores are causal: truncating the future changes nothing", "[causality]") {
    const auto root = std::filesystem::temp_directory_path() / "gm-causality-tests" / "view_b";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    constexpr int kTickers = 6;
    constexpr int kLookback = 10;
    constexpr int kShortFrames = 40;   // scores exist from frame kLookback onward
    constexpr int kLongFrames = 90;    // the same run, plus fifty more days of future

    const auto full = synthetic_geometry(kLongFrames, kTickers);

    const auto config = root / "boundaries.toml";
    {
        std::ofstream out(config);
        out << "[boundaries]\n"
            << "alpha = 0.05\n"
            << "views = \"B\"\n"
            << "view_b_lookback_days = " << kLookback << "\n";
    }

    const auto short_dir = make_run(root, "short", full, kShortFrames, kTickers);
    const auto long_dir = make_run(root, "long", full, kLongFrames, kTickers);
    REQUIRE(run_boundaries(config, short_dir, "short") == 0);
    REQUIRE(run_boundaries(config, long_dir, "long") == 0);

    const auto short_depths = read_depths(short_dir);
    const auto long_depths = read_depths(long_dir);

    // The short run must have produced real work, or this test proves
    // nothing by comparing two empty sets.
    REQUIRE(short_depths.size() > 50);

    std::size_t compared = 0;
    for (const auto& [key, depth] : short_depths) {
        const auto found = long_depths.find(key);
        INFO("key = " << key);
        REQUIRE(found != long_depths.end());
        // EXACTLY equal, not close. Both runs fit the same estimator to the
        // same trailing window of the same numbers; any difference at all
        // means the longer run's extra data reached a score it should not
        // have been able to touch.
        CHECK(found->second == depth);
        ++compared;
    }
    CHECK(compared == short_depths.size());

    std::filesystem::remove_all(root);
}

TEST_CASE("the causality test can actually detect a leak", "[causality]") {
    // A test that compares two runs is worthless if the two runs would
    // agree regardless. This establishes that the synthetic panel really
    // does score differently when the window it is fitted to differs - so
    // the agreement above is evidence of causality rather than evidence
    // that nothing varies.
    const auto root = std::filesystem::temp_directory_path() / "gm-causality-tests" / "sensitivity";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    constexpr int kTickers = 6;
    constexpr int kFrames = 60;
    const auto full = synthetic_geometry(kFrames, kTickers);

    const auto make_config = [&](int lookback) {
        const auto path = root / ("lookback_" + std::to_string(lookback) + ".toml");
        std::ofstream out(path);
        out << "[boundaries]\nalpha = 0.05\nviews = \"B\"\nview_b_lookback_days = " << lookback
            << "\n";
        return path;
    };

    const auto dir_a = make_run(root, "a", full, kFrames, kTickers);
    const auto dir_b = make_run(root, "b", full, kFrames, kTickers);
    REQUIRE(run_boundaries(make_config(10), dir_a, "a") == 0);
    REQUIRE(run_boundaries(make_config(20), dir_b, "b") == 0);

    const auto a = read_depths(dir_a);
    const auto b = read_depths(dir_b);

    std::size_t differing = 0, shared = 0;
    for (const auto& [key, depth] : a) {
        const auto found = b.find(key);
        if (found == b.end()) continue;
        ++shared;
        if (found->second != depth) ++differing;
    }
    REQUIRE(shared > 20);
    // Fitting to a different window really does move the score, on most of
    // the dates both runs cover.
    CHECK(differing > shared / 2);

    std::filesystem::remove_all(root);
}

namespace {

/// A panel where every ticker sits in a tight cloud for the whole history
/// and then, on the LAST date, ticker T0 alone jumps far away.
///
/// The jump is the instrument. Scored against prior history only, T0's last
/// day is wildly unusual. Scored against a window that includes the jump
/// itself, the cloud stretches to cover it and the same day looks ordinary.
/// The two readings differ by orders of magnitude, which is what makes the
/// check unambiguous rather than a tolerance argument.
gm::io::Table panel_with_final_jump(int frames, int tickers, double jump) {
    std::vector<std::string> dates, names;
    std::vector<double> xs, ys, zs;
    for (int f = 0; f < frames; ++f) {
        char buf[16];
        std::snprintf(buf, sizeof(buf), "20%02d-%02d-%02d", 20 + f / 336,
                      1 + (f / 28) % 12, 1 + f % 28);
        for (int t = 0; t < tickers; ++t) {
            dates.emplace_back(buf);
            names.push_back("T" + std::to_string(t));
            // A small, varied wander - varied enough that the median
            // absolute deviation is non-zero in every dimension, which the
            // estimators require.
            const double a = 0.37 * static_cast<double>(f) + 1.7 * static_cast<double>(t);
            double x = 0.01 * std::sin(a);
            double y = 0.01 * std::cos(a * 1.1);
            double z = 0.01 * std::sin(a * 0.6);
            if (t == 0 && f == frames - 1) {
                x += jump;
                y += jump;
                z += jump;
            }
            xs.push_back(x);
            ys.push_back(y);
            zs.push_back(z);
        }
    }
    gm::io::Table table;
    REQUIRE(table.add_string_column("date", std::move(dates)).has_value());
    REQUIRE(table.add_string_column("ticker", std::move(names)).has_value());
    REQUIRE(table.add_double_column("x", std::move(xs)).has_value());
    REQUIRE(table.add_double_column("y", std::move(ys)).has_value());
    REQUIRE(table.add_double_column("z", std::move(zs)).has_value());
    return table;
}

} // namespace

TEST_CASE("View B never includes the day it is scoring in that day's own training window",
          "[causality]") {
    // ADR-011: the window is strictly PRIOR history. A point included in the
    // cloud it is measured against pulls that cloud toward itself, so the
    // more unusual a day is the better it hides - and the scores decay
    // toward "nothing is ever an outlier" without anything failing.
    //
    // This is deliberately a separate test from the truncation one above,
    // because the truncation test CANNOT see this: including today's own
    // point is not look-ahead relative to the end of the panel, so both runs
    // agree and the property passes while the estimator is ruined. Found by
    // mutating the window bound and watching the other test stay green.
    const auto root = std::filesystem::temp_directory_path() / "gm-causality-tests" / "self";
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root);

    constexpr int kTickers = 5;
    constexpr int kFrames = 30;
    constexpr int kLookback = 10;
    const auto full = panel_with_final_jump(kFrames, kTickers, 5.0);

    const auto config = root / "boundaries.toml";
    {
        std::ofstream out(config);
        out << "[boundaries]\nalpha = 0.05\nviews = \"B\"\nview_b_lookback_days = " << kLookback
            << "\n";
    }
    const auto dir = make_run(root, "jump", full, kFrames, kTickers);
    REQUIRE(run_boundaries(config, dir, "jump") == 0);

    const auto depths = read_depths(dir);

    // The final date, formatted the same way the generator formats it.
    char last[16];
    std::snprintf(last, sizeof(last), "20%02d-%02d-%02d", 20 + (kFrames - 1) / 336,
                  1 + ((kFrames - 1) / 28) % 12, 1 + (kFrames - 1) % 28);

    const std::string jumped = std::string(last) + "|T0|B|mahalanobis";
    const auto found = depths.find(jumped);
    REQUIRE(found != depths.end());

    // A quiet ticker on the same date, as the control: same window length,
    // same estimator, no jump.
    const std::string quiet = std::string(last) + "|T1|B|mahalanobis";
    const auto control = depths.find(quiet);
    REQUIRE(control != depths.end());

    INFO("jumped depth = " << found->second << ", control depth = " << control->second);

    // `depth` is a SIGNED margin - distance minus the critical distance - so
    // an assertion phrased as a ratio is vacuous whenever the control is
    // negative, which for a quiet ticker inside its own boundary it is.
    // Mutation testing caught exactly that: with the window extended to
    // include today, jumped fell from 21720.7 to 0.21963 while control went
    // from 1.8394 to -0.300882, and "jumped > 100 * control" stayed true
    // because 0.21963 > -30.09. The margin itself is the thing to assert on.
    //
    // Scored against prior history alone, a five-unit jump out of a cloud
    // spanning 0.02 sits enormously outside. If the jump were inside its own
    // training window it would be one point in eleven, the cloud would
    // stretch to reach it, and this margin would collapse to nearly nothing.
    CHECK(found->second > 1000.0);
    CHECK(found->second > control->second + 1000.0);

    // And it must be REPORTED as outside, which is the column a consumer
    // actually reads.
    const auto inside = read_inside(dir);
    const auto inside_jumped = inside.find(jumped);
    REQUIRE(inside_jumped != inside.end());
    CHECK_FALSE(inside_jumped->second);

    std::filesystem::remove_all(root);
}
