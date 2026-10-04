#include <gm-io/csv.hpp>

#include <catch2/catch_test_macros.hpp>

using gm::io::parse_csv;

TEST_CASE("parses a simple well-formed CSV", "[csv]") {
    auto t = parse_csv("date,close,volume\n2024-01-02,185.64,82488700\n2024-01-03,184.25,58414500\n");
    REQUIRE(t.has_value());
    CHECK(t->header == std::vector<std::string>{"date", "close", "volume"});
    REQUIRE(t->rows.size() == 2);
    CHECK(t->rows[0] == std::vector<std::string>{"2024-01-02", "185.64", "82488700"});
    CHECK(t->rows[1] == std::vector<std::string>{"2024-01-03", "184.25", "58414500"});
}

TEST_CASE("handles a file with no trailing newline", "[csv]") {
    auto t = parse_csv("a,b\n1,2");
    REQUIRE(t.has_value());
    REQUIRE(t->rows.size() == 1);
    CHECK(t->rows[0] == std::vector<std::string>{"1", "2"});
}

TEST_CASE("handles CRLF line endings", "[csv]") {
    auto t = parse_csv("a,b\r\n1,2\r\n3,4\r\n");
    REQUIRE(t.has_value());
    REQUIRE(t->rows.size() == 2);
    CHECK(t->rows[0] == std::vector<std::string>{"1", "2"});
    CHECK(t->rows[1] == std::vector<std::string>{"3", "4"});
}

TEST_CASE("quoted field with an embedded delimiter", "[csv]") {
    auto t = parse_csv("name,note\nAAPL,\"Apple, Inc.\"\n");
    REQUIRE(t.has_value());
    REQUIRE(t->rows.size() == 1);
    CHECK(t->rows[0][1] == "Apple, Inc.");
}

TEST_CASE("quoted field with an embedded newline", "[csv]") {
    auto t = parse_csv("name,note\nAAPL,\"line one\nline two\"\n");
    REQUIRE(t.has_value());
    REQUIRE(t->rows.size() == 1);
    CHECK(t->rows[0][1] == "line one\nline two");
}

TEST_CASE("escaped double-quote inside a quoted field", "[csv]") {
    auto t = parse_csv("name,note\nAAPL,\"she said \"\"hi\"\"\"\n");
    REQUIRE(t.has_value());
    REQUIRE(t->rows.size() == 1);
    CHECK(t->rows[0][1] == "she said \"hi\"");
}

TEST_CASE("trailing comma produces a trailing empty field", "[csv]") {
    auto t = parse_csv("a,b,c\n1,2,\n");
    REQUIRE(t.has_value());
    REQUIRE(t->rows.size() == 1);
    CHECK(t->rows[0] == std::vector<std::string>{"1", "2", ""});
}

TEST_CASE("wrong field count is an error, not a best-effort parse", "[csv]") {
    auto t = parse_csv("a,b,c\n1,2\n");
    REQUIRE_FALSE(t.has_value());
    CHECK(t.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("unterminated quote is an error", "[csv]") {
    auto t = parse_csv("a,b\n1,\"unterminated\n");
    REQUIRE_FALSE(t.has_value());
    CHECK(t.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("empty input is an error: no header row", "[csv]") {
    auto t = parse_csv("");
    REQUIRE_FALSE(t.has_value());
    CHECK(t.error().code == gm::ErrorCode::kParseFailure);
}

TEST_CASE("header-only input is valid with zero data rows", "[csv]") {
    auto t = parse_csv("a,b,c\n");
    REQUIRE(t.has_value());
    CHECK(t->rows.empty());
}

TEST_CASE("column_index finds and rejects header names", "[csv]") {
    auto t = parse_csv("date,close\n2024-01-02,185.64\n");
    REQUIRE(t.has_value());
    CHECK(t->column_index("close") == 1);
    CHECK(t->column_index("date") == 0);
    CHECK_FALSE(t->column_index("nonexistent").has_value());
}

TEST_CASE("custom delimiter", "[csv]") {
    auto t = parse_csv("a;b\n1;2\n", ';');
    REQUIRE(t.has_value());
    CHECK(t->rows[0] == std::vector<std::string>{"1", "2"});
}
