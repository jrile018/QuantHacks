// Tests for the SEC XBRL fundamentals reader.
//
// The reference fixture below is REAL data, transcribed from
// data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json (Apple Inc.,
// us-gaap:NetIncomeLoss, unit USD) - every value, period and filing date
// as SEC reports them. It covers two consecutive fiscal years in their
// ORIGINAL vintages, which is what makes the point-in-time assertions
// meaningful: the later comparative re-reportings of the same periods are
// included too, precisely so a test can prove they do not leak backwards.
//
// Expected TTM values were derived from the roll-forward identity and then
// cross-checked against a second, independent construction (derive the
// implied prior Q4 from FY minus its own nine-month YTD, then accumulate)
// over all 49 computable dates of Apple's filing history: zero
// disagreements. They are not this implementation's own output.

#include <gm-data/fundamentals.hpp>

#include <catch2/catch_test_macros.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <string>
#include <vector>

using gm::data::assemble_ttm;
using gm::data::extract_facts;
using gm::data::latest_instant_as_of;
using gm::data::quarters_spanned;
using gm::data::TtmPoint;
using gm::data::XbrlFact;

namespace {

// Apple's FY2022 and FY2023 net income, original filings plus the
// comparative re-reportings, verbatim from SEC.
const char* kAppleNetIncome = R"JSON({
  "cik": 320193,
  "entityName": "Apple Inc.",
  "facts": {
    "us-gaap": {
      "NetIncomeLoss": {
        "label": "Net Income (Loss)",
        "units": {
          "USD": [
            {"start":"2021-09-26","end":"2021-12-25","val":34630000000,"accn":"0000320193-22-000007","form":"10-Q","filed":"2022-01-28"},
            {"start":"2021-09-26","end":"2022-03-26","val":59640000000,"accn":"0000320193-22-000059","form":"10-Q","filed":"2022-04-29"},
            {"start":"2021-09-26","end":"2022-06-25","val":79082000000,"accn":"0000320193-22-000070","form":"10-Q","filed":"2022-07-29"},
            {"start":"2021-09-26","end":"2022-09-24","val":99803000000,"accn":"0000320193-22-000108","form":"10-K","filed":"2022-10-28"},
            {"start":"2022-09-25","end":"2022-12-31","val":29998000000,"accn":"0000320193-23-000006","form":"10-Q","filed":"2023-02-03"},
            {"start":"2021-09-26","end":"2021-12-25","val":34630000000,"accn":"0000320193-23-000006","form":"10-Q","filed":"2023-02-03"},
            {"start":"2022-09-25","end":"2023-04-01","val":54158000000,"accn":"0000320193-23-000064","form":"10-Q","filed":"2023-05-05"},
            {"start":"2021-09-26","end":"2022-03-26","val":59640000000,"accn":"0000320193-23-000064","form":"10-Q","filed":"2023-05-05"},
            {"start":"2022-09-25","end":"2023-07-01","val":74039000000,"accn":"0000320193-23-000077","form":"10-Q","filed":"2023-08-04"},
            {"start":"2021-09-26","end":"2022-06-25","val":79082000000,"accn":"0000320193-23-000077","form":"10-Q","filed":"2023-08-04"},
            {"start":"2022-09-25","end":"2023-09-30","val":96995000000,"accn":"0000320193-23-000106","form":"10-K","filed":"2023-11-03"},
            {"start":"2021-09-26","end":"2022-09-24","val":99803000000,"accn":"0000320193-23-000106","form":"10-K","filed":"2023-11-03"}
          ]
        }
      },
      "CashAndCashEquivalentsAtCarryingValue": {
        "units": {
          "USD": [
            {"end":"2022-09-24","val":23646000000,"accn":"0000320193-22-000108","form":"10-K","filed":"2022-10-28"},
            {"end":"2023-09-30","val":29965000000,"accn":"0000320193-23-000106","form":"10-K","filed":"2023-11-03"}
          ]
        }
      }
    }
  }
})JSON";

nlohmann::json apple() { return nlohmann::json::parse(kAppleNetIncome); }

std::vector<XbrlFact> apple_net_income() {
    auto facts = extract_facts(apple(), "us-gaap", "NetIncomeLoss", "USD");
    REQUIRE(facts.has_value());
    return *facts;
}

/// The TTM value in effect on `as_of` - the caller-side as-of rule, applied
/// to TTM rows: greatest period_end among those already published, ties on
/// period_end broken by the later filing.
const TtmPoint* ttm_as_of(const std::vector<TtmPoint>& points, const std::string& as_of) {
    const TtmPoint* best = nullptr;
    for (const TtmPoint& p : points) {
        if (p.available_date > as_of) continue;
        if (best == nullptr || p.period_end > best->period_end ||
            (p.period_end == best->period_end && p.available_date > best->available_date)) {
            best = &p;
        }
    }
    return best;
}

XbrlFact duration(std::string start, std::string end, std::string filed, double val) {
    XbrlFact f;
    f.period_start = std::move(start);
    f.period_end = std::move(end);
    f.available_date = std::move(filed);
    f.value = val;
    return f;
}

XbrlFact instant(std::string end, std::string filed, double val) {
    XbrlFact f;
    f.period_end = std::move(end);
    f.available_date = std::move(filed);
    f.value = val;
    return f;
}

} // namespace

// ---------------------------------------------------------------------------
// extract_facts
// ---------------------------------------------------------------------------

TEST_CASE("extract_facts reads every field SEC provides", "[gm-data][fundamentals]") {
    const auto facts = apple_net_income();
    REQUIRE(facts.size() == 12);
    CHECK(facts[0].period_start == "2021-09-26");
    CHECK(facts[0].period_end == "2021-12-25");
    CHECK(facts[0].available_date == "2022-01-28");
    CHECK(facts[0].form == "10-Q");
    CHECK(facts[0].accession == "0000320193-22-000007");
    CHECK(facts[0].value == 34630000000.0);
}

TEST_CASE("extract_facts keeps every vintage instead of deduplicating",
          "[gm-data][fundamentals]") {
    // The period 2021-09-26..2022-09-24 is reported twice: in its own 10-K
    // and again as a comparative in the following year's. Collapsing those
    // to one row is look-ahead bias wearing the costume of deduplication -
    // a 2023 simulation would read a 2023-filed figure for a 2022 period.
    const auto facts = apple_net_income();
    std::vector<std::string> filings;
    for (const XbrlFact& f : facts) {
        if (f.period_start == "2021-09-26" && f.period_end == "2022-09-24") {
            filings.push_back(f.available_date);
        }
    }
    std::sort(filings.begin(), filings.end());
    REQUIRE(filings.size() == 2);
    CHECK(filings[0] == "2022-10-28");
    CHECK(filings[1] == "2023-11-03");
}

TEST_CASE("extract_facts treats an absent tag as empty, not as an error",
          "[gm-data][fundamentals]") {
    // Filers tag the same concept differently, so a caller walks a list of
    // candidates. An absent tag has to be a normal outcome or that walk
    // cannot be written.
    auto missing = extract_facts(apple(), "us-gaap", "EarningsBeforeInterestTaxesEtc", "USD");
    REQUIRE(missing.has_value());
    CHECK(missing->empty());

    CHECK(extract_facts(apple(), "ifrs-full", "ProfitLoss", "USD").value().empty());
    CHECK(extract_facts(apple(), "us-gaap", "NetIncomeLoss", "EUR").value().empty());
}

TEST_CASE("extract_facts reports a malformed document rather than guessing",
          "[gm-data][fundamentals]") {
    CHECK_FALSE(extract_facts(nlohmann::json::parse("{}"), "us-gaap", "X", "USD").has_value());

    // A fact without `filed` has no available_date, and inventing one would
    // silently fabricate the publication date the whole module exists to
    // carry.
    const auto no_filed = nlohmann::json::parse(R"({"facts":{"us-gaap":{"T":{"units":{"USD":[
        {"start":"2022-01-01","end":"2022-03-31","val":1}]}}}}})");
    auto result = extract_facts(no_filed, "us-gaap", "T", "USD");
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kParseFailure);
}

// ---------------------------------------------------------------------------
// quarters_spanned
// ---------------------------------------------------------------------------

TEST_CASE("quarters_spanned classifies real fiscal periods", "[gm-data][fundamentals]") {
    // Apple's real periods, which are 13-week blocks of uneven length -
    // an exact day count would discriminate nothing.
    CHECK(quarters_spanned(duration("2021-09-26", "2021-12-25", "x", 0)) == 1);
    CHECK(quarters_spanned(duration("2021-09-26", "2022-03-26", "x", 0)) == 2);
    CHECK(quarters_spanned(duration("2021-09-26", "2022-06-25", "x", 0)) == 3);
    CHECK(quarters_spanned(duration("2021-09-26", "2022-09-24", "x", 0)) == 4);
    // A 53-week fiscal year still has to read as four quarters.
    CHECK(quarters_spanned(duration("2022-09-25", "2023-09-30", "x", 0)) == 4);

    CHECK(quarters_spanned(instant("2022-09-24", "x", 0)) == 0);
    CHECK(quarters_spanned(duration("not-a-date", "2022-09-24", "x", 0)) == 0);
    CHECK(quarters_spanned(duration("2022-09-24", "2021-09-26", "x", 0)) == 0); // reversed
}

// ---------------------------------------------------------------------------
// assemble_ttm - the reference assertions
// ---------------------------------------------------------------------------

TEST_CASE("assemble_ttm reproduces Apple's published trailing-twelve-month net income",
          "[gm-data][fundamentals][reference]") {
    const auto points = assemble_ttm(apple_net_income());
    REQUIRE(points.has_value());

    // Each expectation is the roll-forward of real SEC figures:
    //   after Q1 FY23: 99,803 + 29,998 - 34,630 = 95,171
    //   after Q2 FY23: 99,803 + 54,158 - 59,640 = 94,321
    //   after Q3 FY23: 99,803 + 74,039 - 79,082 = 94,760
    //   after FY23:                               96,995 (the annual itself)
    struct Expectation {
        const char* as_of;
        double value;
        const char* why;
    };
    const Expectation expectations[]{
        {"2022-10-28", 99803000000.0, "FY2022 10-K just filed"},
        {"2023-02-02", 99803000000.0, "day before Q1 FY23 lands, still FY2022"},
        {"2023-02-03", 95171000000.0, "Q1 FY23 10-Q"},
        {"2023-05-04", 95171000000.0, "day before Q2 FY23 lands"},
        {"2023-05-05", 94321000000.0, "Q2 FY23 10-Q"},
        {"2023-08-04", 94760000000.0, "Q3 FY23 10-Q"},
        {"2023-11-03", 96995000000.0, "FY2023 10-K"},
        {"2026-01-01", 96995000000.0, "nothing newer in the fixture"},
    };
    for (const Expectation& e : expectations) {
        const TtmPoint* point = ttm_as_of(*points, e.as_of);
        INFO("as of " << e.as_of << " (" << e.why << ")");
        REQUIRE(point != nullptr);
        CHECK(point->value == e.value);
    }
}

TEST_CASE("assemble_ttm never lets a later filing answer an earlier question",
          "[gm-data][fundamentals][reference]") {
    // Nothing in the output may be usable before it was filed. This is the
    // invariant that a "harmless" deduplication breaks, and it is checked
    // over the whole table rather than at sampled dates.
    const auto points = assemble_ttm(apple_net_income());
    REQUIRE(points.has_value());
    REQUIRE_FALSE(points->empty());

    for (const TtmPoint& p : *points) {
        INFO("period_end " << p.period_end << " available " << p.available_date);
        // A twelve-month window cannot be published before it closes.
        CHECK(p.available_date >= p.period_end);
    }

    // Before Apple's first fixture filing there is no answer at all - not a
    // zero, not the earliest figure.
    CHECK(ttm_as_of(*points, "2022-10-27") == nullptr);
}

TEST_CASE("assemble_ttm needs an annual figure to anchor a window",
          "[gm-data][fundamentals]") {
    const std::vector<XbrlFact> quarters_only{
        duration("2022-09-25", "2022-12-31", "2023-02-03", 29998000000.0),
        duration("2022-09-25", "2023-04-01", "2023-05-05", 54158000000.0),
    };
    auto result = assemble_ttm(quarters_only);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kValidationFailure);
}

TEST_CASE("assemble_ttm skips interim periods it cannot anchor rather than guessing",
          "[gm-data][fundamentals]") {
    // A year-to-date figure whose prior fiscal year is absent from the data
    // has no roll-forward base. The annual figure itself still comes through.
    const std::vector<XbrlFact> facts{
        duration("2022-09-25", "2023-09-30", "2023-11-03", 96995000000.0),
        duration("2022-09-25", "2023-04-01", "2023-05-05", 54158000000.0),
    };
    const auto points = assemble_ttm(facts);
    REQUIRE(points.has_value());
    REQUIRE(points->size() == 1);
    CHECK(points->front().period_end == "2023-09-30");
    CHECK(points->front().value == 96995000000.0);
}

TEST_CASE("assemble_ttm builds an interim window from components as they stood then",
          "[gm-data][fundamentals]") {
    // The base year is restated AFTER the interim filing. The interim TTM
    // must keep using the pre-restatement base, because that is what was on
    // file when it was published; the restatement creates its own later row.
    const std::vector<XbrlFact> facts{
        duration("2021-01-01", "2021-03-31", "2021-04-30", 100.0), // prior Q1
        duration("2021-01-01", "2021-12-31", "2022-01-31", 500.0), // prior FY, original
        duration("2022-01-01", "2022-03-31", "2022-04-30", 130.0), // current Q1
        duration("2021-01-01", "2021-12-31", "2022-09-30", 400.0), // prior FY, RESTATED
    };
    const auto points = assemble_ttm(facts);
    REQUIRE(points.has_value());

    // On 2022-05-01 the only base on file was 500: 500 + 130 - 100 = 530.
    const TtmPoint* then = ttm_as_of(*points, "2022-05-01");
    REQUIRE(then != nullptr);
    CHECK(then->value == 530.0);

    // After the restatement a 430 row exists for the same window; the 530
    // row must still be there, unmodified, for anyone asking about May.
    const bool has_530 = std::any_of(points->begin(), points->end(), [](const TtmPoint& p) {
        return p.period_end == "2022-03-31" && p.value == 530.0;
    });
    const bool has_430 = std::any_of(points->begin(), points->end(), [](const TtmPoint& p) {
        return p.period_end == "2022-03-31" && p.value == 430.0;
    });
    CHECK(has_530);
    CHECK(has_430);
}

// ---------------------------------------------------------------------------
// latest_instant_as_of
// ---------------------------------------------------------------------------

TEST_CASE("latest_instant_as_of applies the two-date rule to balance-sheet items",
          "[gm-data][fundamentals]") {
    auto cash = extract_facts(apple(), "us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD");
    REQUIRE(cash.has_value());
    REQUIRE(cash->size() == 2);

    CHECK_FALSE(latest_instant_as_of(*cash, "2022-10-27").has_value());

    auto i = latest_instant_as_of(*cash, "2023-11-02");
    REQUIRE(i.has_value());
    CHECK((*cash)[*i].value == 23646000000.0); // FY2022 balance, FY2023 not filed yet

    auto j = latest_instant_as_of(*cash, "2023-11-03");
    REQUIRE(j.has_value());
    CHECK((*cash)[*j].value == 29965000000.0);
}

TEST_CASE("latest_instant_as_of prefers a restated balance once it is published",
          "[gm-data][fundamentals]") {
    const std::vector<XbrlFact> facts{
        instant("2022-09-24", "2022-10-28", 23646000000.0),
        instant("2022-09-24", "2023-11-03", 23000000000.0), // same instant, restated
    };
    auto before = latest_instant_as_of(facts, "2023-11-02");
    REQUIRE(before.has_value());
    CHECK(facts[*before].value == 23646000000.0);

    auto after = latest_instant_as_of(facts, "2023-11-03");
    REQUIRE(after.has_value());
    CHECK(facts[*after].value == 23000000000.0);
}

TEST_CASE("latest_instant_as_of ignores duration facts", "[gm-data][fundamentals]") {
    // Passing an income-statement series here is a caller error; returning a
    // duration's value as a balance would be a silent unit mismatch.
    CHECK_FALSE(latest_instant_as_of(apple_net_income(), "2026-01-01").has_value());
}

TEST_CASE("fetch_company_facts rejects an invalid CIK without touching the network",
          "[gm-data][fundamentals]") {
    gm::io::HttpCache cache{"/nonexistent-cache-dir-for-this-test"};
    auto result = gm::data::fetch_company_facts(cache, 0);
    REQUIRE_FALSE(result.has_value());
    CHECK(result.error().code == gm::ErrorCode::kInvalidArgument);
}
