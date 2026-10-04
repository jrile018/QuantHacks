#include <gm-boundaries/kde.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace gm::boundaries {

namespace {

constexpr double kLog2Pi = 1.8378770664093453;  // ln(2*pi)
constexpr double kMinBandwidth = 1e-9;

double logsumexp(const std::vector<double>& log_values) {
    double max_val = *std::max_element(log_values.begin(), log_values.end());
    if (!std::isfinite(max_val)) return max_val;  // all -inf: sum is -inf too
    double sum = 0.0;
    for (double v : log_values) sum += std::exp(v - max_val);
    return max_val + std::log(sum);
}

/// log-density at `point` given `fit` - shared by fit_kde (self-scoring
/// every training point to determine the level) and kde_density (public
/// scoring API), so the two can never compute density differently.
double log_density_at(const KdeFit& fit, const Eigen::VectorXd& point) {
    const Eigen::Index n = fit.training_points.rows();
    const Eigen::Index k = fit.training_points.cols();

    double log_norm_const = -0.5 * static_cast<double>(k) * kLog2Pi;
    for (Eigen::Index j = 0; j < k; ++j) log_norm_const -= std::log(fit.bandwidth(j));

    std::vector<double> log_kernel(static_cast<std::size_t>(n));
    for (Eigen::Index i = 0; i < n; ++i) {
        double sum_sq = 0.0;
        for (Eigen::Index j = 0; j < k; ++j) {
            double u = (point(j) - fit.training_points(i, j)) / fit.bandwidth(j);
            sum_sq += u * u;
        }
        log_kernel[static_cast<std::size_t>(i)] = log_norm_const - 0.5 * sum_sq;
    }

    return logsumexp(log_kernel) - std::log(static_cast<double>(n));
}

} // namespace

Result<KdeFit> fit_kde(const Eigen::MatrixXd& points, double alpha) {
    const Eigen::Index n = points.rows();
    const Eigen::Index k = points.cols();

    if (k < 1) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "points has zero columns"));
    }
    if (n < 2) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "fit_kde requires at least 2 points"));
    }
    if (!(alpha > 0.0 && alpha < 1.0)) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "alpha must be in (0, 1)"));
    }

    // Scott's rule: h_j = std_j * N^(-1/(k+4)).
    Eigen::VectorXd mean = points.colwise().mean();
    Eigen::MatrixXd centered = points.rowwise() - mean.transpose();
    Eigen::VectorXd variance = centered.array().square().colwise().sum() / static_cast<double>(n - 1);

    double exponent = -1.0 / (static_cast<double>(k) + 4.0);
    double n_factor = std::pow(static_cast<double>(n), exponent);

    Eigen::VectorXd bandwidth(k);
    for (Eigen::Index j = 0; j < k; ++j) {
        double std_j = std::sqrt(std::max(variance(j), 0.0));
        bandwidth(j) = std::max(std_j * n_factor, kMinBandwidth);
    }

    KdeFit fit{points, bandwidth, 0.0, alpha};

    // Self-scoring every training point costs O(sample_size * N) (each
    // self-score is itself an O(N) density evaluation over the full
    // training set) - bounded via a deterministic stride, not a random
    // subsample, when N exceeds kde_max_level_sample_points(). See the
    // header comment for why this matters at real View B scale.
    const Eigen::Index sample_size =
        std::min(n, static_cast<Eigen::Index>(kde_max_level_sample_points()));
    // Ceiling division, not floor: floor(n/sample_size) as the stride
    // under-strides (a real bug caught by the M3 code review) - e.g.
    // n=756, sample_size=200 gives stride=756/200=3 (floor), and
    // striding by 3 actually visits ceil(756/3)=252 points, 26% over
    // the intended cap. Ceiling division (n+sample_size-1)/sample_size
    // gives stride=4 here, visiting ceil(756/4)=189 <= 200 points.
    const Eigen::Index stride = std::max<Eigen::Index>(1, (n + sample_size - 1) / sample_size);

    std::vector<double> sample_log_densities;
    sample_log_densities.reserve(static_cast<std::size_t>(sample_size));
    for (Eigen::Index i = 0; i < n; i += stride) {
        sample_log_densities.push_back(log_density_at(fit, points.row(i)));
    }
    std::sort(sample_log_densities.begin(), sample_log_densities.end());

    // Order-statistic threshold over the sample: the level below which
    // ~floor(alpha*sample_size) of the SAMPLED points fall, so ~(1-alpha)
    // of the training mass sits at or above `level` (ADR-011's "level
    // set containing (1-alpha) of training mass") - approximated from
    // the sample when N was too large to self-score exactly.
    auto idx = static_cast<std::size_t>(alpha * static_cast<double>(sample_log_densities.size()));
    idx = std::min(idx, sample_log_densities.size() - 1);
    fit.level = std::exp(sample_log_densities[idx]);

    return fit;
}

Result<double> kde_density(const KdeFit& fit, const Eigen::VectorXd& point) {
    if (point.size() != fit.training_points.cols()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "point dimension does not match fit dimension"));
    }
    return std::exp(log_density_at(fit, point));
}

Result<KdeScore> score_kde(const KdeFit& fit, const Eigen::VectorXd& point) {
    if (point.size() != fit.training_points.cols()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "point dimension does not match fit dimension"));
    }

    double log_density = log_density_at(fit, point);
    double density = std::exp(log_density);
    double depth = std::log(fit.level) - log_density;
    bool inside = depth <= 0.0;

    return KdeScore{density, log_density, depth, inside};
}

} // namespace gm::boundaries
