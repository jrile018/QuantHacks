#pragma once

// Point-in-time S&P 500 membership (ADR-001, ADR §7.1). Loads the
// snapshotted current-constituent table (data/reference/sp500_constituents.csv)
// and answers "was this ticker a member on this date" for any ticker
// still in the index today. It CANNOT answer that for a ticker removed
// from the index before today - the survivorship gap ADR-016 already
// scoped and assigned to a later-phase paid data source. This class
// does not hide that limitation: is_member() is documented as
// one-directional, and the gap is a measurable, reportable quantity
// (coverage stats), not a silent wrong answer.

#include <gm-core/date.hpp>
#include <gm-core/error.hpp>
#include <gm-core/types.hpp>

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace gm::data {

struct ConstituentRecord {
    gm::TickerId ticker;
    std::string security_name;
    std::string gics_sector;
    std::string gics_sub_industry;
    std::string hq_location;
    gm::Date date_added;
    gm::Cik cik;
    std::optional<int> founded_year;  // absent for a small number of entries in the source table
};

class Universe {
public:
    /// Loads and parses the snapshot CSV written by the
    /// fetch-and-snapshot step described in ADR §7.1. Fails on missing
    /// file, malformed CSV, or an unparseable date/CIK field - never
    /// silently drops a row.
    [[nodiscard]] static Result<Universe> load_sp500_snapshot(const std::filesystem::path& csv_path);

    /// True iff `ticker` is a current S&P 500 constituent whose
    /// date_added is on or before `as_of`. See the class-level comment:
    /// this is a one-directional answer. A ticker that was removed from
    /// the index before `as_of` returns false here even if it was
    /// genuinely a member on that date - there is no data in this
    /// snapshot to know otherwise.
    [[nodiscard]] bool is_member(const gm::TickerId& ticker, const gm::Date& as_of) const noexcept;

    /// All tickers with date_added <= `as_of`, sorted by ticker symbol.
    [[nodiscard]] std::vector<gm::TickerId> members_as_of(const gm::Date& as_of) const;

    [[nodiscard]] Result<const ConstituentRecord*> find(const gm::TickerId& ticker) const;

    [[nodiscard]] const std::vector<ConstituentRecord>& all_records() const noexcept { return records_; }
    [[nodiscard]] std::size_t size() const noexcept { return records_.size(); }

private:
    std::vector<ConstituentRecord> records_;  // sorted by ticker for binary search
};

} // namespace gm::data
