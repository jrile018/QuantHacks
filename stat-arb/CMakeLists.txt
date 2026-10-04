cmake_minimum_required(VERSION 3.27)

project(geomarket
  VERSION 0.1.0
  DESCRIPTION "Geometric market manifold - equity relationship geometry for statistical arbitrage"
  LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# All stage executables land in one directory so gm-run can find its
# siblings by "the directory I was launched from" (apps/gm-run/main.cpp)
# without a separate install step, and so this matches the deployable
# bin/ layout used by `install(TARGETS ... RUNTIME DESTINATION bin)`
# (cmake/GmStageApp.cmake).
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
foreach(config_type ${CMAKE_CONFIGURATION_TYPES})
  string(TOUPPER ${config_type} config_type_upper)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${config_type_upper} ${CMAKE_BINARY_DIR}/bin)
endforeach()

option(GM_BUILD_TESTS "Build unit/golden/property tests" ON)
option(GM_BUILD_BENCHMARKS "Build google-benchmark suites" ON)
option(GM_SANITIZE "Build with ASan+UBSan (Linux/GCC only)" OFF)

list(APPEND CMAKE_MODULE_PATH ${CMAKE_SOURCE_DIR}/cmake)
include(GmBuildInfo)
include(GmStageApp)

# ---------------------------------------------------------------------------
# ADR-004/ADR-019: strict floating-point conformance, no fast-math, ever.
# ADR-004: warnings-as-errors in CI; kept as a real error locally too so a
# milestone cannot "pass" on a developer machine and fail on the remote box.
# ---------------------------------------------------------------------------
add_library(gm_project_options INTERFACE)
add_library(gm::project_options ALIAS gm_project_options)

if (MSVC)
  target_compile_options(gm_project_options INTERFACE
    /W4 /WX
    /fp:precise
    /permissive-
    /Zc:preprocessor
    # C4714: a function marked __forceinline was not inlined. Emitted from
    # boost::math's headers, and NOT suppressed by the /external:W0 already
    # applied to the vcpkg include tree - C4714 is issued during code
    # generation rather than while parsing the header, so it escapes the
    # scope /external governs. It reports an optimiser decision about
    # somebody else's header and says nothing about this code.
    /wd4714
  )
  # std::getenv and friends are standard C++; MSVC's C4996 deprecation of
  # them is a vendor opinion this project does not share, and the suggested
  # replacements are not portable. Scoped to a definition rather than
  # /wd4996 so a genuine deprecation of OUR OWN code still warns.
  target_compile_definitions(gm_project_options INTERFACE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(gm_project_options INTERFACE
    -Wall -Wextra -Wconversion -Wsign-conversion -Wpedantic -Werror
    -fno-fast-math
  )
  if (GM_SANITIZE)
    target_compile_options(gm_project_options INTERFACE -fsanitize=address,undefined -fno-omit-frame-pointer -g)
    target_link_options(gm_project_options INTERFACE -fsanitize=address,undefined)
  endif()
endif()

# ---------------------------------------------------------------------------
# Dependencies (ADR-005). Each library CMakeLists.txt links only what it
# actually uses; find_package is centralized here so every milestone's
# additions are visible in one place.
# ---------------------------------------------------------------------------
find_package(tomlplusplus CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)
find_package(CLI11 CONFIG REQUIRED)
find_package(date CONFIG REQUIRED)

if (GM_BUILD_TESTS)
  find_package(Catch2 3 CONFIG REQUIRED)
  include(CTest)
  include(Catch)
endif()

if (GM_BUILD_BENCHMARKS)
  find_package(benchmark CONFIG QUIET)
  add_subdirectory(tests/benchmarks)
endif()

# Vendored single-header libraries (ADR-005: pinned, licensed, not vcpkg).
add_library(gm_third_party INTERFACE)
add_library(gm::third_party ALIAS gm_third_party)
target_include_directories(gm_third_party INTERFACE ${CMAKE_SOURCE_DIR}/third_party)

# ---------------------------------------------------------------------------
# Libraries and apps. Added incrementally as each milestone lands; a
# subdirectory only appears here once it has a real CMakeLists.txt, so the
# tree always configures cleanly from a clean clone (ADR "correctness is
# provable, not assumed" - no aspirational subdirectories).
# ---------------------------------------------------------------------------
add_subdirectory(libs/gm-core)
add_subdirectory(libs/gm-io)
add_subdirectory(libs/gm-data)
add_subdirectory(libs/gm-topology)
add_subdirectory(libs/gm-geometry)
add_subdirectory(libs/gm-boundaries)
add_subdirectory(libs/gm-signals)
add_subdirectory(libs/gm-backtest)
add_subdirectory(libs/gm-sweep)
add_subdirectory(libs/gm-profiles)

add_subdirectory(apps/gm-universe)
add_subdirectory(apps/gm-ingest)
add_subdirectory(apps/gm-features)
add_subdirectory(apps/gm-geometry)
add_subdirectory(apps/gm-boundaries)
add_subdirectory(apps/gm-signals)
add_subdirectory(apps/gm-backtest)
add_subdirectory(apps/gm-sweep)
add_subdirectory(apps/gm-profiles)
add_subdirectory(apps/gm-report)
add_subdirectory(apps/gm-run)

add_subdirectory(apps/gm-view)

# M1+: apps/gm-sweep; libs/gm-features(math),
# gm-geometry(math), gm-boundaries(math), gm-topology, gm-signals(math),
# gm-backtest(math), gm-plot.

if (GM_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests/golden)
endif()
