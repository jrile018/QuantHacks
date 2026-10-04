find_package(tomlplusplus CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)

add_library(gm-sweep-lib STATIC
  src/parameter_grid.cpp
  src/cell_executor.cpp
  src/cell_runner.cpp
)
add_library(gm::sweep ALIAS gm-sweep-lib)

target_include_directories(gm-sweep-lib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src>
)

target_link_libraries(gm-sweep-lib
  PUBLIC
    gm::core
    gm::backtest
    tomlplusplus::tomlplusplus
    spdlog::spdlog
)

target_compile_features(gm-sweep-lib PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
