add_executable(gm-io-tests
  csv_test.cpp
  table_test.cpp
  parquet_test.cpp
  http_cache_test.cpp
  mesh_test.cpp
)

target_link_libraries(gm-io-tests
  PRIVATE
    gm::io
    Catch2::Catch2WithMain
)

catch_discover_tests(gm-io-tests)
