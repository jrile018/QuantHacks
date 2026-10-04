#pragma once

// The NYSE trading calendar. Referenced by ADR-010: "day-count bugs are
// the quietest way to corrupt every downstream number" - every rolling
// window, every lag, every alignment in this system goes through here.
//
// Design (see calendar.cpp for the rules, each with its own reference
// test in tests/calendar_test.cpp against known historical closures):
//   - Weekends are always non-trading.
//   - "Nth weekday" holidays (MLK, Presidents, Memorial, Labor,
//     Thanksgiving) never need a weekend-shift rule - they are defined
//     relative to a weekday already.
//   - Good Friday is computed from the Gregorian Easter algorithm.
//   - Fixed-date holidays (Independence Day, Christmas, Juneteenth)
//     shift Saturday->preceding Friday, Sunday->following Monday.
//   - New Year's Day is a documented NYSE exception: it shifts
//     Sunday->Monday but does NOT shift Saturday->the preceding Friday
//     (which would fall in the previous year).
//   - A short, explicit list of one-off closures (weather, mourning)
//     that no rule can generate.
//
// Full-day closures are generated and verified for [kFirstYear,
// kLastYear]. Half-days (early 1pm closes) are tracked on a best-effort
// basis only in this milestone - see the note on is_half_day().

#include <gm-core/date.hpp>

#include <cstdint>
#include <vector>

namespace gm {

class NyseCalendar {
public:
    static constexpr int kFirstYear = 2000;
    static constexpr int kLastYear = 2035;

    NyseCalendar();

    [[nodiscard]] bool is_weekend(const Date& d) const noexcept;
    [[nodiscard]] bool is_holiday(const Date& d) const noexcept;
    [[nodiscard]] bool is_trading_day(const Date& d) const noexcept;

    /// Best-effort only in M0: covers the day after Thanksgiving and the
    /// pre-Independence-Day early close when July 3rd is a business day.
    /// Does NOT yet model the Christmas Eve early-close edge cases.
    /// TODO(M1): complete against the official NYSE early-close schedule.
    [[nodiscard]] bool is_half_day(const Date& d) const noexcept;

    /// Smallest trading day strictly after `d`.
    [[nodiscard]] Date next_trading_day(const Date& d) const;
    /// Largest trading day strictly before `d`.
    [[nodiscard]] Date prev_trading_day(const Date& d) const;
    /// `d` shifted by `n` trading days (n may be negative or zero). If
    /// `d` itself is not a trading day, `n == 0` returns the next trading
    /// day at/after `d`.
    [[nodiscard]] Date add_trading_days(const Date& d, std::int64_t n) const;

    /// Count of trading days in the closed interval [start, end].
    [[nodiscard]] std::int64_t count_trading_days(const Date& start, const Date& end) const;

    /// All trading days in the closed interval [start, end], ascending.
    [[nodiscard]] std::vector<Date> trading_days_in_range(const Date& start, const Date& end) const;

    /// Easter Sunday (Gregorian) for a given year - exposed for testing;
    /// also used internally to derive Good Friday.
    [[nodiscard]] static Date easter_sunday(int year);

private:
    std::vector<Date> holidays_;   // sorted, deduplicated
    std::vector<Date> half_days_;  // sorted, deduplicated, best-effort

    void generate_holidays();
    void generate_half_days();
    void add_one_off_closures();
};

} // namespace gm
