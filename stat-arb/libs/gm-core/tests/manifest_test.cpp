#include <gm-core/manifest.hpp>

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>

using gm::Manifest;

namespace {
std::filesystem::path temp_manifest_path(const char* name) {
    return std::filesystem::temp_directory_path() / "gm-core-tests" / name;
}
} // namespace

TEST_CASE("create populates the mandatory fields", "[manifest]") {
    auto m = Manifest::create("gm-ingest", "2026-08-29__test", "abc1234", "GCC 13.3.0",
                               "RelWithDebInfo");
    CHECK(m.schema_version() == gm::kManifestSchemaVersion);
    CHECK(m.stage() == "gm-ingest");
    CHECK(m.run_id() == "2026-08-29__test");
    CHECK(m.raw().contains("created_at_utc"));
    CHECK(m.raw().contains("git_commit"));
    CHECK(m.raw()["git_commit"] == "abc1234");
}

TEST_CASE("write then read round-trips through JSON on disk", "[manifest]") {
    auto path = temp_manifest_path("roundtrip.json");

    auto m = Manifest::create("gm-geometry", "run-42", "deadbeef", "MSVC 19.43", "Debug");
    m.set_int("rows_written", 12345);
    m.set_double("wall_time_seconds", 1.5);
    m.add_input_hash("prices.parquet", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");

    auto write_result = m.write(path);
    REQUIRE(write_result.has_value());

    auto read_result = Manifest::read(path);
    REQUIRE(read_result.has_value());
    CHECK(read_result->stage() == "gm-geometry");
    CHECK(read_result->run_id() == "run-42");
    CHECK(read_result->raw()["rows_written"] == 12345);
    CHECK(read_result->raw()["input_hashes"].contains("prices.parquet"));

    std::filesystem::remove(path);
}

TEST_CASE("read rejects a manifest with an unrecognized schema_version", "[manifest]") {
    auto path = temp_manifest_path("bad_schema.json");
    std::filesystem::create_directories(path.parent_path());
    {
        std::ofstream out(path);
        out << R"({"schema_version": "99.0.0", "stage": "x", "run_id": "y"})";
    }

    auto read_result = Manifest::read(path);
    REQUIRE_FALSE(read_result.has_value());
    CHECK(read_result.error().code == gm::ErrorCode::kSchemaVersionMismatch);

    std::filesystem::remove(path);
}

TEST_CASE("read fails cleanly on a missing file", "[manifest]") {
    auto read_result = Manifest::read(temp_manifest_path("does_not_exist.json"));
    REQUIRE_FALSE(read_result.has_value());
    CHECK(read_result.error().code == gm::ErrorCode::kNotFound);
}

TEST_CASE("read fails cleanly on malformed JSON", "[manifest]") {
    auto path = temp_manifest_path("malformed.json");
    std::filesystem::create_directories(path.parent_path());
    {
        std::ofstream out(path);
        out << "{ not valid json ";
    }

    auto read_result = Manifest::read(path);
    REQUIRE_FALSE(read_result.has_value());
    CHECK(read_result.error().code == gm::ErrorCode::kParseFailure);

    std::filesystem::remove(path);
}
