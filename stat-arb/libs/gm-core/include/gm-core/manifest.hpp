#pragma once

// The run/stage manifest (ADR-017). Every stage binary writes one of
// these alongside its output artifacts: what config produced them, what
// git commit and compiler built the binary, what the inputs hashed to,
// how long it took. Every consumer - gm-report, gm-view, the next stage
// in the chain - checks schema_version before trusting anything else in
// the file (ADR-006, ADR-017).
//
// Manifests carry a wall-clock created_at timestamp for human/audit
// purposes only (ADR §3 principle 2, determinism, governs SCORED
// numerical output - it was never a ban on metadata timestamps; nothing
// here feeds back into a computation).

#include <gm-core/error.hpp>

#include <nlohmann/json.hpp>

#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>

namespace gm {

/// The schema version this build of gm-core writes and the newest it
/// will accept on read. Bump on any breaking manifest field change.
inline constexpr std::string_view kManifestSchemaVersion = "1.0.0";

class Manifest {
public:
    /// Starts a new manifest for `stage` (e.g. "gm-ingest") belonging to
    /// `run_id`. `git_commit` and `compiler_id` are supplied by the
    /// caller (populated by CMake at build time) rather than discovered
    /// here - gm-core does not shell out.
    static Manifest create(std::string stage, std::string run_id, std::string git_commit,
                            std::string compiler_id, std::string build_type);

    /// Loads and validates a manifest previously written by `write()`.
    /// Rejects (kSchemaVersionMismatch) any schema_version this build
    /// does not recognize, rather than guessing at forward/backward
    /// compatibility (ADR-017).
    [[nodiscard]] static Result<Manifest> read(const std::filesystem::path& path);

    [[nodiscard]] VoidResult write(const std::filesystem::path& path) const;

    void set_wall_time_seconds(double seconds) { doc_["wall_time_seconds"] = seconds; }
    void set_string(std::string_view key, std::string_view value) { doc_[std::string{key}] = value; }
    void set_int(std::string_view key, std::int64_t value) { doc_[std::string{key}] = value; }
    void set_double(std::string_view key, double value) { doc_[std::string{key}] = value; }
    void set_json(std::string_view key, nlohmann::json value) { doc_[std::string{key}] = std::move(value); }
    void add_input_hash(std::string_view artifact_path, std::string_view sha256_hex);

    [[nodiscard]] std::string schema_version() const;
    [[nodiscard]] std::string stage() const;
    [[nodiscard]] std::string run_id() const;
    [[nodiscard]] const nlohmann::json& raw() const noexcept { return doc_; }

private:
    explicit Manifest(nlohmann::json doc) : doc_(std::move(doc)) {}

    nlohmann::json doc_;
};

} // namespace gm
