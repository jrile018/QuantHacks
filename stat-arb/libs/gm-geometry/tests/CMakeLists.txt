add_executable(gm-geometry-tests
  correlation_test.cpp
  shrinkage_test.cpp
  rmt_test.cpp
  rie_test.cpp
  distance_test.cpp
  mds_test.cpp
  procrustes_test.cpp
  graph_test.cpp
)

target_link_libraries(gm-geometry-tests
  PRIVATE
    gm::geometry
    Catch2::Catch2WithMain
)

catch_discover_tests(gm-geometry-tests)
