find_package(Arrow CONFIG REQUIRED)
find_package(Parquet CONFIG REQUIRED)
find_package(cpr CONFIG REQUIRED)

# Arrow exports EITHER the static or the shared targets depending on how it
# was built, never a neutral alias for "whichever this is". vcpkg's default
# triplet is static on Linux (x64-linux) and shared on Windows
# (x64-windows), so naming one of them directly builds on one platform and
# fails the CMake GENERATE step on the other - after every dependency has
# already been compiled, which is an expensive place to find out.
#
# ADR-020 requires green on both, so this picks what is actually installed
# and says so plainly if neither is.
if (TARGET Arrow::arrow_static)
  set(GM_ARROW_TARGET Arrow::arrow_static)
elseif (TARGET Arrow::arrow_shared)
  set(GM_ARROW_TARGET Arrow::arrow_shared)
else()
  message(FATAL_ERROR
    "Arrow was found but exports neither Arrow::arrow_static nor "
    "Arrow::arrow_shared - the installed Arrow package is not one this "
    "build understands.")
endif()

if (TARGET Parquet::parquet_static)
  set(GM_PARQUET_TARGET Parquet::parquet_static)
elseif (TARGET Parquet::parquet_shared)
  set(GM_PARQUET_TARGET Parquet::parquet_shared)
else()
  message(FATAL_ERROR
    "Parquet was found but exports neither Parquet::parquet_static nor "
    "Parquet::parquet_shared.")
endif()

message(STATUS "gm-io linking ${GM_ARROW_TARGET} and ${GM_PARQUET_TARGET}")

add_library(gm-io STATIC
  src/http_cache.cpp
  src/csv.cpp
  src/table.cpp
  src/mesh.cpp
  src/parquet.cpp
)
add_library(gm::io ALIAS gm-io)

target_include_directories(gm-io
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_link_libraries(gm-io
  PUBLIC
    gm::core
  PRIVATE
    ${GM_ARROW_TARGET}
    ${GM_PARQUET_TARGET}
    cpr::cpr
)

target_compile_features(gm-io PUBLIC cxx_std_20)

if (GM_BUILD_TESTS)
  add_subdirectory(tests)
endif()
