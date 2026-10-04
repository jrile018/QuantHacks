#include <gm-sweep/execution/cell_runner.hpp>

#include <gm-core/config.hpp>
#include <gm-sweep/execution/cell_executor.hpp>

#include <spdlog/spdlog.h>
#include <toml++/toml.hpp>

#include <cstdlib>
#include <fstream>
#include <sstream>

#if !defined(_WIN32)
#include <sys/wait.h>
#endif

namespace gm::sweep::execution {

static std::string quote_arg(const std::string& s) {
    std::string out = "\"";
    for (char c : s) {
        if (c == '"') out += '\\';
        out += c;
    }
    out += '"';
    return out;
}

static int normalized_exit_code(int system_result) {
#if defined(_WIN32)
    return system_result;
#else
    if (system_result == -1) return -1;
    if (WIFEXITED(system_result)) return WEXITSTATUS(system_result);
    return -1;
#endif
}

CellResult execute_cell(
    const SweepCell& cell,
    const fs::path& upstream_root,
    const fs::path& base_config_path,
    const fs::path& sweep_root,
    const fs::path& signals_exe,
    const fs::path& backtest_exe,
    int run_id) {

    CellResult result;
    result.cell_id = cell.cell_id;
    result.success = false;
    result.sharpe_ratio = 0.0;

    auto base_config = gm::Config::load(base_config_path);
    if (!base_config) {
        result.error_message = "failed to load base config: " + base_config.error().to_string();
        spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
        return result;
    }

    // The real config files this project uses (config/params.toml) are
    // flat top-level tables ([universe], [boundaries], [signals], ...)
    // - there is no [pipeline] wrapper section anywhere else in this
    // codebase (every other stage's Config::get_double_or("boundaries.alpha", ...)
    // etc. resolves straight against the top-level table). Overriding
    // against a nonexistent [pipeline] indirection would make every
    // cell fail with "base config missing [pipeline] section" against
    // any real config, which is exactly what happened until this was
    // checked against the actual file on disk instead of only a
    // synthetic fixture.
    auto overridden_table = override_config_with_cell_params(base_config->raw(), cell);
    if (!overridden_table) {
        result.error_message = "failed to apply cell overrides: " + overridden_table.error().to_string();
        spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
        return result;
    }

    auto cell_dir = create_cell_directory(sweep_root, cell.cell_id);
    if (!cell_dir) {
        result.error_message = "failed to create cell directory: " + cell_dir.error().to_string();
        spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
        return result;
    }

    auto link_result = link_upstream_artifacts(*cell_dir, upstream_root);
    if (!link_result) {
        result.error_message = "failed to link upstream artifacts: " + link_result.error().to_string();
        spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
        return result;
    }

    fs::path cell_config_path = *cell_dir / "config.toml";
    try {
        std::ofstream config_file{cell_config_path};
        if (!config_file) {
            result.error_message = "cannot create cell config file";
            spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
            return result;
        }
        config_file << overridden_table.value() << "\n";
        config_file.close();
    } catch (const std::exception& e) {
        result.error_message = std::string("failed to write cell config: ") + e.what();
        spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
        return result;
    }

    std::string cell_run_id = std::to_string(run_id) + "_cell_" + std::to_string(cell.cell_id);

    {
        fs::path signals_output = *cell_dir / "gm-signals";
        fs::create_directories(signals_output);

        std::ostringstream cmd;
        cmd << quote_arg(signals_exe.string())
            << " --config " << quote_arg(cell_config_path.string())
            << " --run-id " << quote_arg(cell_run_id)
            << " --output-dir " << quote_arg(signals_output.string());

        spdlog::debug("Cell {}: running gm-signals", cell.cell_id);
        int raw_exit = std::system(cmd.str().c_str());
        int exit_code = normalized_exit_code(raw_exit);

        if (exit_code != 0) {
            result.error_message = "gm-signals exited with code " + std::to_string(exit_code);
            spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
            return result;
        }
    }

    {
        fs::path backtest_output = *cell_dir / "gm-backtest";
        fs::create_directories(backtest_output);

        std::ostringstream cmd;
        cmd << quote_arg(backtest_exe.string())
            << " --config " << quote_arg(cell_config_path.string())
            << " --run-id " << quote_arg(cell_run_id)
            << " --output-dir " << quote_arg(backtest_output.string());

        spdlog::debug("Cell {}: running gm-backtest", cell.cell_id);
        int raw_exit = std::system(cmd.str().c_str());
        int exit_code = normalized_exit_code(raw_exit);

        if (exit_code != 0) {
            result.error_message = "gm-backtest exited with code " + std::to_string(exit_code);
            spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
            return result;
        }
    }

    fs::path backtest_results = *cell_dir / "gm-backtest" / "backtest_results.json";
    auto dsr_inputs = extract_dsr_inputs_from_backtest_results(backtest_results);
    if (!dsr_inputs) {
        result.error_message = "failed to extract DSR inputs: " + dsr_inputs.error().to_string();
        spdlog::warn("Cell {}: {}", cell.cell_id, result.error_message);
        return result;
    }

    result.success = true;
    result.sharpe_ratio = dsr_inputs->sharpe_ratio_daily;
    result.trading_days = dsr_inputs->trading_days;
    result.skewness = dsr_inputs->skewness;
    result.kurtosis = dsr_inputs->kurtosis;
    spdlog::info("Cell {}: success, sharpe_ratio_daily = {:.6f}, T={}, skew={:.4f}, kurt={:.4f}",
                 cell.cell_id, result.sharpe_ratio, result.trading_days, result.skewness, result.kurtosis);
    return result;
}

} // namespace gm::sweep::execution
