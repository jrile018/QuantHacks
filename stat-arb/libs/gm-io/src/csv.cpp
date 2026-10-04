#include <gm-io/csv.hpp>

#include <fstream>
#include <sstream>

namespace gm::io {

namespace {

enum class State { kFieldStart, kUnquoted, kQuoted, kQuotedQuote };

/// The actual RFC-4180 state machine. Returns raw records (header +
/// data rows undifferentiated) or an error for an unterminated quoted
/// field - the one input shape this parser refuses to guess about,
/// since a silently-truncated quote would otherwise merge two rows'
/// content into one field with no visible symptom.
Result<std::vector<std::vector<std::string>>> parse_records(std::string_view text, char delimiter) {
    std::vector<std::vector<std::string>> records;
    std::vector<std::string> current_record;
    std::string current_field;
    State state = State::kFieldStart;

    auto end_field = [&] {
        current_record.push_back(std::move(current_field));
        current_field.clear();
    };
    auto end_record = [&] {
        end_field();
        records.push_back(std::move(current_record));
        current_record.clear();
    };

    std::size_t i = 0;
    const std::size_t n = text.size();
    while (i < n) {
        char c = text[i];
        switch (state) {
            case State::kFieldStart:
                if (c == '"') {
                    state = State::kQuoted;
                    ++i;
                } else if (c == delimiter) {
                    end_field();
                    ++i;
                } else if (c == '\r') {
                    if (i + 1 < n && text[i + 1] == '\n') ++i;
                    end_record();
                    state = State::kFieldStart;
                    ++i;
                } else if (c == '\n') {
                    end_record();
                    ++i;
                } else {
                    current_field.push_back(c);
                    state = State::kUnquoted;
                    ++i;
                }
                break;

            case State::kUnquoted:
                if (c == delimiter) {
                    end_field();
                    state = State::kFieldStart;
                    ++i;
                } else if (c == '\r') {
                    if (i + 1 < n && text[i + 1] == '\n') ++i;
                    end_record();
                    state = State::kFieldStart;
                    ++i;
                } else if (c == '\n') {
                    end_record();
                    state = State::kFieldStart;
                    ++i;
                } else {
                    current_field.push_back(c);
                    ++i;
                }
                break;

            case State::kQuoted:
                if (c == '"') {
                    state = State::kQuotedQuote;
                } else {
                    current_field.push_back(c);  // delimiters/newlines are literal inside quotes
                }
                ++i;
                break;

            case State::kQuotedQuote:
                if (c == '"') {
                    // "" inside a quoted field is an escaped literal quote.
                    current_field.push_back('"');
                    state = State::kQuoted;
                    ++i;
                } else if (c == delimiter) {
                    end_field();
                    state = State::kFieldStart;
                    ++i;
                } else if (c == '\r') {
                    if (i + 1 < n && text[i + 1] == '\n') ++i;
                    end_record();
                    state = State::kFieldStart;
                    ++i;
                } else if (c == '\n') {
                    end_record();
                    state = State::kFieldStart;
                    ++i;
                } else {
                    // Something follows a closing quote that isn't a
                    // delimiter or newline (e.g. `"abc"def`). Not valid
                    // RFC-4180, but our fixed, known source formats
                    // never produce this - treat the rest as a literal
                    // continuation rather than failing the whole parse.
                    current_field.push_back(c);
                    state = State::kUnquoted;
                    ++i;
                }
                break;
        }
    }

    if (state == State::kQuoted) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "unterminated quoted field at end of input"));
    }

    // Flush a pending field/record - covers input with no trailing
    // newline, and RFC-4180's trailing-empty-field-after-a-comma case.
    if (state != State::kFieldStart || !current_field.empty() || !current_record.empty()) {
        end_record();
    }

    return records;
}

} // namespace

std::optional<std::size_t> CsvTable::column_index(std::string_view name) const {
    for (std::size_t i = 0; i < header.size(); ++i) {
        if (header[i] == name) return i;
    }
    return std::nullopt;
}

Result<CsvTable> parse_csv(std::string_view text, char delimiter) {
    auto records = parse_records(text, delimiter);
    if (!records) return tl::unexpected(records.error());

    if (records->empty()) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kParseFailure, "empty CSV input: no header row"));
    }

    CsvTable table;
    table.header = std::move((*records)[0]);
    table.rows.reserve(records->size() - 1);

    for (std::size_t row_idx = 1; row_idx < records->size(); ++row_idx) {
        auto& row = (*records)[row_idx];
        if (row.size() != table.header.size()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure, "CSV row has wrong field count",
                "row " + std::to_string(row_idx) + ": expected " +
                    std::to_string(table.header.size()) + " fields, got " +
                    std::to_string(row.size())));
        }
        table.rows.push_back(std::move(row));
    }

    return table;
}

Result<CsvTable> read_csv_file(const std::filesystem::path& path, char delimiter) {
    std::error_code ec;
    if (!std::filesystem::exists(path, ec)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNotFound, "CSV file not found",
                                               path.string()));
    }
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return tl::unexpected(
            gm::Error::make(gm::ErrorCode::kIoFailure, "failed to open CSV file", path.string()));
    }
    std::ostringstream buf;
    buf << in.rdbuf();
    return parse_csv(buf.str(), delimiter);
}

} // namespace gm::io
