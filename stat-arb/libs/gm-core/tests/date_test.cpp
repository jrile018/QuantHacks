#include <gm-core/date.hpp>

#include <catch2/catch_test_macros.hpp>

using gm::Date;

TEST_CASE("parse_iso accepts strict well-formed dates", "[date]") {
    auto d = Date::parse_iso("2024-03-05");
    REQUIRE(d.has_value());
    CHECK(d->year() == 2024);
    CHECK(d->month() == 3);
    CHECK(d->day() == 5);
}

TEST_CASE("parse_iso rejects malformed input rather than guessing", "[date]") {
    CHECK_FALSE(Date::parse_iso("2024/03/05").has_value());   // wrong separator
    CHECK_FALSE(Date::parse_iso("03-05-2024").has_value());   // wrong field order
    CHECK_FALSE(Date::parse_iso("2024-3-5").has_value());     // not zero-padded
    CHECK_FALSE(Date::parse_iso("2024-13-01").has_value());   // month 13
    CHECK_FALSE(Date::parse_iso("2024-02-30").has_value());   // Feb 30 does not exist
    CHECK_FALSE(Date::parse_iso("2023-02-29").has_value());   // 2023 is not a leap year
    CHECK_FALSE(Date::parse_iso("").has_value());
    CHECK_FALSE(Date::parse_iso("2024-02-2x").has_value());
}

TEST_CASE("parse_iso accepts leap day only in leap years", "[date]") {
    CHECK(Date::parse_iso("2024-02-29").has_value());   // 2024 is a leap year
    CHECK_FALSE(Date::parse_iso("2100-02-29").has_value());  // divisible by 100, not 400
    CHECK(Date::parse_iso("2000-02-29").has_value());   // divisible by 400
}

TEST_CASE("to_iso round-trips through parse_iso", "[date]") {
    for (const char* s : {"2010-01-01", "2019-12-31", "2024-02-29", "2026-08-29"}) {
        auto d = Date::parse_iso(s);
        REQUIRE(d.has_value());
        CHECK(d->to_iso() == s);
    }
}

TEST_CASE("ordering is chronological", "[date]") {
    CHECK(Date{2024, 1, 1} < Date{2024, 1, 2});
    CHECK(Date{2023, 12, 31} < Date{2024, 1, 1});
    CHECK(Date{2024, 1, 1} == Date{2024, 1, 1});
}

TEST_CASE("weekday() matches known days of the week", "[date]") {
    // 2024-01-01 was a Monday; 2026-08-29 (the ADR date) was a Saturday.
    CHECK(Date{2024, 1, 1}.weekday() == date::Monday);
    CHECK(Date{2026, 8, 29}.weekday() == date::Saturday);
}
