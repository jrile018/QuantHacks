// ADR-020 layer 1: FastMCD against a published Rousseeuw reference example.
//
// WHY THIS FILE EXISTS
// --------------------
// ADR-020 requires every in-house numeric routine to be validated against
// published or analytically-derived answers, and names "FastMCD against
// the published Rousseeuw examples" specifically. That requirement went
// unmet through three rounds of work on this estimator. It was left
// unmet deliberately rather than satisfied with numbers produced by this
// implementation, which would only have proved the code agrees with
// itself - the exact circularity that a previous revision of
// fastmcd.cpp was corrected for.
//
// THE REFERENCE
// -------------
// The Hawkins-Bradu-Kass artificial data (Hawkins, D.M., Bradu, D. and
// Kass, G.V. (1984), "Location of Several Outliers in Multiple
// Regression Data Using Elemental Sets", Technometrics 26, 197-208), the
// standard worked example for MCD in Rousseeuw & Leroy (1987) and in
// Rousseeuw & Van Driessen (1999), the paper this implementation follows.
//
// n = 75 points in p = 3 dimensions (the three explanatory variables;
// the response column Y is not part of the MCD example - the canonical
// call is covMcd(hbk[, 1:3])). Fourteen outliers were planted: cases
// 1-10 as bad leverage points and 11-14 as good leverage points. All
// fourteen are outlying in the 3-dimensional x-space this test fits.
//
// The published claim, quoted from the robustbase reference manual entry
// for this dataset: "Only observations 12, 13 and 14 appear as outliers
// when using classical methods, but can be easily unmasked using robust
// distances". The dataset is a textbook demonstration of the MASKING
// effect - a cluster of outliers large enough to drag the classical mean
// and covariance toward itself, so that its own members then look
// unremarkable.
//
// PROVENANCE OF THE 225 NUMBERS BELOW
// -----------------------------------
// Retrieved from two fully independent public sources and compared
// programmatically before being written here:
//   A. https://vincentarelbundock.github.io/Rdatasets/csv/robustbase/hbk.csv
//      (the Rdatasets mirror of R's robustbase package)
//   B. http://parker.ad.siu.edu/Olive/hbk.txt
//      (D.J. Olive's dataset collection, which carries its own citation
//      to Hawkins, Bradu & Kass 1984)
// All 75 rows x 5 columns agreed exactly, so the table is not a
// transcription of any single mirror. The literals were emitted by a
// script from the CSV rather than typed, because a hand-copied fixture
// that quietly disagrees with the published data would produce a test
// that passes while validating nothing.
//
// WHAT IS ASSERTED, AND WHAT IS ONLY MEASURED
// -------------------------------------------
// Asserted as the PUBLISHED result: the MCD robust distances separate
// exactly observations 1-14 from the other 61, at the standard
// chi-squared_{3, 0.975} cutoff.
//
// Asserted as a DISCRIMINATION CONTROL, measured here and labelled as
// measured rather than published: the classical Mahalanobis distances
// from the full-sample mean and covariance flag only 2 of those 14
// (observations 12 and 14; observation 13 sits at 2.66 against a 3.06
// cutoff). Twelve of the fourteen planted outliers hide, and three of
// them - 1, 2 and 8, at 1.92, 1.86 and 1.92 - look MORE central than the
// most extreme genuinely clean point in the dataset (observation 53, at
// 2.21). This half of the test is what makes the first half worth
// having: it establishes that a non-robust estimator FAILS here, so the
// robust assertion is not something any covariance estimate would pass.
//
// The robustbase sentence says "12, 13 and 14" for classical methods,
// while the measurement here gives 12 and 14 at this particular cutoff.
// That sentence is not specific about which classical procedure it means
// (least-squares regression diagnostics on Y and Mahalanobis distances
// in x-space are different computations), so this file does not assert
// the exact classical set. It asserts the masking, which is the claim
// the dataset was constructed to demonstrate and which the measurement
// supports strongly either way.
//
// WHAT MUTATION TESTING SHOWED THIS TEST DOES AND DOES NOT CATCH
// ---------------------------------------------------------------
// Verified by reintroducing each defect into fastmcd.cpp and rebuilding,
// because a regression test nobody has seen fail is a claim, not a test:
//
//  CAUGHT - h set to n, which removes the robustness entirely. The
//    flagged set becomes {1-14, 30, 42, 53, 60, 75} and the separation
//    margin collapses from 7.2x the cutoff to 1.01x. Both assertions
//    fail. This is the mutation that matters here: it is the one that
//    turns MCD back into the classical estimator the published example
//    exists to discredit.
//
//  NOT CAUGHT - selecting the MAXIMUM-determinant candidate instead of
//    the minimum. On this dataset every C-step trial converges to the
//    same optimum, so minimum and maximum are the same object and no
//    selection rule can be distinguished. That defect is pinned by
//    "FastMCD returns the minimum-determinant candidate, not the
//    maximum" in fastmcd_test.cpp, on a fixture built specifically to
//    make the trials diverge. Recorded here so this file is not
//    mistaken for broader coverage than it has.
//
//  NOT CAUGHT - forcing the Ledoit-Wolf intensity to 1.0, which replaces
//    the covariance with a scaled identity and discards all shape
//    information. HBK's clean core is close enough to spherical, and its
//    outliers far enough away, that a shape-free estimate still
//    separates the two groups. Finding that this passed - along with all
//    22 other test cases in the suite at the time - is what prompted
//    "FastMCD recovers the SHAPE of the clean data, not just its center"
//    in fastmcd_test.cpp, which does catch it.
//
// No location or covariance values are pinned. Published numeric MCD
// estimates for this dataset could not be obtained from a citable
// source, and inventing a tolerance around this implementation's own
// output would restore exactly the circularity this file exists to
// avoid. The flagged SET is the published result, and it is a far
// sharper assertion than a tolerance: it is an exact equality over a
// 75-element partition.

#include <gm-boundaries/fastmcd.hpp>

#include <catch2/catch_test_macros.hpp>

#include <Eigen/Dense>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <random>
#include <set>
#include <string>
#include <vector>

using gm::boundaries::fit_fastmcd;
using gm::boundaries::score_fastmcd;

namespace {

// Hawkins-Bradu-Kass, columns X1 X2 X3, observations 1-75 in published
// order. Observations 1-14 are the planted outliers.
constexpr double kHbk[75][3] = {
    {10.1, 19.6, 28.3},  // 1
    {9.5, 20.5, 28.9},  // 2
    {10.7, 20.2, 31.0},  // 3
    {9.9, 21.5, 31.7},  // 4
    {10.3, 21.1, 31.1},  // 5
    {10.8, 20.4, 29.2},  // 6
    {10.5, 20.9, 29.1},  // 7
    {9.9, 19.6, 28.8},  // 8
    {9.7, 20.7, 31.0},  // 9
    {9.3, 19.7, 30.3},  // 10
    {11.0, 24.0, 35.0},  // 11
    {12.0, 23.0, 37.0},  // 12
    {12.0, 26.0, 34.0},  // 13
    {11.0, 34.0, 34.0},  // 14
    {3.4, 2.9, 2.1},
    {3.1, 2.2, 0.3},
    {0.0, 1.6, 0.2},
    {2.3, 1.6, 2.0},
    {0.8, 2.9, 1.6},
    {3.1, 3.4, 2.2},  // 20
    {2.6, 2.2, 1.9},
    {0.4, 3.2, 1.9},
    {2.0, 2.3, 0.8},
    {1.3, 2.3, 0.5},
    {1.0, 0.0, 0.4},
    {0.9, 3.3, 2.5},
    {3.3, 2.5, 2.9},
    {1.8, 0.8, 2.0},
    {1.2, 0.9, 0.8},
    {1.2, 0.7, 3.4},  // 30
    {3.1, 1.4, 1.0},
    {0.5, 2.4, 0.3},
    {1.5, 3.1, 1.5},
    {0.4, 0.0, 0.7},
    {3.1, 2.4, 3.0},
    {1.1, 2.2, 2.7},
    {0.1, 3.0, 2.6},
    {1.5, 1.2, 0.2},
    {2.1, 0.0, 1.2},
    {0.5, 2.0, 1.2},  // 40
    {3.4, 1.6, 2.9},
    {0.3, 1.0, 2.7},
    {0.1, 3.3, 0.9},
    {1.8, 0.5, 3.2},
    {1.9, 0.1, 0.6},
    {1.8, 0.5, 3.0},
    {3.0, 0.1, 0.8},
    {3.1, 1.6, 3.0},
    {3.1, 2.5, 1.9},
    {2.1, 2.8, 2.9},  // 50
    {2.3, 1.5, 0.4},
    {3.3, 0.6, 1.2},
    {0.3, 0.4, 3.3},
    {1.1, 3.0, 0.3},
    {0.5, 2.4, 0.9},
    {1.8, 3.2, 0.9},
    {1.8, 0.7, 0.7},
    {2.4, 3.4, 1.5},
    {1.6, 2.1, 3.0},
    {0.3, 1.5, 3.3},  // 60
    {0.4, 3.4, 3.0},
    {0.9, 0.1, 0.3},
    {1.1, 2.7, 0.2},
    {2.8, 3.0, 2.9},
    {2.0, 0.7, 2.7},
    {0.2, 1.8, 0.8},
    {1.6, 2.0, 1.2},
    {0.1, 0.0, 1.1},
    {2.0, 0.6, 0.3},
    {1.0, 2.2, 2.9},  // 70
    {2.2, 2.5, 2.3},
    {0.6, 2.0, 1.5},
    {0.3, 1.7, 2.2},
    {0.0, 2.2, 1.6},
    {0.3, 0.4, 2.6},
};

constexpr int kN = 75;
constexpr int kP = 3;
// chi-squared_{3, 0.975}, the conventional robust-distance cutoff for
// this example. Passed to score_fastmcd as its exceedance probability.
constexpr double kAlpha = 0.025;

Eigen::MatrixXd hbk_matrix() {
    Eigen::MatrixXd points(kN, kP);
    for (int i = 0; i < kN; ++i) {
        for (int k = 0; k < kP; ++k) points(i, k) = kHbk[i][k];
    }
    return points;
}

// The published answer: the first fourteen observations, 1-based.
std::set<int> published_outliers() {
    std::set<int> s;
    for (int i = 1; i <= 14; ++i) s.insert(i);
    return s;
}

// Fits `points` (whose row r holds original observation `origin[r]`, 0-based)
// and returns the 1-based ORIGINAL observation numbers scored outside.
std::set<int> flagged_originals(const Eigen::MatrixXd& points, const std::vector<int>& origin) {
    std::set<int> out;
    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    for (int i = 0; i < static_cast<int>(points.rows()); ++i) {
        auto sc = score_fastmcd(*fit, points.row(i).transpose(), kAlpha);
        REQUIRE(sc.has_value());
        if (!sc->inside) out.insert(origin[static_cast<std::size_t>(i)] + 1);
    }
    return out;
}

std::string to_string(const std::set<int>& s) {
    std::string out;
    for (int v : s) out += (out.empty() ? "" : " ") + std::to_string(v);
    return out.empty() ? "(none)" : out;
}

} // namespace

TEST_CASE("FastMCD unmasks all 14 planted outliers in the Hawkins-Bradu-Kass data",
          "[fastmcd][reference]") {
    const Eigen::MatrixXd points = hbk_matrix();
    std::vector<int> identity(kN);
    std::iota(identity.begin(), identity.end(), 0);

    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    CHECK(fit->degrees_of_freedom == kP);

    std::set<int> flagged;
    double smallest_flagged = std::numeric_limits<double>::infinity();
    double largest_clean = 0.0;
    double cutoff = 0.0;
    for (int i = 0; i < kN; ++i) {
        auto sc = score_fastmcd(*fit, points.row(i).transpose(), kAlpha);
        REQUIRE(sc.has_value());
        cutoff = sc->critical_distance;
        if (sc->inside) {
            largest_clean = std::max(largest_clean, sc->distance);
        } else {
            flagged.insert(i + 1);
            smallest_flagged = std::min(smallest_flagged, sc->distance);
        }
    }

    INFO("flagged = " << to_string(flagged));
    INFO("cutoff distance = " << cutoff << ", smallest flagged = " << smallest_flagged
                              << ", largest unflagged = " << largest_clean);
    CHECK(flagged == published_outliers());

    // The published result is not a marginal call. The two groups are
    // separated by an order of magnitude, so this assertion does not
    // depend on the exact cutoff and will not flicker across compilers.
    CHECK(smallest_flagged > 5.0 * cutoff);
    CHECK(largest_clean < cutoff);
}

TEST_CASE("Classical Mahalanobis distances are masked on the same data, so the robust "
          "reference test discriminates",
          "[fastmcd][reference]") {
    // Without this, the test above would only show that SOME estimator
    // flags the planted outliers. This shows the non-robust one does not,
    // which is the whole content of the published example.
    const Eigen::MatrixXd points = hbk_matrix();

    Eigen::VectorXd mean = points.colwise().mean();
    Eigen::MatrixXd centered = points.rowwise() - mean.transpose();
    Eigen::MatrixXd cov = (centered.transpose() * centered) / static_cast<double>(kN - 1);
    Eigen::MatrixXd inv = cov.inverse();

    // Same cutoff as the robust test, taken from the estimator itself so
    // the two halves are compared on identical terms.
    auto fit = fit_fastmcd(points);
    REQUIRE(fit.has_value());
    auto probe = score_fastmcd(*fit, points.row(0).transpose(), kAlpha);
    REQUIRE(probe.has_value());
    const double cutoff = probe->critical_distance;

    std::vector<double> classical(kN);
    for (int i = 0; i < kN; ++i) {
        Eigen::VectorXd d = points.row(i).transpose() - mean;
        classical[static_cast<std::size_t>(i)] = std::sqrt(static_cast<double>(d.transpose() * inv * d));
    }

    int planted_flagged = 0;
    for (int i = 0; i < 14; ++i) {
        if (classical[static_cast<std::size_t>(i)] > cutoff) ++planted_flagged;
    }
    INFO("classical flags " << planted_flagged << " of the 14 planted outliers, cutoff " << cutoff);
    CHECK(planted_flagged <= 2);

    // Masking made concrete: some planted outliers sit closer to the
    // classical centre than the most extreme clean observation does.
    double largest_clean = 0.0;
    for (int i = 14; i < kN; ++i) largest_clean = std::max(largest_clean, classical[static_cast<std::size_t>(i)]);
    int hidden_below_clean_max = 0;
    for (int i = 0; i < 14; ++i) {
        if (classical[static_cast<std::size_t>(i)] < largest_clean) ++hidden_below_clean_max;
    }
    INFO("largest classical distance among the 61 clean points = " << largest_clean);
    CHECK(hidden_below_clean_max >= 3);
}

TEST_CASE("The Hawkins-Bradu-Kass result survives row reordering and affine maps",
          "[fastmcd][reference]") {
    // MCD is defined by affine equivariance, and the published result is
    // a property of the point cloud, not of the order it happens to be
    // stored in. fastmcd.hpp is explicit that permutation invariance is
    // NOT guaranteed by construction, so this section measures it on the
    // reference data rather than assuming it: if a future change makes
    // the estimate order-sensitive enough to move a point across the
    // cutoff on this well-separated example, that is worth knowing.
    const Eigen::MatrixXd base = hbk_matrix();
    const std::set<int> expected = published_outliers();
    std::vector<int> identity(kN);
    std::iota(identity.begin(), identity.end(), 0);

    SECTION("row permutations") {
        for (int t = 0; t < 8; ++t) {
            std::vector<int> order = identity;
            // Hand-rolled shuffle: std::shuffle's sequence is
            // implementation-defined, and this fixture must permute the
            // same way on every platform.
            std::mt19937 rng(static_cast<unsigned>(9000 + t));
            for (int i = kN - 1; i > 0; --i) {
                const int j = static_cast<int>(rng() % static_cast<unsigned>(i + 1));
                std::swap(order[static_cast<std::size_t>(i)], order[static_cast<std::size_t>(j)]);
            }
            Eigen::MatrixXd permuted(kN, kP);
            for (int i = 0; i < kN; ++i) permuted.row(i) = base.row(order[static_cast<std::size_t>(i)]);

            const std::set<int> flagged = flagged_originals(permuted, order);
            INFO("permutation " << t << " flagged " << to_string(flagged));
            CHECK(flagged == expected);
        }
    }

    SECTION("uniform rescaling of the input units") {
        for (double s : {1e-6, 1e-3, 1.0, 1e3, 1e6}) {
            const std::set<int> flagged = flagged_originals(base * s, identity);
            INFO("scale " << s << " flagged " << to_string(flagged));
            CHECK(flagged == expected);
        }
    }

    SECTION("a non-orthogonal anisotropic linear map") {
        Eigen::Matrix3d a;
        a <<  2.0, 0.5, -1.0,
              0.0, 3.0,  0.7,
             -0.4, 0.0,  1.5;
        REQUIRE(std::abs(a.determinant()) > 1e-6);
        const std::set<int> flagged = flagged_originals(base * a.transpose(), identity);
        INFO("anisotropic map flagged " << to_string(flagged));
        CHECK(flagged == expected);
    }
}
