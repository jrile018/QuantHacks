#include <gm-core/instrument.hpp>

#include <algorithm>

namespace gm {

namespace {

/// Zero-padded to ten digits, the SEC's own canonical width. Without
/// this, 320193 and 0000320193 are different strings for the same
/// issuer, and the registry would report a rename that is really a
/// formatting difference.
std::string canonical_cik(std::int64_t cik) {
    std::string digits = std::to_string(cik);
    if (digits.size() < 10) digits.insert(0, 10 - digits.size(), '0');
    return "CIK:" + digits;
}

}  // namespace

Result<InstrumentId> InstrumentId::from_cik(std::int64_t cik) {
    if (cik <= 0) {
        // gm-universe writes 0 for a row with no metadata. Accepting it
        // would collapse every unidentified name in the panel onto one
        // shared key, which is worse than having no key at all.
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "a CIK must be positive", std::to_string(cik)));
    }
    return InstrumentId{canonical_cik(cik), true};
}

Result<InstrumentId> InstrumentId::from_ticker(const std::string& ticker) {
    if (ticker.empty()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "an instrument stand-in needs a ticker", "empty"));
    }
    return InstrumentId{"TICKER:" + ticker, false};
}

Result<InstrumentId> InstrumentId::resolve(std::optional<std::int64_t> cik, const std::string& ticker) {
    if (cik.has_value() && *cik > 0) return from_cik(*cik);
    return from_ticker(ticker);
}

VoidResult InstrumentRegistry::observe(const std::string& ticker, std::optional<std::int64_t> cik) {
    auto id = InstrumentId::resolve(cik, ticker);
    if (!id) return tl::unexpected(id.error());

    auto existing = ids_by_ticker_.find(ticker);
    if (existing == ids_by_ticker_.end()) {
        ids_by_ticker_.emplace(ticker, *id);
    } else if (existing->second != *id) {
        // The same ticker seen under two identities. Both are kept -
        // that IS the reused-symbol finding, and dropping either would
        // hide it - but the forward lookup has to answer with one, and
        // it answers with the first, so a later reuse cannot silently
        // rewrite history that has already been joined.
        tickers_by_id_[*id].insert(ticker);
        return {};
    }
    tickers_by_id_[*id].insert(ticker);
    return {};
}

std::optional<InstrumentId> InstrumentRegistry::id_for(const std::string& ticker) const {
    auto it = ids_by_ticker_.find(ticker);
    if (it == ids_by_ticker_.end()) return std::nullopt;
    return it->second;
}

std::vector<TickerAlias> InstrumentRegistry::aliases() const {
    std::vector<TickerAlias> out;
    for (const auto& [id, tickers] : tickers_by_id_) {
        if (tickers.size() < 2) continue;
        TickerAlias alias;
        alias.id = id;
        alias.tickers.assign(tickers.begin(), tickers.end());
        out.push_back(std::move(alias));
    }
    return out;
}

std::vector<ReusedTicker> InstrumentRegistry::reused_tickers() const {
    // Inverted from the same store rather than maintained separately, so
    // the two views cannot disagree.
    std::map<std::string, std::set<InstrumentId>> by_ticker;
    for (const auto& [id, tickers] : tickers_by_id_) {
        for (const auto& t : tickers) by_ticker[t].insert(id);
    }
    std::vector<ReusedTicker> out;
    for (const auto& [ticker, ids] : by_ticker) {
        if (ids.size() < 2) continue;
        ReusedTicker reused;
        reused.ticker = ticker;
        reused.ids.assign(ids.begin(), ids.end());
        out.push_back(std::move(reused));
    }
    return out;
}

std::size_t InstrumentRegistry::num_provisional() const noexcept {
    return static_cast<std::size_t>(std::count_if(
        tickers_by_id_.begin(), tickers_by_id_.end(),
        [](const auto& kv) { return !kv.first.is_permanent(); }));
}

}  // namespace gm
