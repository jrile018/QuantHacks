#pragma once

// Rotationally-invariant estimator (RIE) for a correlation matrix,
// ADR-009 as amended.
//
// WHY THIS EXISTS
// ---------------
// The default path applies Ledoit-Wolf shrinkage and THEN Marchenko-
// Pastur eigenvalue clipping, as though they were two halves of one
// pipeline. They are not. They are two competing estimators of the same
// corrected spectrum:
//
//   - Shrinkage pulls every eigenvalue toward the grand mean by one
//     global intensity, chosen to minimise expected Frobenius loss.
//   - MP clipping replaces everything inside the bulk with a single
//     value and leaves everything above it untouched - a step function.
//
// Running them in series applies one correction to a spectrum that has
// already had a different correction applied, so the intensity Ledoit-
// Wolf solved for is no longer the intensity that matrix needs, and the
// bulk edge MP is testing against is no longer the bulk edge of a
// sample covariance. The composition is not the optimum of either.
//
// The RIE is what the literature converged on instead. It keeps the
// sample eigenVECTORS - there is no information about rotation in a
// sample covariance beyond what the eigenvectors already carry - and
// replaces each eigenVALUE with the value that minimises expected loss
// GIVEN the whole observed spectrum. Shrinkage and clipping are both
// crude special cases of it: one constant pull, one step function,
// versus a smooth map fitted to the actual eigenvalue distribution.
//
// Reference: Bun, Bouchaud & Potters (2017), "Cleaning large
// correlation matrices: tools from random matrix theory", Physics
// Reports 666. The estimator below is their practical form, with the
// complex regulator that makes the Stieltjes transform finite on the
// real axis.
//
// WHAT IT DOES NOT DO
// -------------------
// It does not decide whether the peer baskets built from the resulting
// distance matrix are any better. That is an empirical question and the
// answer is a gate run with `geometry.correlation_estimator = "rie"`
// compared against one without. This header supplies the estimator; it
// makes no claim about the comparison.

#include <gm-core/error.hpp>

#include <Eigen/Dense>

namespace gm::geometry {

struct RieResult {
    Eigen::MatrixXd cleaned_correlation;   // unit diagonal, symmetric
    Eigen::VectorXd sample_eigenvalues;    // ascending, of the input
    Eigen::VectorXd cleaned_eigenvalues;   // ascending, of cleaned_correlation
    double q{};                            // N / T, as supplied
    double eta{};                          // the regulator actually used
};

/// Rotationally-invariant cleaning of a correlation matrix.
///
/// `correlation` must be square and symmetric with a unit diagonal (as
/// produced by sample_correlation()). `q` is N/T - the same aspect
/// ratio mp_denoise() takes - and must be positive; the caller supplies
/// it because this function sees only the matrix, not the window that
/// produced it.
///
/// Each sample eigenvalue lambda_i is mapped to
///
///     xi_i = lambda_i / |1 - q + q * z_i * g(z_i)|^2 ,
///     z_i  = lambda_i - i*eta ,
///     g(z) = (1/N) * sum_j 1/(z - lambda_j)
///
/// The imaginary regulator eta is what keeps g finite when z sits on
/// top of an eigenvalue; it is set to N^(-1/2), the scale at which
/// eigenvalue spacing and regulator are comparable, so the transform is
/// smoothed over neighbouring levels rather than over the whole
/// spectrum.
///
/// The rebuilt matrix is then renormalised to a unit diagonal, which
/// makes it a correlation matrix again and restores trace = N exactly.
///
/// Fails on a non-square, non-symmetric or empty matrix, on a
/// non-positive q, and on an eigendecomposition that does not converge.
[[nodiscard]] Result<RieResult> rie_clean_correlation(const Eigen::MatrixXd& correlation, double q);

}  // namespace gm::geometry
