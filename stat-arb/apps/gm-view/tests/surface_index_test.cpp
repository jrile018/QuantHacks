// Tests for SurfaceIndex - the map from a run's exported .gmmesh files to
// "which surface belongs on screen right now".
//
// Two things here are worth testing rather than eyeballing:
//
// 1. The look-ahead rule. View B tubes are exported on a stride, so the
//    viewer almost always has to pick an earlier date's surface. Picking
//    a LATER one would put a shape on screen that was fitted to data not
//    yet available on the date being displayed - the same look-ahead
//    ADR-011 forbids in the scores, and no more acceptable in a picture.
//    A one-character slip (upper_bound -> lower_bound, prev dropped) does
//    exactly that and changes nothing else visible.
//
// 2. Filename parsing. Two real S&P symbols contain a dot (BRK.B, BF.B),
//    so anything that splits the name on punctuation mangles them into a
//    ticker nobody can look up. The date is fixed-width ISO, so the view
//    marker is at a known offset and the ticker is simply the rest.
//
// Fixtures here are empty files with the right NAMES: index_surfaces
// reads names, never contents, and using real meshes would make these
// tests depend on the mesh writer for no added coverage.

#include "../data_loader.hpp"

#include <catch2/catch_test_macros.hpp>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace {

/// A scratch run directory of this test's own name. catch_discover_tests
/// registers every TEST_CASE as a separate ctest test, so `ctest -j` runs
/// these as concurrent processes - a shared directory plus the remove_all
/// below is the race already fixed in universe_test.cpp and http_cache_test.cpp.
std::filesystem::path make_run(const char* test_name,
                               const std::vector<std::string>& surface_names,
                               const std::string& manifest_body = "") {
    const auto run_dir = std::filesystem::temp_directory_path() / "gm-view-surface-tests" / test_name;
    std::filesystem::remove_all(run_dir);
    const auto surfaces = run_dir / "gm-boundaries" / "surfaces";
    std::filesystem::create_directories(surfaces);
    for (const auto& name : surface_names) {
        std::ofstream out(surfaces / name, std::ios::binary | std::ios::trunc);
        out << "not a real mesh";
    }
    if (!manifest_body.empty()) {
        std::ofstream out(run_dir / "gm-boundaries" / "manifest.json", std::ios::trunc);
        out << manifest_body;
    }
    return run_dir;
}

} // namespace

TEST_CASE("index_surfaces separates View A dates from View B tubes", "[surface_index]") {
    const auto run = make_run("separates_views", {
                                                     "2024-01-05_A.gmmesh",
                                                     "2024-01-12_A.gmmesh",
                                                     "2024-01-05_B_AAPL.gmmesh",
                                                     "2024-01-12_B_AAPL.gmmesh",
                                                     "2024-01-12_B_MSFT.gmmesh",
                                                 });
    const auto index = gm::view::index_surfaces(run);

    CHECK(index.directory_exists);
    CHECK(index.view_a_dates.size() == 2);
    CHECK(index.view_a_dates.count("2024-01-05") == 1);
    // A View A date must NOT appear as a ticker, and a View B file must not
    // be counted as a View A date - the two are drawn against different
    // point clouds, so a file landing in the wrong bucket puts one view's
    // surface around the other view's points.
    CHECK(index.view_b_dates.size() == 2);
    CHECK(index.view_b_dates.at("AAPL").size() == 2);
    CHECK(index.view_b_dates.at("MSFT").size() == 1);
    CHECK(index.view_b_dates.count("2024-01-05") == 0);

    std::filesystem::remove_all(run);
}

TEST_CASE("index_surfaces keeps the dot in a dotted ticker", "[surface_index]") {
    // BRK.B and BF.B are real S&P 500 symbols. Splitting the filename on
    // '.' would index them as "BRK" and "BF" - names that match no ticker
    // in the run, so the viewer would report no tube for a name it in fact
    // exported one for.
    const auto run = make_run("dotted_ticker", {
                                                   "2024-01-05_B_BRK.B.gmmesh",
                                                   "2024-01-05_B_BF.B.gmmesh",
                                               });
    const auto index = gm::view::index_surfaces(run);

    CHECK(index.view_b_dates.count("BRK.B") == 1);
    CHECK(index.view_b_dates.count("BF.B") == 1);
    CHECK(index.view_b_dates.count("BRK") == 0);

    std::filesystem::remove_all(run);
}

TEST_CASE("view_b_surface_for never returns a date later than asked for", "[surface_index]") {
    // The tube at date D is fitted to history BEFORE D. Showing the tube
    // from a later date against date D's points would draw a shape built
    // from data that did not exist yet - look-ahead, in a picture.
    const auto run = make_run("no_lookahead", {
                                                  "2024-01-05_B_AAPL.gmmesh",
                                                  "2024-02-09_B_AAPL.gmmesh",
                                                  "2024-03-15_B_AAPL.gmmesh",
                                              });
    const auto index = gm::view::index_surfaces(run);

    // Exact hit stays put.
    CHECK(index.view_b_surface_for("AAPL", "2024-02-09").value() == "2024-02-09");
    // Between exports: snaps BACK, never forward.
    CHECK(index.view_b_surface_for("AAPL", "2024-02-28").value() == "2024-02-09");
    CHECK(index.view_b_surface_for("AAPL", "2024-03-14").value() == "2024-02-09");
    // The day the next one lands.
    CHECK(index.view_b_surface_for("AAPL", "2024-03-15").value() == "2024-03-15");
    // After the last export, the last one is still the newest available.
    CHECK(index.view_b_surface_for("AAPL", "2029-12-31").value() == "2024-03-15");
    // Before the first, there is nothing causal to show - and showing the
    // first anyway is precisely the look-ahead this test exists for.
    CHECK_FALSE(index.view_b_surface_for("AAPL", "2024-01-04").has_value());
    CHECK_FALSE(index.view_b_surface_for("AAPL", "2023-06-01").has_value());
    // A ticker with no tubes at all.
    CHECK_FALSE(index.view_b_surface_for("MSFT", "2024-03-15").has_value());

    std::filesystem::remove_all(run);
}

TEST_CASE("view_b_surface_for is correct regardless of directory order", "[surface_index]") {
    // std::filesystem::directory_iterator order is unspecified, and
    // view_b_surface_for binary-searches the vector it fills. Unsorted
    // input makes upper_bound return an arbitrary element rather than
    // failing, so this would surface as an occasionally-wrong picture on
    // some filesystems and never on others.
    const auto run = make_run("order_independent", {
                                                       "2024-03-15_B_AAPL.gmmesh",
                                                       "2024-01-05_B_AAPL.gmmesh",
                                                       "2024-02-09_B_AAPL.gmmesh",
                                                   });
    auto index = gm::view::index_surfaces(run);
    const auto& dates = index.view_b_dates.at("AAPL");
    CHECK(std::is_sorted(dates.begin(), dates.end()));
    CHECK(index.view_b_surface_for("AAPL", "2024-02-28").value() == "2024-02-09");

    std::filesystem::remove_all(run);
}

TEST_CASE("index_surfaces reads view_b_lookback_days from the stage manifest",
          "[surface_index]") {
    // The viewer defaults its trajectory length to this so the drawn path
    // and the drawn tube cover the same window.
    const auto run = make_run("reads_lookback", {"2024-01-05_B_AAPL.gmmesh"},
                              R"({"schema_version":"1.0.0","stage":"gm-boundaries",)"
                              R"("run_id":"t","view_b_lookback_days":756})");
    const auto index = gm::view::index_surfaces(run);
    CHECK(index.view_b_lookback_days == 756);

    std::filesystem::remove_all(run);
}

TEST_CASE("index_surfaces tolerates a run with no surfaces and one with junk",
          "[surface_index]") {
    const auto empty_run =
        std::filesystem::temp_directory_path() / "gm-view-surface-tests" / "no_surfaces";
    std::filesystem::remove_all(empty_run);
    std::filesystem::create_directories(empty_run);
    const auto missing = gm::view::index_surfaces(empty_run);
    // Not an error - it is the normal state of a run made without meshes,
    // and the viewer says so rather than reporting a failure.
    CHECK_FALSE(missing.directory_exists);
    CHECK(missing.view_a_dates.empty());
    std::filesystem::remove_all(empty_run);

    // Names this build does not recognize are ignored, not rejected: a
    // later gm-boundaries adding a third view should not stop an older
    // viewer drawing the two it does know.
    const auto junk_run = make_run("junk_names", {
                                                     "readme.txt",
                                                     "2024-01-05_C_WEIRD.gmmesh",
                                                     "_A.gmmesh",
                                                     "2024-01-05_B_.gmmesh",
                                                     "2024-01-05_A.gmmesh",
                                                 });
    const auto index = gm::view::index_surfaces(junk_run);
    CHECK(index.view_a_dates.size() == 1);
    CHECK(index.view_b_dates.empty());
    std::filesystem::remove_all(junk_run);
}
