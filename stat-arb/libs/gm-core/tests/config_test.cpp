#include <gm-core/config.hpp>

#include <catch2/catch_test_macros.hpp>

using gm::Config;

namespace {
constexpr std::string_view kSample = R"toml(
[universe]
top_n = 100
base_pool = "sp500+nasdaq100"

[geometry]
window_days = 60
embedding_dims = 3
use_rmt_denoise = true
market_removal_ratio = 0.5
)toml";
} // namespace

TEST_CASE("parse loads a well-formed TOML document", "[config]") {
    auto cfg = Config::parse(kSample);
    REQUIRE(cfg.has_value());
}

TEST_CASE("parse rejects malformed TOML rather than guessing", "[config]") {
    auto cfg = Config::parse("this is not [ valid toml");
    REQUIRE_FALSE(cfg.has_value());
    CHECK(cfg.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("typed accessors read dotted keys with correct types", "[config]") {
    auto cfg = Config::parse(kSample);
    REQUIRE(cfg.has_value());

    auto top_n = cfg->get_int("universe.top_n");
    REQUIRE(top_n.has_value());
    CHECK(*top_n == 100);

    auto pool = cfg->get_string("universe.base_pool");
    REQUIRE(pool.has_value());
    CHECK(*pool == "sp500+nasdaq100");

    auto window = cfg->get_int("geometry.window_days");
    REQUIRE(window.has_value());
    CHECK(*window == 60);

    auto ratio = cfg->get_double("geometry.market_removal_ratio");
    REQUIRE(ratio.has_value());
    CHECK(*ratio == 0.5);

    auto rmt = cfg->get_bool("geometry.use_rmt_denoise");
    REQUIRE(rmt.has_value());
    CHECK(*rmt == true);
}

TEST_CASE("missing keys fail rather than silently defaulting", "[config]") {
    auto cfg = Config::parse(kSample);
    REQUIRE(cfg.has_value());

    auto missing = cfg->get_int("universe.does_not_exist");
    REQUIRE_FALSE(missing.has_value());
    CHECK(missing.error().code == gm::ErrorCode::kNotFound);
}

TEST_CASE("wrong-typed key access fails rather than coercing", "[config]") {
    auto cfg = Config::parse(kSample);
    REQUIRE(cfg.has_value());

    // base_pool is a string; asking for it as an int must fail, not
    // silently coerce (this is the entire reason TOML was chosen over
    // YAML in ADR-005).
    auto wrong_type = cfg->get_int("universe.base_pool");
    REQUIRE_FALSE(wrong_type.has_value());
}

TEST_CASE("int/double coercion is rejected in both directions", "[config]") {
    // ADR-005's entire case for TOML over YAML is "no implicit type
    // coercion" - verify that holds both ways, not just one. toml++
    // stores TOML's integer and float as genuinely distinct node types,
    // so this should hold; if it didn't, that would itself be an
    // ADR-005 violation at the wrapper level, not just a test gap.
    auto cfg = Config::parse("int_val = 42\nfloat_val = 3.14");
    REQUIRE(cfg.has_value());

    CHECK_FALSE(cfg->get_double("int_val").has_value());
    CHECK_FALSE(cfg->get_int("float_val").has_value());

    // Sanity: each reads correctly as its own actual type.
    CHECK(cfg->get_int("int_val").value_or(-1) == 42);
    CHECK(cfg->get_double("float_val").value_or(-1.0) == 3.14);
}

TEST_CASE("_or accessors fall back on missing keys", "[config]") {
    auto cfg = Config::parse(kSample);
    REQUIRE(cfg.has_value());

    CHECK(cfg->get_int_or("universe.top_n", -1) == 100);
    CHECK(cfg->get_int_or("universe.missing", -1) == -1);
    CHECK(cfg->get_string_or("universe.missing", "fallback") == "fallback");
}

TEST_CASE("has() reports key presence", "[config]") {
    auto cfg = Config::parse(kSample);
    REQUIRE(cfg.has_value());
    CHECK(cfg->has("universe.top_n"));
    CHECK_FALSE(cfg->has("universe.nonexistent"));
}

TEST_CASE("load fails cleanly on a missing file", "[config]") {
    auto cfg = Config::load("Z:/definitely/does/not/exist.toml");
    REQUIRE_FALSE(cfg.has_value());
    CHECK(cfg.error().code == gm::ErrorCode::kNotFound);
}
