find_package(imgui CONFIG REQUIRED)
find_package(implot CONFIG REQUIRED)
find_package(glfw3 CONFIG REQUIRED)
find_package(glad CONFIG REQUIRED)
find_package(OpenGL REQUIRED)

add_executable(gm-view
  main.cpp
  gl.cpp
  camera.cpp
  data_loader.cpp
)

target_link_libraries(gm-view
  PRIVATE
    gm::core
    gm::io
    imgui::imgui
    implot::implot
    glfw
    glad::glad
    OpenGL::GL
)

gm_inject_build_info(gm-view)
install(TARGETS gm-view RUNTIME DESTINATION bin)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
