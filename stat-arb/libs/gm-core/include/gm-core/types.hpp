#pragma once

// ADR-019: strong types cross interfaces, never bare int/string. Cheaper
// than it looks: this file is the only place a TickerId ever compares
// implicitly-convertibly to a raw std::string.

#include <compare>
#include <cstdint>
#include <functional>
#include <string>
#include <utility>

namespace gm {

/// Generic strong-typed wrapper. Two StrongId<TagA, T> and StrongId<TagB, T>
/// with the same underlying type are still distinct, non-interconvertible
/// types - that is the entire point.
template <typename Tag, typename Underlying>
class StrongId {
public:
    using underlying_type = Underlying;

    constexpr StrongId() = default;
    constexpr explicit StrongId(Underlying value) : value_(std::move(value)) {}

    [[nodiscard]] constexpr const Underlying& value() const noexcept { return value_; }

    friend constexpr auto operator<=>(const StrongId&, const StrongId&) = default;
    friend constexpr bool operator==(const StrongId&, const StrongId&) = default;

private:
    Underlying value_{};
};

struct TickerIdTag {};
/// Exchange ticker symbol, e.g. "AAPL". Point-in-time universe logic
/// (ADR-001) keys on this; it is intentionally not validated against any
/// live exchange list here - that is gm-data's job.
using TickerId = StrongId<TickerIdTag, std::string>;

struct CikTag {};
/// SEC Central Index Key - the stable identifier across ticker changes
/// (see ADR §7.1, §7.3).
using Cik = StrongId<CikTag, std::uint64_t>;

struct FrameIndexTag {};
/// Zero-based index of a trading day within a run's date range. Distinct
/// from Date: a FrameIndex is a dense array position, a Date is a
/// calendar day - the NYSE calendar (calendar.hpp) maps between them.
using FrameIndex = StrongId<FrameIndexTag, std::int64_t>;

struct RunIdTag {};
/// Immutable run directory name, e.g. "2026-08-29__w60_k3_mds_rmt" (ADR-017).
using RunId = StrongId<RunIdTag, std::string>;

} // namespace gm

namespace std {
template <typename Tag, typename Underlying>
struct hash<gm::StrongId<Tag, Underlying>> {
    std::size_t operator()(const gm::StrongId<Tag, Underlying>& id) const noexcept {
        return std::hash<Underlying>{}(id.value());
    }
};
} // namespace std
