#pragma once

// Point-in-time index membership reconstructed from dated observations
// (tools/sp500_membership_history.py), including names that have since
// LEFT the index.
//
// This is the other half of what universe.hpp can do. That class reads
// the current-constituent snapshot and says so plainly: its answer is
// one-directional, because a name removed before today simply is not in
// the file. ADR-016 assigned that gap to a paid point-in-time vendor.
// The gap is real; the assignment was wrong. Wikipedia's article on the
// index keeps every revision back past 2010, and each revision carries
// the constituent table as it stood that day, so the membership half of
// survivorship is recoverable from a free source.
//
// The input is a long CSV of (observed_date, ticker) pairs: one row per
// ticker per sampled revision. Sampling is monthly, which is the honest
// limitation to state - a join or a removal can be misdated by up to a
// month. That is a much smaller error than a name being absent from
// sixteen years of history, and it is visible rather than implied: the
// observation dates are in the file.
//
// What this does NOT fix is PRICES for delisted names. Knowing that
// PXD belonged in the 2015 universe does not produce its price series.
// What it does give is the honest denominator, so the remaining gap is
// a measured number instead of an unknown.

#include <gm-core/date.hpp>
#include <gm-core/error.hpp>
#include <gm-core/types.hpp>

#include <filesystem>
#include <optional>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace gm::data {

class MembershipHistory {
public:
    /// Loads the observation CSV. Fails on a missing file, a missing or
    /// misnamed header, an unparseable date, or an empty file - never
    /// returns a silently empty history, which downstream would read as
    /// "the index had no members".
    [[nodiscard]] static Result<MembershipHistory> load(const std::filesystem::path& csv_path);

    /// The members recorded by the newest observation at or before
    /// `as_of`, sorted by symbol.
    ///
    /// Strictly backwards. Snapping forward to a nearer observation
    /// would import the composition of a revision that had not been
    /// written yet - look-ahead, and of the worst kind, since the very
    /// names it would add are the ones about to be added for having
    /// done well. Before the first observation the answer is empty.
    [[nodiscard]] std::vector<gm::TickerId> members_as_of(const gm::Date& as_of) const;

    /// True iff `ticker` appears in that same observation.
    [[nodiscard]] bool is_member(const gm::TickerId& ticker, const gm::Date& as_of) const;

    /// The observation actually used by members_as_of(`as_of`), so a
    /// caller can report how stale its answer is rather than guess.
    [[nodiscard]] std::optional<gm::Date> observation_used(const gm::Date& as_of) const;

    /// Every ticker seen in any observation, sorted.
    [[nodiscard]] std::vector<gm::TickerId> all_tickers() const;

    /// Tickers seen at some point but absent from the last
    /// `recent_observations` observations: the survivorship gap a
    /// current-constituents snapshot cannot see.
    ///
    /// Not "absent from the final observation". Parsing a rendered
    /// table across sixteen years of markup is not perfect, and on the
    /// real file eleven names are missing from exactly one observation
    /// while present in the ones either side. Measured against the
    /// final observation alone, any name the FINAL revision happened to
    /// miss is reported as departed - AvalonBay and Campbell's both
    /// were, and both are still in the index. Taking the union of the
    /// last few observations costs nothing and removes that whole class
    /// of false positive; on the real file the count moves 416 -> 413.
    [[nodiscard]] std::vector<gm::TickerId> departed_tickers(
        std::size_t recent_observations = 3) const;

    [[nodiscard]] const std::vector<gm::Date>& observation_dates() const noexcept { return dates_; }
    [[nodiscard]] std::size_t num_observations() const noexcept { return dates_.size(); }

private:
    // std::map/std::set, not the unordered forms: every list this class
    // hands out is ordered, and ordering that comes from the container
    // cannot drift between runs (ADR-003).
    std::map<gm::Date, std::set<std::string>> by_date_;
    std::vector<gm::Date> dates_;  // sorted, the keys of by_date_
};

} // namespace gm::data
