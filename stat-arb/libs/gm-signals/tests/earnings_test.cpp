#include <gm-signals/earnings.hpp>

#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>

using gm::signals::extract_filings;

TEST_CASE("filters to the requested form types", "[earnings]") {
    // Shape matches SEC's real "filings.recent" object (verified
    // against a live fetch for CIK0000320193/Apple during design: the
    // same parallel-array "form"/"filingDate" fields, filtered here to
    // just "8-K" out of a mix including "4", "10-Q", "144", "SD").
    auto node = nlohmann::json::parse(R"({
        "form": ["4", "4", "10-Q", "8-K", "144", "8-K"],
        "filingDate": ["2026-08-27", "2026-08-20", "2026-07-31", "2026-07-30", "2026-08-11", "2026-06-17"]
    })");

    auto result = extract_filings(node, {"8-K"});
    REQUIRE(result.has_value());
    REQUIRE(result->size() == 2);
    CHECK((*result)[0].date == "2026-07-30");
    CHECK((*result)[0].form == "8-K");
    CHECK((*result)[1].date == "2026-06-17");
    CHECK((*result)[1].form == "8-K");
}

TEST_CASE("empty form_types returns every form", "[earnings]") {
    auto node = nlohmann::json::parse(R"({
        "form": ["4", "10-Q", "8-K"],
        "filingDate": ["2026-08-27", "2026-07-31", "2026-07-30"]
    })");

    auto result = extract_filings(node, {});
    REQUIRE(result.has_value());
    CHECK(result->size() == 3);
}

TEST_CASE("multiple requested form types are all included", "[earnings]") {
    auto node = nlohmann::json::parse(R"({
        "form": ["4", "10-Q", "8-K", "10-K"],
        "filingDate": ["2026-08-27", "2026-07-31", "2026-07-30", "2026-01-15"]
    })");

    auto result = extract_filings(node, {"8-K", "10-K"});
    REQUIRE(result.has_value());
    REQUIRE(result->size() == 2);
    CHECK((*result)[0].form == "8-K");
    CHECK((*result)[1].form == "10-K");
}

TEST_CASE("an empty recent object with no filings of the requested type returns empty", "[earnings]") {
    auto node = nlohmann::json::parse(R"({"form": ["4", "144"], "filingDate": ["2026-01-01", "2026-01-02"]})");
    auto result = extract_filings(node, {"8-K"});
    REQUIRE(result.has_value());
    CHECK(result->empty());
}

TEST_CASE("a missing form field is rejected", "[earnings]") {
    auto node = nlohmann::json::parse(R"({"filingDate": ["2026-01-01"]})");
    auto result = extract_filings(node, {"8-K"});
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("a missing filingDate field is rejected", "[earnings]") {
    auto node = nlohmann::json::parse(R"({"form": ["8-K"]})");
    auto result = extract_filings(node, {"8-K"});
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("mismatched form/filingDate array lengths are rejected", "[earnings]") {
    auto node = nlohmann::json::parse(R"({"form": ["8-K", "10-Q"], "filingDate": ["2026-01-01"]})");
    auto result = extract_filings(node, {"8-K"});
    REQUIRE_FALSE(result.has_value());
}

TEST_CASE("a malformed shape (form is not an array of strings) is caught, not thrown", "[earnings]") {
    // form as a single object rather than an array of strings - .size()
    // on an object still "succeeds" in nlohmann (returns the key
    // count), but forms[i].get<std::string>() on an object entry
    // throws a type_error - exercising the try/catch boundary, not just
    // the explicit contains()/length checks above it.
    auto node = nlohmann::json::parse(R"({"form": {"bad": "shape"}, "filingDate": ["2026-01-01"]})");
    auto result = extract_filings(node, {});
    REQUIRE_FALSE(result.has_value());
}
