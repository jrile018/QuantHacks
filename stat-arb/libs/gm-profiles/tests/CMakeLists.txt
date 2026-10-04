add_executable(gm-profiles-tests
  profiles_test.cpp
)

target_link_libraries(gm-profiles-tests
  PRIVATE
    gm::profiles
    Catch2::Catch2WithMain
)

catch_discover_tests(gm-profiles-tests)
