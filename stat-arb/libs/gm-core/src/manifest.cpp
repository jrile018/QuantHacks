#include <gm-core/manifest.hpp>

#include <chrono>
#include <cstdio>
#include <ctime>
#include <fstream>

namespace gm {

namespace {

// Deliberately NOT std::format on a chrono type: GCC 13 (the remote
// box's compiler, ADR-004) has incomplete <chrono> formatter support and
// this would silently fail to compile there while working fine under
// MSVC - exactly the kind of cross-platform trap dual-compiler CI exists
// to catch before it reaches a milestone. gmtime_r/snprintf are boring
// and portable to both.
std::string utc_timestamp_now() {
    std::time_t now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &now);
#else
    gmtime_r(&now, &utc);
#endif
    // See the identical comment in date.cpp: oversized for GCC's
    // -Wformat-truncation worst-case analysis on %d given int's full
    // range, not because a UTC timestamp actually needs 96 bytes.
    char buf[96];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ", utc.tm_year + 1900,
                  utc.tm_mon + 1, utc.tm_mday, utc.tm_hour, utc.tm_min, utc.tm_sec);
    return std::string{buf};
}

} // namespace

Manifest Manifest::create(std::string stage, std::string run_id, std::string git_commit,
                           std::string compiler_id, std::string build_type) {
    nlohmann::json doc;
    doc["schema_version"] = std::string{kManifestSchemaVersion};
    doc["stage"] = std::move(stage);
    doc["run_id"] = std::move(run_id);
    doc["git_commit"] = std::move(git_commit);
    doc["compiler_id"] = std::move(compiler_id);
    doc["build_type"] = std::move(build_type);
    doc["created_at_utc"] = utc_timestamp_now();
    doc["wall_time_seconds"] = 0.0;
    doc["input_hashes"] = nlohmann::json::object();
    return Manifest{std::move(doc)};
}

void Manifest::add_input_hash(std::string_view artifact_path, std::string_view sha256_hex) {
    doc_["input_hashes"][std::string{artifact_path}] = std::string{sha256_hex};
}

std::string Manifest::schema_version() const {
    return doc_.value("schema_version", std::string{});
}

std::string Manifest::stage() const { return doc_.value("stage", std::string{}); }

std::string Manifest::run_id() const { return doc_.value("run_id", std::string{}); }

VoidResult Manifest::write(const std::filesystem::path& path) const {
    std::error_code ec;
    auto parent = path.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent, ec);
        if (ec) {
            return tl::unexpected(Error::make(ErrorCode::kIoFailure,
                                               "failed to create manifest directory",
                                               parent.string() + ": " + ec.message()));
        }
    }

    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) {
        return tl::unexpected(
            Error::make(ErrorCode::kIoFailure, "failed to open manifest for writing", path.string()));
    }
    out << doc_.dump(2);
    if (!out) {
        return tl::unexpected(
            Error::make(ErrorCode::kIoFailure, "failed writing manifest contents", path.string()));
    }
    return {};
}

Result<Manifest> Manifest::read(const std::filesystem::path& path) {
    std::error_code ec;
    if (!std::filesystem::exists(path, ec)) {
        return tl::unexpected(Error::make(ErrorCode::kNotFound, "manifest not found", path.string()));
    }

    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return tl::unexpected(
            Error::make(ErrorCode::kIoFailure, "failed to open manifest", path.string()));
    }

    nlohmann::json doc;
    try {
        in >> doc;
    } catch (const nlohmann::json::parse_error& e) {
        return tl::unexpected(
            Error::make(ErrorCode::kParseFailure, "manifest JSON parse error",
                        path.string() + ": " + e.what()));
    }

    Manifest manifest{std::move(doc)};
    if (manifest.schema_version() != kManifestSchemaVersion) {
        return tl::unexpected(Error::make(
            ErrorCode::kSchemaVersionMismatch, "unsupported manifest schema_version",
            path.string() + ": got '" + manifest.schema_version() + "', expected '" +
                std::string{kManifestSchemaVersion} + "'"));
    }
    return manifest;
}

} // namespace gm
