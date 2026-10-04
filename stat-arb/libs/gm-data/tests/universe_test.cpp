#include <gm-data/universe.hpp>

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>

using gm::Date;
using gm::TickerId;
using gm::data::Universe;

namespace {

/// Writes a fixture into a directory OF ITS OWN, named after the fixture.
///
/// The nesting is the whole point. catch_discover_tests registers every
/// TEST_CASE as a separate ctest test, so `ctest -j` runs several processes
/// of this binary concurrently. When these tests all shared one
/// "gm-data-tests" directory, each one's closing
/// remove_all(path.parent_path()) deleted every other running test's
/// fixtures - a race that produced roughly one failure per three full-suite
/// runs, always blamed on whichever test happened to be reading at the
/// moment another finished. Giving each fixture its own directory makes
/// those existing cleanup calls correct without changing any of them.
std::filesystem::path write_fixture(const char* name, const std::string& contents) {
    auto path = std::filesystem::temp_directory_path() / "gm-data-tests" / name / name;
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    out << contents;
    return path;
}

constexpr const char* kGoodHeader =
    "symbol,security,gics_sector,gics_sub_industry,hq_location,date_added,cik,founded\n";

} // namespace

TEST_CASE("loads a well-formed snapshot and reports point-in-time membership", "[universe]") {
    auto path = write_fixture("good.csv",
                               std::string{kGoodHeader} +
                                   "AAPL,Apple Inc.,Information Technology,Technology Hardware,"
                                   "Cupertino California,1982-11-30,320193,1976\n"
                                   "RDDT,Reddit Inc.,Communication Services,Interactive Media,"
                                   "San Francisco California,2025-09-15,1713445,2005\n");

    auto universe = Universe::load_sp500_snapshot(path);
    REQUIRE(universe.has_value());
    CHECK(universe->size() == 2);

    // AAPL joined 1982-11-30: a member well before and after that date.
    CHECK(universe->is_member(TickerId{"AAPL"}, Date{1990, 1, 1}));
    CHECK(universe->is_member(TickerId{"AAPL"}, Date{1982, 11, 30}));  // exactly the join date
    CHECK_FALSE(universe->is_member(TickerId{"AAPL"}, Date{1982, 11, 29}));  // one day before

    // RDDT joined 2025-09-15.
    CHECK_FALSE(universe->is_member(TickerId{"RDDT"}, Date{2020, 1, 1}));
    CHECK(universe->is_member(TickerId{"RDDT"}, Date{2026, 1, 1}));

    // A ticker never in the snapshot at all.
    CHECK_FALSE(universe->is_member(TickerId{"NOTREAL"}, Date{2020, 1, 1}));

    std::filesystem::remove_all(path.parent_path());
}

TEST_CASE("members_as_of returns exactly the tickers eligible on that date, sorted", "[universe]") {
    auto path = write_fixture("members.csv",
                               std::string{kGoodHeader} +
                                   "MSFT,Microsoft,Information Technology,Software,Redmond "
                                   "Washington,1994-06-01,789019,1975\n"
                                   "AAPL,Apple Inc.,Information Technology,Technology "
                                   "Hardware,Cupertino California,1982-11-30,320193,1976\n"
                                   "RDDT,Reddit Inc.,Communication Services,Interactive "
                                   "Media,San Francisco California,2025-09-15,1713445,2005\n");

    auto universe = Universe::load_sp500_snapshot(path);
    REQUIRE(universe.has_value());

    auto members_2000 = universe->members_as_of(Date{2000, 1, 1});
    REQUIRE(members_2000.size() == 2);
    CHECK(members_2000[0].value() == "AAPL");
    CHECK(members_2000[1].value() == "MSFT");

    auto members_2026 = universe->members_as_of(Date{2026, 1, 1});
    CHECK(members_2026.size() == 3);

    std::filesystem::remove_all(path.parent_path());
}

TEST_CASE("find returns the full record or a not-found error", "[universe]") {
    auto path = write_fixture(
        "find.csv", std::string{kGoodHeader} +
                        "AAPL,Apple Inc.,Information Technology,Technology Hardware,Cupertino "
                        "California,1982-11-30,320193,1976 (as Apple Computer Company)\n");

    auto universe = Universe::load_sp500_snapshot(path);
    REQUIRE(universe.has_value());

    auto found = universe->find(TickerId{"AAPL"});
    REQUIRE(found.has_value());
    CHECK((*found)->security_name == "Apple Inc.");
    CHECK((*found)->cik.value() == 320193);
    REQUIRE((*found)->founded_year.has_value());
    CHECK(*(*found)->founded_year == 1976);  // leading-year parse ignores the trailing note

    auto missing = universe->find(TickerId{"NOTREAL"});
    REQUIRE_FALSE(missing.has_value());
    CHECK(missing.error().code == gm::ErrorCode::kNotFound);

    std::filesystem::remove_all(path.parent_path());
}

TEST_CASE("a malformed date_added fails the whole load, not just that row", "[universe]") {
    auto path = write_fixture("bad_date.csv",
                               std::string{kGoodHeader} +
                                   "AAPL,Apple Inc.,Information Technology,Technology Hardware,"
                                   "Cupertino California,not-a-date,320193,1976\n");

    auto universe = Universe::load_sp500_snapshot(path);
    REQUIRE_FALSE(universe.has_value());
    CHECK(universe.error().code == gm::ErrorCode::kParseFailure);

    std::filesystem::remove_all(path.parent_path());
}

TEST_CASE("a duplicate ticker fails the load", "[universe]") {
    auto path = write_fixture("dup.csv",
                               std::string{kGoodHeader} +
                                   "AAPL,Apple Inc.,Information Technology,Technology Hardware,"
                                   "Cupertino California,1982-11-30,320193,1976\n"
                                   "AAPL,Apple Inc. Duplicate,Information Technology,Technology "
                                   "Hardware,Cupertino California,1982-11-30,320193,1976\n");

    auto universe = Universe::load_sp500_snapshot(path);
    REQUIRE_FALSE(universe.has_value());
    CHECK(universe.error().code == gm::ErrorCode::kParseFailure);

    std::filesystem::remove_all(path.parent_path());
}

TEST_CASE("a mismatched header schema fails cleanly", "[universe]") {
    auto path = write_fixture("bad_header.csv", "wrong,header,schema\na,b,c\n");

    auto universe = Universe::load_sp500_snapshot(path);
    REQUIRE_FALSE(universe.has_value());
    CHECK(universe.error().code == gm::ErrorCode::kParseFailure);

    std::filesystem::remove_all(path.parent_path());
}

TEST_CASE("load fails cleanly on a missing file", "[universe]") {
    auto universe = Universe::load_sp500_snapshot(
        std::filesystem::temp_directory_path() / "gm-data-tests" / "does_not_exist.csv");
    REQUIRE_FALSE(universe.has_value());
    CHECK(universe.error().code == gm::ErrorCode::kNotFound);
}
