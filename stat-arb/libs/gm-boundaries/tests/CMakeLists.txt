add_executable(gm-boundaries-tests
  mahalanobis_test.cpp
  fastmcd_test.cpp
  fastmcd_reference_test.cpp
  kde_test.cpp
  marching_tetrahedra_test.cpp
)

target_link_libraries(gm-boundaries-tests
  PRIVATE
    gm::boundaries
    Catch2::Catch2WithMain
)

# src/ on the include path so tests can reach fastmcd_detail.hpp, the
# internal helpers that subset-generation and RNG tests must call
# directly (see that header for why).
target_include_directories(gm-boundaries-tests
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../src
)

catch_discover_tests(gm-boundaries-tests)
