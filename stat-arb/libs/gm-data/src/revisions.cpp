#include <gm-data/revisions.hpp>

#include <map>
#include <utility>

namespace gm::data {

Result<RevisionReport> compare_price_panels(const gm::io::Table& prior,
                                            const gm::io::Table& current,
                                            const std::string& value_column) {
    auto p_ticker = prior.string_column("ticker");
    if (!p_ticker) return tl::unexpected(p_ticker.error());
    auto p_date = prior.string_column("date");
    if (!p_date) return tl::unexpected(p_date.error());
    auto p_value = prior.double_column(value_column);
    if (!p_value) return tl::unexpected(p_value.error());

    auto c_ticker = current.string_column("ticker");
    if (!c_ticker) return tl::unexpected(c_ticker.error());
    auto c_date = current.string_column("date");
    if (!c_date) return tl::unexpected(c_date.error());
    auto c_value = current.double_column(value_column);
    if (!c_value) return tl::unexpected(c_value.error());

    using Key = std::pair<std::string, std::string>;
    // std::map, not unordered: the first example reported below has to be
    // the same one on every run over the same data, or a diagnostic
    // becomes a coin toss (ADR-003).
    std::map<Key, double> before;
    for (std::size_t i = 0; i < p_ticker->size() && i < p_value->size(); ++i) {
        before[{(*p_ticker)[i], (*p_date)[i]}] = (*p_value)[i];
    }
    std::map<Key, double> after;
    for (std::size_t i = 0; i < c_ticker->size() && i < c_value->size(); ++i) {
        after[{(*c_ticker)[i], (*c_date)[i]}] = (*c_value)[i];
    }

    RevisionReport report;
    for (const auto& [key, now] : after) {
        const auto it = before.find(key);
        if (it == before.end()) {
            ++report.added;
            continue;
        }
        ++report.compared;
        if (it->second != now) {
            ++report.revised;
            report.revised_tickers.insert(key.first);
            if (report.first_example.empty()) {
                report.first_example = key.first + " " + key.second + ": " +
                                        std::to_string(it->second) + " -> " + std::to_string(now);
            }
        }
    }
    for (const auto& [key, was] : before) {
        (void)was;
        if (after.find(key) == after.end()) ++report.removed;
    }
    return report;
}

} // namespace gm::data
