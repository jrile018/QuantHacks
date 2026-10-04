// Tests for the retroactive-change screen.
//
// A detector that has never been shown to detect anything is a comment,
// not a check - which is the whole reason this lives in a library rather
// than inside gm-ingest, where the network would be in the way of testing
// it.

#include <gm-data/revisions.hpp>

#include <catch2/catch_test_macros.hpp>

#include <cmath>
#include <string>
#include <vector>

using gm::data::compare_price_panels;

namespace {

gm::io::Table panel(const std::vector<std::string>& tickers,
                    const std::vector<std::string>& dates,
                    const std::vector<double>& adjclose) {
    gm::io::Table t;
    REQUIRE(t.add_string_column("ticker", tickers).has_value());
    REQUIRE(t.add_string_column("date", dates).has_value());
    REQUIRE(t.add_double_column("adjclose", adjclose).has_value());
    return t;
}

} // namespace

TEST_CASE("an unchanged panel reports no revisions", "[gm-data][revisions]") {
    const std::vector<std::string> tickers{"AAA", "AAA", "BBB", "BBB"};
    const std::vector<std::string> dates{"2024-01-02", "2024-01-03", "2024-01-02", "2024-01-03"};
    const std::vector<double> values{10.0, 11.0, 20.0, 21.0};

    const auto report = compare_price_panels(panel(tickers, dates, values),
                                              panel(tickers, dates, values), "adjclose");
    REQUIRE(report.has_value());
    CHECK(report->compared == 4);
    CHECK(report->revised == 0);
    CHECK(report->added == 0);
    CHECK(report->removed == 0);
    CHECK(report->revised_tickers.empty());
    CHECK(report->first_example.empty());
}

TEST_CASE("a rewritten historical bar is detected and named", "[gm-data][revisions]") {
    // The case the screen exists for: a date three entries back silently
    // becomes a different number, and every result built on the old panel
    // stops being reproducible from the new one.
    const std::vector<std::string> tickers{"AAA", "AAA", "BBB", "BBB"};
    const std::vector<std::string> dates{"2024-01-02", "2024-01-03", "2024-01-02", "2024-01-03"};
    const std::vector<double> before{10.0, 11.0, 20.0, 21.0};
    const std::vector<double> after{10.0, 11.0, 19.5, 21.0};  // BBB's first bar re-adjusted

    const auto report = compare_price_panels(panel(tickers, dates, before),
                                              panel(tickers, dates, after), "adjclose");
    REQUIRE(report.has_value());
    CHECK(report->compared == 4);
    CHECK(report->revised == 1);
    REQUIRE(report->revised_tickers.size() == 1);
    CHECK(*report->revised_tickers.begin() == "BBB");
    // The example names the ticker, the date and both values - enough to
    // go and look, which a bare count is not.
    CHECK(report->first_example.find("BBB") != std::string::npos);
    CHECK(report->first_example.find("2024-01-02") != std::string::npos);
}

TEST_CASE("a difference in the last bit still counts as a revision", "[gm-data][revisions]") {
    // Deliberately exact rather than tolerant. A value differing only in
    // the last bit still makes a backtest irreproducible, which is the
    // thing being detected - and a tolerance would hide precisely the
    // small revisions hardest to notice by eye.
    const std::vector<std::string> tickers{"AAA"};
    const std::vector<std::string> dates{"2024-01-02"};
    const double base = 123.456789012345;
    const std::vector<double> before_values{base};
    const std::vector<double> after_values{std::nextafter(base, 1e30)};
    const auto report = compare_price_panels(panel(tickers, dates, before_values),
                                              panel(tickers, dates, after_values), "adjclose");
    REQUIRE(report.has_value());
    CHECK(report->revised == 1);
}

TEST_CASE("new and removed bars are counted apart from revisions", "[gm-data][revisions]") {
    // The panel extends every day and the universe turns over; neither is
    // a revision, and reporting them together would make a normal daily
    // run look like the vendor had rewritten history.
    const auto before = panel({"AAA", "AAA", "OLD"}, {"2024-01-02", "2024-01-03", "2024-01-02"},
                              {10.0, 11.0, 5.0});
    const auto after = panel({"AAA", "AAA", "AAA", "NEW"},
                             {"2024-01-02", "2024-01-03", "2024-01-04", "2024-01-04"},
                             {10.0, 11.0, 12.0, 99.0});

    const auto report = compare_price_panels(before, after, "adjclose");
    REQUIRE(report.has_value());
    CHECK(report->compared == 2);   // AAA's two shared bars
    CHECK(report->revised == 0);
    CHECK(report->added == 2);      // AAA's new day, and NEW entirely
    CHECK(report->removed == 1);    // OLD left the universe
}

TEST_CASE("the reported example is the same one every time", "[gm-data][revisions]") {
    // A diagnostic that names a different bar on each run over the same
    // data is a coin toss, not a diagnostic (ADR-003). Ordered iteration
    // is what makes it stable.
    const std::vector<std::string> tickers{"ZZZ", "AAA", "MMM"};
    const std::vector<std::string> dates{"2024-01-02", "2024-01-02", "2024-01-02"};
    const auto before = panel(tickers, dates, {1.0, 2.0, 3.0});
    const auto after = panel(tickers, dates, {1.5, 2.5, 3.5});  // all three revised

    for (int repeat = 0; repeat < 5; ++repeat) {
        const auto report = compare_price_panels(before, after, "adjclose");
        REQUIRE(report.has_value());
        CHECK(report->revised == 3);
        // AAA sorts first, so it is always the example.
        CHECK(report->first_example.rfind("AAA", 0) == 0);
    }
}

TEST_CASE("a missing column is an error, not an empty report", "[gm-data][revisions]") {
    const auto p = panel({"AAA"}, {"2024-01-02"}, {10.0});
    const auto report = compare_price_panels(p, p, "close");  // not in these fixtures
    CHECK_FALSE(report.has_value());
}
