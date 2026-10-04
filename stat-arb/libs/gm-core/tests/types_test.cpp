#include <gm-core/types.hpp>

#include <catch2/catch_test_macros.hpp>

#include <unordered_set>

using gm::Cik;
using gm::FrameIndex;
using gm::TickerId;

TEST_CASE("strong ids compare by value", "[types]") {
    CHECK(TickerId{"AAPL"} == TickerId{"AAPL"});
    CHECK(TickerId{"AAPL"} != TickerId{"MSFT"});
    CHECK(FrameIndex{5} < FrameIndex{10});
}

TEST_CASE("strong ids of different tags do not implicitly convert", "[types]") {
    // This is a compile-time property, not a runtime one: the following
    // would fail to compile if uncommented, which is the entire point of
    // StrongId (ADR-019). Left here as executable documentation.
    //
    //   TickerId t = FrameIndex{1};  // must not compile
    //
    TickerId t{"AAPL"};
    FrameIndex f{1};
    CHECK(t.value() == "AAPL");
    CHECK(f.value() == 1);
}

TEST_CASE("strong ids are hashable for use in unordered containers", "[types]") {
    std::unordered_set<TickerId> universe;
    universe.insert(TickerId{"AAPL"});
    universe.insert(TickerId{"MSFT"});
    universe.insert(TickerId{"AAPL"});  // duplicate
    CHECK(universe.size() == 2);
    CHECK(universe.contains(TickerId{"AAPL"}));
    CHECK_FALSE(universe.contains(TickerId{"GOOG"}));
}

TEST_CASE("Cik wraps an unsigned integer distinct from FrameIndex", "[types]") {
    Cik cik{320193};  // Apple Inc.'s actual SEC CIK, for realism
    CHECK(cik.value() == 320193);
}
