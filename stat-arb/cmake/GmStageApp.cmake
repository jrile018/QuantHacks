# Every gm-* stage executable (ADR-006) is built the same way: one
# main.cpp, link gm-core (which pulls in CLI11/spdlog/toml++/json/date
# publicly), stamp build-identity compile definitions. This function is
# that boilerplate, written once.
function(gm_add_stage_app name)
  add_executable(${name} ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp)
  target_link_libraries(${name} PRIVATE gm::core)
  gm_inject_build_info(${name})
  install(TARGETS ${name} RUNTIME DESTINATION bin)
endfunction()
