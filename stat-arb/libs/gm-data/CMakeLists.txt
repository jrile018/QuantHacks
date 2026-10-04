add_library(gm-data STATIC
  src/universe.cpp
  src/liquidity.cpp
  src/fundamentals.cpp
  src/revisions.cpp
  src/membership.cpp
)
add_library(gm::data ALIAS gm-data)

target_include_directories(gm-data
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-data
  PUBLIC
    gm::core
    gm::io
)

target_compile_features(gm-data PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
