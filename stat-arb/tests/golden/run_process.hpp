#pragma once

// Running a built binary from a test, portably.
//
// Shared by m0_pipeline_test.cpp and causality_test.cpp, which both shell
// out to a stage executable and both need the same two pieces of
// platform handling. It lived duplicated in each before, and the Windows
// half was wrong in both.

#include <cstdlib>
#include <string>

#if !defined(_WIN32)
#include <sys/wait.h>
#endif

namespace gm::test {

/// The process's own exit status, from whatever std::system returned.
///
/// POSIX packs the status into a wait(2) word that has to be unpacked;
/// Windows returns the exit code directly. A test comparing the raw POSIX
/// value against 0 happens to work for success and reports nonsense for
/// every failure.
inline int normalized_exit_code(int system_result) {
#if defined(_WIN32)
    return system_result;
#else
    return WIFEXITED(system_result) ? WEXITSTATUS(system_result) : -1;
#endif
}

/// Runs `command` through the shell and returns the child's exit code.
///
/// On Windows the command is wrapped in ONE MORE pair of quotes before
/// being handed to std::system. cmd.exe strips the first and last quote
/// characters of a command line that both starts with a quote and contains
/// others, so
///
///     "C:\path\gm-run.exe" --config "C:\path\x.toml"
///
/// arrives at the parser as
///
///     C:\path\gm-run.exe" --config "C:\path\x.toml
///
/// which names no executable. The extra pair is what cmd consumes,
/// leaving the intended line intact. Quoting each path is still required -
/// the repository path on a Windows machine routinely contains spaces.
inline int run_command(const std::string& command) {
#if defined(_WIN32)
    const std::string wrapped = "\"" + command + "\"";
    return normalized_exit_code(std::system(wrapped.c_str()));
#else
    return normalized_exit_code(std::system(command.c_str()));
#endif
}

} // namespace gm::test
