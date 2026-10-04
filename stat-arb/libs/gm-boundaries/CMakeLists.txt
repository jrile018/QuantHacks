find_package(Eigen3 CONFIG REQUIRED)
find_package(boost_math CONFIG REQUIRED)

add_library(gm-boundaries-lib STATIC
  src/mahalanobis.cpp
  src/fastmcd.cpp
  src/kde.cpp
  src/marching_tetrahedra.cpp
)
add_library(gm::boundaries ALIAS gm-boundaries-lib)

target_include_directories(gm-boundaries-lib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-boundaries-lib
  PUBLIC
    gm::core
    Eigen3::Eigen
    Boost::math
)

target_compile_features(gm-boundaries-lib PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
