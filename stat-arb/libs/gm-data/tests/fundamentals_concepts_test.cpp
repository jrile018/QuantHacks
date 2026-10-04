// Tests for concept resolution and fundamentals assembly - the layer that
// turns "which of five tags did this filer use for depreciation" into a
// point-in-time row.
//
// The thing worth testing here is not arithmetic. It is that the assembly
// keeps three promises that are all silent when broken:
//
//   1. A balance-sheet item is read as of the row's AVAILABLE_DATE, never as
//      of its period_end. Reading it as of period_end puts a number in the
//      row that nobody could see on the day the row claims to be knowable -
//      look-ahead, and it improves a backtest rather than breaking it.
//   2. A partially-assembled figure is absent, not approximated. EBITDA needs
//      operating income AND depreciation; adding only the one that resolved
//      would produce a plausible number that is simply wrong.
//   3. Zero substituted for an absent optional concept is COUNTED. Reading a
//      missing ShortTermInvestments tag as zero is correct - the issuer holds
//      none - but it is still an assumption, and an assumption nobody can
//      count is indistinguishable from a bug.
//
// Fixture figures are real Apple filings (CIK 0000320193), transcribed from
// data.sec.gov, in their original vintages.

#include <gm-data/fundamentals.hpp>

#include <catch2/catch_test_macros.hpp>

#include <nlohmann/json.hpp>

#include <cmath>
#include <string>
#include <utility>
#include <vector>

using gm::data::build_fundamentals;
using gm::data::ConceptChain;
using gm::data::resolve_concept;

namespace {

constexpr double kMillion = 1e6;

/// A companyfacts document with one full fiscal year of every concept the
/// assembly needs, so tests can remove exactly one thing and see what
/// happens. Values are Apple FY2022/FY2023 order-of-magnitude figures.
std::string full_document(bool include_operating_income = true,
                          bool include_short_term_debt = true,
                          bool include_short_term_investments = true,
                          bool include_cash = true) {
    std::string doc = R"JSON({
  "cik": 320193, "entityName": "Test Co",
  "facts": { "us-gaap": {
    "NetIncomeLoss": { "units": { "USD": [
      {"start":"2021-09-26","end":"2022-09-24","val":99803000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"start":"2022-09-25","end":"2023-09-30","val":96995000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}},
    "DepreciationDepletionAndAmortization": { "units": { "USD": [
      {"start":"2021-09-26","end":"2022-09-24","val":11104000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"start":"2022-09-25","end":"2023-09-30","val":11519000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}},
    "NetCashProvidedByUsedInOperatingActivities": { "units": { "USD": [
      {"start":"2021-09-26","end":"2022-09-24","val":122151000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"start":"2022-09-25","end":"2023-09-30","val":110543000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}},
    "PaymentsToAcquirePropertyPlantAndEquipment": { "units": { "USD": [
      {"start":"2021-09-26","end":"2022-09-24","val":10708000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"start":"2022-09-25","end":"2023-09-30","val":10959000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}},
    "LongTermDebtNoncurrent": { "units": { "USD": [
      {"end":"2022-09-24","val":98959000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"end":"2023-09-30","val":95281000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}},
    "CommonStockSharesOutstanding": { "units": { "shares": [
      {"end":"2022-09-24","val":15943425000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"end":"2023-09-30","val":15550061000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}})JSON";

    if (include_cash) {
        doc += R"JSON(,
    "CashAndCashEquivalentsAtCarryingValue": { "units": { "USD": [
      {"end":"2022-09-24","val":23646000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"end":"2023-09-30","val":29965000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}})JSON";
    }

    if (include_operating_income) {
        doc += R"JSON(,
    "OperatingIncomeLoss": { "units": { "USD": [
      {"start":"2021-09-26","end":"2022-09-24","val":119437000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"start":"2022-09-25","end":"2023-09-30","val":114301000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}})JSON";
    }
    if (include_short_term_debt) {
        doc += R"JSON(,
    "LongTermDebtCurrent": { "units": { "USD": [
      {"end":"2022-09-24","val":11128000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"end":"2023-09-30","val":9822000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}})JSON";
    }
    if (include_short_term_investments) {
        doc += R"JSON(,
    "ShortTermInvestments": { "units": { "USD": [
      {"end":"2022-09-24","val":24658000000,"accn":"a","form":"10-K","filed":"2022-10-28"},
      {"end":"2023-09-30","val":31590000000,"accn":"b","form":"10-K","filed":"2023-11-03"}
    ]}})JSON";
    }
    doc += "\n  }}\n}";
    return doc;
}

nlohmann::json doc(bool oi = true, bool std_debt = true, bool sti = true, bool cash = true) {
    return nlohmann::json::parse(full_document(oi, std_debt, sti, cash));
}

/// The FY2023 row - the one with a full prior year behind it.
const gm::data::FundamentalsRecord& fy2023(const gm::data::FundamentalsBuild& b) {
    for (const auto& row : b.rows) {
        if (row.period_end == "2023-09-30" && row.available_date == "2023-11-03") return row;
    }
    FAIL("no FY2023 row in the build");
    return b.rows.front();
}

} // namespace

TEST_CASE("resolve_concept takes the FIRST candidate present, not any of them",
          "[gm-data][fundamentals][concepts]") {
    // Ordering is the whole point of a chain. If resolution picked whichever
    // tag it happened to see first in the document, two issuers reporting
    // both DepreciationDepletionAndAmortization and Depreciation could end up
    // on different tags - one an aggregate, one a component - and their
    // series would silently not be comparable.
    const auto document = nlohmann::json::parse(R"JSON({"facts": {"us-gaap": {
      "Depreciation": { "units": { "USD": [
        {"start":"2022-01-01","end":"2022-12-31","val":100,"accn":"a","form":"10-K","filed":"2023-02-01"}]}},
      "DepreciationDepletionAndAmortization": { "units": { "USD": [
        {"start":"2022-01-01","end":"2022-12-31","val":175,"accn":"a","form":"10-K","filed":"2023-02-01"}]}}
    }}})JSON");

    const ConceptChain* da = nullptr;
    for (const auto& chain : gm::data::flow_concepts()) {
        if (chain.name == "depreciation_amortisation") da = &chain;
    }
    REQUIRE(da != nullptr);

    const auto resolved = resolve_concept(document, *da);
    REQUIRE(resolved.has_value());
    CHECK(resolved->tag_used == "us-gaap:DepreciationDepletionAndAmortization");
    REQUIRE(resolved->facts.size() == 1);
    CHECK(resolved->facts[0].value == 175.0); // the aggregate, not the component
}

TEST_CASE("resolve_concept reports an entirely absent concept without failing",
          "[gm-data][fundamentals][concepts]") {
    // Absence is the normal state for several concepts at several issuers -
    // 16 of 40 measured have no short-term investments tag at all. Treating
    // it as an error would make the reader unusable on real filings.
    const auto empty_doc = nlohmann::json::parse(R"JSON({"facts": {"us-gaap": {}}})JSON");
    for (const auto& chain : gm::data::instant_concepts()) {
        const auto resolved = resolve_concept(empty_doc, chain);
        INFO("concept = " << chain.name);
        REQUIRE(resolved.has_value());
        CHECK(resolved->tag_used.empty());
        CHECK(resolved->facts.empty());
    }
}

TEST_CASE("build_fundamentals assembles EBITDA and free cash flow by their definitions",
          "[gm-data][fundamentals][concepts]") {
    const auto build = build_fundamentals(doc());
    REQUIRE(build.has_value());
    const auto& row = fy2023(*build);

    CHECK(row.net_income_ttm == 96995 * kMillion);
    // EBITDA = operating income + D&A
    CHECK(row.ebitda_ttm == (114301 + 11519) * kMillion);
    // FCF = operating cash flow - capital expenditure. Capex is reported as a
    // positive payment, so it subtracts; adding it would inflate free cash
    // flow by twice capex and still look like a plausible number.
    CHECK(row.free_cash_flow_ttm == (110543 - 10959) * kMillion);
    // total debt = long-term + short-term
    CHECK(row.total_debt == (95281 + 9822) * kMillion);
    // cash = cash and equivalents + short-term investments
    CHECK(row.cash_and_equivalents == (29965 + 31590) * kMillion);
    CHECK(row.shares_outstanding == 15550061000.0);
}

TEST_CASE("build_fundamentals reads balance-sheet items as of available_date, not period_end",
          "[gm-data][fundamentals][concepts]") {
    // The look-ahead test. The FY2023 balance sheet has period_end
    // 2023-09-30 but was not filed until 2023-11-03. A row anchored on the
    // FY2022 filing (available 2022-10-28) must therefore carry the FY2022
    // balance sheet, never the FY2023 one - even though FY2023's period_end
    // is "before" nothing and its numbers are sitting right there in the
    // same document.
    const auto build = build_fundamentals(doc());
    REQUIRE(build.has_value());

    const gm::data::FundamentalsRecord* fy2022 = nullptr;
    for (const auto& row : build->rows) {
        if (row.available_date == "2022-10-28") fy2022 = &row;
    }
    REQUIRE(fy2022 != nullptr);
    CHECK(fy2022->cash_and_equivalents == (23646 + 24658) * kMillion); // FY2022 figures
    CHECK(fy2022->total_debt == (98959 + 11128) * kMillion);
    CHECK(fy2022->shares_outstanding == 15943425000.0);
    // And emphatically not FY2023's, which were not public until 2023-11-03.
    CHECK(fy2022->cash_and_equivalents != (29965 + 31590) * kMillion);
}

TEST_CASE("build_fundamentals leaves EBITDA absent rather than half-assembled",
          "[gm-data][fundamentals][concepts]") {
    // The bank case: no operating-income subtotal. Depreciation IS present,
    // so a naive assembly would happily return D&A alone as "EBITDA" - a
    // number roughly a tenth of the truth, with nothing to mark it wrong.
    const auto build = build_fundamentals(doc(/*oi=*/false));
    REQUIRE(build.has_value());
    const auto& row = fy2023(*build);

    CHECK(std::isnan(row.ebitda_ttm));
    CHECK(build->tag_used.at("operating_income").empty());
    // Everything not derived from operating income is unaffected - which is
    // the point: this issuer still gets E/P and FCF/P.
    CHECK(row.net_income_ttm == 96995 * kMillion);
    CHECK(row.free_cash_flow_ttm == (110543 - 10959) * kMillion);
    CHECK(std::isfinite(row.shares_outstanding));
}

TEST_CASE("build_fundamentals counts every zero it substitutes for an absent optional",
          "[gm-data][fundamentals][concepts]") {
    // Reading an absent ShortTermInvestments as zero is CORRECT - the issuer
    // holds none, and nobody files a zero. But it is still an assumption, and
    // an assumption nobody can count is indistinguishable from a bug. These
    // counts go to the stage manifest.
    const auto build = build_fundamentals(doc(true, /*std_debt=*/false, /*sti=*/false));
    REQUIRE(build.has_value());
    const auto& row = fy2023(*build);

    CHECK(row.total_debt == 95281 * kMillion);          // long-term only
    CHECK(row.cash_and_equivalents == 29965 * kMillion); // cash only
    CHECK(build->substituted_zero.at("short_term_debt") ==
          static_cast<std::int64_t>(build->rows.size()));
    CHECK(build->substituted_zero.at("short_term_investments") ==
          static_cast<std::int64_t>(build->rows.size()));
    // A REQUIRED concept is never zero-substituted, so it must not appear.
    CHECK(build->substituted_zero.count("cash") == 0);
    CHECK(build->substituted_zero.count("long_term_debt") == 0);
}

TEST_CASE("build_fundamentals publishes which tag actually produced each number",
          "[gm-data][fundamentals][concepts]") {
    const auto build = build_fundamentals(doc());
    REQUIRE(build.has_value());
    CHECK(build->tag_used.at("net_income") == "us-gaap:NetIncomeLoss");
    CHECK(build->tag_used.at("depreciation_amortisation") ==
          "us-gaap:DepreciationDepletionAndAmortization");
    CHECK(build->tag_used.at("capital_expenditure") ==
          "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment");
    CHECK(build->tag_used.at("shares_outstanding") == "us-gaap:CommonStockSharesOutstanding");
    // Every concept in both chains has an entry, present or not - so a reader
    // can distinguish "resolved to nothing" from "never looked".
    for (const auto& chain : gm::data::flow_concepts()) {
        CHECK(build->tag_used.count(std::string{chain.name}) == 1);
    }
    for (const auto& chain : gm::data::instant_concepts()) {
        CHECK(build->tag_used.count(std::string{chain.name}) == 1);
    }
}

TEST_CASE("build_fundamentals fails when there is no net income to anchor on",
          "[gm-data][fundamentals][concepts]") {
    // Not a silent empty result: an issuer with no net income at all means
    // either the document is wrong or the chain is, and both need looking at.
    const auto empty_doc = nlohmann::json::parse(R"JSON({"facts": {"us-gaap": {}}})JSON");
    const auto build = build_fundamentals(empty_doc);
    REQUIRE_FALSE(build.has_value());
    CHECK(build.error().code == gm::ErrorCode::kValidationFailure);
}

TEST_CASE("build_fundamentals never substitutes zero for a REQUIRED concept",
          "[gm-data][fundamentals][concepts]") {
    // The counterpart to the zero-substitution test above, and the one
    // mutation testing found missing: with no test here, replacing the
    // "absent" return with 0.0 passed the entire suite. That mutation
    // fabricates a balance sheet - an issuer reporting no cash would be
    // recorded as holding exactly none, and that zero flows straight into
    // enterprise value as though it had been measured. An enterprise value
    // built on an invented cash figure is wrong in the direction that makes
    // a company look expensive, silently.
    const auto build = build_fundamentals(doc(true, true, true, /*cash=*/false));
    REQUIRE(build.has_value());
    const auto& row = fy2023(*build);

    CHECK(std::isnan(row.cash_and_equivalents));
    CHECK(row.cash_and_equivalents != 0.0);
    CHECK(build->tag_used.at("cash").empty());
    // Never counted as a substitution, because none was made.
    CHECK(build->substituted_zero.count("cash") == 0);
    // And the coordinates that do not need cash are untouched.
    CHECK(row.net_income_ttm == 96995 * kMillion);
    CHECK(row.free_cash_flow_ttm == (110543 - 10959) * kMillion);
}

TEST_CASE("build_fundamentals leaves total debt absent when the long-term leg is missing",
          "[gm-data][fundamentals][concepts]") {
    // Same shape of error on the other required instant. Short-term debt
    // alone is not total debt, and reporting it as though it were would
    // understate enterprise value for every issuer whose debt tags this
    // chain does not reach - 5 of 40 measured.
    auto document = doc();
    document["facts"]["us-gaap"].erase("LongTermDebtNoncurrent");
    const auto build = build_fundamentals(document);
    REQUIRE(build.has_value());
    const auto& row = fy2023(*build);

    CHECK(std::isnan(row.total_debt));
    CHECK(build->tag_used.at("long_term_debt").empty());
    CHECK(build->substituted_zero.count("long_term_debt") == 0);
}

namespace {

/// The depreciation_amortisation chain, which is the only one with a
/// component-sum fallback.
const ConceptChain& da_chain() {
    for (const auto& chain : gm::data::flow_concepts()) {
        if (chain.name == "depreciation_amortisation") return chain;
    }
    FAIL("no depreciation_amortisation chain");
    return gm::data::flow_concepts().front();
}

nlohmann::json components(bool include_depreciation, bool include_amortisation,
                          const char* amortisation_filed = "2023-02-01") {
    nlohmann::json doc = nlohmann::json::parse(R"JSON({"facts": {"us-gaap": {}}})JSON");
    if (include_depreciation) {
        doc["facts"]["us-gaap"]["Depreciation"]["units"]["USD"] =
            nlohmann::json::array({{{"start", "2022-01-01"},
                                    {"end", "2022-12-31"},
                                    {"val", 100},
                                    {"accn", "a"},
                                    {"form", "10-K"},
                                    {"filed", "2023-02-01"}}});
    }
    if (include_amortisation) {
        doc["facts"]["us-gaap"]["AmortizationOfIntangibleAssets"]["units"]["USD"] =
            nlohmann::json::array({{{"start", "2022-01-01"},
                                    {"end", "2022-12-31"},
                                    {"val", 75},
                                    {"accn", "a"},
                                    {"form", "10-K"},
                                    {"filed", amortisation_filed}}});
    }
    return doc;
}

} // namespace

TEST_CASE("resolve_concept adds components when no aggregate is reported",
          "[gm-data][fundamentals][concepts]") {
    // Three of twelve issuers in the first real run reported no
    // depreciation-and-amortisation aggregate at all. Before this, the chain
    // fell through to us-gaap:Depreciation alone - which omits amortisation
    // entirely and understated EBITDA for those issuers with nothing marking
    // it wrong.
    const auto resolved = resolve_concept(components(true, true), da_chain());
    REQUIRE(resolved.has_value());
    CHECK(resolved->tag_used == "us-gaap:Depreciation+us-gaap:AmortizationOfIntangibleAssets");
    REQUIRE(resolved->facts.size() == 1);
    CHECK(resolved->facts[0].value == 175.0); // 100 + 75, not 100
    CHECK(resolved->facts[0].period_end == "2022-12-31");
    CHECK(resolved->facts[0].available_date == "2023-02-01");
}

TEST_CASE("resolve_concept refuses a PARTIAL component sum",
          "[gm-data][fundamentals][concepts]") {
    // Half an add-back is a plausible number that is quietly too small, and
    // an EBITDA that is quietly too small makes a company look cheaper than
    // it is - which is the direction that generates a trade.
    for (auto [dep, amort] : {std::pair{true, false}, std::pair{false, true}}) {
        const auto resolved = resolve_concept(components(dep, amort), da_chain());
        INFO("depreciation = " << dep << ", amortisation = " << amort);
        REQUIRE(resolved.has_value());
        CHECK(resolved->tag_used.empty());
        CHECK(resolved->facts.empty());
    }
}

TEST_CASE("resolve_concept only adds components that describe the same filing",
          "[gm-data][fundamentals][concepts]") {
    // Two components from different filings are two different vintages of a
    // number, not two halves of one. Adding across them would mix a figure
    // published in February with one published in May and stamp the result
    // with whichever date came first - which is look-ahead if that is the
    // earlier one.
    const auto resolved =
        resolve_concept(components(true, true, /*amortisation_filed=*/"2023-05-01"), da_chain());
    REQUIRE(resolved.has_value());
    CHECK(resolved->facts.empty());
    CHECK(resolved->tag_used.empty());
}

TEST_CASE("resolve_concept still prefers a reported aggregate over the component sum",
          "[gm-data][fundamentals][concepts]") {
    // The fallback must stay a fallback. An issuer reporting both the
    // aggregate and its parts would otherwise be at risk of double-counting.
    auto doc = components(true, true);
    doc["facts"]["us-gaap"]["DepreciationDepletionAndAmortization"]["units"]["USD"] =
        nlohmann::json::array({{{"start", "2022-01-01"},
                                {"end", "2022-12-31"},
                                {"val", 180},
                                {"accn", "a"},
                                {"form", "10-K"},
                                {"filed", "2023-02-01"}}});
    const auto resolved = resolve_concept(doc, da_chain());
    REQUIRE(resolved.has_value());
    CHECK(resolved->tag_used == "us-gaap:DepreciationDepletionAndAmortization");
    REQUIRE(resolved->facts.size() == 1);
    CHECK(resolved->facts[0].value == 180.0); // the reported total, not 175 and not 355
}

TEST_CASE("build_fundamentals separates 'this filer reports none' from 'not published yet'",
          "[gm-data][fundamentals][concepts]") {
    // Both produce a zero in the row, and they mean different things. The
    // first is a permanent property of the issuer - it holds no short-term
    // debt, and zero is simply correct. The second is early history: the
    // issuer does report short-term debt, just not by the date this row
    // claims to be knowable on, so the zero is a gap in coverage that will
    // close as the history fills in.
    //
    // A single blended counter cannot tell a run that is mostly early
    // history from one whose issuers genuinely hold none of this - and those
    // call for different responses.
    auto document = doc();
    // Short-term debt exists, but only from the FY2023 filing onward. The
    // FY2022-anchored row (available 2022-10-28) therefore cannot see it.
    document["facts"]["us-gaap"]["LongTermDebtCurrent"]["units"]["USD"] =
        nlohmann::json::array({{{"end", "2023-09-30"},
                                {"val", 9822000000},
                                {"accn", "b"},
                                {"form", "10-K"},
                                {"filed", "2023-11-03"}}});

    const auto build = build_fundamentals(document);
    REQUIRE(build.has_value());

    // The concept resolved - the issuer does report it - so nothing is
    // counted as a filer property.
    CHECK_FALSE(build->tag_used.at("short_term_debt").empty());
    CHECK(build->substituted_zero.count("short_term_debt") == 0);
    // But the FY2022 row could not see it, and that is counted apart.
    CHECK(build->substituted_zero_not_yet_published.at("short_term_debt") >= 1);

    const gm::data::FundamentalsRecord* fy2022 = nullptr;
    for (const auto& row : build->rows) {
        if (row.available_date == "2022-10-28") fy2022 = &row;
    }
    REQUIRE(fy2022 != nullptr);
    CHECK(fy2022->total_debt == 98959 * kMillion); // long-term only, current portion unseen
    // And the FY2023 row, which can see it, includes it.
    CHECK(fy2023(*build).total_debt == (95281 + 9822) * kMillion);
}
