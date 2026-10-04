find_package(Eigen3 CONFIG REQUIRED)
find_package(osqp CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)

add_library(gm-signals-lib STATIC
  src/peer_basket.cpp
  src/ou_fit.cpp
  src/excursion.cpp
  src/earnings.cpp
  src/survival.cpp
  src/matching.cpp
  src/cluster.cpp
  src/competing_risks.cpp
)
add_library(gm::signals ALIAS gm-signals-lib)

target_include_directories(gm-signals-lib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-signals-lib
  PUBLIC
    gm::core
    gm::io
    Eigen3::Eigen
    nlohmann_json::nlohmann_json
  PRIVATE
    # osqp's vcpkg port only guarantees the shared-lib target
    # (osqp::osqp) OR the static one (osqp::osqpstatic) depending on
    # how the port was built, per vcpkg's own generated usage note -
    # this selects whichever actually exists rather than hardcoding one.
    $<IF:$<TARGET_EXISTS:osqp::osqp>,osqp::osqp,osqp::osqpstatic>
)

# When the SHARED osqp is the one being linked, its headers only decorate
# the API with __declspec(dllimport) if OSQP_SHARED_LIB is defined - see
# osqp_export_define.h. Without it MSVC emits calls to undecorated names
# while the import library exports __imp_-prefixed ones, and the link
# fails with four unresolved externals that look like a missing library
# rather than a missing macro. Conditioned on exactly the same target test
# as the link above, so the two can never disagree.
target_compile_definitions(gm-signals-lib PRIVATE
  $<$<TARGET_EXISTS:osqp::osqp>:OSQP_SHARED_LIB>
)

target_compile_features(gm-signals-lib PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
