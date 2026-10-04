#pragma once

// A calendar date - no time-of-day, no timezone. Backed by
// date::sys_days (days since the Unix epoch, civil calendar). Strong
// type: a bare std::chrono::time_point or int day-count never crosses a
// module boundary (ADR-019). This is the type NyseCalendar (calendar.hpp)
// and every timestamped artifact column key on.

#include <gm-core/error.hpp>

#include <date/date.h>

#include <chrono>
#include <compare>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace gm {

class Date {
public:
    constexpr Date() = default;
    constexpr explicit Date(date::sys_days days) : days_(days) {}
    Date(int year, unsigned month, unsigned day)
        : days_(date::sys_days{date::year{year} / date::month{month} / date::day{day}}) {}

    /// Parses a strict "YYYY-MM-DD" date. Rejects anything else, including
    /// otherwise-valid but ambiguous formats - a data-quality boundary
    /// (ADR-015) should never guess.
    [[nodiscard]] static std::optional<Date> parse_iso(std::string_view yyyy_mm_dd);

    [[nodiscard]] std::string to_iso() const;

    [[nodiscard]] constexpr date::sys_days sys_days() const noexcept { return days_; }
    [[nodiscard]] date::year_month_day ymd() const noexcept { return date::year_month_day{days_}; }
    [[nodiscard]] date::weekday weekday() const noexcept { return date::weekday{days_}; }

    [[nodiscard]] int year() const noexcept { return int{ymd().year()}; }
    [[nodiscard]] unsigned month() const noexcept { return unsigned{ymd().month()}; }
    [[nodiscard]] unsigned day() const noexcept { return unsigned{ymd().day()}; }

    [[nodiscard]] constexpr Date operator+(date::days d) const { return Date{days_ + d}; }
    [[nodiscard]] constexpr Date operator-(date::days d) const { return Date{days_ - d}; }
    [[nodiscard]] constexpr date::days operator-(const Date& other) const { return days_ - other.days_; }

    friend constexpr auto operator<=>(const Date&, const Date&) = default;
    friend constexpr bool operator==(const Date&, const Date&) = default;

private:
    date::sys_days days_{};
};

} // namespace gm
