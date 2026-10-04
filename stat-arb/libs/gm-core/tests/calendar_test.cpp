// Reference tests for NyseCalendar (ADR-020 layer 1). Every date below
// is a specific, independently-verifiable historical fact - a real NYSE
// closure or open day - not a value derived from the code under test.

#include <gm-core/calendar.hpp>

#include <catch2/catch_test_macros.hpp>

using gm::Date;
using gm::NyseCalendar;

TEST_CASE("easter_sunday matches published Gregorian Easter dates", "[calendar]") {
    // Independently verifiable Easter Sundays, 2010-2026.
    CHECK(NyseCalendar::easter_sunday(2010) == Date{2010, 4, 4});
    CHECK(NyseCalendar::easter_sunday(2011) == Date{2011, 4, 24});
    CHECK(NyseCalendar::easter_sunday(2012) == Date{2012, 4, 8});
    CHECK(NyseCalendar::easter_sunday(2013) == Date{2013, 3, 31});
    CHECK(NyseCalendar::easter_sunday(2015) == Date{2015, 4, 5});
    CHECK(NyseCalendar::easter_sunday(2018) == Date{2018, 4, 1});
    CHECK(NyseCalendar::easter_sunday(2020) == Date{2020, 4, 12});
    CHECK(NyseCalendar::easter_sunday(2021) == Date{2021, 4, 4});
    CHECK(NyseCalendar::easter_sunday(2024) == Date{2024, 3, 31});
    CHECK(NyseCalendar::easter_sunday(2026) == Date{2026, 4, 5});
}

TEST_CASE("standard nth-weekday holidays land on known dates", "[calendar]") {
    NyseCalendar cal;

    // MLK Day: 3rd Monday of January.
    CHECK(cal.is_holiday(Date{2010, 1, 18}));
    CHECK(cal.is_holiday(Date{2021, 1, 18}));
    CHECK(cal.is_holiday(Date{2024, 1, 15}));

    // Presidents Day: 3rd Monday of February.
    CHECK(cal.is_holiday(Date{2011, 2, 21}));
    CHECK(cal.is_holiday(Date{2023, 2, 20}));

    // Memorial Day: last Monday of May.
    CHECK(cal.is_holiday(Date{2012, 5, 28}));
    CHECK(cal.is_holiday(Date{2020, 5, 25}));

    // Labor Day: 1st Monday of September.
    CHECK(cal.is_holiday(Date{2013, 9, 2}));
    CHECK(cal.is_holiday(Date{2019, 9, 2}));

    // Thanksgiving: 4th Thursday of November.
    CHECK(cal.is_holiday(Date{2013, 11, 28}));
    CHECK(cal.is_holiday(Date{2023, 11, 23}));

    // Good Friday = Easter Sunday - 2 days.
    CHECK(cal.is_holiday(Date{2020, 4, 10}));
    CHECK(cal.is_holiday(Date{2013, 3, 29}));
}

TEST_CASE("fixed-date holidays shift across weekends both directions", "[calendar]") {
    NyseCalendar cal;

    // Independence Day: 2015 (Sat) observed Friday Jul 3; 2021 (Sun)
    // observed Monday Jul 5; 2018 (Wed) unshifted.
    CHECK(cal.is_holiday(Date{2015, 7, 3}));
    CHECK_FALSE(cal.is_trading_day(Date{2015, 7, 3}));
    CHECK(cal.is_holiday(Date{2021, 7, 5}));
    CHECK(cal.is_holiday(Date{2018, 7, 4}));

    // Christmas: 2021 (Sat) observed Friday Dec 24; 2016 (Sun) observed
    // Monday Dec 26; 2013 (Wed) unshifted.
    CHECK(cal.is_holiday(Date{2021, 12, 24}));
    CHECK(cal.is_holiday(Date{2016, 12, 26}));
    CHECK(cal.is_holiday(Date{2013, 12, 25}));

    // Juneteenth: added starting 2022. 2021-06-18/21 must NOT be
    // holidays (the observance did not exist yet); 2022 (Sun) observed
    // Monday Jun 20; 2023 (Mon) unshifted Jun 19.
    CHECK_FALSE(cal.is_holiday(Date{2021, 6, 18}));
    CHECK_FALSE(cal.is_holiday(Date{2021, 6, 21}));
    CHECK(cal.is_holiday(Date{2022, 6, 20}));
    CHECK(cal.is_holiday(Date{2023, 6, 19}));
}

TEST_CASE("New Year's Day is the documented NYSE exception", "[calendar]") {
    NyseCalendar cal;

    // 2011 and 2022: Jan 1 fell on a Saturday. NYSE does NOT shift to the
    // preceding Friday (which would land in the prior year) - there is
    // no market closure at all that week beyond the ordinary weekend.
    CHECK_FALSE(cal.is_holiday(Date{2010, 12, 31}));
    CHECK(cal.is_trading_day(Date{2010, 12, 31}));
    CHECK_FALSE(cal.is_holiday(Date{2021, 12, 31}));
    CHECK(cal.is_trading_day(Date{2021, 12, 31}));

    // 2012, 2017, 2023: Jan 1 fell on a Sunday. NYSE DOES shift forward
    // to the following Monday.
    CHECK(cal.is_holiday(Date{2012, 1, 2}));
    CHECK(cal.is_holiday(Date{2017, 1, 2}));
    CHECK(cal.is_holiday(Date{2023, 1, 2}));

    // 2013, 2014, 2018: Jan 1 fell on a weekday - unshifted.
    CHECK(cal.is_holiday(Date{2013, 1, 1}));
    CHECK(cal.is_holiday(Date{2018, 1, 1}));
}

TEST_CASE("one-off closures are present and are not derivable from any rule", "[calendar]") {
    NyseCalendar cal;

    // Hurricane Sandy: NYSE closed both trading days.
    CHECK(cal.is_holiday(Date{2012, 10, 29}));
    CHECK(cal.is_holiday(Date{2012, 10, 30}));
    // The market was open the trading days immediately surrounding it.
    CHECK(cal.is_trading_day(Date{2012, 10, 26}));
    CHECK(cal.is_trading_day(Date{2012, 10, 31}));

    // National Day of Mourning, President George H.W. Bush.
    CHECK(cal.is_holiday(Date{2018, 12, 5}));
    CHECK(cal.is_trading_day(Date{2018, 12, 4}));
    CHECK(cal.is_trading_day(Date{2018, 12, 6}));
}

TEST_CASE("weekends are always non-trading regardless of holiday status", "[calendar]") {
    NyseCalendar cal;
    CHECK(cal.is_weekend(Date{2024, 6, 1}));   // Saturday
    CHECK(cal.is_weekend(Date{2024, 6, 2}));   // Sunday
    CHECK_FALSE(cal.is_trading_day(Date{2024, 6, 1}));
    CHECK_FALSE(cal.is_trading_day(Date{2024, 6, 2}));
}

TEST_CASE("next/prev trading day skip weekends and holidays together", "[calendar]") {
    NyseCalendar cal;

    // Wed Dec 24, 2014 was a normal trading day (Christmas Day 2014 fell
    // on Thursday, unshifted); the next trading day skips both the
    // Thursday holiday and the following weekend, landing on Monday.
    CHECK(cal.next_trading_day(Date{2014, 12, 24}) == Date{2014, 12, 26});

    // Friday before Labor Day 2020 (Sep 4) -> next trading day skips the
    // weekend and the Monday holiday, landing on Tuesday Sep 8.
    CHECK(cal.next_trading_day(Date{2020, 9, 4}) == Date{2020, 9, 8});
    CHECK(cal.prev_trading_day(Date{2020, 9, 8}) == Date{2020, 9, 4});
}

TEST_CASE("count_trading_days matches a hand-verified short window", "[calendar]") {
    NyseCalendar cal;
    // Mon Jan 2 - Fri Jan 6, 2023: Jan 2 is the observed New Year's Day
    // holiday (Jan 1 was a Sunday), so trading days are Jan 3-6 = 4 days.
    CHECK(cal.count_trading_days(Date{2023, 1, 2}, Date{2023, 1, 6}) == 4);
}

TEST_CASE("half-day: day after Thanksgiving is flagged", "[calendar]") {
    NyseCalendar cal;
    CHECK(cal.is_half_day(Date{2023, 11, 24}));  // day after Nov 23 Thanksgiving
    CHECK(cal.is_trading_day(Date{2023, 11, 24}));  // still a full trading day, just early close
}
