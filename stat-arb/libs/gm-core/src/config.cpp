#include <gm-core/config.hpp>

#include <fstream>
#include <sstream>

namespace gm {

Result<Config> Config::load(const std::filesystem::path& path) {
    std::error_code ec;
    if (!std::filesystem::exists(path, ec)) {
        return tl::unexpected(Error::make(ErrorCode::kNotFound, "config file not found",
                                           path.string()));
    }

    std::ifstream in(path, std::ios::binary);
    if (!in) {
        return tl::unexpected(Error::make(ErrorCode::kIoFailure, "failed to open config file",
                                           path.string()));
    }
    std::ostringstream buf;
    buf << in.rdbuf();
    return parse(buf.str());
}

Result<Config> Config::parse(std::string_view toml_text) {
    try {
        toml::table table = toml::parse(toml_text);
        return Config{std::move(table)};
    } catch (const toml::parse_error& e) {
        std::ostringstream msg;
        msg << e.description();
        return tl::unexpected(
            Error::make(ErrorCode::kParseFailure, "TOML parse error", msg.str()));
    }
}

bool Config::has(std::string_view dotted_key) const {
    return static_cast<bool>(table_.at_path(dotted_key));
}

Result<std::int64_t> Config::get_int(std::string_view dotted_key) const {
    // Deliberately checked via is_integer() rather than trusting
    // node_view::value<T>()'s own conversion rules: toml++'s value<T>()
    // performs "reasonable" numeric widening (an integer node silently
    // reads as a double) which is exactly the implicit-coercion behavior
    // ADR-005 says TOML was chosen to avoid. Narrowing (float read as
    // int) already fails value<T>() on its own, but we check explicitly
    // here too so both directions are enforced by our own logic, not by
    // an incidental property of the library we wrap.
    auto node = table_.at_path(dotted_key);
    if (node.is_integer()) {
        if (auto v = node.value<std::int64_t>()) return *v;
    }
    return tl::unexpected(Error::make(ErrorCode::kNotFound, "missing or wrong-typed int key",
                                       std::string{dotted_key}));
}

Result<double> Config::get_double(std::string_view dotted_key) const {
    // See get_int() above: checked via is_floating_point() specifically
    // to reject the int->double widening that value<double>() would
    // otherwise silently perform.
    auto node = table_.at_path(dotted_key);
    if (node.is_floating_point()) {
        if (auto v = node.value<double>()) return *v;
    }
    return tl::unexpected(Error::make(ErrorCode::kNotFound, "missing or wrong-typed double key",
                                       std::string{dotted_key}));
}

Result<std::string> Config::get_string(std::string_view dotted_key) const {
    auto node = table_.at_path(dotted_key);
    if (node.is_string()) {
        if (auto v = node.value<std::string>()) return *v;
    }
    return tl::unexpected(Error::make(ErrorCode::kNotFound, "missing or wrong-typed string key",
                                       std::string{dotted_key}));
}

Result<bool> Config::get_bool(std::string_view dotted_key) const {
    auto node = table_.at_path(dotted_key);
    if (node.is_boolean()) {
        if (auto v = node.value<bool>()) return *v;
    }
    return tl::unexpected(Error::make(ErrorCode::kNotFound, "missing or wrong-typed bool key",
                                       std::string{dotted_key}));
}

// The four _or accessors below delegate to the strict Result-returning
// versions above rather than duplicating the is_*()-checked lookup, so
// there is exactly one place that decides what counts as a type match -
// no way for the two to drift out of sync the way get_double_or() would
// have silently re-introduced the int->double coercion bug fixed above.
std::int64_t Config::get_int_or(std::string_view dotted_key, std::int64_t fallback) const {
    return get_int(dotted_key).value_or(fallback);
}

double Config::get_double_or(std::string_view dotted_key, double fallback) const {
    return get_double(dotted_key).value_or(fallback);
}

std::string Config::get_string_or(std::string_view dotted_key, std::string fallback) const {
    auto r = get_string(dotted_key);
    return r.has_value() ? *std::move(r) : std::move(fallback);
}

bool Config::get_bool_or(std::string_view dotted_key, bool fallback) const {
    return get_bool(dotted_key).value_or(fallback);
}

} // namespace gm
