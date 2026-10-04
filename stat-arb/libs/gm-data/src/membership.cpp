#include <gm-data/membership.hpp>

#include <algorithm>
#include <fstream>

namespace gm::data {

namespace {

std::string trim(std::string s) {
    const auto not_space = [](unsigned char c) { return c != ' ' && c != '\t' && c != '\r'; };
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), not_space));
    s.erase(std::find_if(s.rbegin(), s.rend(), not_space).base(), s.end());
    return s;
}

} // namespace

Result<MembershipHistory> MembershipHistory::load(const std::filesystem::path& csv_path) {
    std::ifstream in(csv_path);
    if (!in) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kNotFound,
                                               "membership history CSV could not be opened",
                                               csv_path.string()));
    }

    std::string line;
    if (!std::getline(in, line)) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "membership history CSV is empty",
                                               csv_path.string()));
    }
    if (trim(line) != "observed_date,ticker") {
        // Refusing an unexpected header rather than guessing at column
        // positions: a silently misread column would produce a universe
        // that is wrong in a way nothing downstream can detect.
        return tl::unexpected(gm::Error::make(
            gm::ErrorCode::kInvalidArgument,
            "membership history CSV header must be exactly 'observed_date,ticker'", trim(line)));
    }

    MembershipHistory history;
    std::int64_t line_number = 1;
    while (std::getline(in, line)) {
        ++line_number;
        line = trim(line);
        if (line.empty()) continue;
        const auto comma = line.find(',');
        if (comma == std::string::npos) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "membership history CSV row has no comma",
                                                   "line " + std::to_string(line_number)));
        }
        const auto date = gm::Date::parse_iso(line.substr(0, comma));
        if (!date) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "membership history CSV row has an unparseable date",
                                                   "line " + std::to_string(line_number) + ": " + line));
        }
        const std::string ticker = trim(line.substr(comma + 1));
        if (ticker.empty()) {
            return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                                   "membership history CSV row has an empty ticker",
                                                   "line " + std::to_string(line_number)));
        }
        history.by_date_[*date].insert(ticker);
    }

    if (history.by_date_.empty()) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "membership history CSV has a header but no rows",
                                               csv_path.string()));
    }
    history.dates_.reserve(history.by_date_.size());
    for (const auto& [date, members] : history.by_date_) {
        (void)members;
        history.dates_.push_back(date);
    }
    return history;
}

std::optional<gm::Date> MembershipHistory::observation_used(const gm::Date& as_of) const {
    // upper_bound then step back: the newest observation at or before
    // as_of, and nothing later. See the header on why never forward.
    const auto it = by_date_.upper_bound(as_of);
    if (it == by_date_.begin()) return std::nullopt;
    return std::prev(it)->first;
}

std::vector<gm::TickerId> MembershipHistory::members_as_of(const gm::Date& as_of) const {
    std::vector<gm::TickerId> out;
    const auto used = observation_used(as_of);
    if (!used) return out;
    const auto& members = by_date_.at(*used);
    out.reserve(members.size());
    for (const auto& ticker : members) out.emplace_back(ticker);
    return out;
}

bool MembershipHistory::is_member(const gm::TickerId& ticker, const gm::Date& as_of) const {
    const auto used = observation_used(as_of);
    if (!used) return false;
    const auto& members = by_date_.at(*used);
    return members.find(ticker.value()) != members.end();
}

std::vector<gm::TickerId> MembershipHistory::all_tickers() const {
    std::set<std::string> seen;
    for (const auto& [date, members] : by_date_) {
        (void)date;
        seen.insert(members.begin(), members.end());
    }
    std::vector<gm::TickerId> out;
    out.reserve(seen.size());
    for (const auto& ticker : seen) out.emplace_back(ticker);
    return out;
}

std::vector<gm::TickerId> MembershipHistory::departed_tickers(
    std::size_t recent_observations) const {
    if (recent_observations == 0) recent_observations = 1;

    // The union of the last few observations, so one imperfectly parsed
    // revision cannot report a sitting member as departed. See the
    // header for the two real names this was hiding.
    std::set<std::string> recent;
    std::size_t taken = 0;
    for (auto it = by_date_.rbegin(); it != by_date_.rend() && taken < recent_observations;
         ++it, ++taken) {
        recent.insert(it->second.begin(), it->second.end());
    }

    std::vector<gm::TickerId> out;
    for (const auto& ticker : all_tickers()) {
        if (recent.find(ticker.value()) == recent.end()) out.push_back(ticker);
    }
    return out;
}

} // namespace gm::data
