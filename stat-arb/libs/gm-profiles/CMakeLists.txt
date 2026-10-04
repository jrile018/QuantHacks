find_package(nlohmann_json CONFIG REQUIRED)

add_library(gm-profiles-lib STATIC
  src/profiles.cpp
)
add_library(gm::profiles ALIAS gm-profiles-lib)

target_include_directories(gm-profiles-lib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-profiles-lib
  PUBLIC
    gm::core
    gm::io
    nlohmann_json::nlohmann_json
)

target_compile_features(gm-profiles-lib PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
