#pragma once

// HTTP fetch with a mandatory on-disk cache (ADR-015: "All raw pulls are
// cached to disk with a fetch timestamp so a run is reproducible even
// after the upstream data changes"). There is no plain uncached fetch
// exposed at this layer on purpose - every caller of gm-io goes through
// the cache, so "reproducible from cached raw data" isn't something a
// caller can accidentally opt out of.
//
// Cache layout: <cache_dir>/<cache_key>.body (raw response bytes) and
// <cache_dir>/<cache_key>.meta.json (url, fetched_at_utc, status_code,
// content length - enough to audit what a run actually saw). The caller
// supplies cache_key rather than this module hashing the URL: a
// meaningful key ("stooq_aapl_daily", "sec_cik_0000320193") is more
// debuggable in a directory listing than a hash, and keeps cache
// filenames stable across trivial URL changes (e.g. a query param
// reordering) that shouldn't invalidate anything.

#include <gm-core/error.hpp>

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>

namespace gm::io {

struct CacheEntry {
    std::filesystem::path body_path;
    std::string url;
    std::string fetched_at_utc;
    long status_code = 0;
    std::uintmax_t content_length = 0;

    /// Reads the cached body into memory. Separate from fetching it
    /// because callers of a large CSV may prefer to stream the file
    /// path (e.g. into a CSV parser) rather than materialize it twice.
    [[nodiscard]] Result<std::string> read_body() const;
};

class HttpCache {
public:
    explicit HttpCache(std::filesystem::path cache_dir);

    /// Returns the cached entry for `cache_key` if one exists on disk
    /// and `force_refresh` is false; otherwise performs a real HTTP GET
    /// against `url`, writes both the body and a metadata sidecar to
    /// the cache, and returns the freshly-written entry.
    ///
    /// A non-2xx HTTP response is still written to the cache (so a
    /// persistent 404 doesn't get re-fetched every run) but this call
    /// still reports it as an error, on both the fetch path and a later
    /// cache-hit path alike - get()'s contract is "a usable 2xx
    /// response, or an error", full stop. A caller that specifically
    /// wants to inspect a cached error response's status_code without
    /// that being surfaced as a Result failure should call
    /// read_cached() directly instead.
    [[nodiscard]] Result<CacheEntry> get(const std::string& url, std::string_view cache_key,
                                          bool force_refresh = false);

    /// Reads back a previously-written cache entry without performing
    /// any network activity. Returns kNotFound if nothing is cached
    /// under this key yet.
    [[nodiscard]] Result<CacheEntry> read_cached(std::string_view cache_key) const;

private:
    std::filesystem::path cache_dir_;

    [[nodiscard]] std::filesystem::path body_path(std::string_view cache_key) const;
    [[nodiscard]] std::filesystem::path meta_path(std::string_view cache_key) const;
};

} // namespace gm::io
