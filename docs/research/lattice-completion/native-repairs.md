# Native Lattice math repairs

Date: 2026-10-04. This repair pass covers the native findings in `docs/research/lattice-math-audit/`. The earlier audit is unchanged. No investment or backtest conclusion follows from these tests.

## Changes

| Area | Repair | Regression |
|---|---|---|
| Ledoit–Wolf | Normalize the entire shrunk covariance by its diagonal. The T=3 hand case is `5/(6 sqrt(7))`; perfect two-point correlation remains 1 at zero reported shrinkage. | `shrinkage_test.cpp` |
| Marchenko–Pastur | Return continuous lower edge `(1-sqrt(q))^2` for all positive finite q; expose separate zero atom `max(0,1-1/q)`. | `rmt_test.cpp` |
| RIE | Reject a singular or near-singular sample correlation at a scale-aware eigenvalue tolerance, including q>1 rank deficiency. Reject nonfinite q and matrix entries. | `rie_test.cpp` |
| Graph | Reject NaN, infinity and negative distances; guard disconnected Prim selection before indexing. | `graph_test.cpp` |
| OU | Compare half-life with `(n-1)*dt`, in the same time unit. Reject nonfinite dt. | `ou_fit_test.cpp` |
| Boundary mesh | Require at least three scored dimensions when mesh export is requested; repeat the guard at the exporter entry. | App syntax check only. |

RIE's q>1 nullspace correction is **not implemented**. The primary formula cited in the prior native spectral audit requires a companion-spectrum transform. Returning `kInvalidArgument` for unsupported singular input is explicit and avoids presenting an epsilon floor or a rank-deficient matrix as RIE output. A run selecting RIE with N>T may now stop; the other estimators remain selectable.

## Remote RED/GREEN receipt

Host: `home-pc` (`john-riley-X870-GAMING-WIFI6`). Isolated path: `/home/john-riley/QuantHacks/lattice-completion-20261004/native-repairs/`. Exact local source, header and test files are archived separately in `red-sources.tar.gz` and `green-sources.tar.gz`; each manifest was checked with `sha256sum -c` before compilation. Existing Eigen/Catch2 dependencies came from `/home/john-riley/projects/geomarket/build/linux-gcc-release/vcpkg_installed/x64-linux`. Compiler: `g++ 13.3.0`.

Detached jobs: `qh-native-repairs-red-20261004`, `qh-native-repairs-green-20261004`, `qh-native-repairs-app2-20261004`. The scripts use the shared `/home/john-riley/.cache/quanthaxs-heavy-compute.lock`, set OMP/OpenBLAS/MKL threads to 2, and cap virtual memory at 4 GiB. `run-native-tests.sh` builds five C++20 binaries with `-O0 -fno-fast-math -Wall -Wextra -Werror` and runs their whole `[shrinkage]`, `[rmt]`, `[rie]`, `[graph]`, `[ou]` tag sets. `app-compile.sh` checks the exact modified boundary app source with `g++ -fsyntax-only` and the same warnings.

| Remote artifact | SHA-256 |
|---|---|
| `red-sources.tar.gz` | `d605b75e7216439869f8dfd56382f9f726896a7f99b73fc003ee1913f70643c0` |
| `green-sources.tar.gz` | `4e9190b085962743a9004934cb810c7cfb3c525d55caee3267af5fcc4454bad0` |
| `red-manifest.sha256` | `fce4a1cd114639bfbed1b82a28faaba9f66caeab39ff841558273d638e45af54` |
| `green-manifest.sha256` | `3463419cb8c36ff66aa85b403e25379b645a6bc4012558fbf03074aefbc52917` |
| `run-native-tests.sh` | `3b6484488f42e2fd1c433ad8d9d7178663bece6b7f01df45298e1fe02926158a` |
| `app-compile.sh` | `e96a36975c826165248b67b5982e40ebf1e9ab856104a686264bc5fa6b31ea8b` |
| `red.log` | `4b3fdd3b61e46828698dd3e3f2c3dc9a1cb709fb856c927f701bfa79f90e1815` |
| `green.log` | `bc9a12c67bc1995b19a30acdc1ed6d20c1060be7ab8d6ca8386a519945dc17e3` |
| `app-compile.log` | `b1ed75e26c0b0164a3e4308fc4c7bf7576c22288a848d4fa76fd185a94b7d397` |

RED: LW's hand and perfect-correlation cases failed; RIE returned a value for the rank-two q=4/3 example; graph NaN reached an Eigen bounds assertion; OU failed both dt-unit cases. RMT failed to compile because `zero_atom_mass` did not exist. `red.log` ends `CASE_FAILURES:5`, `EXIT_CODE:1`.

GREEN: all five builds and binaries exited zero. They passed respectively 7/21, 7/26, 7/3333, 10/44, and 14/30 test cases/assertions: **45 cases, 3,454 assertions** total. `green.log` ends `CASE_FAILURES:0`, `EXIT_CODE:0`. The boundary app syntax check ends `EXIT_CODE:0`. An initial app check used a wrong remote include path; the corrected script and successful log are the hashed artifacts here.

The full project CMake/CTest suite, mesh runtime fixture, sanitizers/Valgrind, and any market-data refit or performance benchmark were not run in this bounded lane. The mesh guard has compile verification only. No options-native file, shared schema, commit or PR was changed.
