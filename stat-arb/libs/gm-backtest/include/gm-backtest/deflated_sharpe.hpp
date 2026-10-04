#pragma once

// Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014, "The Deflated
// Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting,
// and Non-Normality" - ADR-014: "Every reported Sharpe is accompanied
// by the Deflated Sharpe Ratio"). Formulas transcribed directly from
// the paper's own equations (1)/(5) and (2), and verified against the
// paper's own worked numerical example (see deflated_sharpe_test.cpp) -
// not reconstructed from memory alone, given how consequential getting
// this specific formula right is (it is the mechanism this whole
// project relies on to avoid quietly overfitting a parameter sweep).
//
// All quantities here are PER-OBSERVATION (non-annualized), matching
// the paper's own convention throughout - T is literally the number of
// return observations used to estimate the Sharpe ratio. A caller
// working with annualized Sharpe ratios must de-annualize before
// calling these functions (divide by sqrt(periods_per_year) for the
// Sharpe ratio itself, divide by periods_per_year for a VARIANCE of
// Sharpe ratios) - the paper's own worked example does exactly this
// conversion (an annualized SR=2.5 with 250 obs/year becomes a
// per-day SR of 2.5/sqrt(250)).

#include <gm-core/error.hpp>

#include <vector>

namespace gm::backtest {

/// The expected maximum Sharpe ratio across `n_trials` independent
/// trials (SR_0, paper Eq. 1/5/6), under the null hypothesis that the
/// trials' true Sharpe ratios are drawn from a distribution with mean 0
/// and variance `trial_sharpe_variance`. This is the "how good would
/// the best of N random, skill-less trials look by chance alone"
/// benchmark that the Deflated Sharpe Ratio measures the observed
/// Sharpe against, instead of against 0.
///
/// `n_trials <= 1` returns 0 exactly (the paper's own stated special
/// case: "When N=1, the expected maximum equals the mean" - with a
/// single trial there is no multiple-testing selection to correct for,
/// and the general formula's Z^-1(1 - 1/N) term is undefined at N=1
/// rather than naturally reducing to this).
[[nodiscard]] Result<double> expected_max_sharpe(double trial_sharpe_variance, int n_trials);

/// The Deflated Sharpe Ratio (paper Eq. 2): the probability that the
/// strategy's TRUE Sharpe ratio exceeds `sr0` (typically
/// expected_max_sharpe's output), given the observed Sharpe ratio
/// `observed_sharpe` estimated from `t_observations` per-period returns
/// with sample skewness `skewness` and sample kurtosis `kurtosis` (the
/// ordinary, non-excess kurtosis - a Normal distribution has kurtosis
/// 3, not 0; ADR §11's OU/DSR reference-test discipline requires this
/// be stated explicitly since it is a common sign-flip/off-by-3 source
/// of error).
///
/// Returns a probability in [0, 1]; values below the caller's chosen
/// confidence level (conventionally 0.95) mean the observed Sharpe
/// ratio is not distinguishable from what N trials of pure luck would
/// have produced, and ADR-013's own framing applies: it "ships as a
/// visualization tool and is not traded."
[[nodiscard]] Result<double> deflated_sharpe_ratio(double observed_sharpe, double sr0,
                                                     int t_observations, double skewness, double kurtosis);

struct SampleMoments {
    double mean;
    double std_dev;   // population (1/n divisor) standard deviation - see the note below on why
    double skewness;   // gamma3: (1/n * sum((x-mean)^3)) / std_dev^3
    double kurtosis;    // gamma4: (1/n * sum((x-mean)^4)) / std_dev^4 - RAW, not excess (Normal = 3)
};

/// Plug-in (method-of-moments) sample skewness/kurtosis, matching the
/// convention deflated_sharpe_ratio's gamma3/gamma4 parameters expect
/// (raw kurtosis, Normal distribution = 3, not 0) - the standardizing
/// std_dev used inside the skewness/kurtosis ratios is the POPULATION
/// (1/n) standard deviation, the conventional choice for these plug-in
/// moment estimators, which is deliberately NOT necessarily the same
/// divisor a caller might use elsewhere for the Sharpe ratio's own
/// (commonly sample, 1/(n-1)) standard deviation - std_dev is exposed
/// here specifically so a caller doesn't have two different
/// "standard deviation of the same series" values silently drift out of
/// sync from computing them separately with different divisors.
///
/// Requires at least 2 observations with nonzero variance (a constant
/// series has undefined skewness/kurtosis, division by a zero std_dev).
[[nodiscard]] Result<SampleMoments> sample_moments(const std::vector<double>& returns);

} // namespace gm::backtest
