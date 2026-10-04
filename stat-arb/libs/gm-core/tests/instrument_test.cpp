// Tests for permanent instrument identity (ADR-023).
//
// The two that matter are the rename and the reused symbol: they are
// the concrete failures a ticker-as-identity causes in this panel, and
// they fail in opposite directions, so an implementation that catches
// only one is not half right.

#include <gm-core/instrument.hpp>

#include <catch2/catch_test_macros.hpp>

#include <string>
#include <vector>

using gm::InstrumentId;
using gm::InstrumentRegistry;

TEST_CASE("a CIK is canonical regardless of how it was written", "[gm-core][instrument]") {
    // The SEC writes CIKs zero-padded to ten digits; parquet stores an
    // integer. Without canonicalisation, 320193 and 0000320193 are two
    // different keys for one issuer, and the registry would report a
    // rename that is really a formatting difference.
    const auto a = InstrumentId::from_cik(320193);
    REQUIRE(a.has_value());
    CHECK(a->value() == "CIK:0000320193");
    CHECK(a->is_permanent());
}

TEST_CASE("a missing CIK becomes a stand-in that admits what it is",
          "[gm-core][instrument]") {
    // 394 of 897 tickers with price history have no metadata at all, and
    // they skew towards the old departures - precisely where renames
    // hide. A stand-in key is unavoidable; a stand-in that cannot be
    // TOLD from a real key is not, and would turn a known blind spot
    // into an invisible one.
    const auto id = InstrumentId::resolve(std::nullopt, "OLDCO");
    REQUIRE(id.has_value());
    CHECK(id->value() == "TICKER:OLDCO");
    CHECK_FALSE(id->is_permanent());

    // gm-universe writes 0 for a row with no metadata. Treating that as
    // a CIK would collapse every unidentified name in the panel onto one
    // shared key - worse than having no key.
    const auto zero = InstrumentId::resolve(0, "OLDCO");
    REQUIRE(zero.has_value());
    CHECK_FALSE(zero->is_permanent());
    CHECK(zero->value() == "TICKER:OLDCO");

    CHECK_FALSE(InstrumentId::from_cik(0).has_value());
    CHECK_FALSE(InstrumentId::from_cik(-5).has_value());
    CHECK_FALSE(InstrumentId::from_ticker("").has_value());
}

TEST_CASE("a ticker change is one instrument, not a departure and an arrival",
          "[gm-core][instrument]") {
    // The BK -> BNY case. Under ticker-as-identity the membership series
    // shows one name leaving and another joining: the survivorship
    // correction counts a departure that never happened, and sixteen
    // years of continuous price history becomes two shorter series.
    InstrumentRegistry registry;
    REQUIRE(registry.observe("BK", 1390777).has_value());
    REQUIRE(registry.observe("BNY", 1390777).has_value());
    REQUIRE(registry.observe("AAPL", 320193).has_value());

    CHECK(registry.num_instruments() == 2);  // not three
    CHECK(registry.num_tickers() == 3);

    const auto aliases = registry.aliases();
    REQUIRE(aliases.size() == 1);
    CHECK(aliases[0].id.value() == "CIK:0001390777");
    CHECK(aliases[0].tickers == std::vector<std::string>{"BK", "BNY"});

    // Both strings resolve to the same instrument, which is what makes
    // the two price series joinable.
    CHECK(registry.id_for("BK") == registry.id_for("BNY"));
    CHECK(registry.id_for("AAPL") != registry.id_for("BK"));
    CHECK_FALSE(registry.id_for("NEVERSEEN").has_value());
}

TEST_CASE("a reused symbol is two instruments, not one", "[gm-core][instrument]") {
    // The opposite failure, and the more dangerous one: exchanges
    // reassign symbols after a delisting, so joining on the string welds
    // two unrelated issuers into one series with a discontinuity in the
    // middle that no data screen flags, because each half is
    // individually clean.
    InstrumentRegistry registry;
    REQUIRE(registry.observe("XYZ", 111).has_value());
    REQUIRE(registry.observe("XYZ", 222).has_value());

    CHECK(registry.num_instruments() == 2);
    const auto reused = registry.reused_tickers();
    REQUIRE(reused.size() == 1);
    CHECK(reused[0].ticker == "XYZ");
    CHECK(reused[0].ids.size() == 2);

    // The forward lookup still answers with the first identity seen, so
    // a later reuse cannot silently rewrite a join that already
    // happened.
    const auto id = registry.id_for("XYZ");
    REQUIRE(id.has_value());
    CHECK(id->value() == "CIK:0000000111");
}

TEST_CASE("a clean panel reports no pathologies", "[gm-core][instrument]") {
    // The null case. An implementation that reported aliases for every
    // instrument would pass the two tests above and be useless.
    InstrumentRegistry registry;
    REQUIRE(registry.observe("AAPL", 320193).has_value());
    REQUIRE(registry.observe("MSFT", 789019).has_value());
    REQUIRE(registry.observe("XOM", 34088).has_value());
    CHECK(registry.aliases().empty());
    CHECK(registry.reused_tickers().empty());
    CHECK(registry.num_instruments() == 3);
    CHECK(registry.num_provisional() == 0);
}

TEST_CASE("observing the same pair twice changes nothing", "[gm-core][instrument]") {
    // universe.parquet holds one row per ticker per trading day, so the
    // registry sees the same pair a few thousand times. If that
    // accumulated, every name would look like an alias of itself.
    InstrumentRegistry registry;
    for (int i = 0; i < 500; ++i) {
        REQUIRE(registry.observe("AAPL", 320193).has_value());
    }
    CHECK(registry.num_instruments() == 1);
    CHECK(registry.num_tickers() == 1);
    CHECK(registry.aliases().empty());
}

TEST_CASE("the blind spot is counted rather than assumed", "[gm-core][instrument]") {
    InstrumentRegistry registry;
    REQUIRE(registry.observe("AAPL", 320193).has_value());
    REQUIRE(registry.observe("GONE1", std::nullopt).has_value());
    REQUIRE(registry.observe("GONE2", std::nullopt).has_value());

    CHECK(registry.num_instruments() == 3);
    CHECK(registry.num_provisional() == 2);
    // Two names with no permanent key are two names a rename could hide
    // behind, and they stay separate instruments rather than being
    // merged on the strength of nothing.
    CHECK(registry.aliases().empty());
}

TEST_CASE("an empty ticker is an error", "[gm-core][instrument]") {
    InstrumentRegistry registry;
    const auto r = registry.observe("", std::nullopt);
    REQUIRE_FALSE(r.has_value());
    CHECK(r.error().code == gm::ErrorCode::kInvalidArgument);
}

TEST_CASE("listings do not depend on observation order", "[gm-core][instrument]") {
    // Every listing here is emitted into an artifact, so two runs over
    // the same observations must produce the same bytes (ADR-003).
    InstrumentRegistry forward, backward;
    const std::vector<std::pair<std::string, std::int64_t>> obs{
        {"BK", 1390777}, {"BNY", 1390777}, {"AAPL", 320193}, {"XYZ", 111}, {"XYZ", 222}};
    for (const auto& [t, c] : obs) REQUIRE(forward.observe(t, c).has_value());
    for (auto it = obs.rbegin(); it != obs.rend(); ++it) {
        REQUIRE(backward.observe(it->first, it->second).has_value());
    }

    const auto fa = forward.aliases();
    const auto ba = backward.aliases();
    REQUIRE(fa.size() == ba.size());
    for (std::size_t i = 0; i < fa.size(); ++i) {
        CHECK(fa[i].id.value() == ba[i].id.value());
        CHECK(fa[i].tickers == ba[i].tickers);
    }

    const auto fr = forward.reused_tickers();
    const auto br = backward.reused_tickers();
    REQUIRE(fr.size() == br.size());
    for (std::size_t i = 0; i < fr.size(); ++i) {
        CHECK(fr[i].ticker == br[i].ticker);
        REQUIRE(fr[i].ids.size() == br[i].ids.size());
        for (std::size_t j = 0; j < fr[i].ids.size(); ++j) {
            CHECK(fr[i].ids[j].value() == br[i].ids[j].value());
        }
    }
}
