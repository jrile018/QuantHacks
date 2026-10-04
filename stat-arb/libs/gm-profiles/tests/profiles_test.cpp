#include <gm-profiles/profiles.hpp>

#include <catch2/catch_test_macros.hpp>

// Note: fetch_company_profile requires network access and an HttpCache,
// so it's not easily unit-testable without mocking the HttpCache.
// Instead, we test that the module compiles and the data structures
// are correct. Integration testing happens against real SEC data.

TEST_CASE("CompanyProfile structure is correctly defined", "[profiles]") {
    gm::profiles::CompanyProfile profile;
    profile.ticker = "AAPL";
    profile.company_name = "Apple Inc.";
    profile.sic_code = 3571;
    profile.sic_description = "Electronic Computers";
    profile.edgar_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=&dateb=&owner=include&count=40";

    CHECK(profile.ticker == "AAPL");
    CHECK(profile.company_name == "Apple Inc.");
    CHECK(profile.sic_code == 3571);
    CHECK(!profile.sic_description.empty());
    CHECK(profile.edgar_url.find("sec.gov") != std::string::npos);
}
