#include <gm-core/calendar.hpp>

#include <algorithm>
#include <stdexcept>

namespace gm {

namespace {

[[nodiscard]] Date nth_weekday_of_month(int year, unsigned month, date::weekday wd, unsigned index) {
    auto ymwd = date::year{year} / date::month{month} / wd[index];
    return Date{date::sys_days{ymwd}};
}

[[nodiscard]] Date last_weekday_of_month(int year, unsigned month, date::weekday wd) {
    auto ymwdl = date::year{year} / date::month{month} / wd[date::last];
    return Date{date::sys_days{ymwdl}};
}

/// NYSE weekend-shift rule for a fixed-date holiday: Saturday shifts to
/// the preceding Friday, Sunday shifts to the following Monday, weekdays
/// are unshifted. Applies to Independence Day, Christmas, and Juneteenth
/// (all confirmed against their actual NYSE observed dates in the
/// calendar reference tests).
[[nodiscard]] Date shift_weekend_both_ways(const Date& d) {
    auto wd = d.weekday();
    if (wd == date::Saturday) return d - date::days{1};
    if (wd == date::Sunday) return d + date::days{1};
    return d;
}

/// New Year's Day is a documented NYSE exception to the standard rule
/// above: it shifts Sunday->Monday but does NOT observe a Saturday
/// New Year's Day on the preceding Friday (which falls in the prior
/// year). Confirmed against actual NYSE closures: 2011 and 2022 both had
/// January 1st fall on a Saturday with no market closure that week.
[[nodiscard]] Date shift_new_years(const Date& d) {
    if (d.weekday() == date::Sunday) return d + date::days{1};
    return d;
}

} // namespace

NyseCalendar::NyseCalendar() {
    generate_holidays();
    add_one_off_closures();
    std::sort(holidays_.begin(), holidays_.end());
    holidays_.erase(std::unique(holidays_.begin(), holidays_.end()), holidays_.end());

    generate_half_days();
    std::sort(half_days_.begin(), half_days_.end());
    half_days_.erase(std::unique(half_days_.begin(), half_days_.end()), half_days_.end());
}

Date NyseCalendar::easter_sunday(int year) {
    // Meeus/Jones/Butcher Gregorian Easter algorithm. Published, widely
    // reference-tested; verified in calendar_test.cpp against known
    // Easter Sundays 2010-2026.
    const int a = year % 19;
    const int b = year / 100;
    const int c = year % 100;
    const int d = b / 4;
    const int e = b % 4;
    const int f = (b + 8) / 25;
    const int g = (b - f + 1) / 3;
    const int h = (19 * a + b - d - g + 15) % 30;
    const int i = c / 4;
    const int k = c % 4;
    const int l = (32 + 2 * e + 2 * i - h - k) % 7;
    const int m = (a + 11 * h + 22 * l) / 451;
    const int month = (h + l - 7 * m + 114) / 31;
    const int day = ((h + l - 7 * m + 114) % 31) + 1;
    return Date{year, static_cast<unsigned>(month), static_cast<unsigned>(day)};
}

void NyseCalendar::generate_holidays() {
    for (int year = kFirstYear; year <= kLastYear; ++year) {
        holidays_.push_back(shift_new_years(Date{year, 1, 1}));                          // New Year's Day
        holidays_.push_back(nth_weekday_of_month(year, 1, date::Monday, 3));             // MLK Day
        holidays_.push_back(nth_weekday_of_month(year, 2, date::Monday, 3));             // Washington's Birthday
        holidays_.push_back(easter_sunday(year) - date::days{2});                        // Good Friday
        holidays_.push_back(last_weekday_of_month(year, 5, date::Monday));               // Memorial Day
        if (year >= 2022) {
            holidays_.push_back(shift_weekend_both_ways(Date{year, 6, 19}));             // Juneteenth
        }
        holidays_.push_back(shift_weekend_both_ways(Date{year, 7, 4}));                  // Independence Day
        holidays_.push_back(nth_weekday_of_month(year, 9, date::Monday, 1));             // Labor Day
        holidays_.push_back(nth_weekday_of_month(year, 11, date::Thursday, 4));          // Thanksgiving
        holidays_.push_back(shift_weekend_both_ways(Date{year, 12, 25}));                // Christmas
    }
}

void NyseCalendar::add_one_off_closures() {
    // Hurricane Sandy - NYSE floor and electronic trading both closed.
    holidays_.push_back(Date{2012, 10, 29});
    holidays_.push_back(Date{2012, 10, 30});
    // National Day of Mourning, President George H.W. Bush.
    holidays_.push_back(Date{2018, 12, 5});
}

void NyseCalendar::generate_half_days() {
    for (int year = kFirstYear; year <= kLastYear; ++year) {
        // Day after Thanksgiving (Friday) is a standing NYSE early close.
        half_days_.push_back(nth_weekday_of_month(year, 11, date::Thursday, 4) + date::days{1});

        // July 3rd early close, when it is itself a business day (i.e.
        // not a weekend and not already the observed July 4th holiday).
        Date july3{year, 7, 3};
        bool july3_is_weekend = july3.weekday() == date::Saturday || july3.weekday() == date::Sunday;
        if (!july3_is_weekend && !is_holiday(july3)) {
            half_days_.push_back(july3);
        }
    }
}

bool NyseCalendar::is_weekend(const Date& d) const noexcept {
    auto wd = d.weekday();
    return wd == date::Saturday || wd == date::Sunday;
}

bool NyseCalendar::is_holiday(const Date& d) const noexcept {
    return std::binary_search(holidays_.begin(), holidays_.end(), d);
}

bool NyseCalendar::is_trading_day(const Date& d) const noexcept {
    return !is_weekend(d) && !is_holiday(d);
}

bool NyseCalendar::is_half_day(const Date& d) const noexcept {
    return std::binary_search(half_days_.begin(), half_days_.end(), d);
}

Date NyseCalendar::next_trading_day(const Date& d) const {
    Date cur = d + date::days{1};
    while (!is_trading_day(cur)) {
        cur = cur + date::days{1};
    }
    return cur;
}

Date NyseCalendar::prev_trading_day(const Date& d) const {
    Date cur = d - date::days{1};
    while (!is_trading_day(cur)) {
        cur = cur - date::days{1};
    }
    return cur;
}

Date NyseCalendar::add_trading_days(const Date& d, std::int64_t n) const {
    Date cur = d;
    if (n == 0) {
        while (!is_trading_day(cur)) {
            cur = cur + date::days{1};
        }
        return cur;
    }
    if (n > 0) {
        for (std::int64_t i = 0; i < n; ++i) {
            cur = next_trading_day(cur);
        }
    } else {
        for (std::int64_t i = 0; i < -n; ++i) {
            cur = prev_trading_day(cur);
        }
    }
    return cur;
}

std::int64_t NyseCalendar::count_trading_days(const Date& start, const Date& end) const {
    if (end < start) return 0;
    std::int64_t count = 0;
    Date cur = start;
    while (cur <= end) {
        if (is_trading_day(cur)) ++count;
        cur = cur + date::days{1};
    }
    return count;
}

std::vector<Date> NyseCalendar::trading_days_in_range(const Date& start, const Date& end) const {
    std::vector<Date> out;
    if (end < start) return out;
    Date cur = start;
    while (cur <= end) {
        if (is_trading_day(cur)) out.push_back(cur);
        cur = cur + date::days{1};
    }
    return out;
}

} // namespace gm
