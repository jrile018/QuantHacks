#include <gm-sweep/execution/cell_executor.hpp>

#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#include <fstream>
#include <sstream>

namespace gm::sweep::execution {

Result<toml::table> override_config_with_cell_params(
    const toml::table& base_config,
    const SweepCell& cell) {
    toml::table result = base_config;

    for (const auto& [dotted_key, value_str] : cell.param_overrides) {
        std::vector<std::string> path_parts;
        {
            std::istringstream iss{dotted_key};
            std::string part;
            while (std::getline(iss, part, '.')) {
                if (part.empty()) {
                    return tl::unexpected(gm::Error{
                        gm::ErrorCode::kInvalidArgument,
                        "empty component in dotted path: " + dotted_key, ""});
                }
                path_parts.push_back(part);
            }
        }

        if (path_parts.empty()) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kInvalidArgument, "empty dotted path", ""});
        }

        toml::table* current_table = &result;
        for (std::size_t i = 0; i + 1 < path_parts.size(); ++i) {
            const auto& component = path_parts[i];
            auto* node = current_table->get(component);

            if (!node) {
                toml::table new_table;
                current_table->insert_or_assign(component, new_table);
                node = current_table->get(component);
            }

            if (!node->is_table()) {
                return tl::unexpected(gm::Error{
                    gm::ErrorCode::kInvalidArgument,
                    "cannot traverse non-table node at: " + component, ""});
            }

            current_table = node->as_table();
        }

        const auto& final_key = path_parts.back();
        try {
            std::string temp_toml = "temp = " + value_str;
            auto parsed = toml::parse(temp_toml);
            auto parsed_value = parsed["temp"];
            current_table->insert_or_assign(final_key, parsed_value);
        } catch (const toml::parse_error& e) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kParseFailure,
                std::string("failed to parse parameter override: ") + e.what(), ""});
        }
    }

    return result;
}

Result<fs::path> create_cell_directory(const fs::path& sweep_root, int cell_id) {
    fs::path cell_dir = sweep_root / ("cell_" + std::to_string(cell_id));
    try {
        fs::create_directories(cell_dir);
        return cell_dir;
    } catch (const std::filesystem::filesystem_error& e) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kIoFailure,
            std::string("failed to create cell directory: ") + e.what(), ""});
    }
}

Result<double> extract_sharpe_from_backtest_results(const fs::path& backtest_results_path) {
    if (!fs::exists(backtest_results_path)) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kNotFound,
            "backtest_results.json not found: " + backtest_results_path.string(), ""});
    }

    try {
        std::ifstream file{backtest_results_path};
        if (!file) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kIoFailure,
                "cannot open backtest_results.json: " + backtest_results_path.string(), ""});
        }

        nlohmann::json results;
        file >> results;
        file.close();

        if (!results.contains("sharpe_ratio_daily")) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kValidationFailure,
                "backtest_results.json missing sharpe_ratio_daily", ""});
        }

        auto sharpe_val = results["sharpe_ratio_daily"];
        if (sharpe_val.is_null()) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kValidationFailure,
                "sharpe_ratio_daily is null", ""});
        }

        if (!sharpe_val.is_number()) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kValidationFailure,
                "sharpe_ratio_daily is not a number", ""});
        }

        return sharpe_val.get<double>();
    } catch (const std::exception& e) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kParseFailure,
            std::string("failed to parse backtest_results.json: ") + e.what(), ""});
    }
}

Result<DsrInputs> extract_dsr_inputs_from_backtest_results(const fs::path& backtest_results_path) {
    if (!fs::exists(backtest_results_path)) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kNotFound,
            "backtest_results.json not found: " + backtest_results_path.string(), ""});
    }

    try {
        std::ifstream file{backtest_results_path};
        if (!file) {
            return tl::unexpected(gm::Error{
                gm::ErrorCode::kIoFailure,
                "cannot open backtest_results.json: " + backtest_results_path.string(), ""});
        }

        nlohmann::json results;
        file >> results;
        file.close();

        const auto require_number = [&](const char* key) -> Result<double> {
            if (!results.contains(key) || results[key].is_null() || !results[key].is_number()) {
                return tl::unexpected(gm::Error{
                    gm::ErrorCode::kValidationFailure,
                    std::string("backtest_results.json missing or non-numeric field: ") + key, ""});
            }
            return results[key].get<double>();
        };

        auto sharpe = require_number("sharpe_ratio_daily");
        if (!sharpe) return tl::unexpected(sharpe.error());
        auto skew = require_number("skewness");
        if (!skew) return tl::unexpected(skew.error());
        auto kurt = require_number("kurtosis");
        if (!kurt) return tl::unexpected(kurt.error());
        auto days = require_number("trading_days_with_positions");
        if (!days) return tl::unexpected(days.error());

        return DsrInputs{*sharpe, static_cast<std::int64_t>(*days), *skew, *kurt};
    } catch (const std::exception& e) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kParseFailure,
            std::string("failed to parse backtest_results.json: ") + e.what(), ""});
    }
}

Result<void> link_upstream_artifacts(
    const fs::path& cell_dir,
    const fs::path& upstream_root) {
    const std::vector<std::string> stages = {
        "gm-universe", "gm-ingest", "gm-features", "gm-geometry", "gm-boundaries"
    };

    try {
        for (const auto& stage : stages) {
            fs::path src = upstream_root / stage;
            fs::path dst = cell_dir / stage;

            if (!fs::exists(src)) {
                return tl::unexpected(gm::Error{
                    gm::ErrorCode::kNotFound,
                    "upstream artifact missing: " + src.string(), ""});
            }

            if (!fs::exists(dst)) {
                fs::create_symlink(fs::absolute(src), dst);
            }
        }
        return {};
    } catch (const std::filesystem::filesystem_error& e) {
        return tl::unexpected(gm::Error{
            gm::ErrorCode::kIoFailure,
            std::string("failed to link upstream artifacts: ") + e.what(), ""});
    }
}

} // namespace gm::sweep::execution
