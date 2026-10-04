#pragma once

// Parquet read/write for gm::io::Table (ADR-017: Parquet is the
// artifact format for tabular data). Arrow types never cross this
// header's boundary - callers work with Table only.

#include <gm-core/error.hpp>
#include <gm-io/table.hpp>

#include <filesystem>

namespace gm::io {

[[nodiscard]] gm::VoidResult write_parquet(const Table& table, const std::filesystem::path& path);
[[nodiscard]] Result<Table> read_parquet(const std::filesystem::path& path);

} // namespace gm::io
