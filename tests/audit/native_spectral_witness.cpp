// Tiny audit witnesses; links the production geometry source without modifying it.
// This checks algebraic behavior, not investment performance or exact population recovery.
#include <gm-geometry/shrinkage.hpp>
#include <gm-geometry/rie.hpp>
#include <gm-geometry/rmt.hpp>
#include <gm-signals/ou_fit.hpp>
#include <Eigen/Eigenvalues>
#include <cmath>
#include <iomanip>
#include <iostream>

int main() {
    std::cout << std::setprecision(17);
    Eigen::MatrixXd x(3, 2);
    x << 1, 2, 2, 1, 3, 6;
    auto lw = gm::geometry::ledoit_wolf_shrink_correlation(x);
    if (!lw) { std::cerr << lw.error().to_string(); return 1; }
    Eigen::MatrixXd x2(2, 2);
    x2 << -1, -1, 1, 1;
    auto lw2 = gm::geometry::ledoit_wolf_shrink_correlation(x2);
    if (!lw2) { std::cerr << lw2.error().to_string(); return 2; }
    Eigen::MatrixXd c(4, 4);
    c << 1, 0, -1, 0,
         0, 1, 0, -1,
         -1, 0, 1, 0,
         0, -1, 0, 1;
    const double q = 4.0 / 3.0;
    auto rie = gm::geometry::rie_clean_correlation(c, q);
    auto mp = gm::geometry::mp_denoise(c, q);
    if (!rie) { std::cerr << rie.error().to_string(); return 3; }
    if (!mp) { std::cerr << mp.error().to_string(); return 4; }
    int cleaned_rank = 0;
    for (int i = 0; i < 4; ++i)
        cleaned_rank += rie->cleaned_eigenvalues(i) > 1e-10;
    std::cout << "{\"lw\":{\"delta\":" << lw->shrinkage_intensity
              << ",\"actual_correlation\":" << lw->correlation(0,1)
              << ",\"expected_normalized_correlation\":" << 5.0/(6.0*std::sqrt(7.0))
              << "},\"lw_zero_delta\":{\"delta\":" << lw2->shrinkage_intensity
              << ",\"actual_correlation\":" << lw2->correlation(0,1)
              << ",\"expected_correlation\":1},\"mp\":{\"q\":" << q
              << ",\"actual_lambda_minus\":" << mp->lambda_minus
              << ",\"expected_continuous_lower_edge\":" << std::pow(1.0-std::sqrt(q), 2)
              << ",\"asymptotic_zero_atom_mass\":" << 1.0-1.0/q
              << "},\"rie\":{\"cleaned_rank_tolerance_1e_10\":" << cleaned_rank
              << ",\"input_rank\":2,\"max_change\":"
              << (rie->cleaned_correlation-c).cwiseAbs().maxCoeff()
              << ",\"cleaned_eigenvalues\":[";
    for (int i = 0; i < 4; ++i) {
        if (i) std::cout << ',';
        std::cout << rie->cleaned_eigenvalues(i);
    }
    Eigen::VectorXd spread(60);
    for (int i = 0; i < 60; ++i) spread(i) = std::pow(0.99, i);
    const auto ou_days = gm::signals::fit_ou(spread, 1.0);
    const auto ou_years = gm::signals::fit_ou(spread, 1.0/252.0);
    std::cout << "]},\"ou_dt_units\":{\"dt1_accepted\":"
              << (ou_days ? "true" : "false")
              << ",\"dt_1_over_252_accepted\":" << (ou_years ? "true" : "false")
              << ",\"analytic_half_life_days\":" << -std::log(2.0)/std::log(0.99)
              << ",\"sample_duration_days\":59,\"sample_duration_years\":" << 59.0/252.0
              << ",\"actual_half_life_years\":" << (ou_years ? ou_years->half_life : -1)
              << "}}\n";
    return 0;
}
