#pragma once

// Thin, typed wrapper over toml++ (ADR-005: TOML chosen over YAML
// specifically to avoid YAML's implicit type-coercion traps - "NO" is a
// string, not a bool, here). Every stage binary loads exactly one Config
// from its --config flag (ADR-006) before doing anything else; loading
// is the one place in the system exceptions are tolerated (ADR-019),
// because a malformed config should fail loudly and immediately, not
// propagate as a Result the caller might not check.

#include <gm-core/error.hpp>

#include <toml++/toml.h>

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>

namespace gm {

/// Read-only view over a parsed TOML document, with typed accessors that
/// return gm::Result instead of throwing or silently defaulting.
class Config {
public:
    /// Parses `path`. Returns an error (never throws) on missing file or
    /// malformed TOML - a stage should surface this and exit non-zero,
    /// not guess at defaults.
    [[nodiscard]] static Result<Config> load(const std::filesystem::path& path);

    /// Parses TOML directly from a string - primarily for tests, so
    /// fixtures don't need a file on disk.
    [[nodiscard]] static Result<Config> parse(std::string_view toml_text);

    /// Dotted key path, e.g. "geometry.window_days".
    [[nodiscard]] Result<std::int64_t> get_int(std::string_view dotted_key) const;
    [[nodiscard]] Result<double> get_double(std::string_view dotted_key) const;
    [[nodiscard]] Result<std::string> get_string(std::string_view dotted_key) const;
    [[nodiscard]] Result<bool> get_bool(std::string_view dotted_key) const;

    [[nodiscard]] std::int64_t get_int_or(std::string_view dotted_key, std::int64_t fallback) const;
    [[nodiscard]] double get_double_or(std::string_view dotted_key, double fallback) const;
    [[nodiscard]] std::string get_string_or(std::string_view dotted_key, std::string fallback) const;
    [[nodiscard]] bool get_bool_or(std::string_view dotted_key, bool fallback) const;

    [[nodiscard]] bool has(std::string_view dotted_key) const;

    /// The raw underlying table, for callers that need iteration (e.g.
    /// gm-universe walking a list of manual-addition tickers) beyond
    /// what the typed accessors above cover.
    [[nodiscard]] const toml::table& raw() const noexcept { return table_; }

private:
    explicit Config(toml::table table) : table_(std::move(table)) {}

    toml::table table_;
};

} // namespace gm
