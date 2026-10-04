#include <gm-data/universe.hpp>

#include <gm-io/csv.hpp>

#include <algorithm>
#include <charconv>

namespace gm::data {

namespace {

/// The "founded" column occasionally carries trailing text after the
/// year (e.g. "1888 (as Abbott Alkaloidal Company)") - real, observed
/// in the live snapshot (39/503 rows). Unlike ticker/date_added/cik,
/// this is a descriptive-only field (ADR §5.3 "learn panel" material),
/// so a lenient leading-4-digit parse is the right amount of strictness:
/// failing the whole row over a decorative parenthetical would be worse
/// than leaving founded_year empty for it.
std::optional<int> parse_leading_year(const std::string& s) {
    if (s.size() < 4) return std::nullopt;
    int year = 0;
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + 4, year);
    if (ec != std::errc{} || ptr != s.data() + 4) return std::nullopt;
    if (year < 1000 || year > 9999) return std::nullopt;
    return year;
}

} // namespace

Result<Universe> Universe::load_sp500_snapshot(const std::filesystem::path& csv_path) {
    auto csv = gm::io::read_csv_file(csv_path);
    if (!csv) return tl::unexpected(csv.error());

    static const std::vector<std::string> kExpectedHeader = {
        "symbol",       "security", "gics_sector", "gics_sub_industry",
        "hq_location",  "date_added", "cik",         "founded"};
    if (csv->header != kExpectedHeader) {
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kParseFailure, "sp500 snapshot CSV header does not match expected schema",
            csv_path.string()));
    }

    Universe universe;
    universe.records_.reserve(csv->rows.size());

    for (std::size_t row_idx = 0; row_idx < csv->rows.size(); ++row_idx) {
        const auto& row = csv->rows[row_idx];
        ConstituentRecord rec;
        rec.ticker = gm::TickerId{row[0]};
        rec.security_name = row[1];
        rec.gics_sector = row[2];
        rec.gics_sub_industry = row[3];
        rec.hq_location = row[4];

        auto date = gm::Date::parse_iso(row[5]);
        if (!date) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure, "unparseable date_added",
                "row " + std::to_string(row_idx) + " (" + row[0] + "): '" + row[5] + "'"));
        }
        rec.date_added = *date;

        std::uint64_t cik_value = 0;
        auto [ptr, ec] = std::from_chars(row[6].data(), row[6].data() + row[6].size(), cik_value);
        if (ec != std::errc{} || ptr != row[6].data() + row[6].size()) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kParseFailure, "unparseable cik",
                "row " + std::to_string(row_idx) + " (" + row[0] + "): '" + row[6] + "'"));
        }
        rec.cik = gm::Cik{cik_value};

        rec.founded_year = parse_leading_year(row[7]);

        universe.records_.push_back(std::move(rec));
    }

    std::sort(universe.records_.begin(), universe.records_.end(),
              [](const ConstituentRecord& a, const ConstituentRecord& b) {
                  return a.ticker.value() < b.ticker.value();
              });

    // Duplicate tickers would silently break binary search below and
    // silently pick an arbitrary record in find() - fail loudly instead.
    for (std::size_t i = 1; i < universe.records_.size(); ++i) {
        if (universe.records_[i].ticker == universe.records_[i - 1].ticker) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kParseFailure,
                                                   "duplicate ticker in sp500 snapshot",
                                                   universe.records_[i].ticker.value()));
        }
    }

    return universe;
}

Result<const ConstituentRecord*> Universe::find(const gm::TickerId& ticker) const {
    auto it = std::lower_bound(records_.begin(), records_.end(), ticker,
                                [](const ConstituentRecord& rec, const gm::TickerId& t) {
                                    return rec.ticker.value() < t.value();
                                });
    if (it != records_.end() && it->ticker == ticker) return &(*it);
    return tl::unexpected(
        gm::Error::make(gm::ErrorCode::kNotFound, "ticker not in universe snapshot", ticker.value()));
}

bool Universe::is_member(const gm::TickerId& ticker, const gm::Date& as_of) const noexcept {
    auto found = find(ticker);
    if (!found) return false;
    return (*found)->date_added <= as_of;
}

std::vector<gm::TickerId> Universe::members_as_of(const gm::Date& as_of) const {
    std::vector<gm::TickerId> members;
    members.reserve(records_.size());
    for (const auto& rec : records_) {
        if (rec.date_added <= as_of) members.push_back(rec.ticker);
    }
    std::sort(members.begin(), members.end(),
              [](const gm::TickerId& a, const gm::TickerId& b) { return a.value() < b.value(); });
    return members;
}

} // namespace gm::data
