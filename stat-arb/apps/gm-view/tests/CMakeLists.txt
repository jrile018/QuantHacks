# camera.cpp is pure math (no GL/GLFW/ImGui headers) - compiled
# directly into the test binary rather than through the gm-view
# executable target, so these tests need no display, no GL context, and
# no windowing dependency at all. gl.cpp is not covered: it needs
# a real GL context. data_loader.cpp is tested via data_loader_test.cpp
# which validates Parquet file loading against real run artifacts.

add_executable(gm-view-tests
  camera_test.cpp
  data_loader_test.cpp
  surface_index_test.cpp
  ../camera.cpp
  ../data_loader.cpp
)

target_include_directories(gm-view-tests PRIVATE ..)

target_link_libraries(gm-view-tests
  PRIVATE
    Catch2::Catch2WithMain
    gm::core
    gm::io
)

catch_discover_tests(gm-view-tests)
