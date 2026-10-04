find_package(boost_math CONFIG REQUIRED)

# Named gm-backtest-lib, not gm-backtest: the latter is already the
# CMake target name of apps/gm-backtest, the pipeline STAGE executable
# (same collision-avoidance pattern as gm-geometry-lib/gm-boundaries-lib).
add_library(gm-backtest-lib STATIC
  src/deflated_sharpe.cpp
  src/trade_simulation.cpp
)
add_library(gm::backtest ALIAS gm-backtest-lib)

target_include_directories(gm-backtest-lib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-backtest-lib
  PUBLIC
    gm::core
    Boost::math
)

target_compile_features(gm-backtest-lib PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
