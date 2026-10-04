add_executable(gm-topology-tests topology_test.cpp)

target_link_libraries(gm-topology-tests
  PRIVATE
    gm::topology
    Catch2::Catch2WithMain
)

target_compile_features(gm-topology-tests PRIVATE cxx_std_20)

catch_discover_tests(gm-topology-tests)
