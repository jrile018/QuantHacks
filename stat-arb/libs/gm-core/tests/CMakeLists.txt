add_executable(gm-core-tests
  date_test.cpp
  calendar_test.cpp
  types_test.cpp
  error_test.cpp
  config_test.cpp
  manifest_test.cpp
  instrument_test.cpp
)

target_link_libraries(gm-core-tests
  PRIVATE
    gm::core
    Catch2::Catch2WithMain
)

catch_discover_tests(gm-core-tests)
