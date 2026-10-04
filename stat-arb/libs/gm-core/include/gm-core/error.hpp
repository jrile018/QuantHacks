#pragma once

// ADR-019: errors cross module boundaries as values (tl::expected), never
// as exceptions. Exceptions are permitted only during process startup and
// config parsing; every stage's hot path returns Result<T> and is noexcept
// from the point config is validated onward.

#include <tl/expected.hpp>

#include <source_location>
#include <string>
#include <string_view>

namespace gm {

enum class ErrorCode {
    kUnknown = 0,
    kIoFailure,          // file/network read or write failed
    kNotFound,           // requested resource does not exist
    kParseFailure,       // malformed input (config, CSV, JSON, ...)
    kSchemaVersionMismatch, // artifact manifest schema_version unsupported
    kValidationFailure,  // data failed a quality/sanity screen (ADR-015)
    kInvalidArgument,    // caller supplied an out-of-domain value
    kNumericFailure,     // solver/eigendecomposition failed to converge
    kNotImplemented,
};

[[nodiscard]] constexpr std::string_view to_string(ErrorCode code) noexcept {
    switch (code) {
        case ErrorCode::kUnknown: return "unknown";
        case ErrorCode::kIoFailure: return "io_failure";
        case ErrorCode::kNotFound: return "not_found";
        case ErrorCode::kParseFailure: return "parse_failure";
        case ErrorCode::kSchemaVersionMismatch: return "schema_version_mismatch";
        case ErrorCode::kValidationFailure: return "validation_failure";
        case ErrorCode::kInvalidArgument: return "invalid_argument";
        case ErrorCode::kNumericFailure: return "numeric_failure";
        case ErrorCode::kNotImplemented: return "not_implemented";
    }
    return "unrecognized_error_code";
}

/// A value-typed error carrying enough context to log and to act on,
/// without ever throwing. Cheap to copy (small strings only); not intended
/// to carry large payloads.
struct Error {
    ErrorCode code{ErrorCode::kUnknown};
    std::string message;
    std::string context;  // e.g. "gm-ingest: AAPL 2019-03-04"
    std::source_location location{std::source_location::current()};

    [[nodiscard]] std::string to_string() const {
        std::string out;
        out.reserve(message.size() + context.size() + 64);
        out += "[";
        out += gm::to_string(code);
        out += "] ";
        out += message;
        if (!context.empty()) {
            out += " (";
            out += context;
            out += ")";
        }
        return out;
    }

    static Error make(ErrorCode code, std::string message, std::string context = {},
                       std::source_location loc = std::source_location::current()) {
        return Error{code, std::move(message), std::move(context), loc};
    }
};

template <typename T>
using Result = tl::expected<T, Error>;

using VoidResult = Result<void>;

} // namespace gm
