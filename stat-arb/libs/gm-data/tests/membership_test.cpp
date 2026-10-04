// Tests for point-in-time membership reconstructed from dated
// observations.
//
// The case that matters is the third one. Everything else here is
// bookkeeping; snapping FORWARD to a nearer observation would silently
// add the names an index committee was about to add, which is exactly
// the look-ahead this whole file exists to remove.

#include <gm-data/membership.hpp>

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>
#include <string>

using gm::data::MembershipHistory;

namespace {

/// Writes `body` to a uniquely-named file and removes it on scope exit.
class TempCsv {
public:
    explicit TempCsv(const std::string& body) {
        static int counter = 0;
        path_ = std::filesystem::temp_directory_path() /
                ("gm_membership_test_" + std::to_string(counter++) + ".csv");
        std::ofstream out(path_);
        out << body;
    }
    ~TempCsv() {
        std::error_code ec;
        std::filesystem::remove(path_, ec);
    }
    TempCsv(const TempCsv&) = delete;
    TempCsv& operator=(const TempCsv&) = delete;

    [[nodiscard]] const std::filesystem::path& path() const { return path_; }

private:
    std::filesystem::path path_;
};

gm::Date on(const char* iso) { return *gm::Date::parse_iso(iso); }

// Three monthly observations. BBB leaves after January and CCC arrives
// in March, so this fixture contains both a departure and an arrival.
const char* kFixture =
    "observed_date,ticker\n"
    "2020-01-01,AAA\n"
    "2020-01-01,BBB\n"
    "2020-02-01,AAA\n"
    "2020-03-01,AAA\n"
    "2020-03-01,CCC\n";

} // namespace

TEST_CASE("membership on an observation date is that observation", "[gm-data][membership]") {
    const TempCsv csv(kFixture);
    const auto history = MembershipHistory::load(csv.path());
    REQUIRE(history.has_value());
    CHECK(history->num_observations() == 3);

    const auto january = history->members_as_of(on("2020-01-01"));
    REQUIRE(january.size() == 2);
    CHECK(january[0].value() == "AAA");
    CHECK(january[1].value() == "BBB");
}

TEST_CASE("membership between observations uses the earlier one", "[gm-data][membership]") {
    const TempCsv csv(kFixture);
    const auto history = MembershipHistory::load(csv.path());
    REQUIRE(history.has_value());

    // Mid-January: the February observation does not exist yet.
    REQUIRE(history->observation_used(on("2020-01-20")) == on("2020-01-01"));
    const auto mid = history->members_as_of(on("2020-01-20"));
    REQUIRE(mid.size() == 2);
    CHECK(mid[1].value() == "BBB");
}

TEST_CASE("membership never snaps forward to a later observation", "[gm-data][membership]") {
    // The one that matters. CCC first appears in the March observation.
    // Any date before that must not see it, however close: snapping to
    // the nearest observation instead of the newest preceding one would
    // put a name in the universe before the day it was announced, and
    // the names being added are disproportionately the ones that just
    // went up.
    const TempCsv csv(kFixture);
    const auto history = MembershipHistory::load(csv.path());
    REQUIRE(history.has_value());

    const gm::TickerId ccc{"CCC"};
    CHECK_FALSE(history->is_member(ccc, on("2020-02-28")));  // one day before, and nearest
    CHECK_FALSE(history->is_member(ccc, on("2020-02-01")));
    CHECK(history->is_member(ccc, on("2020-03-01")));
    CHECK(history->is_member(ccc, on("2020-06-01")));  // last observation carries forward

    // And the corresponding departure: BBB is gone from February on,
    // but was genuinely there in January.
    const gm::TickerId bbb{"BBB"};
    CHECK(history->is_member(bbb, on("2020-01-15")));
    CHECK_FALSE(history->is_member(bbb, on("2020-02-01")));
}

TEST_CASE("before the first observation membership is empty", "[gm-data][membership]") {
    // Not "the first observation carried backwards". The file says
    // nothing about 2019, and inventing an answer would put names in a
    // universe on the strength of a table written a year later.
    const TempCsv csv(kFixture);
    const auto history = MembershipHistory::load(csv.path());
    REQUIRE(history.has_value());
    CHECK(history->members_as_of(on("2019-12-31")).empty());
    CHECK_FALSE(history->observation_used(on("2019-12-31")).has_value());
    CHECK_FALSE(history->is_member(gm::TickerId{"AAA"}, on("2019-12-31")));
}

TEST_CASE("departed tickers are the ones a current snapshot cannot see",
          "[gm-data][membership]") {
    const TempCsv csv(kFixture);
    const auto history = MembershipHistory::load(csv.path());
    REQUIRE(history.has_value());

    CHECK(history->all_tickers().size() == 3);
    // Looking at one observation: BBB left after January, CCC arrived
    // in March, so only BBB is gone.
    const auto departed = history->departed_tickers(1);
    REQUIRE(departed.size() == 1);
    CHECK(departed[0].value() == "BBB");
}

TEST_CASE("one imperfectly parsed observation cannot retire a sitting member",
          "[gm-data][membership]") {
    // Reconstruction parses a rendered table whose markup changed over
    // sixteen years, and on the real file eleven names are missing from
    // exactly one observation while present either side. If "departed"
    // meant "absent from the final observation", every such name in the
    // LAST revision would be reported as having left the index -
    // AvalonBay and Campbell's both were, and both are still in it.
    const TempCsv csv(
        "observed_date,ticker\n"
        "2020-01-01,AAA\n2020-01-01,GONE\n2020-01-01,FLICKER\n"
        "2020-02-01,AAA\n2020-02-01,FLICKER\n"
        "2020-03-01,AAA\n2020-03-01,FLICKER\n"
        "2020-04-01,AAA\n");  // the FINAL parse is the one that missed FLICKER
    const auto history = MembershipHistory::load(csv.path());
    REQUIRE(history.has_value());

    const auto naive = history->departed_tickers(1);
    REQUIRE(naive.size() == 2);  // the false positive the default avoids

    const auto robust = history->departed_tickers(3);
    REQUIRE(robust.size() == 1);
    CHECK(robust[0].value() == "GONE");  // genuinely absent since January
}

TEST_CASE("a malformed membership file is an error, not an empty universe",
          "[gm-data][membership]") {
    // Each of these would otherwise read downstream as "the index had
    // no members that day", which is indistinguishable from a real
    // answer and would quietly empty the universe.
    SECTION("wrong header") {
        const TempCsv csv("date,symbol\n2020-01-01,AAA\n");
        CHECK_FALSE(MembershipHistory::load(csv.path()).has_value());
    }
    SECTION("header only") {
        const TempCsv csv("observed_date,ticker\n");
        CHECK_FALSE(MembershipHistory::load(csv.path()).has_value());
    }
    SECTION("empty file") {
        const TempCsv csv("");
        CHECK_FALSE(MembershipHistory::load(csv.path()).has_value());
    }
    SECTION("unparseable date") {
        const TempCsv csv("observed_date,ticker\n01/02/2020,AAA\n");
        CHECK_FALSE(MembershipHistory::load(csv.path()).has_value());
    }
    SECTION("empty ticker") {
        const TempCsv csv("observed_date,ticker\n2020-01-01,\n");
        CHECK_FALSE(MembershipHistory::load(csv.path()).has_value());
    }
    SECTION("missing file") {
        CHECK_FALSE(MembershipHistory::load("/nonexistent/membership.csv").has_value());
    }
}

TEST_CASE("membership lists are ordered the same way on every load",
          "[gm-data][membership]") {
    // ADR-003: a universe whose row order depends on hash iteration
    // produces artifacts that differ byte-for-byte between runs over
    // identical inputs.
    const TempCsv csv(
        "observed_date,ticker\n"
        "2020-01-01,ZZZ\n2020-01-01,AAA\n2020-01-01,MMM\n");
    for (int repeat = 0; repeat < 5; ++repeat) {
        const auto history = MembershipHistory::load(csv.path());
        REQUIRE(history.has_value());
        const auto members = history->members_as_of(on("2020-01-01"));
        REQUIRE(members.size() == 3);
        CHECK(members[0].value() == "AAA");
        CHECK(members[1].value() == "MMM");
        CHECK(members[2].value() == "ZZZ");
    }
}
