add_library(gm-core STATIC
  src/date.cpp
  src/calendar.cpp
  src/config.cpp
  src/manifest.cpp
  src/instrument.cpp
)
add_library(gm::core ALIAS gm-core)

target_include_directories(gm-core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-core
  PUBLIC
    gm::project_options
    gm::third_party
    tomlplusplus::tomlplusplus
    nlohmann_json::nlohmann_json
    date::date
    spdlog::spdlog
    CLI11::CLI11
)

target_compile_features(gm-core PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
