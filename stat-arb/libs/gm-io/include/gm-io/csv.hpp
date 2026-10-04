#pragma once

// Hand-rolled RFC-4180 CSV parsing (ADR-005: "formats are known and
// fixed; a hand-rolled RFC-4180 reader with tests beats a dependency").
// Handles quoted fields (including embedded delimiters, embedded
// newlines, and "" as an escaped quote), both CRLF and LF line endings,
// and a trailing newline with or without a final blank line.

#include <gm-core/error.hpp>

#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace gm::io {

struct CsvTable {
    std::vector<std::string> header;
    std::vector<std::vector<std::string>> rows;  // every row.size() == header.size()

    /// Case-sensitive header lookup. Returns nullopt if not found.
    [[nodiscard]] std::optional<std::size_t> column_index(std::string_view name) const;
};

/// Parses CSV text already in memory. The first line is always treated
/// as the header. Every data row must have the same field count as the
/// header - a short or long row is a parse error (ADR-015 spirit:
/// malformed input is an error, not a best-effort partial parse), since
/// silently accepting a ragged row is exactly the kind of thing that
/// produces a misaligned column downstream with no visible symptom.
[[nodiscard]] Result<CsvTable> parse_csv(std::string_view text, char delimiter = ',');

/// Reads and parses a CSV file from disk.
[[nodiscard]] Result<CsvTable> read_csv_file(const std::filesystem::path& path, char delimiter = ',');

} // namespace gm::io
