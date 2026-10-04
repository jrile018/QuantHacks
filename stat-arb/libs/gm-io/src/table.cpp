#include <gm-io/table.hpp>

namespace gm::io {

const Table::Column* Table::find(std::string_view name) const noexcept {
    for (const auto& col : columns_) {
        if (col.name == name) return &col;
    }
    return nullptr;
}

gm::VoidResult Table::add_column_checked(std::string name, ColumnType type, ColumnData data,
                                          std::size_t values_size) {
    if (find(name) != nullptr) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kInvalidArgument, "Table: duplicate column name", name));
    }
    if (!columns_.empty() && values_size != num_rows_) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument, "Table: column length does not match table's row count",
            name + ": table has " + std::to_string(num_rows_) + " rows, column has " +
                std::to_string(values_size)));
    }
    if (columns_.empty()) {
        num_rows_ = values_size;
    }
    column_names_.push_back(name);
    columns_.push_back(Column{std::move(name), type, std::move(data)});
    return {};
}

gm::VoidResult Table::add_string_column(std::string name, std::vector<std::string> values) {
    std::size_t n = values.size();
    return add_column_checked(std::move(name), ColumnType::kString, ColumnData{std::move(values)}, n);
}

gm::VoidResult Table::add_int64_column(std::string name, std::vector<std::int64_t> values) {
    std::size_t n = values.size();
    return add_column_checked(std::move(name), ColumnType::kInt64, ColumnData{std::move(values)}, n);
}

gm::VoidResult Table::add_double_column(std::string name, std::vector<double> values) {
    std::size_t n = values.size();
    return add_column_checked(std::move(name), ColumnType::kDouble, ColumnData{std::move(values)}, n);
}

gm::VoidResult Table::add_bool_column(std::string name, std::vector<std::uint8_t> values) {
    std::size_t n = values.size();
    return add_column_checked(std::move(name), ColumnType::kBool, ColumnData{std::move(values)}, n);
}

bool Table::has_column(std::string_view name) const noexcept { return find(name) != nullptr; }

Result<ColumnType> Table::column_type(std::string_view name) const {
    if (const auto* col = find(name)) return col->type;
    return tl::unexpected(
        gm::Error::make(gm::ErrorCode::kNotFound, "no such column", std::string{name}));
}

// Note: deliberately four small near-identical bodies rather than one
// shared free-function template - a shared helper would need to name
// Table::Column/Table::ColumnData in its signature, and both are
// private nested types inaccessible outside Table's own member
// functions. Duplicating four short lookups is cheaper than the
// friend-declaration plumbing to share it.

Result<std::vector<std::string>> Table::string_column(std::string_view name) const {
    const Column* col = find(name);
    if (col == nullptr) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "no such column", std::string{name}));
    }
    if (col->type != ColumnType::kString) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "column type mismatch", std::string{name}));
    }
    return std::get<std::vector<std::string>>(col->data);
}

Result<std::vector<std::int64_t>> Table::int64_column(std::string_view name) const {
    const Column* col = find(name);
    if (col == nullptr) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "no such column", std::string{name}));
    }
    if (col->type != ColumnType::kInt64) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "column type mismatch", std::string{name}));
    }
    return std::get<std::vector<std::int64_t>>(col->data);
}

Result<std::vector<double>> Table::double_column(std::string_view name) const {
    const Column* col = find(name);
    if (col == nullptr) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "no such column", std::string{name}));
    }
    if (col->type != ColumnType::kDouble) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "column type mismatch", std::string{name}));
    }
    return std::get<std::vector<double>>(col->data);
}

Result<std::vector<std::uint8_t>> Table::bool_column(std::string_view name) const {
    const Column* col = find(name);
    if (col == nullptr) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "no such column", std::string{name}));
    }
    if (col->type != ColumnType::kBool) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "column type mismatch", std::string{name}));
    }
    return std::get<std::vector<std::uint8_t>>(col->data);
}

} // namespace gm::io
