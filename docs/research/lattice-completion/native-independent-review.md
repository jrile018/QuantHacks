# Independent native repair review

Date: 2026-10-04. Scope: the native repair diff and local receipts in `artifacts/lattice-completion/native-v2/`. This was a read-only code and evidence review; I did not rerun the full C++ build or any market fit.

## Verdict

No P1 or P2 implementation finding in the six reviewed repairs. The bounded GREEN receipt reports 45 cases and 3,454 assertions, with zero failures. The app's boundary change has a successful syntax compile receipt only; mesh runtime behavior remains unverified.

## Oracle checks

| Repair | Independent check |
|---|---|
| Ledoit–Wolf | The code constructs the shrunk covariance, then applies `D^-1/2 C D^-1/2` before setting the exact unit diagonal. In the fixed T=3 case, `delta=7/12`, covariance off-diagonal `5/(9 sqrt(7))`, and diagonal `2/3` give correlation `5/(6 sqrt(7))`. The added zero-intensity perfect-correlation case tests that normalization does not add unintended shrinkage. |
| OU | The fit estimates the AR slope from `n-1` pairs and computes half-life in the units of `dt`; its guard compares against `(n-1)*dt`. The new tests cover `dt=0.25` rejection and `dt=2` acceptance. |
| Marchenko–Pastur | For every finite positive `q`, the continuous lower edge is `(1-sqrt(q))^2`; the separate zero atom is `max(0,1-1/q)`. The q=4 test expects edge 1 and atom 0.75. |
| RIE | Input q and matrix entries must be finite; eigenvalues at or below `1e-10*max(1,lambda_max)` are refused before the unchanged nonsingular eigenvalue map. The rank-two q=4/3 fixture is rejected instead of receiving a fabricated nullspace estimate. |
| Graph | Finite nonnegative distance checks precede neighbor selection. Prim checks `best` and its parent before indexing, returning an error if disconnected. The new test exercises NaN, infinity and negative entries. |
| Boundary mesh | The caller rejects mesh requests with 1 or 2 scored dimensions before the frame loop; the exporter repeats the guard on its training matrix. The modified app source passed `-fsyntax-only`; no runtime mesh fixture was part of this bounded lane. |

## Limits

- The RIE q>1 nullspace estimator remains unsupported by design. Inputs near the eigenvalue tolerance may now be refused; this is explicit and preferable to claiming an estimator result from rank-deficient data.
- The boundary mesh guard has no runtime regression case in this receipt. A later app integration run should exercise a two-dimensional mesh request and confirm the error before any output is written.
- The receipt does not cover full CMake/CTest, sanitizers, a full pipeline, or financial performance. Native math repair success is not evidence of a profitable or executable signal.
