add_executable(gm-data-tests
  universe_test.cpp
  liquidity_test.cpp
  fundamentals_test.cpp
  fundamentals_concepts_test.cpp
  revisions_test.cpp
  membership_test.cpp
)

target_link_libraries(gm-data-tests
  PRIVATE
    gm::data
    Catch2::Catch2WithMain
)

catch_discover_tests(gm-data-tests)
