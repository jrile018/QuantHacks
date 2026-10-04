#pragma once

// Shared bootstrap for every gm-* stage executable (ADR-006). Each stage
// binary is thin: parse --config/--run-id, load the TOML config, start a
// Manifest, call one function that does the actual work, write the
// manifest, report timing, exit non-zero on failure. This header is
// where that ceremony lives exactly once.

#include <gm-core/config.hpp>
#include <gm-core/error.hpp>
#include <gm-core/manifest.hpp>

#include <CLI/CLI.hpp>
#include <spdlog/spdlog.h>

#include <chrono>
#include <filesystem>
#include <functional>
#include <string>

// Injected by CMake (see cmake/GitVersion.cmake) so gm-core never shells
// out to git itself (ADR-019: gm-core is a library, not a process).
#ifndef GM_GIT_COMMIT
#define GM_GIT_COMMIT "unknown"
#endif
#ifndef GM_COMPILER_ID
#define GM_COMPILER_ID "unknown"
#endif
#ifndef GM_BUILD_TYPE
#define GM_BUILD_TYPE "unknown"
#endif

namespace gm {

/// The work a stage does, given its loaded config: read upstream
/// artifacts, do the stage's job, write outputs under `output_dir`
/// (owned by this stage alone - gm-run assigns a distinct, run_id-keyed
/// directory per stage, ADR-017), and populate `manifest` with
/// stage-specific fields (row counts, etc. - the mandatory fields are
/// already set by run_stage_main before this is called).
using StageFn =
    std::function<VoidResult(const Config& config, const std::filesystem::path& output_dir,
                              Manifest& manifest)>;

/// Standard entry point body for a gm-* stage. Returns a process exit
/// code (0 on success). Every apps/gm-*/main.cpp is a call to this.
inline int run_stage_main(int argc, char** argv, const std::string& stage_name, StageFn stage_fn) {
    CLI::App app{stage_name};

    std::string config_path;
    std::string run_id;
    std::string manifest_out;
    std::string output_dir;

    app.add_option("--config", config_path, "Path to this stage's TOML config")->required();
    app.add_option("--run-id", run_id, "Immutable run identifier (ADR-017)")->required();
    app.add_option("--manifest-out", manifest_out,
                    "Where to write this stage's manifest.json (default: <config dir>/manifest.json)");
    app.add_option("--output-dir", output_dir,
                    "Directory this stage owns for its output artifacts (ADR-017)")
        ->required();

    CLI11_PARSE(app, argc, argv);

    if (manifest_out.empty()) {
        manifest_out = (std::filesystem::path{config_path}.parent_path() / "manifest.json").string();
    }

    spdlog::info("{} starting (run_id={}, config={})", stage_name, run_id, config_path);

    auto config = Config::load(config_path);
    if (!config) {
        spdlog::error("{} failed to load config: {}", stage_name, config.error().to_string());
        return 1;
    }

    Manifest manifest =
        Manifest::create(stage_name, run_id, GM_GIT_COMMIT, GM_COMPILER_ID, GM_BUILD_TYPE);

    auto start = std::chrono::steady_clock::now();
    auto result = stage_fn(*config, std::filesystem::path{output_dir}, manifest);
    auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    manifest.set_wall_time_seconds(elapsed);

    if (!result) {
        spdlog::error("{} failed: {}", stage_name, result.error().to_string());
        // Write the manifest even on failure - a failed run is still a
        // fact worth recording (what config, what commit, how long
        // before it died), not merely a silent non-event.
        manifest.set_string("status", "failed");
        manifest.set_string("error", result.error().to_string());
        (void)manifest.write(manifest_out);
        return 1;
    }

    manifest.set_string("status", "ok");
    auto write_result = manifest.write(manifest_out);
    if (!write_result) {
        spdlog::error("{} succeeded but failed to write manifest: {}", stage_name,
                      write_result.error().to_string());
        return 1;
    }

    spdlog::info("{} completed in {:.3f}s (manifest: {})", stage_name, elapsed, manifest_out);
    return 0;
}

} // namespace gm
