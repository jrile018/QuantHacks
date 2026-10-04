#include <gm-sweep/parameter_grid.hpp>

#include <catch2/catch_test_macros.hpp>
#include <cmath>

using namespace gm::sweep;

TEST_CASE("ParameterGrid expands to correct Cartesian product", "[parameter_grid]") {
    // Create a simple 2x3 grid: 2 values for axis1, 3 for axis2
    toml::table t;
    toml::array arr1, arr2;
    arr1.push_back(1.0);
    arr1.push_back(2.0);
    arr2.push_back(3.0);
    arr2.push_back(4.0);
    arr2.push_back(5.0);
    t.insert_or_assign("axis1", arr1);
    t.insert_or_assign("axis2", arr2);

    auto grid_result = ParameterGrid::from_toml(t);
    REQUIRE(grid_result.has_value());
    auto& grid = grid_result.value();

    REQUIRE(grid.size() == 6);
    
    auto cells = grid.expand_cells();
    REQUIRE(cells.size() == 6);

    // Verify cell_ids are unique and sequential
    for (std::size_t i = 0; i < cells.size(); ++i) {
        CHECK(cells[i].cell_id == static_cast<int>(i));
    }

    // Verify each cell has both axes
    for (const auto& cell : cells) {
        CHECK(cell.param_overrides.count("axis1") == 1);
        CHECK(cell.param_overrides.count("axis2") == 1);
    }

    // Spot-check first and last cells (order: rightmost index changes fastest)
    CHECK(cells[0].param_overrides["axis1"] == "1");
    CHECK(cells[0].param_overrides["axis2"] == "3");
    CHECK(cells[5].param_overrides["axis1"] == "2");
    CHECK(cells[5].param_overrides["axis2"] == "5");
}

TEST_CASE("ParameterGrid rejects empty section", "[parameter_grid]") {
    toml::table t;
    auto result = ParameterGrid::from_toml(t);
    REQUIRE(!result.has_value());
}

TEST_CASE("ParameterGrid rejects non-array values", "[parameter_grid]") {
    toml::table t;
    t.insert_or_assign("bad_axis", 42);
    auto result = ParameterGrid::from_toml(t);
    REQUIRE(!result.has_value());
}

TEST_CASE("ParameterGrid rejects empty arrays", "[parameter_grid]") {
    toml::table t;
    toml::array empty;
    t.insert_or_assign("empty_axis", empty);
    auto result = ParameterGrid::from_toml(t);
    REQUIRE(!result.has_value());
}

TEST_CASE("compute_trial_stats works with constant Sharpes", "[trial_stats]") {
    std::vector<double> sharpes{1.5, 1.5, 1.5};
    auto result = compute_trial_stats(sharpes);
    REQUIRE(result.has_value());
    
    const auto& stats = result.value();
    CHECK(stats.n_trials == 3);
    CHECK(stats.trial_sharpe_mean == 1.5);
    CHECK(stats.trial_sharpe_variance == 0.0);
}

TEST_CASE("compute_trial_stats computes variance correctly", "[trial_stats]") {
    // Example: Sharpes [0, 1, 2] have mean=1, variance=(1+0+1)/3 = 2/3
    std::vector<double> sharpes{0.0, 1.0, 2.0};
    auto result = compute_trial_stats(sharpes);
    REQUIRE(result.has_value());
    
    const auto& stats = result.value();
    CHECK(stats.n_trials == 3);
    CHECK(stats.trial_sharpe_mean == 1.0);
    CHECK(std::abs(stats.trial_sharpe_variance - 2.0/3.0) < 1e-10);
}

TEST_CASE("compute_trial_stats rejects NaN", "[trial_stats]") {
    std::vector<double> sharpes{1.0, std::nan(""), 2.0};
    auto result = compute_trial_stats(sharpes);
    REQUIRE(!result.has_value());
}

TEST_CASE("compute_trial_stats rejects empty", "[trial_stats]") {
    std::vector<double> sharpes;
    auto result = compute_trial_stats(sharpes);
    REQUIRE(!result.has_value());
}

TEST_CASE("ParameterGrid formats doubles with precision", "[parameter_grid]") {
    toml::table t;
    toml::array arr;
    arr.push_back(2.123456789);
    arr.push_back(3.987654321);
    t.insert_or_assign("param", arr);

    auto grid_result = ParameterGrid::from_toml(t);
    REQUIRE(grid_result.has_value());
    
    auto cells = grid_result.value().expand_cells();
    REQUIRE(cells.size() == 2);
    
    // Verify double -> string -> double round-trip works
    double v0 = std::stod(cells[0].param_overrides["param"]);
    double v1 = std::stod(cells[1].param_overrides["param"]);
    CHECK(std::abs(v0 - 2.123456789) < 1e-14);
    CHECK(std::abs(v1 - 3.987654321) < 1e-14);
}

TEST_CASE("ParameterGrid handles integer and double mixed in same array", "[parameter_grid]") {
    toml::table t;
    toml::array arr;
    arr.push_back(1);          // integer
    arr.push_back(2.5);        // floating point
    arr.push_back(3);          // integer again
    t.insert_or_assign("mixed", arr);

    auto grid_result = ParameterGrid::from_toml(t);
    REQUIRE(grid_result.has_value());
    
    auto cells = grid_result.value().expand_cells();
    REQUIRE(cells.size() == 3);
    CHECK(cells[0].param_overrides["mixed"] == "1");
    CHECK(std::abs(std::stod(cells[1].param_overrides["mixed"]) - 2.5) < 1e-10);
    CHECK(cells[2].param_overrides["mixed"] == "3");
}
