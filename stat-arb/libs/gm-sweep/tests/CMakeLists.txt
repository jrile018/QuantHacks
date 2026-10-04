add_executable(gm-sweep-tests
  parameter_grid_test.cpp
)

target_link_libraries(gm-sweep-tests
  PRIVATE
    gm::sweep
    Catch2::Catch2WithMain
)

target_compile_features(gm-sweep-tests PRIVATE cxx_std_20)

catch_discover_tests(gm-sweep-tests)
