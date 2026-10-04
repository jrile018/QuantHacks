#include <gm-io/mesh.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cstdint>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

using gm::io::MeshData;
using gm::io::read_gmmesh;
using gm::io::write_gmmesh;

namespace {

std::filesystem::path temp_mesh_path(const std::string& name) {
    auto dir = std::filesystem::temp_directory_path() / "gm-mesh-tests";
    std::filesystem::create_directories(dir);
    auto path = dir / (name + ".gmmesh");
    std::filesystem::remove(path);
    return path;
}

/// A tetrahedron: the smallest closed surface, and enough to exercise every
/// field of the format.
MeshData tetrahedron() {
    MeshData mesh;
    mesh.vertices = {{0.0, 0.0, 0.0},
                     {1.5, 0.0, 0.0},
                     {0.0, 2.5, 0.0},
                     {0.0, 0.0, 3.5}};
    mesh.triangles = {{0, 1, 2}, {0, 1, 3}, {0, 2, 3}, {1, 2, 3}};
    return mesh;
}

/// Overwrites `count` bytes at `offset` in an existing file, for the
/// corruption cases below.
void poke(const std::filesystem::path& path, std::size_t offset, const char* data,
          std::size_t count) {
    std::fstream f(path, std::ios::binary | std::ios::in | std::ios::out);
    REQUIRE(f.good());
    f.seekp(static_cast<std::streamoff>(offset));
    f.write(data, static_cast<std::streamsize>(count));
}

} // namespace

TEST_CASE("gmmesh round-trips a mesh exactly", "[gm-io][mesh]") {
    const auto path = temp_mesh_path("roundtrip");
    const MeshData original = tetrahedron();
    REQUIRE(write_gmmesh(original, path).has_value());

    const auto loaded = read_gmmesh(path);
    REQUIRE(loaded.has_value());
    REQUIRE(loaded->vertices.size() == original.vertices.size());
    REQUIRE(loaded->triangles.size() == original.triangles.size());
    for (std::size_t i = 0; i < original.vertices.size(); ++i) {
        // Exact, not approximate: the format stores float64 precisely so a
        // mesh means numerically the same thing after a round trip. A
        // tolerance here would hide a lossy write.
        CHECK(loaded->vertices[i][0] == original.vertices[i][0]);
        CHECK(loaded->vertices[i][1] == original.vertices[i][1]);
        CHECK(loaded->vertices[i][2] == original.vertices[i][2]);
    }
    for (std::size_t i = 0; i < original.triangles.size(); ++i) {
        CHECK(loaded->triangles[i] == original.triangles[i]);
    }
}

TEST_CASE("gmmesh round-trips values that a float32 write would damage",
          "[gm-io][mesh]") {
    // Directly pins the float64 decision in the header comment: each of
    // these survives a double round trip and would not survive a float
    // one.
    const auto path = temp_mesh_path("precision");
    MeshData mesh;
    mesh.vertices = {{0.1, 1.0 / 3.0, 1e-300},
                     {123456789.123456789, -2.718281828459045, 1e300}};
    mesh.triangles = {};
    REQUIRE(write_gmmesh(mesh, path).has_value());

    const auto loaded = read_gmmesh(path);
    REQUIRE(loaded.has_value());
    for (std::size_t i = 0; i < mesh.vertices.size(); ++i) {
        for (std::size_t k = 0; k < 3; ++k) {
            INFO("vertex " << i << " component " << k);
            CHECK(loaded->vertices[i][k] == mesh.vertices[i][k]);
            CHECK(static_cast<double>(static_cast<float>(mesh.vertices[i][k])) !=
                  mesh.vertices[i][k]);
        }
    }
}

TEST_CASE("gmmesh handles an empty mesh", "[gm-io][mesh]") {
    // marching_tetrahedra legitimately returns nothing when the isosurface
    // misses the sampled box entirely, so an empty mesh is a normal artifact
    // and must not be confused with a truncated file.
    const auto path = temp_mesh_path("empty");
    REQUIRE(write_gmmesh(MeshData{}, path).has_value());
    CHECK(std::filesystem::file_size(path) == 24); // header only

    const auto loaded = read_gmmesh(path);
    REQUIRE(loaded.has_value());
    CHECK(loaded->vertices.empty());
    CHECK(loaded->triangles.empty());
}

TEST_CASE("gmmesh refuses to write a triangle that indexes a missing vertex",
          "[gm-io][mesh]") {
    // Leaving this on disk under an immutable run directory would ship an
    // artifact that crashes whatever draws it.
    const auto path = temp_mesh_path("bad-index-write");
    MeshData mesh;
    mesh.vertices = {{0, 0, 0}, {1, 0, 0}, {0, 1, 0}};
    mesh.triangles = {{0, 1, 7}};
    auto result = write_gmmesh(mesh, path);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kValidationFailure);
    CHECK_FALSE(std::filesystem::exists(path));
}

TEST_CASE("gmmesh rejects a file whose magic is wrong", "[gm-io][mesh]") {
    const auto path = temp_mesh_path("bad-magic");
    REQUIRE(write_gmmesh(tetrahedron(), path).has_value());
    poke(path, 0, "XXXXXX", 6);

    auto result = read_gmmesh(path);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("gmmesh refuses a version it does not understand", "[gm-io][mesh]") {
    // ADR-017: consumers validate the version and refuse what they cannot
    // read, rather than reading it hopefully and producing nonsense.
    const auto path = temp_mesh_path("bad-version");
    REQUIRE(write_gmmesh(tetrahedron(), path).has_value());
    const std::uint16_t future = 999;
    poke(path, 6, reinterpret_cast<const char*>(&future), sizeof(future));

    auto result = read_gmmesh(path);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kSchemaVersionMismatch);
}

TEST_CASE("gmmesh rejects a truncated file", "[gm-io][mesh]") {
    const auto path = temp_mesh_path("truncated");
    REQUIRE(write_gmmesh(tetrahedron(), path).has_value());
    const auto full = std::filesystem::file_size(path);
    std::filesystem::resize_file(path, full - 5);

    auto result = read_gmmesh(path);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("gmmesh rejects a header claiming an impossible size without allocating for it",
          "[gm-io][mesh]") {
    // The point of checking length before resizing: a corrupt or hostile
    // header must not be able to request an enormous allocation first and
    // fail second. If this test ever starts failing by running out of memory
    // rather than returning an error, that ordering has been inverted.
    const auto path = temp_mesh_path("absurd-header");
    REQUIRE(write_gmmesh(tetrahedron(), path).has_value());
    const std::uint64_t enormous = 0x0FFFFFFFFFFFFFFFULL;
    poke(path, 8, reinterpret_cast<const char*>(&enormous), sizeof(enormous));

    auto result = read_gmmesh(path);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("gmmesh rejects a correctly-sized file with an out-of-range index",
          "[gm-io][mesh]") {
    // A file can be exactly the length its header implies and still describe
    // a mesh that indexes past the vertex buffer, so the length check alone
    // is not enough.
    const auto path = temp_mesh_path("bad-index-read");
    const MeshData mesh = tetrahedron();
    REQUIRE(write_gmmesh(mesh, path).has_value());
    const std::uint32_t out_of_range = 4; // only 4 vertices, so 4 is one past the end
    poke(path, 24 + mesh.vertices.size() * 24, reinterpret_cast<const char*>(&out_of_range),
         sizeof(out_of_range));

    auto result = read_gmmesh(path);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kValidationFailure);
}

TEST_CASE("gmmesh reports a missing file as not found", "[gm-io][mesh]") {
    auto result = read_gmmesh(std::filesystem::temp_directory_path() / "no-such-file.gmmesh");
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kNotFound);
}

TEST_CASE("gmmesh creates the parent directory it is asked to write into",
          "[gm-io][mesh]") {
    // gm-boundaries writes into runs/<id>/gm-boundaries/surfaces/, which does
    // not exist before the first mesh of a run.
    // Named for this test alone: a shared scratch directory plus a
    // remove_all is the race fixed in universe_test.cpp, and there is no
    // reason to reintroduce it here.
    const auto root = std::filesystem::temp_directory_path() / "gm-mesh-tests" / "creates-parent";
    auto dir = root / "nested" / "surfaces";
    std::filesystem::remove_all(root);
    const auto path = dir / "frame0001.gmmesh";
    REQUIRE(write_gmmesh(tetrahedron(), path).has_value());
    CHECK(std::filesystem::exists(path));
}
