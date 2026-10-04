#pragma once

// Permanent instrument identity (ADR-023).
//
// WHY A TICKER IS NOT AN IDENTITY
// -------------------------------
// Everything in this pipeline is keyed on a ticker string, and a ticker
// is a display label that issuers change and exchanges reassign. Two
// failure modes, both already present in the panel:
//
//   A RENAME LOOKS LIKE A DEPARTURE PLUS AN ARRIVAL. When Bank of New
//   York Mellon moved from BK to BNY, the membership series shows BK
//   disappearing and BNY appearing - indistinguishable from one company
//   leaving the index and another joining. One continuous sixteen-year
//   price history becomes two shorter ones, the survivorship correction
//   counts a departure that never happened, and any statistic computed
//   per name silently treats one company as two.
//
//   A REUSED TICKER LOOKS LIKE ONE COMPANY. Exchanges do reassign
//   symbols after a delisting. Joining history on the string alone
//   welds two unrelated issuers into a single series with a
//   discontinuity in the middle that no data screen would flag,
//   because each half is individually clean.
//
// WHAT IS USED AS THE KEY, AND WHY IT IS NOT OpenFIGI
// ---------------------------------------------------
// ADR-023 named OpenFIGI. OpenFIGI needs an API key and a network round
// trip per instrument, and the pipeline already carries something that
// is permanent, free, and already in universe.parquet: the SEC's CIK.
// A CIK identifies an ISSUER for the life of that issuer's registration
// and survives every ticker change, so it answers both failure modes
// above without adding a dependency.
//
// The tradeoff is honest and bounded: a CIK is per-issuer, not per-
// security, so an issuer with two share classes maps both to one key.
// This project holds one line per company, so that is not currently a
// distinction it can make anyway - but it is the reason the key is a
// tagged string rather than a bare integer, since a later share-class
// key can be added as a new namespace without invalidating anything
// already written.
//
// THE FALLBACK IS THE WHOLE DESIGN PROBLEM
// ----------------------------------------
// 394 of the 897 tickers carrying price history have no metadata row at
// all, and those are disproportionately the old departures - which is
// exactly the population where renames hide. Those names fall back to a
// ticker-derived key, so a rename involving one of them stays
// invisible. The fallback is therefore NAMESPACED and visible in the
// value itself ("TICKER:" rather than "CIK:"), so a consumer can always
// tell a real identity from a stand-in, and a count of stand-ins is a
// measurement rather than a guess. See BLOCKED.md entry 5.

#include <gm-core/error.hpp>

#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace gm {

/// An opaque, permanent key for one instrument. Compared and joined on,
/// never parsed for meaning by consumers - the namespace prefix exists
/// so that provenance is visible, not so that callers can branch on it.
/// The only supported question is `is_permanent()`.
class InstrumentId {
public:
    InstrumentId() = default;

    /// Key from an SEC CIK - permanent across ticker changes. Zero is
    /// not a CIK; gm-universe writes it for rows with no metadata, so it
    /// is rejected rather than turned into "CIK:0".
    [[nodiscard]] static Result<InstrumentId> from_cik(std::int64_t cik);

    /// Stand-in key for a name with no permanent identifier available.
    /// Carries the ticker, and carries the fact that it is a stand-in.
    [[nodiscard]] static Result<InstrumentId> from_ticker(const std::string& ticker);

    /// The rule the pipeline uses: a real CIK if there is one, a
    /// namespaced ticker stand-in otherwise.
    [[nodiscard]] static Result<InstrumentId> resolve(std::optional<std::int64_t> cik,
                                                       const std::string& ticker);

    [[nodiscard]] const std::string& value() const noexcept { return value_; }
    /// False for a ticker stand-in. A study that joins across time
    /// should count these rather than assume they behave.
    [[nodiscard]] bool is_permanent() const noexcept { return permanent_; }

    friend bool operator==(const InstrumentId& l, const InstrumentId& r) { return l.value_ == r.value_; }
    friend bool operator!=(const InstrumentId& l, const InstrumentId& r) { return !(l == r); }
    friend bool operator<(const InstrumentId& l, const InstrumentId& r) { return l.value_ < r.value_; }

private:
    InstrumentId(std::string value, bool permanent)
        : value_(std::move(value)), permanent_(permanent) {}
    std::string value_;
    bool permanent_ = false;
};

/// One instrument that wore more than one ticker.
struct TickerAlias {
    InstrumentId id;
    std::vector<std::string> tickers;  // sorted, deduplicated
};

/// One ticker string that was used by more than one instrument.
struct ReusedTicker {
    std::string ticker;
    std::vector<InstrumentId> ids;  // sorted, deduplicated
};

/// Observed (ticker, cik) pairs folded into identities, with the two
/// pathologies named separately because they are different bugs with
/// opposite consequences.
class InstrumentRegistry {
public:
    /// Records one observation. Later observations of the same pair are
    /// idempotent. An empty ticker is rejected; a missing CIK produces a
    /// stand-in rather than a failure, because a row with no metadata is
    /// an expected state of this panel, not an error.
    [[nodiscard]] VoidResult observe(const std::string& ticker, std::optional<std::int64_t> cik);

    [[nodiscard]] std::optional<InstrumentId> id_for(const std::string& ticker) const;

    /// Instruments seen under two or more tickers: rename candidates.
    /// Each one is a departure the survivorship correction would
    /// otherwise have counted, and a history it would have cut in two.
    [[nodiscard]] std::vector<TickerAlias> aliases() const;

    /// Tickers seen under two or more instruments: symbol reuse. Joining
    /// on the string here welds unrelated issuers together.
    [[nodiscard]] std::vector<ReusedTicker> reused_tickers() const;

    [[nodiscard]] std::size_t num_instruments() const noexcept { return tickers_by_id_.size(); }
    [[nodiscard]] std::size_t num_tickers() const noexcept { return ids_by_ticker_.size(); }
    /// How many instruments rest on a ticker stand-in rather than a real
    /// permanent key - the size of the blind spot, as a number.
    [[nodiscard]] std::size_t num_provisional() const noexcept;

private:
    // std::map/std::set, not unordered: every listing this class returns
    // is emitted into an artifact, and two runs over the same
    // observations must produce the same bytes (ADR-003).
    std::map<std::string, InstrumentId> ids_by_ticker_;
    std::map<InstrumentId, std::set<std::string>> tickers_by_id_;
};

}  // namespace gm
