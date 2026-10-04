#pragma once

// A minimal, typed, in-memory columnar table - the shape every gm-*
// stage actually needs (a handful of named typed columns, all the same
// length), independent of Arrow in its public interface so callers
// never touch Arrow types directly. gm-io/parquet.hpp converts to and
// from Arrow only at the read_parquet/write_parquet boundary.

#include <gm-core/error.hpp>

#include <cstdint>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

namespace gm::io {

enum class ColumnType { kString, kInt64, kDouble, kBool };

/// bool is stored as uint8_t (0/1), not std::vector<bool>, because the
/// latter's bit-packed specialization has no contiguous storage to hand
/// to Arrow's builder API - this sidesteps that entirely rather than
/// working around it at the parquet.cpp call site.
class Table {
public:
    Table() = default;

    /// Every add_*_column call must supply exactly num_rows() values,
    /// except the very first column added (which establishes
    /// num_rows()). Column names must be unique. Violating either
    /// returns an error rather than asserting: these ARE programming
    /// errors in the caller, but ADR §3 principle 1 ("correctness is
    /// provable, not assumed") outranks the usual C++ convention of
    /// asserting on caller contracts - and concretely, this project's
    /// own RelWithDebInfo build (used for every "release" test run)
    /// defines NDEBUG by default, which would have compiled an assert
    /// here to a silent no-op in exactly the build configuration this
    /// codebase actually ships and tests.
    [[nodiscard]] gm::VoidResult add_string_column(std::string name, std::vector<std::string> values);
    [[nodiscard]] gm::VoidResult add_int64_column(std::string name, std::vector<std::int64_t> values);
    [[nodiscard]] gm::VoidResult add_double_column(std::string name, std::vector<double> values);
    [[nodiscard]] gm::VoidResult add_bool_column(std::string name, std::vector<std::uint8_t> values);

    [[nodiscard]] std::size_t num_rows() const noexcept { return num_rows_; }
    [[nodiscard]] std::size_t num_columns() const noexcept { return columns_.size(); }
    [[nodiscard]] const std::vector<std::string>& column_names() const noexcept { return column_names_; }

    [[nodiscard]] bool has_column(std::string_view name) const noexcept;
    [[nodiscard]] Result<ColumnType> column_type(std::string_view name) const;

    [[nodiscard]] Result<std::vector<std::string>> string_column(std::string_view name) const;
    [[nodiscard]] Result<std::vector<std::int64_t>> int64_column(std::string_view name) const;
    [[nodiscard]] Result<std::vector<double>> double_column(std::string_view name) const;
    [[nodiscard]] Result<std::vector<std::uint8_t>> bool_column(std::string_view name) const;

private:
    using ColumnData = std::variant<std::vector<std::string>, std::vector<std::int64_t>,
                                     std::vector<double>, std::vector<std::uint8_t>>;

    struct Column {
        std::string name;
        ColumnType type;
        ColumnData data;
    };

    [[nodiscard]] gm::VoidResult add_column_checked(std::string name, ColumnType type, ColumnData data,
                                                      std::size_t values_size);
    [[nodiscard]] const Column* find(std::string_view name) const noexcept;

    std::vector<Column> columns_;
    std::vector<std::string> column_names_;
    std::size_t num_rows_ = 0;
};

} // namespace gm::io
