#include "centrality.hpp"

#include <algorithm>
#include <map>
#include <set>

namespace gm::features {

std::vector<double> compute_pit_sector_centrality(const std::vector<std::string>& dates,
                                                    const std::vector<std::string>& tickers,
                                                    const std::vector<std::string>& sectors) {
    // Pass 1: for every date, the set of distinct tickers in each
    // sector ON THAT DATE ONLY. std::map/std::set (not unordered_*) per
    // ADR determinism - this feeds a scored feature.
    std::map<std::string, std::map<std::string, std::set<std::string>>> members_by_date_sector;
    for (std::size_t i = 0; i < dates.size(); ++i) {
        members_by_date_sector[dates[i]][sectors[i]].insert(tickers[i]);
    }

    // Pass 2: collapse to counts and the per-date max-sector-size divisor.
    struct DateStats {
        std::map<std::string, std::size_t> sector_counts;
        std::size_t max_sector_size = 0;
    };
    std::map<std::string, DateStats> stats_by_date;
    for (const auto& [date, sector_map] : members_by_date_sector) {
        DateStats stats;
        for (const auto& [sector, members] : sector_map) {
            stats.sector_counts[sector] = members.size();
            stats.max_sector_size = std::max(stats.max_sector_size, members.size());
        }
        stats_by_date[date] = std::move(stats);
    }

    // Pass 3: one centrality value per input row, using only that row's
    // own date's stats.
    std::vector<double> centrality;
    centrality.reserve(dates.size());
    for (std::size_t i = 0; i < dates.size(); ++i) {
        const auto& stats = stats_by_date.at(dates[i]);
        std::size_t sector_size = stats.sector_counts.at(sectors[i]);
        double normalized =
            static_cast<double>(sector_size) / (1.0 + static_cast<double>(stats.max_sector_size));
        centrality.push_back(normalized);
    }
    return centrality;
}

} // namespace gm::features
