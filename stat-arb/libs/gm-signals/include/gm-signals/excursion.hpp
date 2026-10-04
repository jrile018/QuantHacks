#pragma once

// Excursion detection over a z-score series (ADR §6.5/§13's "excursion
// tracking"): an episode where |z| exceeds an entry threshold, tracked
// until it reverts back under a (lower) exit threshold or the series
// ends while still outside ("censored"). This is the raw material the
// ADR-013 reversion study (gm-report) buckets by depth and conditions
// on earnings/8-K presence to answer "do excursions revert?"

#include <gm-core/error.hpp>

#include <Eigen/Dense>

#include <cstddef>
#include <vector>

namespace gm::signals {

struct Excursion {
    std::size_t start_index; // first index where |z| exceeded entry_threshold
    std::size_t end_index;   // index where |z| first fell back to <= exit_threshold
                              // (reverted), OR the series' last index (censored)
    double peak_depth;       // max |z| observed over [start_index, end_index]
    bool reverted;           // true iff the episode closed by crossing back under
                              // exit_threshold before the series ran out
};

/// `entry_threshold` must exceed `exit_threshold` (both > 0) - a
/// hysteresis band, matching ADR §6.5's z_entry=2.0/z_exit=0.5. Without
/// exit_threshold < entry_threshold, an excursion could close and
/// immediately reopen on the very next bar as |z| hovers near a single
/// shared threshold, fragmenting one real episode into many spurious
/// ones.
[[nodiscard]] Result<std::vector<Excursion>> detect_excursions(const Eigen::VectorXd& z_scores,
                                                                 double entry_threshold,
                                                                 double exit_threshold);

} // namespace gm::signals
