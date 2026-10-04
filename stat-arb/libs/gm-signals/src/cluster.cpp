#include <gm-signals/cluster.hpp>

#include <Eigen/Dense>

#include <cmath>
#include <map>
#include <set>

namespace gm::signals {

namespace {

/// The regression is `value ~ 1 + treated`, so the design matrix has
/// exactly two columns and the coefficient on `treated` IS the
/// difference in means. Writing it as a regression rather than as two
/// sample means is what makes the cluster-robust sandwich available;
/// the point estimate is identical either way.
constexpr int kParams = 2;

/// One cluster-robust variance for a single clustering dimension:
///
///     V = (X'X)^-1 [ sum_g (X_g' u_g)(X_g' u_g)' ] (X'X)^-1 * c
///
/// with the usual finite-sample correction
/// c = G/(G-1) * (N-1)/(N-K).
Eigen::Matrix2d one_way_variance(const Eigen::Matrix2d& xtx_inv,
                                  const std::map<std::string, Eigen::Vector2d>& score_by_cluster,
                                  std::int64_t n, std::int64_t g) {
    Eigen::Matrix2d meat = Eigen::Matrix2d::Zero();
    for (const auto& [key, s] : score_by_cluster) {
        (void)key;
        meat += s * s.transpose();
    }
    double correction = 1.0;
    if (g > 1 && n > kParams) {
        correction = (static_cast<double>(g) / static_cast<double>(g - 1)) *
                     (static_cast<double>(n - 1) / static_cast<double>(n - kParams));
    }
    return xtx_inv * meat * xtx_inv * correction;
}

}  // namespace

Result<DifferenceEstimate> clustered_difference(const std::vector<ClusterObservation>& obs) {
    const std::int64_t n = static_cast<std::int64_t>(obs.size());
    if (n < 3) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "clustered difference needs at least three observations",
                                               std::to_string(n) + " supplied"));
    }

    DifferenceEstimate est;
    double sum_t = 0.0, sum_c = 0.0;
    for (const auto& o : obs) {
        if (o.treated) {
            ++est.n_treated;
            sum_t += o.value;
        } else {
            ++est.n_control;
            sum_c += o.value;
        }
    }
    if (est.n_treated == 0 || est.n_control == 0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "clustered difference needs both a treated and a control arm",
                                               "treated=" + std::to_string(est.n_treated) +
                                                   " control=" + std::to_string(est.n_control)));
    }

    est.treated_mean = sum_t / static_cast<double>(est.n_treated);
    est.control_mean = sum_c / static_cast<double>(est.n_control);
    est.difference = est.treated_mean - est.control_mean;

    // (X'X) for X = [1, treated] is [[N, T], [T, T]]; its inverse is
    // closed-form and never needs a decomposition.
    const double N = static_cast<double>(n);
    const double T = static_cast<double>(est.n_treated);
    Eigen::Matrix2d xtx;
    xtx << N, T, T, T;
    const double det = N * T - T * T;  // = T * (N - T), positive since both arms are non-empty
    Eigen::Matrix2d xtx_inv;
    xtx_inv << T, -T, -T, N;
    xtx_inv /= det;

    // Residual from the unit's own arm mean - which is exactly the OLS
    // residual for this design.
    double ssr = 0.0;
    // std::map, not unordered: cluster keys accumulate in a fixed order,
    // so the summed meat matrix is bit-identical across runs (ADR-003).
    std::map<std::string, Eigen::Vector2d> score_a, score_b, score_ab;
    std::set<std::string> keys_a, keys_b, keys_ab;

    for (const auto& o : obs) {
        const double fitted = o.treated ? est.treated_mean : est.control_mean;
        const double u = o.value - fitted;
        ssr += u * u;
        Eigen::Vector2d x;
        x << 1.0, o.treated ? 1.0 : 0.0;
        const Eigen::Vector2d contrib = x * u;

        const std::string ab = o.cluster_a + "\x1f" + o.cluster_b;
        auto add = [&contrib](std::map<std::string, Eigen::Vector2d>& m, const std::string& key) {
            auto it = m.find(key);
            if (it == m.end()) {
                m.emplace(key, contrib);
            } else {
                it->second += contrib;
            }
        };
        add(score_a, o.cluster_a);
        add(score_b, o.cluster_b);
        add(score_ab, ab);
        keys_a.insert(o.cluster_a);
        keys_b.insert(o.cluster_b);
        keys_ab.insert(ab);
    }

    est.clusters_a = static_cast<std::int64_t>(keys_a.size());
    est.clusters_b = static_cast<std::int64_t>(keys_b.size());
    est.clusters_ab = static_cast<std::int64_t>(keys_ab.size());
    est.min_clusters = std::min(est.clusters_a, est.clusters_b);

    // Naive (homoskedastic) variance of the same coefficient, kept for
    // the design-effect ratio.
    const double sigma2 = ssr / static_cast<double>(n - kParams);
    const Eigen::Matrix2d v_iid = xtx_inv * sigma2;
    const double var_iid = v_iid(1, 1);
    est.se_iid = var_iid > 0.0 ? std::sqrt(var_iid) : 0.0;

    const Eigen::Matrix2d va = one_way_variance(xtx_inv, score_a, n, est.clusters_a);
    const Eigen::Matrix2d vb = one_way_variance(xtx_inv, score_b, n, est.clusters_b);
    const Eigen::Matrix2d vab = one_way_variance(xtx_inv, score_ab, n, est.clusters_ab);

    double var_clustered = va(1, 1) + vb(1, 1) - vab(1, 1);
    if (!(var_clustered > 0.0)) {
        // Documented failure mode of the two-way estimator: the
        // subtraction can overshoot. Falling back to the larger one-way
        // variance is the standard conservative repair, and it is
        // flagged rather than silently substituted.
        est.two_way_variance_adjusted = true;
        var_clustered = std::max(va(1, 1), vb(1, 1));
    }
    est.se_clustered = var_clustered > 0.0 ? std::sqrt(var_clustered) : 0.0;

    est.t_statistic = est.se_clustered > 0.0 ? est.difference / est.se_clustered : 0.0;
    // Normal critical value; see the header and BLOCKED.md entry 10 for
    // why, and why min_clusters is reported next to it.
    constexpr double kZ95 = 1.959963984540054;
    est.ci_low = est.difference - kZ95 * est.se_clustered;
    est.ci_high = est.difference + kZ95 * est.se_clustered;

    est.design_effect = var_iid > 0.0 ? var_clustered / var_iid : 0.0;
    est.effective_n = est.design_effect > 0.0 ? N / est.design_effect : 0.0;

    return est;
}

}  // namespace gm::signals
