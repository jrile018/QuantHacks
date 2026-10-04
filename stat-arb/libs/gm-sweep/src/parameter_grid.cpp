#include <gm-sweep/parameter_grid.hpp>

#include <cmath>
#include <numeric>
#include <spdlog/spdlog.h>

namespace gm::sweep {

Result<ParameterGrid> ParameterGrid::from_toml(const toml::table& sweep_section) {
    ParameterGrid grid;

    for (auto& [key, val] : sweep_section) {
        std::string axis_name = std::string{key};
        
        if (!val.is_array()) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kParseFailure,
                "sweep." + axis_name + " must be an array", ""});
        }

        auto* arr = val.as_array();
        std::vector<std::string> values;
        
        for (std::size_t i = 0; i < arr->size(); ++i) {
            auto& elem = (*arr)[i];
            std::string str_val;
            
            if (elem.is_integer()) {
                str_val = std::to_string(elem.as_integer()->get());
            } else if (elem.is_floating_point()) {
                double d = elem.as_floating_point()->get();
                char buf[32];
                std::snprintf(buf, sizeof(buf), "%.15g", d);
                str_val = buf;
            } else {
                return tl::unexpected(gm::Error{
                    gm::ErrorCode::kParseFailure,
                    "sweep." + axis_name + " contains non-numeric value", ""});
            }
            values.push_back(str_val);
        }

        if (values.empty()) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kParseFailure,
                "sweep." + axis_name + " is an empty array", ""});
        }

        grid.axis_names_.push_back(axis_name);
        grid.axes_[axis_name] = std::move(values);
    }

    if (grid.axis_names_.empty()) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kParseFailure,
            "[sweep] section is empty or missing", ""});
    }

    return grid;
}

std::vector<SweepCell> ParameterGrid::expand_cells() const {
    if (axes_.empty()) return {};

    std::vector<SweepCell> cells;
    std::size_t n_axes = axis_names_.size();
    std::vector<std::size_t> indices(n_axes, 0);
    
    while (true) {
        SweepCell cell;
        cell.cell_id = static_cast<int>(cells.size());
        
        for (std::size_t i = 0; i < n_axes; ++i) {
            const auto& axis_name = axis_names_[i];
            const auto& axis_values = axes_.at(axis_name);
            cell.param_overrides[axis_name] = axis_values[indices[i]];
        }
        
        cells.push_back(cell);
        
        bool done = true;
        for (std::size_t i = n_axes; i > 0; --i) {
            std::size_t idx = i - 1;
            const auto& axis_name = axis_names_[idx];
            const auto& axis_values = axes_.at(axis_name);
            indices[idx]++;
            if (indices[idx] < axis_values.size()) {
                done = false;
                break;
            }
            indices[idx] = 0;
        }
        
        if (done) break;
    }
    
    return cells;
}

std::size_t ParameterGrid::size() const {
    std::size_t prod = 1;
    for (const auto& axis_name : axis_names_) {
        prod *= axes_.at(axis_name).size();
    }
    return prod;
}

const std::vector<std::string>& ParameterGrid::get_axis_values(const std::string& axis_name) const {
    auto it = axes_.find(axis_name);
    if (it == axes_.end()) {
        static const std::vector<std::string> empty;
        return empty;
    }
    return it->second;
}

Result<TrialStats> compute_trial_stats(const std::vector<double>& sharpes) {
    if (sharpes.empty()) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kInvalidArgument,
            "compute_trial_stats: empty Sharpe vector", ""});
    }

    for (double s : sharpes) {
        if (std::isnan(s) || std::isinf(s)) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kNumericFailure,
                "compute_trial_stats: NaN or Inf in Sharpe values", ""});
        }
    }

    TrialStats stats;
    stats.n_trials = static_cast<int>(sharpes.size());
    stats.trial_sharpes = sharpes;
    
    double sum = std::accumulate(sharpes.begin(), sharpes.end(), 0.0);
    stats.trial_sharpe_mean = sum / static_cast<double>(sharpes.size());
    
    double sum_sq_dev = 0.0;
    for (double s : sharpes) {
        double dev = s - stats.trial_sharpe_mean;
        sum_sq_dev += dev * dev;
    }
    stats.trial_sharpe_variance = sum_sq_dev / static_cast<double>(sharpes.size());

    spdlog::debug("compute_trial_stats: n={}, mean={:.6f}, var={:.9f}",
                  stats.n_trials, stats.trial_sharpe_mean, stats.trial_sharpe_variance);

    return stats;
}

} // namespace gm::sweep
