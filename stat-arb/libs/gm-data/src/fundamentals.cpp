#include <gm-data/fundamentals.hpp>

#include <gm-core/date.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <map>
#include <set>
#include <vector>

namespace gm::data {
namespace {

std::string zero_padded_cik(std::int64_t cik) {
    char buf[32]; // 32, not 16: a full-width int64 needs 20 digits, and -Werror=format-truncation is right to insist
    std::snprintf(buf, sizeof(buf), "%010lld", static_cast<long long>(cik));
    return std::string{buf};
}

// A fiscal quarter is a 13-week period, so its day count varies; 91.3 days
// is the mean quarter and rounding to the nearest integer separates 1/2/3/4
// quarter durations cleanly without ever needing an exact match.
constexpr double kDaysPerQuarter = 91.3;

/// Among `candidates`, the index of the one filed latest but no later than
/// `cutoff`. nullopt if none qualifies.
std::optional<std::size_t> latest_filed_by(const std::vector<XbrlFact>& facts,
                                            const std::vector<std::size_t>& candidates,
                                            std::string_view cutoff) {
    std::optional<std::size_t> best;
    for (std::size_t i : candidates) {
        if (facts[i].available_date > cutoff) continue;
        if (!best || facts[i].available_date > facts[*best].available_date) best = i;
    }
    return best;
}

} // namespace

Result<std::vector<XbrlFact>> extract_facts(const nlohmann::json& companyfacts,
                                             std::string_view taxonomy, std::string_view tag,
                                             std::string_view unit) {
    std::vector<XbrlFact> out;
    // One try/catch for all navigation: ADR-019 forbids an exception crossing
    // a library boundary, and nlohmann throws on every kind of shape error.
    try {
        if (!companyfacts.contains("facts")) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                                   "companyfacts document has no 'facts' object"));
        }
        const auto& facts = companyfacts.at("facts");

        const std::string taxonomy_key{taxonomy};
        if (!facts.contains(taxonomy_key)) return out; // filer uses another taxonomy
        const auto& tax = facts.at(taxonomy_key);

        const std::string tag_key{tag};
        if (!tax.contains(tag_key)) return out; // absent tag is not an error
        const auto& node = tax.at(tag_key);

        if (!node.contains("units")) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                                   "XBRL tag has no 'units' object",
                                                   taxonomy_key + ":" + tag_key));
        }
        const std::string unit_key{unit};
        if (!node.at("units").contains(unit_key)) return out; // reported in another unit

        for (const auto& entry : node.at("units").at(unit_key)) {
            // end, val and filed are the three fields this code cannot work
            // without. start is genuinely absent for instants.
            if (!entry.contains("end") || !entry.contains("val") || !entry.contains("filed")) {
                return tl::unexpected(gm::Error::make(
                    gm::ErrorCode::kParseFailure, "XBRL fact missing end/val/filed",
                    taxonomy_key + ":" + tag_key + " [" + unit_key + "]"));
            }
            XbrlFact fact;
            if (entry.contains("start")) fact.period_start = entry.at("start").get<std::string>();
            fact.period_end = entry.at("end").get<std::string>();
            fact.available_date = entry.at("filed").get<std::string>();
            fact.value = entry.at("val").get<double>();
            if (entry.contains("form")) fact.form = entry.at("form").get<std::string>();
            if (entry.contains("accn")) fact.accession = entry.at("accn").get<std::string>();
            out.push_back(std::move(fact));
        }
    } catch (const nlohmann::json::exception& e) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                               "companyfacts document has an unexpected shape",
                                               std::string{taxonomy} + ":" + std::string{tag} +
                                                   ": " + e.what()));
    }
    return out;
}

int quarters_spanned(const XbrlFact& fact) {
    if (fact.period_start.empty()) return 0; // an instant
    const auto start = gm::Date::parse_iso(fact.period_start);
    const auto end = gm::Date::parse_iso(fact.period_end);
    if (!start || !end) return 0;
    const double days = static_cast<double>((*end - *start).count());
    if (days <= 0.0) return 0;
    return static_cast<int>(std::lround(days / kDaysPerQuarter));
}

Result<std::vector<TtmPoint>> assemble_ttm(const std::vector<XbrlFact>& facts) {
    // Index the duration facts by (fiscal-year start, quarters spanned). An
    // instant carries no window and cannot contribute to a TTM.
    std::map<std::pair<std::string, int>, std::vector<std::size_t>> by_period;
    std::set<std::string> annual_starts;
    // A fiscal year begins where its FIRST QUARTER begins. Deriving the set
    // of fiscal-year starts from annual figures alone looks equivalent and is
    // not: the current, in-progress year has no 10-K yet, so every one of its
    // quarters would be discarded as un-anchorable - dropping exactly the
    // most recent data, which is the data a backtest running up to today
    // depends on. Caught by a synthetic fixture; the real two-completed-year
    // fixture could not have shown it.
    std::set<std::string> fiscal_year_starts;

    for (std::size_t i = 0; i < facts.size(); ++i) {
        const int q = quarters_spanned(facts[i]);
        if (q < 1 || q > 4) continue;
        by_period[{facts[i].period_start, q}].push_back(i);
        if (q == 1 || q == 4) fiscal_year_starts.insert(facts[i].period_start);
        if (q == 4) annual_starts.insert(facts[i].period_start);
    }

    if (annual_starts.empty()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure,
            "no annual (four-quarter) figure present, so no twelve-month window can be anchored",
            std::to_string(facts.size()) + " facts"));
    }

    // ISO dates sort chronologically and fiscal-year starts strictly advance,
    // so lexical order is calendar order even for a filer that shifts its
    // fiscal calendar (Apple moved from 2021-09-26 to 2022-09-25 to
    // 2023-10-01).
    const std::vector<std::string> ordered_starts(fiscal_year_starts.begin(),
                                                  fiscal_year_starts.end());
    std::map<std::string, std::string> prior_start;
    for (std::size_t k = 1; k < ordered_starts.size(); ++k) {
        prior_start[ordered_starts[k]] = ordered_starts[k - 1];
    }

    std::vector<TtmPoint> out;

    // An annual figure IS a twelve-month window; every vintage of it is a
    // separate answer to "what was the TTM as of when you asked".
    for (const std::string& start : ordered_starts) {
        for (std::size_t i : by_period[{start, 4}]) {
            out.push_back(TtmPoint{facts[i].period_end, facts[i].available_date, facts[i].value});
        }
    }

    // Interim windows, by roll-forward.
    for (const auto& [key, indices] : by_period) {
        const auto& [start, q] = key;
        if (q == 4) continue;
        if (fiscal_year_starts.count(start) == 0) continue; // not a year-to-date figure
        const auto prior = prior_start.find(start);
        if (prior == prior_start.end()) continue; // no prior year in the data

        const auto base_it = by_period.find({prior->second, 4});
        const auto prior_ytd_it = by_period.find({prior->second, q});
        if (base_it == by_period.end() || prior_ytd_it == by_period.end()) continue;

        for (std::size_t cur : indices) {
            // One row per moment at which this window's answer could change:
            // when the current year-to-date figure is filed, and again
            // whenever a component of it is later restated. Restating the
            // base year genuinely alters what the trailing twelve months
            // were, and that revised answer is only true from the
            // restatement's own filing date onward - so it becomes an
            // additional vintage rather than overwriting the original.
            std::set<std::string> epochs{facts[cur].available_date};
            for (const std::vector<std::size_t>* component :
                 {&base_it->second, &prior_ytd_it->second}) {
                for (std::size_t i : *component) {
                    if (facts[i].available_date > facts[cur].available_date) {
                        epochs.insert(facts[i].available_date);
                    }
                }
            }

            for (const std::string& epoch : epochs) {
                // Each component in the latest vintage on file at `epoch` -
                // never a later restatement, which is the look-ahead this
                // whole module exists to avoid.
                const auto base = latest_filed_by(facts, base_it->second, epoch);
                const auto prior_ytd = latest_filed_by(facts, prior_ytd_it->second, epoch);
                if (!base || !prior_ytd) continue;
                const double value =
                    facts[*base].value + facts[cur].value - facts[*prior_ytd].value;
                out.push_back(TtmPoint{facts[cur].period_end, epoch, value});
            }
        }
    }

    std::sort(out.begin(), out.end(), [](const TtmPoint& a, const TtmPoint& b) {
        if (a.period_end != b.period_end) return a.period_end < b.period_end;
        if (a.available_date != b.available_date) return a.available_date < b.available_date;
        return a.value < b.value;
    });
    out.erase(std::unique(out.begin(), out.end(),
                          [](const TtmPoint& a, const TtmPoint& b) {
                              return a.period_end == b.period_end &&
                                     a.available_date == b.available_date && a.value == b.value;
                          }),
              out.end());
    return out;
}

std::optional<std::size_t> latest_instant_as_of(const std::vector<XbrlFact>& facts,
                                                 std::string_view as_of) {
    std::optional<std::size_t> best;
    for (std::size_t i = 0; i < facts.size(); ++i) {
        const XbrlFact& fact = facts[i];
        if (!fact.period_start.empty()) continue; // durations are not instants
        if (fact.available_date > as_of) continue; // not published yet
        if (!best) {
            best = i;
            continue;
        }
        const XbrlFact& incumbent = facts[*best];
        const bool newer_instant = fact.period_end > incumbent.period_end;
        const bool same_instant_newer_filing =
            fact.period_end == incumbent.period_end &&
            fact.available_date > incumbent.available_date;
        if (newer_instant || same_instant_newer_filing) best = i;
    }
    return best;
}

const std::vector<ConceptChain>& flow_concepts() {
    // Ordering within a chain is "most standard first", so a filer that
    // reports both gets the same tag as everyone else and the series stay
    // comparable across issuers. The coverage each candidate adds is in the
    // header table.
    static const std::vector<ConceptChain> kChains = {
        {"net_income",
         {{"us-gaap", "NetIncomeLoss", "USD"},
          // ProfitLoss includes non-controlling interests; second because
          // NetIncomeLoss is the attributable-to-parent figure a per-share
          // yield wants.
          {"us-gaap", "ProfitLoss", "USD"}},
         false,
         {}},
        {"operating_income", {{"us-gaap", "OperatingIncomeLoss", "USD"}}, false, {}},
        {"depreciation_amortisation",
         // Aggregates only. Depreciation and AmortizationOfIntangibleAssets
         // are COMPONENTS: either one alone understates the add-back, and an
         // EBITDA that is quietly too small is worse than one reported as
         // unavailable. They move to sum_components below, where both are
         // required together.
         {{"us-gaap", "DepreciationDepletionAndAmortization", "USD"},
          {"us-gaap", "DepreciationAmortizationAndAccretionNet", "USD"},
          {"us-gaap", "DepreciationAndAmortization", "USD"}},
         false,
         {{"us-gaap", "Depreciation", "USD"},
          {"us-gaap", "AmortizationOfIntangibleAssets", "USD"}}},
        {"operating_cash_flow",
         {{"us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"},
          {"us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "USD"}},
         false,
         {}},
        {"capital_expenditure",
         {{"us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD"},
          {"us-gaap", "PaymentsToAcquireProductiveAssets", "USD"},
          {"us-gaap", "PaymentsForCapitalImprovements", "USD"}},
         false,
         {}},
    };
    return kChains;
}

const std::vector<ConceptChain>& instant_concepts() {
    static const std::vector<ConceptChain> kChains = {
        {"long_term_debt",
         {{"us-gaap", "LongTermDebtNoncurrent", "USD"},
          {"us-gaap", "LongTermDebt", "USD"},
          {"us-gaap", "LongTermDebtAndCapitalLeaseObligations", "USD"}},
         false,
         {}},
        // Absent short-term debt means the issuer has none maturing within a
        // year, not that it failed to report - 8 of 40 issuers measured. Zero
        // is the correct reading and it is counted.
        {"short_term_debt",
         {{"us-gaap", "LongTermDebtCurrent", "USD"},
          {"us-gaap", "DebtCurrent", "USD"},
          {"us-gaap", "ShortTermBorrowings", "USD"},
          {"us-gaap", "OtherShortTermBorrowings", "USD"}},
         true,
         {}},
        {"cash",
         {{"us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"},
          {"us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "USD"}},
         false,
         {}},
        // Same reasoning as short-term debt, and the largest such group: 16
        // of 40 issuers hold no separately-reported marketable securities.
        {"short_term_investments",
         {{"us-gaap", "ShortTermInvestments", "USD"},
          {"us-gaap", "MarketableSecuritiesCurrent", "USD"},
          {"us-gaap", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "USD"},
          {"us-gaap", "OtherShortTermInvestments", "USD"}},
         true,
         {}},
        {"shares_outstanding",
         // CommonStockSharesOutstanding is the point-in-time count and is
         // preferred; the weighted averages are period figures standing in
         // for it, which is why they are last. dei's entity-level count is
         // cover-page data and available for nearly everyone.
         {{"us-gaap", "CommonStockSharesOutstanding", "shares"},
          {"dei", "EntityCommonStockSharesOutstanding", "shares"},
          {"us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares"},
          {"us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares"}},
         false,
         {}},
    };
    return kChains;
}

Result<ResolvedConcept> resolve_concept(const nlohmann::json& companyfacts,
                                        const ConceptChain& chain) {
    ResolvedConcept out;
    for (const TagCandidate& candidate : chain.candidates) {
        auto facts = extract_facts(companyfacts, candidate.taxonomy, candidate.tag, candidate.unit);
        // A malformed document IS an error and stops here; an absent tag is
        // not, and just moves to the next candidate.
        if (!facts) return tl::unexpected(facts.error());
        if (facts->empty()) continue;
        out.tag_used = std::string{candidate.taxonomy} + ":" + std::string{candidate.tag};
        out.facts = std::move(*facts);
        return out;
    }

    // No reported aggregate. Fall back to adding the components - but only
    // if EVERY one is present, because a partial sum is a wrong number that
    // looks right.
    if (!chain.sum_components.empty()) {
        std::vector<std::vector<XbrlFact>> parts;
        std::string combined_name;
        for (const TagCandidate& candidate : chain.sum_components) {
            auto facts =
                extract_facts(companyfacts, candidate.taxonomy, candidate.tag, candidate.unit);
            if (!facts) return tl::unexpected(facts.error());
            if (facts->empty()) return out; // one component missing: concept absent
            if (!combined_name.empty()) combined_name += "+";
            combined_name += std::string{candidate.taxonomy} + ":" + std::string{candidate.tag};
            parts.push_back(std::move(*facts));
        }

        // Add component facts that describe the SAME period and were filed on
        // the same day. Anything without a partner in every other component
        // is dropped rather than carried through half-summed - the same rule
        // as above, applied per fact.
        const std::vector<XbrlFact>& first = parts.front();
        for (const XbrlFact& anchor : first) {
            double total = anchor.value;
            bool complete = true;
            for (std::size_t k = 1; k < parts.size(); ++k) {
                bool found = false;
                for (const XbrlFact& other : parts[k]) {
                    if (other.period_start == anchor.period_start &&
                        other.period_end == anchor.period_end &&
                        other.available_date == anchor.available_date) {
                        total += other.value;
                        found = true;
                        break;
                    }
                }
                if (!found) {
                    complete = false;
                    break;
                }
            }
            if (!complete) continue;
            XbrlFact summed = anchor;
            summed.value = total;
            out.facts.push_back(std::move(summed));
        }
        if (!out.facts.empty()) out.tag_used = combined_name;
    }
    return out; // nothing matched; tag_used stays empty
}

namespace {

constexpr double kAbsent = std::numeric_limits<double>::quiet_NaN();

/// The best TTM figure for `period_end` OR ANY EARLIER PERIOD that had been
/// published by `as_of`.
///
/// "or earlier" is doing real work. Net income is re-reported as a
/// comparative in nearly every later filing and so has many more vintages
/// than capex or operating income; requiring an exact period match meant a
/// comparative-only anchor produced a row carrying net income and nothing
/// else, and since the consumer keeps one row per ticker-day, such a row
/// winning cost that day its other coordinates entirely. Measured before
/// this change: every issuer resolved a capex tag, yet only 64% of
/// ticker-days got a free-cash-flow yield.
///
/// This introduces no look-ahead. The available_date cutoff is unchanged and
/// still strict; all that relaxes is the period, in the backwards direction
/// only - which is precisely what an analyst reads off the latest filing to
/// hand. It does mean two coordinates on one row can describe different
/// periods, when one line item has been reported more recently than another;
/// `stale_component` counts those.
std::optional<double> ttm_value_as_of(const std::vector<TtmPoint>& series,
                                       const std::string& period_end,
                                       const std::string& as_of, bool* used_earlier_period) {
    std::optional<double> best;
    std::string best_period;
    std::string best_date;
    for (const TtmPoint& p : series) {
        if (p.period_end > period_end) continue;   // never a later period
        if (p.available_date > as_of) continue;    // never published later
        const bool newer_period = !best || p.period_end > best_period;
        const bool same_period_newer_filing =
            best && p.period_end == best_period && p.available_date > best_date;
        if (newer_period || same_period_newer_filing) {
            best = p.value;
            best_period = p.period_end;
            best_date = p.available_date;
        }
    }
    if (best && used_earlier_period != nullptr && best_period != period_end) {
        *used_earlier_period = true;
    }
    return best;
}

/// Resolves a whole chain list into name -> facts, recording which tag won.
Result<std::map<std::string, ResolvedConcept>> resolve_all(
    const nlohmann::json& doc, const std::vector<ConceptChain>& chains) {
    std::map<std::string, ResolvedConcept> out;
    for (const ConceptChain& chain : chains) {
        auto resolved = resolve_concept(doc, chain);
        if (!resolved) return tl::unexpected(resolved.error());
        out[std::string{chain.name}] = std::move(*resolved);
    }
    return out;
}

} // namespace

Result<FundamentalsBuild> build_fundamentals(const nlohmann::json& companyfacts) {
    FundamentalsBuild build;

    auto flows = resolve_all(companyfacts, flow_concepts());
    if (!flows) return tl::unexpected(flows.error());
    auto instants = resolve_all(companyfacts, instant_concepts());
    if (!instants) return tl::unexpected(instants.error());

    for (const auto& [name, resolved] : *flows) build.tag_used[name] = resolved.tag_used;
    for (const auto& [name, resolved] : *instants) build.tag_used[name] = resolved.tag_used;

    // TTM for every flow concept that resolved. assemble_ttm fails when there
    // is no annual figure to anchor a twelve-month window; that is a
    // per-concept absence, not a document-level error, so it is recorded as
    // an empty series rather than propagated.
    std::map<std::string, std::vector<TtmPoint>> ttm;
    for (const auto& [name, resolved] : *flows) {
        if (resolved.facts.empty()) continue;
        auto series = assemble_ttm(resolved.facts);
        if (series) ttm[name] = std::move(*series);
    }

    const auto anchor = ttm.find("net_income");
    if (anchor == ttm.end() || anchor->second.empty()) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kValidationFailure,
            "no net-income TTM could be assembled, so no fundamentals row can be anchored",
            build.tag_used["net_income"].empty() ? "no net-income tag present"
                                                 : "tag present but no annual figure"));
    }

    // 'concept' is a keyword in C++20, which is what this project builds as -
    // naming the parameter that produced a wall of unrelated parse errors.
    // 'concept' is a keyword in C++20, which is what this project builds as.
    const auto instant_value = [&](const char* concept_name, const std::string& as_of,
                                    bool absence_means_zero) -> double {
        const auto it = instants->find(concept_name);
        if (it == instants->end() || it->second.facts.empty()) {
            // The issuer reports this concept nowhere: a permanent property
            // of the filer, and for an optional concept, zero is the right
            // reading - nobody files a zero, they omit the line.
            if (absence_means_zero) {
                ++build.substituted_zero[concept_name];
                return 0.0;
            }
            return kAbsent;
        }
        const auto idx = latest_instant_as_of(it->second.facts, as_of);
        if (!idx) {
            // The concept exists but nothing was published by this date -
            // early history, before the issuer's first balance sheet in the
            // data. Counted SEPARATELY: this is a property of the date, not
            // of the filer, and lumping the two together makes a run that is
            // mostly early history indistinguishable from one whose issuers
            // genuinely hold none of this.
            if (absence_means_zero) {
                ++build.substituted_zero_not_yet_published[concept_name];
                return 0.0;
            }
            return kAbsent;
        }
        return it->second.facts[*idx].value;
    };

    for (const TtmPoint& point : anchor->second) {
        FundamentalsRecord row;
        row.period_end = point.period_end;
        row.available_date = point.available_date;
        row.net_income_ttm = point.value;

        // EBITDA = operating income + D&A. Both required: adding only one of
        // them would silently understate the figure rather than reporting it
        // as unavailable, and the result would look plausible.
        bool stale = false;
        const auto op = ttm.count("operating_income")
                            ? ttm_value_as_of(ttm["operating_income"], row.period_end,
                                              row.available_date, &stale)
                            : std::nullopt;
        const auto da = ttm.count("depreciation_amortisation")
                            ? ttm_value_as_of(ttm["depreciation_amortisation"], row.period_end,
                                              row.available_date, &stale)
                            : std::nullopt;
        row.ebitda_ttm = (op && da) ? (*op + *da) : kAbsent;
        if (stale && std::isfinite(row.ebitda_ttm)) ++build.stale_component["ebitda_ttm"];

        // Free cash flow = operating cash flow - capital expenditure. Capex is
        // reported as a positive payment amount, so it subtracts.
        bool stale_fcf = false;
        const auto ocf = ttm.count("operating_cash_flow")
                             ? ttm_value_as_of(ttm["operating_cash_flow"], row.period_end,
                                               row.available_date, &stale_fcf)
                             : std::nullopt;
        const auto capex = ttm.count("capital_expenditure")
                               ? ttm_value_as_of(ttm["capital_expenditure"], row.period_end,
                                                 row.available_date, &stale_fcf)
                               : std::nullopt;
        row.free_cash_flow_ttm = (ocf && capex) ? (*ocf - *capex) : kAbsent;
        if (stale_fcf && std::isfinite(row.free_cash_flow_ttm)) {
            ++build.stale_component["free_cash_flow_ttm"];
        }

        // Balance-sheet items as of the day this row became knowable - NOT as
        // of period_end. A row must never contain a number published after
        // the date it claims to be knowable on.
        const double ltd =
            instant_value("long_term_debt", row.available_date, false);
        const double std_ =
            instant_value("short_term_debt", row.available_date, true);
        row.total_debt = std::isfinite(ltd) ? ltd + std_ : kAbsent;

        const double cash =
            instant_value("cash", row.available_date, false);
        const double sti = instant_value("short_term_investments", row.available_date, true);
        row.cash_and_equivalents = std::isfinite(cash) ? cash + sti : kAbsent;

        row.shares_outstanding =
            instant_value("shares_outstanding", row.available_date, false);

        build.rows.push_back(std::move(row));
    }

    return build;
}

Result<std::string> fetch_company_facts(gm::io::HttpCache& cache, std::int64_t cik) {
    if (cik <= 0) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "CIK must be positive", std::to_string(cik)));
    }
    const std::string padded = zero_padded_cik(cik);
    const std::string url =
        "https://data.sec.gov/api/xbrl/companyfacts/CIK" + padded + ".json";
    // A company's already-filed history only grows, so a cached document
    // stays valid indefinitely for every date before the fetch timestamp -
    // the same reasoning earnings.cpp records for the submissions API.
    auto entry = cache.get(url, "sec_companyfacts_CIK" + padded);
    if (!entry) return tl::unexpected(entry.error());
    auto body = entry->read_body();
    if (!body) return tl::unexpected(body.error());
    return *body;
}

} // namespace gm::data
