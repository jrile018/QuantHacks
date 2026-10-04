#include <gm-signals/excursion.hpp>

#include <cmath>

namespace gm::signals {

Result<std::vector<Excursion>> detect_excursions(const Eigen::VectorXd& z_scores, double entry_threshold,
                                                   double exit_threshold) {
    if (!(entry_threshold > 0.0)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "entry_threshold must be > 0"));
    }
    if (!(exit_threshold > 0.0)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "exit_threshold must be > 0"));
    }
    if (!(exit_threshold < entry_threshold)) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "exit_threshold must be strictly less than entry_threshold",
            "entry=" + std::to_string(entry_threshold) + ", exit=" + std::to_string(exit_threshold)));
    }

    std::vector<Excursion> result;
    const Eigen::Index n = z_scores.size();

    bool in_excursion = false;
    std::size_t start_index = 0;
    double peak_depth = 0.0;

    for (Eigen::Index t = 0; t < n; ++t) {
        double abs_z = std::abs(z_scores(t));

        if (!in_excursion) {
            if (abs_z > entry_threshold) {
                in_excursion = true;
                start_index = static_cast<std::size_t>(t);
                peak_depth = abs_z;
            }
            continue;
        }

        // in_excursion == true
        peak_depth = std::max(peak_depth, abs_z);
        if (abs_z <= exit_threshold) {
            result.push_back(Excursion{start_index, static_cast<std::size_t>(t), peak_depth, true});
            in_excursion = false;
        }
    }

    if (in_excursion) {
        // Series ended while still outside the band - censored, not
        // reverted. Reported with what data exists rather than
        // discarded: a censored excursion is real information (it
        // shows the series was still dislocated as of the last
        // observation), just not a reversion outcome to score.
        result.push_back(Excursion{start_index, static_cast<std::size_t>(n - 1), peak_depth, false});
    }

    return result;
}

} // namespace gm::signals
