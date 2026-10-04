# Computes build-identity info once at configure time and exposes
# gm_inject_build_info(target) to stamp it onto a stage executable as
# compile definitions (GM_GIT_COMMIT, GM_COMPILER_ID, GM_BUILD_TYPE -
# consumed by gm-core/stage_main.hpp). gm-core itself never shells out to
# git (ADR-019: it is a library, not a process); this is the one place in
# the build that does, and only at configure time.

find_package(Git QUIET)

if (Git_FOUND)
  execute_process(
    COMMAND ${GIT_EXECUTABLE} rev-parse --short=12 HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GM_GIT_COMMIT_VALUE
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
    RESULT_VARIABLE GM_GIT_RESULT
  )
  if (NOT GM_GIT_RESULT EQUAL 0 OR GM_GIT_COMMIT_VALUE STREQUAL "")
    set(GM_GIT_COMMIT_VALUE "unknown")
  endif()

  execute_process(
    COMMAND ${GIT_EXECUTABLE} diff --quiet HEAD --
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    RESULT_VARIABLE GM_GIT_DIRTY_RESULT
    ERROR_QUIET
  )
  if (NOT GM_GIT_DIRTY_RESULT EQUAL 0)
    set(GM_GIT_COMMIT_VALUE "${GM_GIT_COMMIT_VALUE}-dirty")
  endif()
else()
  set(GM_GIT_COMMIT_VALUE "unknown")
endif()

set(GM_COMPILER_ID_VALUE "${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")

function(gm_inject_build_info target)
  target_compile_definitions(${target} PRIVATE
    GM_GIT_COMMIT="${GM_GIT_COMMIT_VALUE}"
    GM_COMPILER_ID="${GM_COMPILER_ID_VALUE}"
    GM_BUILD_TYPE="$<CONFIG>"
  )
endfunction()
