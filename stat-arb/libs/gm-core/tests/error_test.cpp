#include <gm-core/error.hpp>

#include <catch2/catch_test_macros.hpp>

using gm::Error;
using gm::ErrorCode;
using gm::Result;

namespace {

Result<int> divide(int a, int b) {
    if (b == 0) {
        return tl::unexpected(Error::make(ErrorCode::kInvalidArgument, "division by zero"));
    }
    return a / b;
}

} // namespace

TEST_CASE("Result carries a value on success without throwing", "[error]") {
    auto r = divide(10, 2);
    REQUIRE(r.has_value());
    CHECK(*r == 5);
}

TEST_CASE("Result carries a structured error on failure without throwing", "[error]") {
    auto r = divide(10, 0);
    REQUIRE_FALSE(r.has_value());
    CHECK(r.error().code == ErrorCode::kInvalidArgument);
    CHECK(r.error().message == "division by zero");
}

TEST_CASE("Error::to_string includes the code and message", "[error]") {
    auto e = Error::make(ErrorCode::kNotFound, "ticker not in universe", "XYZ");
    auto s = e.to_string();
    CHECK(s.find("not_found") != std::string::npos);
    CHECK(s.find("ticker not in universe") != std::string::npos);
    CHECK(s.find("XYZ") != std::string::npos);
}

TEST_CASE("VoidResult default-constructs to success", "[error]") {
    gm::VoidResult r{};
    CHECK(r.has_value());
}
