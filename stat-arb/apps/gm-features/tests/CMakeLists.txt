# centrality.cpp/returns.cpp are pure logic (no Parquet/filesystem I/O) -
# compiled directly into the test binary rather than through the
# gm-features executable target, matching gm-view's tests/CMakeLists.txt
# pattern (data_loader.cpp / camera.cpp compiled directly for the same
# reason).

add_executable(gm-features-tests
  centrality_test.cpp
  returns_test.cpp
  valuation_test.cpp
  market_model_test.cpp
  ../centrality.cpp
  ../returns.cpp
  ../valuation.cpp
  ../market_model.cpp
)

target_include_directories(gm-features-tests PRIVATE ..)

target_link_libraries(gm-features-tests
  PRIVATE
    Catch2::Catch2WithMain
    gm::core
)

catch_discover_tests(gm-features-tests)
