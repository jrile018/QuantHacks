# Native spectral and geometry mathematical audit

Audit date: 2026-10-04. Scope: `stat-arb/libs/gm-geometry/{src,include,tests}` and `stat-arb/apps/gm-geometry/main.cpp`, with the graph-date join in `gm-signals`. Production source was read only. Audit harness: `tests/audit/native_spectral_witness.cpp`. Parent owns remote execution and the combined audit.

## Assessment

The native code contains mathematical defects, but the basic correlation orientation, signed distance, classical MDS, and orthogonal Procrustes formulas are coherent. Those defects do not establish that every Lattice result is wrong or that profitability follows after correction. Earlier tests of Python adaptations cannot validate these native formulas.

| Finding | Classification | Priority | Verification at report creation |
|---|---|---|---|
| RIE omits the positive correction for the sample nullspace when q > 1 | Mathematical implementation defect | High when RIE is selected and N > T | Source equation and analytic rank witness; native execution delegated |
| LW output overwrites a nonunit diagonal instead of normalizing its covariance | Mathematical implementation defect | Medium | Exact algebra; existing native test locks incorrect result; native execution delegated |
| MP lower continuous edge reported as zero for q > 1 | Incorrect mathematical metadata | Low | Exact formula; native execution delegated |
| Graph accepts nonfinite distances before unchecked MST indexing | Numerical/domain validation defect | Medium at library boundary | Static only; malformed-input crash not executed |
| Same-day graph selection contradicts a claim that today's price only scores the signal | Timing/interpretation issue | Conditional | Exact stage trace; execution timing handled by signal audit |

No full native test suite, coverage calculation, benchmark, or real-data experiment was run by this reviewer. The harness calls production C++ directly; it is not a Python port. No claim of native runtime verification is made until its remote output is available.

## 1. RIE: the q > 1 nullspace branch is missing

Locations: `src/rie.cpp:55-78`, especially `58-64`; `include/gm-geometry/rie.hpp:65-88`; stage `main.cpp:284,339-344`. Paths in this section are under `stat-arb/libs/gm-geometry` unless stated otherwise.

Actual code sets every nonpositive sample eigenvalue to zero. Positive near-zero eigenvalues also tend to zero at fixed regulator unless their denominator happens to vanish. Renormalization at lines 85-98 is a diagonal congruence, so for positive reconstructed diagonal it cannot supply missing rank.

The required singular-spectrum formula is explicit in [Ledoit and Peche, Theorem 1.4, equation (13), PDF page 10](https://arxiv.org/pdf/0911.3010). Their aspect ratio is gamma = T/N; substituting q = 1/gamma gives

\[
\xi(0)=\frac{1}{(q-1)\,\breve m_{\underline F}(0)},\qquad q>1,
\]

where the transform is for the companion spectrum and uses `m(z)=integral 1/(lambda-z) dF(lambda)`. It is positive under the paper's positive-definite population assumptions. The separate zero atom has mass `1-1/q`; it is not evidence that population variance vanishes in those directions.

Independent analytic witness: `C=[[1,0,-1,0],[0,1,0,-1],[-1,0,1,0],[0,-1,0,1]]`, `q=4/3`. Its spectrum is `(0,0,2,2)`. The two positive eigenvalues receive identical corrections; the native diagonal rescale therefore returns the same C, of rank two. This is a valid sample correlation: take three demeaned observations of two orthogonal nonconstant columns and append their negatives. The witness demonstrates absent nullspace correction, not a guarantee that any finite sample must recover the identity. For population covariance I, the exact oracle values `u_i' I u_i` are all one, including sample-null directions; that is the mathematical reason flooring the entire nullspace is inappropriate.

Affected outputs when `geometry.correlation_estimator="rie"`: cleaned correlations, distances, graph edges, coordinates, and quantities derived from these. The checked config has `liquidity_top_n=100` and `window_days=60` (`stat-arb/config/params.toml:38,50`); actual retained N varies, but N > T is plausible by design. The default estimator is `shrink_clip`, so this defect is not automatically active in every run.

Correction: implement a documented singular-spectrum estimator using a properly estimated companion transform, or reject unsupported singular regimes. Treat tiny eigenvalues with a scale-aware rank tolerance. Do not patch this by arbitrarily replacing zeros with machine epsilon and calling the result the literature estimator.

Existing RIE tests use nonsingular T > N fixtures for accuracy/PSD checks (`tests/rie_test.cpp:58-171`). They do not test this branch. They establish useful invariants, not agreement with a reference estimator.

## 2. LW: Bessel scaling produces an extra identity shrinkage

Locations: `src/shrinkage.cpp:30,46,70-77`; incorrect explanation at `72-75`; contract at `include/gm-geometry/shrinkage.hpp:12-20`.

Let R denote the ordinary sample correlation and `a=(T-1)/T`. The implementation standardizes with the sample standard deviation (`T-1`) but forms covariance S with divisor T. Therefore **S = a R** and **mu = a exactly in exact arithmetic**, not one in expectation.

The LW covariance before the last overwrite is

\[
A=\delta\mu I+(1-\delta)S
 =a[\delta I+(1-\delta)R].
\]

Covariance-to-correlation conversion must divide every entry by its reconstructed standard deviations: `diag(A)^(-1/2) A diag(A)^(-1/2)`. Here that gives `delta I+(1-delta)R`. The code instead sets only the diagonal to one, giving off-diagonal entries `a*(1-delta)*R_ij` and effective shrinkage `delta_eff=delta+(1-delta)/T`. It reports delta, not delta_eff. This derivation follows directly from the native operations; the covariance shrinkage model is [Ledoit and Wolf 2004, sections 2-3](https://perso.ens-lyon.fr/patrick.flandrin/LedoitWolf_JMA2004.pdf).

Exact witnesses:

* `X=[[1,2],[2,1],[3,6]]`: delta = 7/12. Native off-diagonal = `5/(9*sqrt(7))`; correctly normalized result = `5/(6*sqrt(7))`. Native is smaller by a factor 2/3.
* `X=[[-1,-1],[1,1]]`: each standardized observation outer product equals S, hence delta = 0. Native correlation = 0.5 despite reporting no shrinkage, while the actual sample correlation is 1.

`tests/shrinkage_test.cpp:3-15,29-42` hand-derives and enforces the covariance off-diagonal without completing its conversion to correlation. The test and implementation agree; their interpretation is wrong. At T=60 the extra factor is 59/60, so the direct effect is modest, but a downstream eigenvalue crossing a hard clipping threshold can change discretely.

Correction: use a consistent standardization divisor or normalize the final covariance by its diagonal. Update the reference test to assert correlation rather than mixed covariance/correlation units. The existing b-bar expansion itself agrees algebraically with the sum of squared outer-product deviations; omitting a common normalization by N from numerator and denominator does not change delta.

## 3. MP: lower edge and pipeline interpretation

Location: `src/rmt.cpp:27-29`; public description `include/gm-geometry/rmt.hpp:26`.

For identity population, the continuous MP support has endpoints `(1 +/- sqrt(q))^2` for all q > 0. For q > 1 there is additionally a point mass at zero. The implementation returns zero as `lambda_minus` whenever q >= 1. At q = 4/3 the continuous lower edge is about 0.0239322566, whereas the returned value is zero. The original MP equation and the separate zero atom are reviewed in [Ledoit and Peche, section 1.1](https://arxiv.org/pdf/0911.3010). Substituting identity population into that equation gives these endpoints.

This could be described as the minimum of the full support, but the field is explicitly named the *bulk lower edge*, so that description is mathematically misleading. It does not affect the current clipping loop: only `lambda_plus` is used to select bulk eigenvalues. Correct the metadata and represent zero mass separately if needed.

The default `shrink_clip` pipeline (`apps/gm-geometry/main.cpp:346-350`) applies the raw-sample MP upper edge to an already linearly shrunk matrix. Its transformed spectrum is not the raw MP null distribution. The stage and RIE header already acknowledge this composition. Classify it as an estimator heuristic lacking the optimality claimed for either component, not an arithmetic error or proof that its trading results must be worse. Eigenvalues beyond a white-noise edge are not automatically economically useful signals; dependence, heavy tails, and nonstationarity alter that interpretation.

## 4. Valid formulas, approximations, and interpretation corrections

* **Sample correlation orientation is correct.** `correlation.cpp:16-57` treats rows as observations and columns as assets. The T-1 covariance divisor cancels on normalization. Rejecting zero variance is appropriate. `q=N/window_days` at stage line 284 matches its documented N/T convention; it is not inverted.
* **Demeaning loses one degree of freedom.** Rank is at most T-1. Using N/T instead of N/(T-1) is a common asymptotic convention, not a factor-of-q mistake. It should be explicit for short-window comparisons and cannot justify treating all singular eigenvalues as numerical debris.
* **RIE sign and squared modulus are coherent.** With `g(z)=mean(1/(z-lambda))`, the plus sign in `1-q+q*lambda*g` and the squared modulus match [Bun et al., equation (IV.10)](https://arxiv.org/pdf/1502.06736). Native uses finite `z=lambda-i*eta` in both g and its multiplier, a finite-regulator approximation. Changing the half-plane consistently conjugates the denominator and does not change its modulus. No reciprocal-q or missing-square bug was found.
* **RIE smoothing is not independently calibrated.** `eta=N^-1/2` and the use of z rather than real lambda are finite-sample choices. The header says the regulator and spacing are comparable, while source correctly notes spacing O(1/N). They differ by sqrt(N). Unit-diagonal rescaling generally changes eigenvectors, so the final *correlation* need not retain the sample eigenvectors despite the header's broad RIE description. These are interpretation/approximation issues, separate from the missing zero branch.
* **Signed distance is mathematically deliberate.** `distance.cpp:36-48` computes `sqrt(2*(1-rho))`: anti-correlation is far, positive correlation is close. Replacing rho by abs(rho) changes the economic and geometric model. Valid PSD unit-diagonal correlations yield Euclidean distances; range checks alone do not establish PSD.
* **Classical MDS is correct for its stated objective.** `mds.cpp:24-55` forms `B=-J D^2 J/2` and keeps the largest positive eigenmodes. For this distance, `B=J C J`. A rank-k truncation approximates the centered Gram matrix; it does not generally preserve every distance. When k is below rank, claims of exact distance preservation are incorrect. Small eigengaps at the cutoff can make the selected subspace unstable.
* **There is no native coordinate row normalization.** `apps/gm-geometry/main.cpp:371-384,427-445` writes raw aligned MDS coordinates. Any unit-sphere projection or normalized-coordinate view in a Python adaptation is a separate change. Graph edges are built on full D *before* MDS at lines 353-360, so rank-three display distortion does not itself determine native peers.
* **Procrustes is correct.** `procrustes.cpp:21-36` uses the SVD of `Y' reference` and `R=U V'`, minimizing `||Y R-reference||_F` over orthogonal matrices, including reflections. That is appropriate for the arbitrary orientation of centered MDS. It does not perform translation or scale fitting, which is consistent with this pipeline. The normalized residual is relative to the prior frame scale, not a statistical significance level or a symmetric metric.
* **Graph construction matches its documented union.** `graph.cpp:91-124` returns symmetric k-nearest-neighbor closure plus MST, with independent flags. A node may have more than k neighbors because others can select it. This is not the directed top-k set. Equal-distance ties lack an explicit ticker/index tiebreaker, relevant when clipping produces an identity or nearly equidistant structure.

## 5. Numerical boundaries and timing

`graph.cpp:74-85` checks diagonal/symmetry with comparisons that NaN bypasses; it never enforces finite nonnegative entries. Prim's loop at `33-47` leaves `best=-1` if remaining distances are all NaN/Inf and then indexes vectors using that value. This is an invalid-memory-access path for malformed input, statically established, not reproduced in the witness. Add finite/domain checks before sorting and a defensive `best < 0` error. `distance.cpp:27-32` similarly permits NaN through ordered comparisons. `rie.cpp:24` accepts positive infinity q and its denominator fallback can silently return raw eigenvalues. These APIs should reject nonfinite input; normal finite pipeline data is a separate question.

`sample_correlation` catches NaN variances via `!(variance > 0)` but not all overflow cases. `rie` checks symmetry but not unit diagonal or PSD before clipping all negative eigenvalues; it therefore silently repairs some matrices outside its advertised domain. `mds` does not check distance symmetry, negativity, diagonal, or finiteness. Scope these as boundary guarantees; no malformed production artifact was inspected.

The return panel is T x N and dates are correctly aligned: `apps/gm-geometry/main.cpp:108-110,330-336` labels each frame by the endpoint of its final return. Procrustes at `376-384` references only the prior frame. No future alignment anchor was found.

`gm-signals/main.cpp:435-447` joins graph date t directly. Thus price at close t affects neighbor selection even when ridge/OU coefficients use preceding dates. This contradicts a stronger assertion that today's price only scores a preselected model. It is causal for a post-close-t decision executed later; calling it future leakage without examining execution timing would be wrong.

The intersection panel at geometry lines 143-174 can bridge missing dates into multi-session returns while still counting each row as one observation. This is documented behavior and a homogeneity assumption, not evidence of lookahead. `window_days` then means common-date return observations, potentially spanning more trading days.

## Verification and next actions

The harness emits JSON for both LW examples, RIE rank/eigenvalues, MP lower-edge metadata, and the OU dt-unit witness requested by the signal reviewer. Compile against the local snapshot's `correlation.cpp`, `shrinkage.cpp`, `rie.cpp`, `rmt.cpp`, and `gm-signals/src/ou_fit.cpp`, with Eigen, tl::expected, gm-core, gm-geometry, and gm-signals include directories. It requires C++20 and no production source edits. Remote compile/run belongs to the parent and should be recorded in the combined evidence.

Prioritize the q > 1 branch and LW normalization before comparing estimator performance. A native reference suite should test q below/equal/above one, singular samples, nonfinite rejection, correlation rescaling, and exact known Gram/Procrustes invariants. Do not substitute broad claims of >80% coverage, universal profitability, or full estimator validation for these concrete checks; none was established here.
