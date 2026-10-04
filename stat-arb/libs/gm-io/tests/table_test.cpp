#include <gm-io/table.hpp>

#include <catch2/catch_test_macros.hpp>

using gm::io::ColumnType;
using gm::io::Table;

TEST_CASE("Table stores and returns typed columns", "[table]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {"AAPL", "MSFT"}).has_value());
    REQUIRE(t.add_double_column("close", {185.64, 372.52}).has_value());
    REQUIRE(t.add_int64_column("volume", {82488700, 20214800}).has_value());
    REQUIRE(t.add_bool_column("is_half_day", {0, 1}).has_value());

    CHECK(t.num_rows() == 2);
    CHECK(t.num_columns() == 4);

    auto tickers = t.string_column("ticker");
    REQUIRE(tickers.has_value());
    CHECK(*tickers == std::vector<std::string>{"AAPL", "MSFT"});

    auto closes = t.double_column("close");
    REQUIRE(closes.has_value());
    CHECK((*closes)[0] == 185.64);

    auto volumes = t.int64_column("volume");
    REQUIRE(volumes.has_value());
    CHECK((*volumes)[1] == 20214800);

    auto flags = t.bool_column("is_half_day");
    REQUIRE(flags.has_value());
    CHECK((*flags)[0] == 0);
    CHECK((*flags)[1] == 1);
}

TEST_CASE("column_type and has_column report correctly", "[table]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {"AAPL"}).has_value());

    CHECK(t.has_column("ticker"));
    CHECK_FALSE(t.has_column("nonexistent"));

    auto type = t.column_type("ticker");
    REQUIRE(type.has_value());
    CHECK(*type == ColumnType::kString);
}

TEST_CASE("wrong-typed accessor fails rather than reinterpreting", "[table]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {"AAPL"}).has_value());

    auto wrong = t.int64_column("ticker");
    REQUIRE_FALSE(wrong.has_value());
    CHECK(wrong.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("accessing a nonexistent column fails with kNotFound", "[table]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {"AAPL"}).has_value());

    auto missing = t.string_column("nonexistent");
    REQUIRE_FALSE(missing.has_value());
    CHECK(missing.error().code == gm::ErrorCode::kNotFound);
}

TEST_CASE("column_names preserves insertion order", "[table]") {
    Table t;
    REQUIRE(t.add_string_column("c", {"x"}).has_value());
    REQUIRE(t.add_string_column("a", {"y"}).has_value());
    REQUIRE(t.add_string_column("b", {"z"}).has_value());

    CHECK(t.column_names() == std::vector<std::string>{"c", "a", "b"});
}

TEST_CASE("an empty table has zero rows and zero columns", "[table]") {
    Table t;
    CHECK(t.num_rows() == 0);
    CHECK(t.num_columns() == 0);
}

TEST_CASE("adding a duplicate column name fails cleanly instead of corrupting the table",
          "[table]") {
    // Regression test for the M1 code review finding: this contract
    // violation used to be an assert(), which RelWithDebInfo (this
    // project's own "release" build type) compiles to a no-op via
    // -DNDEBUG - meaning it would have silently corrupted the table in
    // exactly the build configuration actually shipped and tested,
    // rather than crashing loudly. Now a Result<void>, checked always.
    Table t;
    REQUIRE(t.add_string_column("ticker", {"AAPL"}).has_value());

    auto dup = t.add_string_column("ticker", {"MSFT"});
    REQUIRE_FALSE(dup.has_value());
    CHECK(dup.error().code == gm::ErrorCode::kInvalidArgument);

    // The failed call must not have mutated the table.
    CHECK(t.num_columns() == 1);
    auto tickers = t.string_column("ticker");
    REQUIRE(tickers.has_value());
    CHECK(*tickers == std::vector<std::string>{"AAPL"});
}

TEST_CASE("adding a column with the wrong row count fails cleanly", "[table]") {
    Table t;
    REQUIRE(t.add_string_column("ticker", {"AAPL", "MSFT", "GOOG"}).has_value());

    auto mismatched = t.add_double_column("close", {185.64, 372.52});  // 2 values, table has 3 rows
    REQUIRE_FALSE(mismatched.has_value());
    CHECK(mismatched.error().code == gm::ErrorCode::kInvalidArgument);

    CHECK(t.num_columns() == 1);  // the bad column must not have been added
    CHECK(t.num_rows() == 3);
}
