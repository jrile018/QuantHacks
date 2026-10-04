# See tests/fixtures/golden_run.toml.in - @GM_REPO_ROOT@ becomes an
# absolute path so the fixture works regardless of ctest's working
# directory.
set(GM_REPO_ROOT ${CMAKE_SOURCE_DIR})
configure_file(
  ${CMAKE_SOURCE_DIR}/tests/fixtures/golden_run.toml.in
  ${CMAKE_CURRENT_BINARY_DIR}/golden_run.toml
  @ONLY
)

add_executable(gm-golden-tests
  m0_pipeline_test.cpp
  causality_test.cpp
  determinism_test.cpp
)

target_link_libraries(gm-golden-tests
  PRIVATE
    gm::core
    gm::io
    Catch2::Catch2WithMain
)

# gm-golden-tests must run after gm-run (and every stage it invokes)
# exists as a built binary - this is a real dependency, not an ordering
# hint, since the test shells out to the gm-run executable by path.
add_dependencies(gm-golden-tests
  gm-run gm-universe gm-ingest gm-features gm-geometry gm-boundaries
  gm-signals gm-backtest gm-profiles gm-report
)

target_compile_definitions(gm-golden-tests PRIVATE
  GM_RUN_EXECUTABLE="$<TARGET_FILE:gm-run>"
  GM_GOLDEN_FIXTURE_CONFIG="${CMAKE_CURRENT_BINARY_DIR}/golden_run.toml"
  # causality_test.cpp drives one stage directly rather than the whole
  # chain: the property it checks (ADR-020 layer 3) is a property of
  # gm-boundaries' windowing, and running the other eight stages to reach
  # it would only add ways for the test to fail for unrelated reasons.
  GM_BOUNDARIES_EXECUTABLE="$<TARGET_FILE:gm-boundaries>"
  GM_GEOMETRY_EXECUTABLE="$<TARGET_FILE:gm-geometry>"
)

catch_discover_tests(gm-golden-tests)
