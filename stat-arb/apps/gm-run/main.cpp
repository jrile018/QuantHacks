// gm-run: drives the full staged pipeline (ADR-006) end to end. Each
// stage is invoked as a separate process, in order, reading the same
// master config and writing its own manifest under
// runs/<run_id>/<stage>/manifest.json. gm-run stops at the first
// failing stage and, once all stages have succeeded, assembles and
// writes the top-level run manifest (ADR-017) by reading every stage
// manifest back and validating its schema_version - proving the
// artifact contract end-to-end, not just asserting it in a comment.
//
// M0 exit criterion (ADR.md §13): this executes the whole chain (of M0
// stub stages) on a stub fixture, on both build platforms.

#include <gm-core/config.hpp>
#include <gm-core/error.hpp>
#include <gm-core/manifest.hpp>

#include <CLI/CLI.hpp>
#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#include <array>
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <sstream>
#include <string>
#include <vector>

#if !defined(_WIN32)
#include <sys/wait.h>
#endif

#ifndef GM_GIT_COMMIT
#define GM_GIT_COMMIT "unknown"
#endif
#ifndef GM_COMPILER_ID
#define GM_COMPILER_ID "unknown"
#endif
#ifndef GM_BUILD_TYPE
#define GM_BUILD_TYPE "unknown"
#endif

namespace {

// Fixed pipeline order (ADR-006). gm-sweep/gm-view are not part of this
// linear chain: gm-sweep drives many gm-run invocations, gm-view only
// reads what this chain produced.
//
// gm-profiles only depends on gm-universe (it reads universe.parquet
// for the ticker/CIK list) and feeds nothing else in this DAG - no
// other stage reads meta/profiles.json, only gm-view does, after the
// whole chain is done. So it can run anywhere after gm-universe without
// changing what any other stage sees. It's placed right before
// gm-report (last of the analytical stages, ahead of only the report
// generator) rather than right after gm-universe, so its ~minutes of
// real SEC EDGAR network I/O don't sit in front of - and delay the
// start of - gm-ingest/gm-features/gm-geometry/gm-boundaries/gm-signals/
// gm-backtest, all of which are on the actual critical path to a
// tradeable backtest result and none of which need it.
constexpr std::array<const char*, 9> kStageOrder = {
    "gm-universe", "gm-ingest",     "gm-features", "gm-geometry",   "gm-boundaries",
    "gm-signals",  "gm-backtest",   "gm-profiles", "gm-report",
};

/// Quotes `s` for use as a single argument in a command line passed to
/// std::system(). Adequate for the trusted, locally-built stage
/// binaries and filesystem paths gm-run itself constructs; this is
/// orchestration glue, not a shell talking to untrusted input.
std::string quote_arg(const std::string& s) {
    std::string out = "\"";
    for (char c : s) {
        if (c == '"') out += '\\';
        out += c;
    }
    out += '"';
    return out;
}

/// Hands `command` to the shell, with the one piece of Windows quoting
/// that a quoted-executable-plus-quoted-arguments line requires.
///
/// cmd.exe strips the FIRST and LAST quote characters of a command line
/// that both begins with a quote and contains others. Since quote_arg
/// above quotes the executable and every argument - which it must, because
/// a Windows repository path routinely contains spaces - the line gm-run
/// builds is exactly that shape, and cmd was mangling it into a path that
/// names nothing. The documented remedy is one more enclosing pair, which
/// cmd consumes.
///
/// The effect of not doing this was total: gm-run could not launch any
/// stage on Windows at all.
int shell_execute(const std::string& command) {
#if defined(_WIN32)
    const std::string wrapped = "\"" + command + "\"";
    return std::system(wrapped.c_str());
#else
    return std::system(command.c_str());
#endif
}

/// std::system()'s return value encodes the child's exit code
/// differently on POSIX (via wait-status macros) vs Windows (the raw
/// exit code) - normalize it here so callers see one convention.
///
/// Windows note: system_result IS the child's exit code directly (no
/// wait-status decoding needed), including for an abnormally-terminated
/// process - Windows exit codes for crashes are large unsigned values
/// (e.g. an unhandled SEH exception) that show up here as a big non-zero
/// int, which the caller already treats as failure. There is no separate
/// "-1 means the shell itself failed to launch" case to special-case
/// the way POSIX has one; std::system on Windows returns -1 for that
/// same condition, so a -1 here is unambiguous (unlike POSIX, where -1
/// can also arise from a signal-terminated child mapped through
/// wait-status macros before this function is called).
int normalized_exit_code(int system_result) {
#if defined(_WIN32)
    return system_result;
#else
    if (system_result == -1) return -1;
    if (WIFEXITED(system_result)) return WEXITSTATUS(system_result);
    return -1;
#endif
}

/// Resolve the optional Python stage before starting the costly equity chain.
/// The config or build directory may be outside the current working directory.
std::filesystem::path find_options_script(const gm::Config& config,
                                           const std::string& config_path,
                                           const std::string& bin_dir) {
    if (config.has("options.script_path")) {
        auto configured = config.get_string("options.script_path");
        if (!configured || configured->empty()) return {};
        return std::filesystem::absolute(std::filesystem::path{*configured});
    }
    for (auto anchor : {std::filesystem::current_path(),
                        std::filesystem::absolute(std::filesystem::path{config_path}).parent_path(),
                        std::filesystem::absolute(std::filesystem::path{bin_dir})}) {
        while (!anchor.empty()) {
            auto candidate = anchor / "tools" / "options_native.py";
            if (std::filesystem::is_regular_file(candidate)) return candidate;
            auto parent = anchor.parent_path();
            if (parent == anchor) break;
            anchor = parent;
        }
    }
    return {};
}

} // namespace

int main(int argc, char** argv) {
    CLI::App app{"gm-run: orchestrates the full geomarket pipeline"};

    std::string config_path;
    std::string run_id;
    std::string bin_dir;

    app.add_option("--config", config_path, "Master TOML config for this run")->required();
    app.add_option("--run-id", run_id, "Immutable run identifier (ADR-017)")->required();
    app.add_option("--bin-dir", bin_dir,
                    "Directory containing the gm-* stage executables (default: this "
                    "executable's own directory)");

    CLI11_PARSE(app, argc, argv);

    if (bin_dir.empty()) {
        bin_dir = std::filesystem::absolute(std::filesystem::path{argv[0]}).parent_path().string();
    }

    auto config = gm::Config::load(config_path);
    if (!config) {
        spdlog::error("gm-run: failed to load config: {}", config.error().to_string());
        return 1;
    }

    std::string runs_base_dir = config->get_string_or("output.runs_base_dir", "runs");
    std::string run_dir = runs_base_dir + "/" + run_id;
    std::filesystem::create_directories(run_dir);

    spdlog::info("gm-run: starting run_id={} run_dir={} bin_dir={}", run_id, run_dir, bin_dir);

    auto overall_start = std::chrono::steady_clock::now();
    std::vector<std::string> completed_stages;

    std::vector<std::string> stages{kStageOrder.begin(), kStageOrder.end()};
    const bool options_enabled = config->has("options.study_dir");
    std::string study_dir;
    std::string options_python;
    std::filesystem::path options_script;
    if (options_enabled) {
        auto configured_study = config->get_string("options.study_dir");
        if (!configured_study || configured_study->empty()) {
            spdlog::error("gm-run: options.study_dir must be a nonempty string");
            return 1;
        }
        study_dir = *configured_study;
        options_python = config->get_string_or("options.python_exe", "python");
        options_script = find_options_script(*config, config_path, bin_dir);
        if (options_script.empty() || !std::filesystem::is_regular_file(options_script)) {
            spdlog::error("gm-run: could not locate tools/options_native.py; set options.script_path");
            return 1;
        }
        if (std::filesystem::path{study_dir}.is_relative()) {
            study_dir = (options_script.parent_path().parent_path() / study_dir)
                            .lexically_normal().string();
        }
        if (!std::filesystem::is_directory(study_dir)) {
            spdlog::error("gm-run: options.study_dir is not a directory: {}", study_dir);
            return 1;
        }
        std::filesystem::path interpreter{options_python};
        if (interpreter.has_parent_path() && interpreter.is_relative()) {
            options_python = (options_script.parent_path().parent_path() / interpreter)
                                 .lexically_normal().string();
        }
        if (interpreter.has_parent_path() && !std::filesystem::is_regular_file(options_python)) {
            spdlog::error("gm-run: options.python_exe is not a file: {}", options_python);
            return 1;
        }
        const std::string python_check = quote_arg(options_python) + " " +
                                         quote_arg(options_script.string()) + " --help";
        if (normalized_exit_code(shell_execute(python_check)) != 0) {
            spdlog::error("gm-run: option Python stage or its dependencies are unavailable");
            return 1;
        }
        stages.push_back("gm-options-ingest");
        stages.push_back("gm-options-study");
    }

    for (const std::string& stage : stages) {
        std::filesystem::path stage_exe =
            std::filesystem::path{bin_dir} / (stage +
#if defined(_WIN32)
                                               ".exe"
#else
                                               ""
#endif
            );
        std::filesystem::path stage_output_dir = std::filesystem::path{run_dir} / stage;
        std::filesystem::path manifest_out = stage_output_dir / "manifest.json";

        std::ostringstream cmd;
        if (stage == "gm-options-ingest") {
            cmd << quote_arg(options_python) << " " << quote_arg(options_script.string())
                << " ingest --study-dir "
                << quote_arg(study_dir) << " --run-id " << quote_arg(run_id)
                << " --output-dir " << quote_arg(stage_output_dir.string());
        } else if (stage == "gm-options-study") {
            cmd << quote_arg(options_python) << " " << quote_arg(options_script.string())
                << " study --ingest-dir "
                << quote_arg((std::filesystem::path{run_dir} / "gm-options-ingest").string())
                << " --scores "
                << quote_arg((std::filesystem::path{run_dir} / "gm-boundaries" / "scores.parquet").string())
                << " --run-id " << quote_arg(run_id)
                << " --output-dir " << quote_arg(stage_output_dir.string());
        } else {
            cmd << quote_arg(stage_exe.string()) << " --config " << quote_arg(config_path)
                << " --run-id " << quote_arg(run_id) << " --output-dir "
                << quote_arg(stage_output_dir.string()) << " --manifest-out "
                << quote_arg(manifest_out.string());
        }

        spdlog::info("gm-run: [{}] launching: {}", stage, cmd.str());
        auto stage_start = std::chrono::steady_clock::now();
        int raw_result = shell_execute(cmd.str());
        int exit_code = normalized_exit_code(raw_result);
        auto stage_elapsed =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - stage_start).count();

        if (exit_code != 0) {
            spdlog::error("gm-run: [{}] FAILED (exit {}) after {:.3f}s - stopping chain", stage,
                          exit_code, stage_elapsed);
            return 1;
        }

        // Validate the stage's manifest was actually written and has a
        // schema_version this build recognizes (ADR-017): proves the
        // contract, doesn't just trust the exit code.
        auto stage_manifest = gm::Manifest::read(manifest_out);
        if (!stage_manifest) {
            spdlog::error("gm-run: [{}] exited 0 but manifest is invalid: {}", stage,
                          stage_manifest.error().to_string());
            return 1;
        }

        spdlog::info("gm-run: [{}] OK in {:.3f}s", stage, stage_elapsed);
        completed_stages.push_back(stage);
    }

    double total_elapsed =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - overall_start).count();

    gm::Manifest run_manifest =
        gm::Manifest::create("gm-run", run_id, GM_GIT_COMMIT, GM_COMPILER_ID, GM_BUILD_TYPE);
    run_manifest.set_wall_time_seconds(total_elapsed);
    run_manifest.set_string("status", "ok");

    nlohmann::json stages_json = nlohmann::json::array();
    for (const auto& s : completed_stages) stages_json.push_back(s);
    run_manifest.set_json("completed_stages", stages_json);

    auto write_result = run_manifest.write(std::filesystem::path{run_dir} / "manifest.json");
    if (!write_result) {
        spdlog::error("gm-run: failed to write top-level run manifest: {}",
                      write_result.error().to_string());
        return 1;
    }

    spdlog::info("gm-run: ALL {} stages completed in {:.3f}s (run manifest: {})",
                 completed_stages.size(), total_elapsed, (std::filesystem::path{run_dir} / "manifest.json").string());
    return 0;
}
