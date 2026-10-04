find_package(Eigen3 CONFIG REQUIRED)

# Named gm-geometry-lib, not gm-geometry: the latter is already the CMake
# target name of apps/gm-geometry, the pipeline STAGE executable (ADR-006 -
# gm-run invokes stages by this exact name, and it can't change). CMake
# target names are a single flat namespace regardless of directory, so
# the two would collide; the gm::geometry ALIAS (a separate namespace)
# is unaffected and is what every consumer actually links against.
add_library(gm-geometry-lib STATIC
  src/correlation.cpp
  src/shrinkage.cpp
  src/rmt.cpp
  src/rie.cpp
  src/distance.cpp
  src/mds.cpp
  src/procrustes.cpp
  src/graph.cpp
)
add_library(gm::geometry ALIAS gm-geometry-lib)

target_include_directories(gm-geometry-lib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-geometry-lib
  PUBLIC
    gm::core
    gm::topology
    Eigen3::Eigen
)

target_compile_features(gm-geometry-lib PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
