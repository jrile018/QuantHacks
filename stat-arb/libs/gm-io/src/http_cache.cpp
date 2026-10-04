#include <gm-io/http_cache.hpp>

#include <cpr/cpr.h>
#include <nlohmann/json.hpp>

#include <chrono>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <sstream>
#include <thread>

namespace gm::io {

namespace {

// Same rationale as gm-core/manifest.cpp: no std::format on chrono
// types (GCC 13's <chrono> formatter support is incomplete), and no
// wall-clock use anywhere except this purely-informational timestamp.
std::string utc_timestamp_now() {
    std::time_t now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &now);
#else
    gmtime_r(&now, &utc);
#endif
    char buf[96];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ", utc.tm_year + 1900,
                  utc.tm_mon + 1, utc.tm_mday, utc.tm_hour, utc.tm_min, utc.tm_sec);
    return std::string{buf};
}

/// Rejects a cache_key that could escape cache_dir or collide with the
/// sidecar naming scheme - defense in depth for keys that ultimately
/// derive from external data (ticker symbols, CIK strings), even though
/// every current caller is our own trusted code.
gm::VoidResult validate_cache_key(std::string_view cache_key) {
    if (cache_key.empty()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument, "cache_key is empty"));
    }
    if (cache_key.find("..") != std::string_view::npos ||
        cache_key.find('/') != std::string_view::npos ||
        cache_key.find('\\') != std::string_view::npos) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "cache_key must not contain '/', '\\', or '..'",
                                               std::string{cache_key}));
    }
    return {};
}

} // namespace

Result<std::string> CacheEntry::read_body() const {
    std::ifstream in(body_path, std::ios::binary);
    if (!in) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                               "failed to open cached body", body_path.string()));
    }
    std::ostringstream buf;
    buf << in.rdbuf();
    return buf.str();
}

HttpCache::HttpCache(std::filesystem::path cache_dir) : cache_dir_(std::move(cache_dir)) {}

std::filesystem::path HttpCache::body_path(std::string_view cache_key) const {
    return cache_dir_ / (std::string{cache_key} + ".body");
}

std::filesystem::path HttpCache::meta_path(std::string_view cache_key) const {
    return cache_dir_ / (std::string{cache_key} + ".meta.json");
}

Result<CacheEntry> HttpCache::read_cached(std::string_view cache_key) const {
    if (auto v = validate_cache_key(cache_key); !v) return tl::unexpected(v.error());

    auto mpath = meta_path(cache_key);
    std::error_code ec;
    if (!std::filesystem::exists(mpath, ec)) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "no cache entry", std::string{cache_key}));
    }

    std::ifstream in(mpath, std::ios::binary);
    if (!in) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to open cache metadata", mpath.string()));
    }

    nlohmann::json meta;
    try {
        in >> meta;
    } catch (const nlohmann::json::parse_error& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "malformed cache metadata",
                                               mpath.string() + ": " + e.what()));
    }

    CacheEntry entry;
    entry.body_path = body_path(cache_key);
    entry.url = meta.value("url", std::string{});
    entry.fetched_at_utc = meta.value("fetched_at_utc", std::string{});
    entry.status_code = meta.value("status_code", 0L);
    entry.content_length = meta.value("content_length", std::uintmax_t{0});

    if (!std::filesystem::exists(entry.body_path, ec)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNotFound,
                                               "cache metadata present but body file is missing",
                                               entry.body_path.string()));
    }

    return entry;
}

namespace {
gm::VoidResult check_status(const CacheEntry& entry) {
    if (entry.status_code < 200 || entry.status_code >= 300) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kIoFailure, "cached response has a non-2xx status",
            entry.url + ": status " + std::to_string(entry.status_code)));
    }
    return {};
}
} // namespace

Result<CacheEntry> HttpCache::get(const std::string& url, std::string_view cache_key,
                                   bool force_refresh) {
    if (auto v = validate_cache_key(cache_key); !v) return tl::unexpected(v.error());

    if (!force_refresh) {
        if (auto cached = read_cached(cache_key)) {
            // Applied here too, not just on the fresh-fetch path below,
            // so get()'s contract - "a usable 2xx response, or an error"
            // - holds identically whether this call fetched or hit the
            // cache. Without this, a persistent 404 would surface as a
            // failure on the first call (which wrote the cache) and
            // silently succeed on every later call that reads it back -
            // an inconsistency that would let gm-ingest treat a cached
            // 404 body as valid price data on a resumed run.
            if (auto status = check_status(*cached); !status) return tl::unexpected(status.error());
            return cached;
        }
        // Fall through to fetch on any read_cached failure (missing,
        // corrupt, or partial) - a bad cache entry should self-heal on
        // the next fetch, not wedge the pipeline.
    }

    std::error_code ec;
    std::filesystem::create_directories(cache_dir_, ec);
    if (ec) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                               "failed to create cache directory",
                                               cache_dir_.string() + ": " + ec.message()));
    }

    // A descriptive User-Agent plus retry-with-backoff on 429/5xx - both
    // discovered necessary the hard way during M1's real gm-ingest
    // fetches: an unadorned client hitting Yahoo's endpoint 10 times in
    // under a second got rate-limited (HTTP 429) on nearly every
    // request. This lives in the general-purpose cache, not gm-ingest,
    // because any caller of gm-io hitting any real API will eventually
    // need the same thing.
    static constexpr int kMaxAttempts = 4;
    static constexpr int kBaseBackoffMs = 500;

    cpr::Response response;
    for (int attempt = 0; attempt < kMaxAttempts; ++attempt) {
        response = cpr::Get(cpr::Url{url}, cpr::Timeout{30000},
                             cpr::Header{{"User-Agent", "geomarket-research/0.1 (+M1 gm-ingest)"}});

        if (response.error) break;  // network-level failure - not retryable here
        bool retryable = response.status_code == 429 ||
                          (response.status_code >= 500 && response.status_code < 600);
        if (!retryable) break;
        if (attempt + 1 < kMaxAttempts) {
            std::this_thread::sleep_for(
                std::chrono::milliseconds(kBaseBackoffMs << attempt));  // 500ms, 1s, 2s
        }
    }

    if (response.error) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kIoFailure, "HTTP request failed",
            url + ": " + response.error.message));
    }

    auto bpath = body_path(cache_key);
    {
        std::ofstream out(bpath, std::ios::binary | std::ios::trunc);
        if (!out) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                                   "failed to write cached body", bpath.string()));
        }
        out.write(response.text.data(), static_cast<std::streamsize>(response.text.size()));
        if (!out) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                                   "failed writing cached body contents",
                                                   bpath.string()));
        }
    }

    CacheEntry entry;
    entry.body_path = bpath;
    entry.url = url;
    entry.fetched_at_utc = utc_timestamp_now();
    entry.status_code = static_cast<long>(response.status_code);
    entry.content_length = response.text.size();

    nlohmann::json meta;
    meta["url"] = entry.url;
    meta["fetched_at_utc"] = entry.fetched_at_utc;
    meta["status_code"] = entry.status_code;
    meta["content_length"] = entry.content_length;

    {
        std::ofstream out(meta_path(cache_key), std::ios::binary | std::ios::trunc);
        if (!out) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                                   "failed to write cache metadata",
                                                   meta_path(cache_key).string()));
        }
        out << meta.dump(2);
    }

    if (auto status = check_status(entry); !status) return tl::unexpected(status.error());

    return entry;
}

} // namespace gm::io
