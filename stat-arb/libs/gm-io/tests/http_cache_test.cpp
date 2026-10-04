// Hermetic tests only - no live network calls. The actual cpr::Get
// fetch path is exercised for real during gm-ingest development against
// the real data sources (ADR §7.2); a unit test suite that depends on
// network reachability is flaky by construction and not worth it here.
// What IS unit-tested: cache_key validation, reading back a hand-written
// cache entry (bypassing the network path entirely), and the
// consistency property that a cached non-2xx response is reported as an
// error identically whether it was just fetched or read from cache.

#include <gm-io/http_cache.hpp>

#include <catch2/catch_test_macros.hpp>

#include <filesystem>
#include <fstream>

using gm::io::HttpCache;

namespace {
/// A cache directory of this test's own. Same reasoning as
/// universe_test.cpp's write_fixture: these tests run as concurrent
/// processes under `ctest -j`, and four of them ended with
/// remove_all(dir) on what used to be a single shared directory. That had
/// not yet been observed failing here, but it is the identical race and
/// worth closing while it is understood rather than after it bites.
std::filesystem::path temp_cache_dir(const char* test_name) {
    return std::filesystem::temp_directory_path() / "gm-io-tests" / "http_cache" / test_name;
}

void write_fake_cache_entry(const std::filesystem::path& dir, const std::string& key,
                             const std::string& body, long status_code) {
    std::filesystem::create_directories(dir);
    {
        std::ofstream out(dir / (key + ".body"), std::ios::binary | std::ios::trunc);
        out << body;
    }
    {
        std::ofstream out(dir / (key + ".meta.json"), std::ios::binary | std::ios::trunc);
        out << "{\"url\": \"http://example.invalid/" << key << "\", "
            << "\"fetched_at_utc\": \"2026-01-01T00:00:00Z\", "
            << "\"status_code\": " << status_code << ", "
            << "\"content_length\": " << body.size() << "}";
    }
}
} // namespace

TEST_CASE("read_cached reads back a hand-written cache entry", "[http_cache]") {
    auto dir = temp_cache_dir("read_cached_hand_written");
    write_fake_cache_entry(dir, "fake_ok", "hello world", 200);

    HttpCache cache{dir};
    auto entry = cache.read_cached("fake_ok");
    REQUIRE(entry.has_value());
    CHECK(entry->status_code == 200);
    CHECK(entry->url == "http://example.invalid/fake_ok");

    auto body = entry->read_body();
    REQUIRE(body.has_value());
    CHECK(*body == "hello world");

    std::filesystem::remove_all(dir);
}

TEST_CASE("read_cached fails cleanly when nothing is cached", "[http_cache]") {
    auto dir = temp_cache_dir("read_cached_missing");
    std::filesystem::remove_all(dir);

    HttpCache cache{dir};
    auto entry = cache.read_cached("never_written");
    REQUIRE_FALSE(entry.has_value());
    CHECK(entry.error().code == gm::ErrorCode::kNotFound);
}

TEST_CASE("get() reports a cached non-2xx response as an error, not a silent success",
          "[http_cache]") {
    auto dir = temp_cache_dir("non_2xx_cached");
    write_fake_cache_entry(dir, "fake_404", "not found", 404);

    HttpCache cache{dir};
    // force_refresh=false, so this hits the cache-read path, not the
    // network path - exercises get()'s consistency guarantee (a cached
    // non-2xx is an error on every call, not just the one that wrote it).
    auto result = cache.get("http://example.invalid/fake_404", "fake_404", /*force_refresh=*/false);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kIoFailure);

    // But the raw entry is still readable directly for a caller that
    // wants to inspect it (e.g. to distinguish a 404 from a 500).
    auto raw = cache.read_cached("fake_404");
    REQUIRE(raw.has_value());
    CHECK(raw->status_code == 404);

    std::filesystem::remove_all(dir);
}

TEST_CASE("empty cache_key is rejected", "[http_cache]") {
    HttpCache cache{temp_cache_dir("path_traversal")};
    auto result = cache.read_cached("");
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("cache_key with path traversal characters is rejected", "[http_cache]") {
    HttpCache cache{temp_cache_dir("path_traversal")};

    for (const char* bad_key : {"../escape", "sub/dir", "back\\slash"}) {
        auto result = cache.read_cached(bad_key);
        REQUIRE_FALSE(result.has_value());
        CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
    }
}

TEST_CASE("a cache entry with metadata but a missing body file fails cleanly", "[http_cache]") {
    auto dir = temp_cache_dir("metadata_without_body");
    write_fake_cache_entry(dir, "fake_partial", "body content", 200);
    std::filesystem::remove(dir / "fake_partial.body");  // simulate a partial/corrupted cache

    HttpCache cache{dir};
    auto entry = cache.read_cached("fake_partial");
    REQUIRE_FALSE(entry.has_value());
    CHECK(entry.error().code == gm::ErrorCode::kNotFound);

    std::filesystem::remove_all(dir);
}
