#pragma once

#include <gm-core/error.hpp>

#include <map>
#include <string>
#include <vector>
#include <toml++/toml.hpp>

namespace gm::sweep {

struct SweepCell {
    int cell_id;
    std::map<std::string, std::string> param_overrides;
};

class ParameterGrid {
public:
    static Result<ParameterGrid> from_toml(const toml::table& sweep_section);

    std::vector<SweepCell> expand_cells() const;

    std::size_t size() const;

    bool empty() const { return axes_.empty(); }

    const std::vector<std::string>& axis_names() const { return axis_names_; }

    const std::vector<std::string>& get_axis_values(const std::string& axis_name) const;

private:
    std::vector<std::string> axis_names_;
    std::map<std::string, std::vector<std::string>> axes_;
};

struct TrialStats {
    int n_trials;
    double trial_sharpe_variance;
    double trial_sharpe_mean;
    std::vector<double> trial_sharpes;
};

Result<TrialStats> compute_trial_stats(const std::vector<double>& sharpes);

} // namespace gm::sweep
