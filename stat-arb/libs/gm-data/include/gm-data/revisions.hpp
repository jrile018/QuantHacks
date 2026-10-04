#pragma once

// ADR-015's retroactive-change screen: has the vendor rewritten history
// since the last run?
//
// Price vendors revise. A split is applied late, a bad tick corrected, a
// dividend restated - and yesterday's number for a date three years ago
// quietly becomes a different number today. Nothing errors. The next
// backtest simply produces a different answer from the last one, and there
// is no way to tell whether the strategy changed or the past did.
//
// That is corrosive in a specific way: it makes historical results
// unreproducible WITHOUT announcing itself, which is the same failure
// ADR-017's immutable runs exist to prevent on our own side of the line.
// This closes the loop on the vendor's side.
//
// Deliberately a library function over two Tables rather than a private
// helper inside gm-ingest. gm-ingest cannot run without the network, so
// anything living there can only be tested by fetching - and a detector
// that has never been shown to detect anything is a comment, not a check.

#include <gm-core/error.hpp>
#include <gm-io/table.hpp>

#include <cstdint>
#include <set>
#include <string>

namespace gm::data {

struct RevisionReport {
    /// Bars present in BOTH panels - the only ones a revision can be
    /// observed on.
    std::int64_t compared{};
    /// Bars present in both whose price differs.
    std::int64_t revised{};
    /// Bars only in the new panel. Normal: the panel extends daily.
    std::int64_t added{};
    /// Bars only in the old panel. Normal too: the universe turns over.
    /// Counted apart from revisions so neither is mistaken for the other.
    std::int64_t removed{};
    std::set<std::string> revised_tickers;
    /// "TICKER DATE: old -> new" for the first revision found, in sorted
    /// order so it is the same example on every run over the same data.
    std::string first_example;
};

/// Compares `current` against `prior` on (ticker, date) -> `value_column`.
///
/// The comparison is EXACT, not tolerant. A vendor re-adjusting for a
/// split changes the number outright rather than in the last bit; and a
/// value differing only in the last bit still makes a backtest
/// irreproducible, which is the thing being detected. A tolerance would
/// hide exactly the small revisions hardest to notice by eye.
[[nodiscard]] Result<RevisionReport> compare_price_panels(const gm::io::Table& prior,
                                                           const gm::io::Table& current,
                                                           const std::string& value_column);

} // namespace gm::data
