# ADR-020 layer 4. The option to build these has been on since the project
# started and there was nothing to build, so the rule that a regression
# beyond threshold fails a milestone had nothing to enforce it.
#
# Guarded on the package actually being found rather than on the option
# alone: the root CMakeLists looks for google-benchmark with QUIET, so a
# machine without it configures fine and simply has no benchmark target,
# which is better than a hard failure for something no test depends on.
if (NOT benchmark_FOUND)
  message(STATUS "google-benchmark not found - skipping gm-benchmarks")
  return()
endif()

add_executable(gm-benchmarks
  frame_loop_bench.cpp
)

target_link_libraries(gm-benchmarks
  PRIVATE
    gm::project_options
    gm::geometry
    gm::boundaries
    benchmark::benchmark
)
