# gm-topology: Vietoris-Rips persistent homology via Ripser (ADR-012)
# Provides H0/H1 persistence features and shape-change detection for regime veto

find_package(Eigen3 CONFIG REQUIRED)

add_library(gm_topology INTERFACE)
add_library(gm::topology ALIAS gm_topology)

target_include_directories(gm_topology INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(gm_topology INTERFACE
    gm::core
    Eigen3::Eigen
)

# Ripser is header-only, vendored at third_party/ripser/
target_include_directories(gm_topology INTERFACE
    ${CMAKE_SOURCE_DIR}/third_party
)

target_compile_features(gm_topology INTERFACE cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
