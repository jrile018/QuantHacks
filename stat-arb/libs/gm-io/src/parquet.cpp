#include <gm-io/parquet.hpp>

#include <arrow/api.h>
#include <arrow/io/file.h>
#include <parquet/arrow/reader.h>
#include <parquet/arrow/writer.h>

namespace gm::io {

namespace {

// Deliberately NOT using ARROW_ASSIGN_OR_RAISE / PARQUET_ASSIGN_OR_THROW
// here: those throw on error, which violates ADR-019 ("exceptions only
// at startup/config, Result<T> everywhere else"). Every arrow::Result<T>
// is checked by hand instead.

gm::Error arrow_status_error(gm::ErrorCode code, std::string_view what,
                              const arrow::Status& status) {
    return gm::Error::make(code, std::string{what}, status.ToString());
}

/// Builds one Arrow array from one Table column. Returns the array plus
/// the arrow::Field describing it (name + type), so the caller can
/// assemble both the schema and the column list from a single pass.
Result<std::pair<std::shared_ptr<arrow::Field>, std::shared_ptr<arrow::Array>>> build_column(
    const Table& table, const std::string& name) {
    auto type_result = table.column_type(name);
    if (!type_result) return tl::unexpected(type_result.error());

    switch (*type_result) {
        case ColumnType::kString: {
            auto values = table.string_column(name);
            if (!values) return tl::unexpected(values.error());
            arrow::StringBuilder builder;
            auto st = builder.AppendValues(*values);
            if (!st.ok()) {
                return tl::unexpected(
                    arrow_status_error(gm::ErrorCode::kIoFailure, "AppendValues (string)", st));
            }
            auto finish = builder.Finish();
            if (!finish.ok()) {
                return tl::unexpected(arrow_status_error(gm::ErrorCode::kIoFailure,
                                                           "Finish (string builder)",
                                                           finish.status()));
            }
            return std::make_pair(arrow::field(name, arrow::utf8()), *finish);
        }
        case ColumnType::kInt64: {
            auto values = table.int64_column(name);
            if (!values) return tl::unexpected(values.error());
            arrow::Int64Builder builder;
            auto st = builder.AppendValues(*values);
            if (!st.ok()) {
                return tl::unexpected(
                    arrow_status_error(gm::ErrorCode::kIoFailure, "AppendValues (int64)", st));
            }
            auto finish = builder.Finish();
            if (!finish.ok()) {
                return tl::unexpected(arrow_status_error(
                    gm::ErrorCode::kIoFailure, "Finish (int64 builder)", finish.status()));
            }
            return std::make_pair(arrow::field(name, arrow::int64()), *finish);
        }
        case ColumnType::kDouble: {
            auto values = table.double_column(name);
            if (!values) return tl::unexpected(values.error());
            arrow::DoubleBuilder builder;
            auto st = builder.AppendValues(*values);
            if (!st.ok()) {
                return tl::unexpected(
                    arrow_status_error(gm::ErrorCode::kIoFailure, "AppendValues (double)", st));
            }
            auto finish = builder.Finish();
            if (!finish.ok()) {
                return tl::unexpected(arrow_status_error(
                    gm::ErrorCode::kIoFailure, "Finish (double builder)", finish.status()));
            }
            return std::make_pair(arrow::field(name, arrow::float64()), *finish);
        }
        case ColumnType::kBool: {
            auto values = table.bool_column(name);
            if (!values) return tl::unexpected(values.error());
            arrow::BooleanBuilder builder;
            auto st = builder.AppendValues(values->data(), static_cast<int64_t>(values->size()));
            if (!st.ok()) {
                return tl::unexpected(
                    arrow_status_error(gm::ErrorCode::kIoFailure, "AppendValues (bool)", st));
            }
            auto finish = builder.Finish();
            if (!finish.ok()) {
                return tl::unexpected(arrow_status_error(
                    gm::ErrorCode::kIoFailure, "Finish (bool builder)", finish.status()));
            }
            return std::make_pair(arrow::field(name, arrow::boolean()), *finish);
        }
    }
    return tl::unexpected(
        gm::Error::make(gm::ErrorCode::kUnknown, "unreachable: unhandled ColumnType"));
}

} // namespace

gm::VoidResult write_parquet(const Table& table, const std::filesystem::path& path) {
    std::vector<std::shared_ptr<arrow::Field>> fields;
    std::vector<std::shared_ptr<arrow::Array>> arrays;
    fields.reserve(table.num_columns());
    arrays.reserve(table.num_columns());

    for (const auto& name : table.column_names()) {
        auto built = build_column(table, name);
        if (!built) return tl::unexpected(built.error());
        fields.push_back(built->first);
        arrays.push_back(built->second);
    }

    auto schema = arrow::schema(fields);
    auto arrow_table = arrow::Table::Make(schema, arrays, static_cast<int64_t>(table.num_rows()));

    std::error_code ec;
    auto parent = path.parent_path();
    if (!parent.empty()) {
        std::filesystem::create_directories(parent, ec);
        if (ec) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kIoFailure,
                                                   "failed to create parquet output directory",
                                                   parent.string() + ": " + ec.message()));
        }
    }

    auto maybe_outfile = arrow::io::FileOutputStream::Open(path.string());
    if (!maybe_outfile.ok()) {
        return tl::unexpected(arrow_status_error(gm::ErrorCode::kIoFailure,
                                                  "failed to open parquet output file (" +
                                                      path.string() + ")",
                                                  maybe_outfile.status()));
    }
    std::shared_ptr<arrow::io::FileOutputStream> outfile = *maybe_outfile;

    // One row group for the whole table - these artifacts are small
    // (per-run, per-ticker scale), not the multi-GB case row-group
    // tuning exists for.
    int64_t chunk_size = static_cast<int64_t>(table.num_rows());
    if (chunk_size <= 0) chunk_size = 1;

    arrow::Status write_status =
        parquet::arrow::WriteTable(*arrow_table, arrow::default_memory_pool(), outfile, chunk_size);
    if (!write_status.ok()) {
        return tl::unexpected(arrow_status_error(
            gm::ErrorCode::kIoFailure, "failed writing parquet table (" + path.string() + ")",
            write_status));
    }

    arrow::Status close_status = outfile->Close();
    if (!close_status.ok()) {
        return tl::unexpected(arrow_status_error(
            gm::ErrorCode::kIoFailure, "failed closing parquet output file (" + path.string() + ")",
            close_status));
    }

    return {};
}

Result<Table> read_parquet(const std::filesystem::path& path) {
    std::error_code ec;
    if (!std::filesystem::exists(path, ec)) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kNotFound, "parquet file not found", path.string()));
    }

    auto maybe_infile = arrow::io::ReadableFile::Open(path.string());
    if (!maybe_infile.ok()) {
        return tl::unexpected(arrow_status_error(
            gm::ErrorCode::kIoFailure, "failed to open parquet file (" + path.string() + ")",
            maybe_infile.status()));
    }
    std::shared_ptr<arrow::io::ReadableFile> infile = *maybe_infile;

    // parquet::arrow::OpenFile and FileReader::ReadTable both moved to
    // arrow::Result<T>-returning signatures (the old Status-with-
    // out-param overloads are deprecated as of Arrow 24.0.0, and this
    // build - Arrow 25.0.1 - errors on the deprecation warning under
    // -Werror per ADR-004).
    auto maybe_reader = parquet::arrow::OpenFile(infile, arrow::default_memory_pool());
    if (!maybe_reader.ok()) {
        return tl::unexpected(arrow_status_error(
            gm::ErrorCode::kParseFailure, "failed to open parquet reader (" + path.string() + ")",
            maybe_reader.status()));
    }
    std::unique_ptr<parquet::arrow::FileReader> reader = std::move(*maybe_reader);

    auto maybe_table = reader->ReadTable();
    if (!maybe_table.ok()) {
        return tl::unexpected(arrow_status_error(
            gm::ErrorCode::kParseFailure, "failed reading parquet table (" + path.string() + ")",
            maybe_table.status()));
    }
    std::shared_ptr<arrow::Table> arrow_table = *maybe_table;

    // Combine to a single chunk per column so each column has exactly
    // one contiguous array to convert, rather than N row-group chunks.
    auto combine_result = arrow_table->CombineChunks(arrow::default_memory_pool());
    if (!combine_result.ok()) {
        return tl::unexpected(arrow_status_error(gm::ErrorCode::kParseFailure,
                                                  "failed combining parquet chunks (" +
                                                      path.string() + ")",
                                                  combine_result.status()));
    }
    arrow_table = *combine_result;

    Table table;
    const auto& schema = *arrow_table->schema();
    for (int col_idx = 0; col_idx < arrow_table->num_columns(); ++col_idx) {
        const std::string& name = schema.field(col_idx)->name();
        std::shared_ptr<arrow::ChunkedArray> chunked = arrow_table->column(col_idx);
        std::shared_ptr<arrow::Array> array =
            chunked->num_chunks() > 0 ? chunked->chunk(0) : nullptr;

        switch (schema.field(col_idx)->type()->id()) {
            case arrow::Type::STRING: {
                auto typed = std::static_pointer_cast<arrow::StringArray>(array);
                std::vector<std::string> values;
                values.reserve(static_cast<std::size_t>(typed ? typed->length() : 0));
                if (typed) {
                    for (int64_t i = 0; i < typed->length(); ++i) values.push_back(typed->GetString(i));
                }
                if (auto r = table.add_string_column(name, std::move(values)); !r) return tl::unexpected(r.error());
                break;
            }
            case arrow::Type::INT64: {
                auto typed = std::static_pointer_cast<arrow::Int64Array>(array);
                std::vector<std::int64_t> values;
                values.reserve(static_cast<std::size_t>(typed ? typed->length() : 0));
                if (typed) {
                    for (int64_t i = 0; i < typed->length(); ++i) values.push_back(typed->Value(i));
                }
                if (auto r = table.add_int64_column(name, std::move(values)); !r) return tl::unexpected(r.error());
                break;
            }
            case arrow::Type::DOUBLE: {
                auto typed = std::static_pointer_cast<arrow::DoubleArray>(array);
                std::vector<double> values;
                values.reserve(static_cast<std::size_t>(typed ? typed->length() : 0));
                if (typed) {
                    for (int64_t i = 0; i < typed->length(); ++i) values.push_back(typed->Value(i));
                }
                if (auto r = table.add_double_column(name, std::move(values)); !r) return tl::unexpected(r.error());
                break;
            }
            case arrow::Type::BOOL: {
                auto typed = std::static_pointer_cast<arrow::BooleanArray>(array);
                std::vector<std::uint8_t> values;
                values.reserve(static_cast<std::size_t>(typed ? typed->length() : 0));
                if (typed) {
                    for (int64_t i = 0; i < typed->length(); ++i)
                        values.push_back(typed->Value(i) ? 1 : 0);
                }
                if (auto r = table.add_bool_column(name, std::move(values)); !r) return tl::unexpected(r.error());
                break;
            }
            default:
                return tl::unexpected(gm::Error::make(
                    gm::ErrorCode::kParseFailure, "unsupported parquet column type",
                    name + ": " + schema.field(col_idx)->type()->ToString()));
        }
    }

    return table;
}

} // namespace gm::io
