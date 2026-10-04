#include <gm-core/config.hpp>
#include <gm-core/error.hpp>
#include <gm-backtest/deflated_sharpe.hpp>
#include <gm-sweep/parameter_grid.hpp>
#include <gm-sweep/execution/cell_runner.hpp>
#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>
#include <tbb/parallel_for.h>
#include <filesystem>
#include <fstream>
#include <vector>
#include <atomic>
#include <mutex>
#include <algorithm>
namespace fs = std::filesystem;
using json = nlohmann::json;
using namespace gm::sweep;
struct SweepState {
    std::vector<execution::CellResult> cell_results;
    std::mutex results_mutex;
    std::atomic<int> completed_cells{0};
    void record_result(const execution::CellResult& result) {
        std::lock_guard<std::mutex> lock(results_mutex);
        cell_results.push_back(result);
        completed_cells++;
    }
};
int main(int argc, char** argv) {
    spdlog::info("gm-sweep: parameter grid orchestration");
    std::string sweep_config_str, output_dir_str;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--sweep-config" && i + 1 < argc) {
            sweep_config_str = argv[++i];
        } else if (arg == "--output-dir" && i + 1 < argc) {
            output_dir_str = argv[++i];
        }
    }
    if (sweep_config_str.empty() || output_dir_str.empty()) {
        spdlog::error("Usage: gm-sweep --sweep-config <toml> --output-dir <dir>");
        return 1;
    }
    fs::path sweep_config_path{sweep_config_str};
    fs::path output_dir{output_dir_str};
    if (!fs::exists(sweep_config_path)) {
        spdlog::error("sweep_config not found");
        return 1;
    }
    fs::create_directories(output_dir);
    toml::table root_table;
    try {
        root_table = toml::parse_file(sweep_config_path.string());
    } catch (const toml::parse_error& e) {
        spdlog::error("Failed to parse sweep config: {}", e.what());
        return 1;
    }
    auto* base_config_path_ptr = root_table.get("base_config_path");
    if (!base_config_path_ptr || !base_config_path_ptr->is_string()) {
        spdlog::error("sweep config missing base_config_path");
        return 1;
    }
    fs::path base_config_path{base_config_path_ptr->as_string()->get()};
    auto* upstream_ptr = root_table.get("upstream_root");
    if (!upstream_ptr || !upstream_ptr->is_string()) {
        spdlog::error("sweep config missing upstream_root");
        return 1;
    }
    fs::path upstream_root{upstream_ptr->as_string()->get()};
    std::string signals_exe_str = "gm-signals";
    auto* signals_ptr = root_table.get("gm_signals_exe");
    if (signals_ptr && signals_ptr->is_string()) {
        signals_exe_str = signals_ptr->as_string()->get();
    }
    fs::path signals_exe{signals_exe_str};
    std::string backtest_exe_str = "gm-backtest";
    auto* backtest_ptr = root_table.get("gm_backtest_exe");
    if (backtest_ptr && backtest_ptr->is_string()) {
        backtest_exe_str = backtest_ptr->as_string()->get();
    }
    fs::path backtest_exe{backtest_exe_str};
    fs::path bin_dir{"."};
    auto* bin_dir_ptr = root_table.get("bin_dir");
    if (bin_dir_ptr && bin_dir_ptr->is_string()) {
        bin_dir = bin_dir_ptr->as_string()->get();
    }
    int run_id = 1;
    auto* run_id_ptr = root_table.get("run_id");
    if (run_id_ptr && run_id_ptr->is_integer()) {
        run_id = static_cast<int>(run_id_ptr->as_integer()->get());
    }
    auto* sweep_table_ptr = root_table.get("sweep");
    if (!sweep_table_ptr || !sweep_table_ptr->is_table()) {
        spdlog::error("[sweep] section not found");
        return 1;
    }
    auto grid_result = ParameterGrid::from_toml(*sweep_table_ptr->as_table());
    if (!grid_result.has_value()) {
        spdlog::error("Failed to parse sweep grid");
        return 1;
    }
    auto grid = grid_result.value();
    auto cells = grid.expand_cells();
    fs::path sweep_root = output_dir / ("sweep_" + std::to_string(run_id));
    fs::create_directories(sweep_root);
    SweepState state;
    spdlog::info("Starting parallel execution of {} cells via TBB", cells.size());
    tbb::parallel_for(tbb::blocked_range<std::size_t>(0, cells.size()),
        [&](const tbb::blocked_range<std::size_t>& r) {
            for (std::size_t i = r.begin(); i != r.end(); ++i) {
                auto cell_result = execution::execute_cell(
                    cells[i], upstream_root, base_config_path, sweep_root,
                    signals_exe, backtest_exe, run_id);
                state.record_result(cell_result);
            }
        });
    // TBB completion order is nondeterministic, and everything downstream
    // (trial stats, best-cell selection, failed_cells serialization) must
    // not depend on it: sort into a fixed, cell_id-ordered sequence before
    // deriving anything from state.cell_results, so sweep_results.json is
    // bit-reproducible run to run.
    std::sort(state.cell_results.begin(), state.cell_results.end(),
        [](const execution::CellResult& a, const execution::CellResult& b) {
            return a.cell_id < b.cell_id;
        });
    std::vector<double> successful_sharpes;
    json failed_cells_json = json::array();
    for (const auto& cell_result : state.cell_results) {
        if (cell_result.success) {
            successful_sharpes.push_back(cell_result.sharpe_ratio);
        } else {
            json failed_cell;
            failed_cell["cell_id"] = cell_result.cell_id;
            failed_cell["error"] = cell_result.error_message;
            failed_cells_json.push_back(failed_cell);
        }
    }
    int n_successful = static_cast<int>(successful_sharpes.size());
    int n_failed = static_cast<int>(state.cell_results.size()) - n_successful;
    if (n_successful == 0) {
        json sweep_results;
        sweep_results["n_trials"] = static_cast<int>(cells.size());
        sweep_results["n_successful"] = 0;
        sweep_results["status"] = "all_cells_failed";
        sweep_results["failed_cells"] = failed_cells_json;
        fs::path results_json_path = output_dir / "sweep_results.json";
        std::ofstream results_file{results_json_path};
        if (!results_file) {
            spdlog::error("Failed to open sweep_results.json for writing: {}", results_json_path.string());
            return 1;
        }
        results_file << sweep_results.dump(2) << "\n";
        if (!results_file) {
            spdlog::error("Failed to write sweep_results.json: {}", results_json_path.string());
            return 1;
        }
        results_file.close();
        return 1;
    }
    auto trial_stats_result = compute_trial_stats(successful_sharpes);
    if (!trial_stats_result.has_value()) {
        return 1;
    }
    const auto& trial_stats = trial_stats_result.value();
    // Find the cell that actually produced the best (max) Sharpe, so its
    // OWN real trading_days_with_positions/skewness/kurtosis - not a
    // T=252-Normal placeholder - go into the DSR calculation. Every
    // cell's backtest_results.json already reports its own real
    // moments; substituting a placeholder when the real figure is one
    // struct field away was a real accuracy gap, not just cosmetic:
    // hand-verifying this formula against the real single-run DSR
    // (1.77e-06 at T=1121, skew=0.63, kurtosis=13.84) showed T alone
    // shifts the result by orders of magnitude.
    const execution::CellResult* best_cell = nullptr;
    for (const auto& cell_result : state.cell_results) {
        if (!cell_result.success) continue;
        // On an exact Sharpe tie, always prefer the smaller cell_id so the
        // winner is deterministic regardless of TBB scheduling (state.cell_results
        // is cell_id-ordered at this point, but the tie-break is made explicit
        // so it stays correct even if the iteration order above ever changes).
        if (!best_cell ||
            cell_result.sharpe_ratio > best_cell->sharpe_ratio ||
            (cell_result.sharpe_ratio == best_cell->sharpe_ratio &&
             cell_result.cell_id < best_cell->cell_id)) {
            best_cell = &cell_result;
        }
    }
    double best_sharpe = best_cell->sharpe_ratio;
    auto sr0_result = gm::backtest::expected_max_sharpe(trial_stats.trial_sharpe_variance, n_successful);
    if (!sr0_result.has_value()) {
        return 1;
    }
    double sr0 = *sr0_result;
    auto dsr_result = gm::backtest::deflated_sharpe_ratio(
        best_sharpe, sr0, static_cast<int>(best_cell->trading_days), best_cell->skewness, best_cell->kurtosis);
    if (!dsr_result.has_value()) {
        return 1;
    }
    double dsr = *dsr_result;
    json sweep_results;
    sweep_results["n_trials"] = static_cast<int>(cells.size());
    sweep_results["n_successful"] = n_successful;
    sweep_results["n_failed"] = n_failed;
    sweep_results["best_sharpe"] = best_sharpe;
    sweep_results["best_cell_trading_days"] = best_cell->trading_days;
    sweep_results["best_cell_skewness"] = best_cell->skewness;
    sweep_results["best_cell_kurtosis"] = best_cell->kurtosis;
    sweep_results["sr0"] = sr0;
    sweep_results["dsr"] = dsr;
    sweep_results["failed_cells"] = failed_cells_json;
    sweep_results["status"] = "ok";
    fs::path results_json_path = output_dir / "sweep_results.json";
    std::ofstream results_file{results_json_path};
    if (!results_file) {
        spdlog::error("Failed to open sweep_results.json for writing: {}", results_json_path.string());
        return 1;
    }
    results_file << sweep_results.dump(2) << "\n";
    if (!results_file) {
        spdlog::error("Failed to write sweep_results.json: {}", results_json_path.string());
        return 1;
    }
    results_file.close();
    return 0;
}
