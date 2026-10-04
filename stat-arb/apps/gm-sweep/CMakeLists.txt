find_package(tomlplusplus CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)
find_package(TBB CONFIG REQUIRED)

add_executable(gm-sweep main.cpp)

target_link_libraries(gm-sweep
  PRIVATE
    gm::sweep
    gm::core
    gm::backtest
    tomlplusplus::tomlplusplus
    nlohmann_json::nlohmann_json
    spdlog::spdlog
    TBB::tbb
)

target_compile_features(gm-sweep PRIVATE cxx_std_20)
