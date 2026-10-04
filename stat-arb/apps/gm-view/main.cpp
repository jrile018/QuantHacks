// gm-view: the interactive viewer (ADR-018). Strictly read-only - it
// loads run artifacts gm-geometry already wrote and draws them; it
// computes nothing financial. This first pass covers the Manifold tab
// (3D point cloud, orbit camera) and the Evolution tab's time scrubber
// plus the structural_change strip (ImPlot); the boundary-surface mesh
// rendering, MST edges, per-point trails, and the click-to-learn panel
// are follow-up work, not attempted in this pass.

#include <glad/glad.h>  // must be included before GLFW's own gl.h pulls a conflicting one

#include <GLFW/glfw3.h>

#include <imgui.h>
#include <imgui_impl_glfw.h>
#include <imgui_impl_opengl3.h>
#include <implot.h>

#include <gm-core/error.hpp>
#include <spdlog/spdlog.h>

#include <cerrno>
#include <cstdlib>
#include <limits>

#include <algorithm>
#include <array>
#include <cstdint>
#include <sstream>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <set>
#include <map>

#include "camera.hpp"
#include "data_loader.hpp"
#include "gl.hpp"

#include <gm-io/mesh.hpp>

#include <filesystem>

namespace {

struct AppState {
    std::vector<gm::view::RunInfo> runs;
    int selected_run = -1;
    gm::view::LoadedRun loaded;
    bool has_loaded_run = false;
    int current_frame = 0;
    bool playing = false;
    double play_accum_seconds = 0.0;

    gm::view::OrbitCamera camera;
    bool camera_initialized = false;
    // UI state for three new tabs
    int selected_tab = 0;  // 0=Manifold, 1=2D Pairs, 2=3D Sectors, 3=Evolution
    // The boundary surface is drawn when the run has one on disk. Runs made
    // without boundaries.write_meshes have no surfaces/ directory at all, in
    // which case this toggle simply has nothing to show - which the control
    // panel says explicitly rather than leaving the user wondering whether
    // the checkbox is broken.
    bool show_surface = true;
    bool surface_available = false;
    /// Which surfaces this run exported, scanned once when it loads.
    gm::view::SurfaceIndex surfaces;
    /// Half-diagonal of the currently uploaded surface's bounding box,
    /// about the frame centroid, or 0 when no surface is drawn. Kept so
    /// the initial camera distance can frame whichever of the points and
    /// the surface is larger - which for a View B tube is always the
    /// surface, by a wide margin.
    float surface_radius = 0.0f;
    /// What the surface currently on screen actually IS - which view, and
    /// for View B which date it was fitted as of. Shown in the panel
    /// rather than left implicit, because the two views produce visually
    /// similar lumps and a reader cannot tell them apart by looking.
    std::string surface_label;

    // How many embedding dimensions this run actually has, and which three
    // of them are on screen. A run written before dimensions past the third
    // were kept has exactly three, and these stay 0/1/2.
    int embedding_dims = 3;
    int axis_x = 0, axis_y = 1, axis_z = 2;

    // The equity being followed. Drawn red and larger than the rest, in
    // both the whole-market view and its own trajectory, so the same name
    // is identifiable as the shape around it changes.
    int tracked_ticker_idx = -1;
    std::string tracked_ticker;

    // Trajectory mode replaces "every equity on this date" with "this one
    // equity across the preceding `trajectory_lookback` dates" - the cloud
    // View B fits its boundary to. Same 3-D projection, different subject.
    bool trajectory_mode = false;
    int trajectory_lookback = 756;
    int selected_ticker1_idx = -1;
    int selected_ticker2_idx = -1;
    std::vector<const char*> available_ticker_labels;
    bool show_sectors = false;
    bool show_learn_panel = false;
    std::string learn_panel_ticker;
    // sector -> distinct RGBA color, one entry per real GICS sector
    // present in the loaded run (see assign_sector_colors below).
    // Rebuilt once per run load, not derived per-point every frame.
    std::map<std::string, std::uint32_t> sector_colors;
};

void glfw_error_callback(int error, const char* description) {
    spdlog::error("gm-view: GLFW error {}: {}", error, description);
}

/// Assigns each distinct GICS sector actually present in `state.loaded`
/// a genuinely distinct color, alphabetically: palette[i] for the i-th
/// sector in sorted order. This is collision-free by construction
/// (unlike a hash mod palette-size, which guarantees a collision for
/// GICS's 11 sectors against anything smaller than an 11-entry
/// palette) as long as the palette has at least as many entries as
/// there are distinct sectors - checked below with a fallback color
/// for any overflow, which should never trigger for real GICS data.
///
/// Palette literals are plain RGBA byte order (0xRRGGBBAA) throughout -
/// the previous palette mixed ARGB-authored literals (0xAARRGGBB, alpha
/// first) into a table that was always decoded as RGBA, so 8 of its 10
/// entries silently rendered with red=0xFF.
void assign_sector_colors(AppState& state) {
    static const std::vector<std::uint32_t> palette = {
        0xE6194BFF,  // red
        0x3CB44BFF,  // green
        0xFFE119FF,  // yellow
        0x4363D8FF,  // blue
        0xF58231FF,  // orange
        0x911EB4FF,  // purple
        0x42D4F4FF,  // cyan
        0xF032E6FF,  // magenta
        0xBFEF45FF,  // lime
        0xFABED4FF,  // pink
        0x469990FF,  // teal
        0x9A6324FF,  // brown
    };
    std::set<std::string> sectors;
    for (const auto& [ticker, meta] : state.loaded.ticker_metadata) {
        sectors.insert(meta.gics_sector);
    }
    state.sector_colors.clear();
    std::size_t i = 0;
    for (const auto& sector : sectors) {  // std::set iterates sorted ascending
        state.sector_colors[sector] = palette[i % palette.size()];
        ++i;
    }
}

std::uint32_t sector_to_color(const AppState& state, const std::string& sector) {
    auto it = state.sector_colors.find(sector);
    if (it != state.sector_colors.end()) return it->second;
    return 0x808080FF;  // neutral gray - a sector with no assigned color (shouldn't happen for real GICS data)
}

/// Ticker `ticker`'s full spread z-score series across every date
/// gm-signals scored it, in ascending date order - NOT filtered to a
/// single date. spreads.parquet has exactly one row per (ticker, date),
/// so filtering on both ticker AND date (the previous behavior) could
/// only ever return zero or one point, which is why the plot rendered
/// a single point. This also plots s.z (the actual z-score, the
/// quantity the +/-1/+/-2 sigma reference bands are calibrated
/// against) rather than s.spread (the raw log-price residual, a
/// different quantity on a different scale that happened to compile
/// but read as nonsense next to those bands).
std::vector<std::pair<std::string, double>> get_spread_series_for_ticker(
    const gm::view::LoadedRun& loaded, const std::string& ticker) {
    std::vector<std::pair<std::string, double>> result;
    for (const auto& s : loaded.spreads) {
        if (s.ticker == ticker) {
            result.push_back({s.date, s.z});
        }
    }
    // gm-signals writes spreads.parquet ticker-major/date-ascending, so
    // this is normally already sorted - sorting defensively here keeps
    // the plot correct even if that upstream ordering ever changes.
    std::sort(result.begin(), result.end(),
              [](const auto& a, const auto& b) { return a.first < b.first; });
    return result;
}

const std::vector<gm::view::Excursion> kEmptyExcursions;

/// O(log n) index lookup (built once in load_run) rather than a linear
/// scan of every excursion row on every rendered frame.
const std::vector<gm::view::Excursion>& get_excursions_for_ticker(
    const gm::view::LoadedRun& loaded, const std::string& ticker) {
    auto it = loaded.excursions_by_ticker.find(ticker);
    if (it == loaded.excursions_by_ticker.end()) return kEmptyExcursions;
    return it->second;
}

/// Recolors/repositions the uploaded point cloud for `frame_idx` and
/// recenters the camera's orbit target on that frame's centroid (the
/// camera's distance/yaw/pitch stay under the user's own mouse control -
/// only the recentering follows the data, so switching frames doesn't
/// fight whatever zoom/angle the user already set).
/// Reads one coordinate of a ticker's position under the current axis
/// selection. Falls back to the first three dimensions for a run that has
/// no others, so this is safe on old artifacts.
float coord_on_axis(const gm::view::Frame& frame, std::size_t row, int axis) {
    if (row < frame.coords.size()) {
        const auto& c = frame.coords[row];
        if (axis >= 0 && static_cast<std::size_t>(axis) < c.size()) return c[static_cast<std::size_t>(axis)];
        return 0.0f;
    }
    if (row < frame.positions.size() && axis >= 0 && axis < 3) {
        return frame.positions[row][static_cast<std::size_t>(axis)];
    }
    return 0.0f;
}

void upload_frame(gm::view::PointCloudRenderer& renderer, gm::view::MeshRenderer& mesh_renderer,
                   gm::view::PointCloudRenderer& highlight_renderer, AppState& state,
                   int frame_idx) {
    if (frame_idx < 0 || static_cast<std::size_t>(frame_idx) >= state.loaded.frames.size()) return;
    const auto& frame = state.loaded.frames[static_cast<std::size_t>(frame_idx)];

    state.available_ticker_labels.clear();
    for (const auto& t : frame.tickers) {
        state.available_ticker_labels.push_back(t.c_str());
    }

    // The boundary surface for what is currently on screen. Cleared first
    // so a frame without a mesh shows no mesh, rather than leaving the
    // previous frame's envelope around a different day's points - a
    // picture that would look plausible and be wrong.
    //
    // WHICH surface depends on what the points are. The two views are
    // different objects and pairing either with the other's points would
    // be a category error:
    //
    //   normal mode      the points are every ticker on one date, so the
    //                    surface is View A - the market's envelope that
    //                    day, {date}_A.gmmesh.
    //   trajectory mode  the points are one ticker across many dates, so
    //                    the surface is View B - that ticker's own tube,
    //                    {date}_B_{ticker}.gmmesh.
    //
    // Both are suppressed unless the axes on screen are dim0/1/2, which is
    // the projection gm-boundaries exported; any other triple would draw a
    // shape belonging to different axes.
    mesh_renderer.clear();
    state.surface_label.clear();
    state.surface_radius = 0.0f;
    std::array<double, 3> surface_lo{};
    std::array<double, 3> surface_hi{};
    bool surface_bounds_valid = false;
    const bool axes_match_export =
        state.axis_x == 0 && state.axis_y == 1 && state.axis_z == 2;
    if (axes_match_export && state.selected_run >= 0 &&
        static_cast<std::size_t>(state.selected_run) < state.runs.size()) {
        const auto surfaces_dir =
            state.runs[static_cast<std::size_t>(state.selected_run)].run_dir / "gm-boundaries" /
            "surfaces";
        std::filesystem::path surface_path;
        std::string label;
        if (state.trajectory_mode && !state.tracked_ticker.empty()) {
            // Exported on a stride, so most dates have no tube of their
            // own and the honest answer is the newest earlier one - which
            // the label names, so a surface a few weeks stale is never
            // mistaken for this date's.
            if (auto as_of = state.surfaces.view_b_surface_for(state.tracked_ticker, frame.date)) {
                surface_path = surfaces_dir / (*as_of + "_B_" + state.tracked_ticker + ".gmmesh");
                label = "View B: " + state.tracked_ticker + "'s own envelope, as of " + *as_of;
            }
        } else if (!state.trajectory_mode && state.surfaces.view_a_dates.count(frame.date) != 0) {
            surface_path = surfaces_dir / (frame.date + "_A.gmmesh");
            label = "View A: the market's envelope on " + frame.date;
        }
        if (!surface_path.empty()) {
            auto mesh = gm::io::read_gmmesh(surface_path);
            if (mesh) {
                for (const auto& v : mesh->vertices) {
                    if (!surface_bounds_valid) {
                        surface_lo = v;
                        surface_hi = v;
                        surface_bounds_valid = true;
                        continue;
                    }
                    for (std::size_t k = 0; k < 3; ++k) {
                        surface_lo[k] = std::min(surface_lo[k], v[k]);
                        surface_hi[k] = std::max(surface_hi[k], v[k]);
                    }
                }
                mesh_renderer.upload(*mesh);
                state.surface_label = std::move(label);
            } else {
                // Indexed but unreadable - truncated write, wrong version.
                // Left unlabelled so the panel reports no surface rather
                // than naming one that is not being drawn.
                spdlog::warn("gm-view: could not read boundary surface {}: {}",
                             surface_path.string(), mesh.error().to_string());
            }
        }
    }

    std::vector<gm::view::PointVertex> verts;
    std::vector<gm::view::PointVertex> highlight;
    float cx = 0.0f, cy = 0.0f, cz = 0.0f;

    if (state.trajectory_mode && !state.tracked_ticker.empty()) {
        // One equity, across the frames leading up to this one. Older
        // positions fade toward the background so the direction of travel
        // is readable from a still image, not only while scrubbing.
        const int first = std::max(0, frame_idx - state.trajectory_lookback + 1);
        const int span = std::max(1, frame_idx - first);
        for (int f = first; f <= frame_idx; ++f) {
            const auto& past = state.loaded.frames[static_cast<std::size_t>(f)];
            const auto it = std::find(past.tickers.begin(), past.tickers.end(), state.tracked_ticker);
            if (it == past.tickers.end()) continue;
            const auto row = static_cast<std::size_t>(std::distance(past.tickers.begin(), it));
            const float x = coord_on_axis(past, row, state.axis_x);
            const float y = coord_on_axis(past, row, state.axis_y);
            const float z = coord_on_axis(past, row, state.axis_z);

            if (f == frame_idx) {
                // Today: the red marker, drawn separately and larger.
                highlight.push_back({x, y, z, 1.0f, 0.32f, 0.28f});
            } else {
                const float age = static_cast<float>(f - first) / static_cast<float>(span);
                const float fade = 0.25f + 0.75f * age;
                verts.push_back({x, y, z, 0.55f * fade, 0.80f * fade, 1.0f * fade});
            }
            cx += x;
            cy += y;
            cz += z;
        }
        const auto n = static_cast<float>(verts.size() + highlight.size());
        if (n > 0.0f) {
            cx /= n;
            cy /= n;
            cz /= n;
        }
    } else {
        for (std::size_t i = 0; i < frame.tickers.size(); ++i) {
            const float x = coord_on_axis(frame, i, state.axis_x);
            const float y = coord_on_axis(frame, i, state.axis_y);
            const float z = coord_on_axis(frame, i, state.axis_z);
            cx += x;
            cy += y;
            cz += z;

            if (!state.tracked_ticker.empty() && frame.tickers[i] == state.tracked_ticker) {
                highlight.push_back({x, y, z, 1.0f, 0.32f, 0.28f});
                continue;
            }
            // Sector coloring looks the ticker up by its parallel index
            // into frame.tickers, since the coordinates carry no identity
            // of their own.
            std::uint32_t color = 0x5A85FFFF;
            if (state.show_sectors) {
                auto meta_it = state.loaded.ticker_metadata.find(frame.tickers[i]);
                if (meta_it != state.loaded.ticker_metadata.end()) {
                    color = sector_to_color(state, meta_it->second.gics_sector);
                }
            }
            const float r = static_cast<float>((color >> 24) & 0xFF) / 255.0f;
            const float g = static_cast<float>((color >> 16) & 0xFF) / 255.0f;
            const float b = static_cast<float>((color >> 8) & 0xFF) / 255.0f;
            verts.push_back({x, y, z, r, g, b});
        }
        const auto n = static_cast<float>(frame.tickers.size());
        if (n > 0.0f) {
            cx /= n;
            cy /= n;
            cz /= n;
        }
    }

    renderer.upload(verts);
    highlight_renderer.upload(highlight);

    state.camera.target_x = cx;
    state.camera.target_y = cy;
    state.camera.target_z = cz;

    if (surface_bounds_valid) {
        // Furthest corner of the surface's box from the centroid the
        // camera orbits. Corners rather than the box's own half-diagonal,
        // because the centroid is the points' centre and need not be the
        // surface's - a trajectory ending in a sharp move sits well off
        // the middle of its own tube.
        for (int corner = 0; corner < 8; ++corner) {
            const float x = static_cast<float>((corner & 1) ? surface_hi[0] : surface_lo[0]);
            const float y = static_cast<float>((corner & 2) ? surface_hi[1] : surface_lo[1]);
            const float z = static_cast<float>((corner & 4) ? surface_hi[2] : surface_lo[2]);
            const float dx = x - cx, dy = y - cy, dz = z - cz;
            state.surface_radius =
                std::max(state.surface_radius, std::sqrt(dx * dx + dy * dy + dz * dz));
        }
    }

    if (!state.camera_initialized) {
        // Distances of every drawn point from the orbit target.
        std::vector<float> distances;
        distances.reserve(verts.size() + highlight.size());
        const auto add = [&](const gm::view::PointVertex& v) {
            const float dx = v.x - cx, dy = v.y - cy, dz = v.z - cz;
            distances.push_back(std::sqrt(dx * dx + dy * dy + dz * dz));
        };
        for (const auto& v : verts) add(v);
        for (const auto& v : highlight) add(v);

        // The 95th percentile, NOT the maximum. Fitting to the furthest
        // single point makes the picture hostage to one outlier: on the
        // March-2020 frame all 81 tickers collapse into one tight clump with
        // three far-flung names, and framing the outliers renders the clump -
        // the actual subject - as a few pixels. That looks like a broken
        // renderer and is really the market clenching, which is worth
        // seeing rather than being hidden by its own extremes.
        //
        // The outliers stay drawn; they simply stop deciding the zoom, and
        // the user can scroll out to them. A boundary surface, when there is
        // one, still frames in full below - it is the subject, not an
        // outlier.
        // The fallback is for a cloud with nothing to frame at all - a
        // single point, or none. It must NOT act as a floor on a real
        // measurement: 0.1 was one, and on the March-2020 frame the entire
        // 81-name cloud is smaller than that, so the floor and not the data
        // set the zoom and the clump still rendered as a smudge.
        float max_dist = 0.0f;
        if (!distances.empty()) {
            const std::size_t idx =
                static_cast<std::size_t>(0.95 * static_cast<double>(distances.size() - 1));
            std::nth_element(distances.begin(), distances.begin() + static_cast<std::ptrdiff_t>(idx),
                             distances.end());
            max_dist = distances[idx];
        }
        // Whichever is bigger. A View B tube is a level set sampled in a
        // box padded by three bandwidths per axis, so it routinely extends
        // several times further than the path it encloses; fitting to the
        // points alone put the camera inside the surface.
        max_dist = std::max(max_dist, state.surface_radius);
        // Only now, once both the points and the surface have had their say.
        if (!(max_dist > 0.0f)) max_dist = 0.1f;
        state.camera.distance = max_dist * 2.5f;
        state.camera_initialized = true;
    }
}

void load_selected_run(AppState& state, gm::view::PointCloudRenderer& renderer,
                        gm::view::MeshRenderer& mesh_renderer,
                        gm::view::PointCloudRenderer& highlight_renderer) {
    if (state.selected_run < 0 || static_cast<std::size_t>(state.selected_run) >= state.runs.size()) {
        return;
    }
    auto loaded = gm::view::load_run(state.runs[static_cast<std::size_t>(state.selected_run)].run_dir);
    if (!loaded) {
        spdlog::error("gm-view: failed to load run: {}", loaded.error().to_string());
        state.has_loaded_run = false;
        return;
    }
    state.loaded = std::move(*loaded);
    state.has_loaded_run = true;
    state.current_frame = 0;
    state.camera_initialized = false;
    // Refresh unconditionally: available_ticker_labels holds const
    // char* pointers into state.loaded's own strings (frame.tickers),
    // and state.loaded was just replaced above. Previously this only
    // happened inside upload_frame, called only when frames is
    // non-empty - a run with zero geometry frames (has_loaded_run
    // still true) left the old run's now-dangling pointers in place.
    state.available_ticker_labels.clear();
    state.selected_ticker1_idx = -1;
    state.selected_ticker2_idx = -1;
    assign_sector_colors(state);
    // Whether this run has surfaces at all, decided once per run rather
    // than probed every frame.
    state.surfaces = gm::view::SurfaceIndex{};
    state.surface_available = false;
    if (state.selected_run >= 0 &&
        static_cast<std::size_t>(state.selected_run) < state.runs.size()) {
        state.surfaces = gm::view::index_surfaces(
            state.runs[static_cast<std::size_t>(state.selected_run)].run_dir);
        state.surface_available = state.surfaces.directory_exists;
    }
    // Default the trajectory length to the window the View B tubes were
    // actually fitted to. Left at its own default, a 756-day path would be
    // drawn inside a tube built from 60 days of history and appear to
    // burst out of it everywhere - which looks like a broken surface and
    // is really just two different numbers. The user can still move the
    // slider; the panel says when it no longer matches.
    if (state.surfaces.view_b_lookback_days > 0) {
        state.trajectory_lookback = static_cast<int>(
            std::clamp<std::int64_t>(state.surfaces.view_b_lookback_days, 1, 100000));
    }
    if (!state.loaded.frames.empty()) state.embedding_dims =
            state.loaded.frames.front().coords.empty()
                ? 3
                : static_cast<int>(state.loaded.frames.front().coords.front().size());
        state.axis_x = 0;
        state.axis_y = std::min(1, state.embedding_dims - 1);
        state.axis_z = std::min(2, state.embedding_dims - 1);
        state.tracked_ticker.clear();
        state.tracked_ticker_idx = -1;
        state.trajectory_mode = false;
        upload_frame(renderer, mesh_renderer, highlight_renderer, state, 0);
}

} // namespace

int main(int argc, char** argv) {
    std::string runs_base_dir = "runs";
    int start_frame = 0;
    // These exist so the viewer can be driven from outside, not only by
    // hand. A GUI whose only entry point is a mouse cannot be exercised on
    // a machine without one, cannot produce a reproducible screenshot, and
    // cannot be checked by anything but a person remembering to look -
    // which is how a view ends up quietly broken between releases.
    std::string track_ticker;
    bool start_in_trajectory_mode = false;
    std::string axes_spec;
    // Without this, a scripted screenshot always lands on the default
    // orbit angle - which for a flat or elongated surface can be exactly
    // edge-on, i.e. the one angle from which the shape is invisible. A
    // verification picture taken from the only useless viewpoint is worse
    // than no picture, because it looks like evidence.
    std::string camera_spec;
    // The other three tabs are unreachable from outside without this, so
    // they get no screenshot, no smoke check, and no evidence they still
    // render at all.
    std::string tab_spec;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--start-frame") {
            if (i + 1 >= argc) {
                spdlog::error("gm-view: --start-frame requires a numeric argument");
                return 1;
            }
            // atoi silently returns 0 on any non-numeric input ("abc",
            // or a typo'd flag like "--start-fame" that this loop would
            // otherwise swallow as runs_base_dir) - strtol with an
            // endptr check tells a genuine parse failure apart from a
            // legitimate "0".
            const char* arg_str = argv[++i];
            char* end = nullptr;
            errno = 0;
            long parsed = std::strtol(arg_str, &end, 10);
            if (end == arg_str || *end != '\0' || errno == ERANGE || parsed < 0 ||
                parsed > std::numeric_limits<int>::max()) {
                spdlog::error("gm-view: --start-frame must be a non-negative integer, got '{}'",
                               arg_str);
                return 1;
            }
            start_frame = static_cast<int>(parsed);
        } else if (arg == "--track") {
            if (i + 1 >= argc) {
                spdlog::error("gm-view: --track requires a ticker symbol");
                return 1;
            }
            track_ticker = argv[++i];
        } else if (arg == "--trajectory") {
            start_in_trajectory_mode = true;
        } else if (arg == "--tab") {
            if (i + 1 >= argc) {
                spdlog::error("gm-view: --tab requires one of manifold, pairs, sectors, evolution");
                return 1;
            }
            tab_spec = argv[++i];
        } else if (arg == "--camera") {
            if (i + 1 >= argc) {
                spdlog::error("gm-view: --camera requires YAW,PITCH in degrees, e.g. --camera 40,25");
                return 1;
            }
            camera_spec = argv[++i];
        } else if (arg == "--axes") {
            if (i + 1 >= argc) {
                spdlog::error("gm-view: --axes requires three comma-separated dimension indices, "
                               "e.g. --axes 0,3,7");
                return 1;
            }
            axes_spec = argv[++i];
        } else {
            runs_base_dir = arg;
        }
    }

#if defined(__linux__)
    // On Linux, glfwInit() against neither an X11 nor a Wayland display
    // (a bare SSH session, a CI box, a container with no compositor)
    // fails in a way that's easy to misread as a build or driver
    // problem rather than "there's nowhere to put a window." Check the
    // obvious cause first and say so plainly - gm-view is genuinely a
    // GUI application with no headless mode, not a bug to work around.
    if (std::getenv("DISPLAY") == nullptr && std::getenv("WAYLAND_DISPLAY") == nullptr) {
        spdlog::error(
            "gm-view: no DISPLAY or WAYLAND_DISPLAY set - this is a GUI application and needs "
            "an X11 or Wayland session to open a window (e.g. run against a real desktop "
            "session's display, such as DISPLAY=:0)");
        return 1;
    }
#endif

    glfwSetErrorCallback(glfw_error_callback);
    if (!glfwInit()) {
        spdlog::error("gm-view: glfwInit failed");
        return 1;
    }

    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);

    GLFWwindow* window = glfwCreateWindow(1280, 800, "gm-view", nullptr, nullptr);
    if (!window) {
        spdlog::error("gm-view: glfwCreateWindow failed");
        glfwTerminate();
        return 1;
    }
    glfwMakeContextCurrent(window);
    glfwSwapInterval(1);

    if (!gladLoadGLLoader(reinterpret_cast<GLADloadproc>(glfwGetProcAddress))) {
        spdlog::error("gm-view: gladLoadGLLoader failed");
        return 1;
    }
    spdlog::info("gm-view: OpenGL {} ({})", reinterpret_cast<const char*>(glGetString(GL_VERSION)),
                 reinterpret_cast<const char*>(glGetString(GL_RENDERER)));

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImPlot::CreateContext();
    ImGui::StyleColorsDark();
    ImGui_ImplGlfw_InitForOpenGL(window, true);
    ImGui_ImplOpenGL3_Init("#version 330");

    auto renderer_result = gm::view::PointCloudRenderer::create();
    if (!renderer_result) {
        spdlog::error("gm-view: failed to create point cloud renderer: {}",
                      renderer_result.error().to_string());
        return 1;
    }
    gm::view::PointCloudRenderer renderer = std::move(*renderer_result);

    auto mesh_renderer_result = gm::view::MeshRenderer::create();
    if (!mesh_renderer_result) {
        spdlog::error("gm-view: failed to create mesh renderer: {}",
                      mesh_renderer_result.error().to_string());
        return 1;
    }
    gm::view::MeshRenderer mesh_renderer = std::move(*mesh_renderer_result);

    // A second point cloud holding only the tracked equity, so it can be
    // drawn at a larger size than the rest. PointCloudRenderer takes one
    // uniform point size per draw call, and a separate call is a great deal
    // simpler than threading a per-vertex size through the shader for a
    // cloud that never has more than one point in it.
    auto highlight_result = gm::view::PointCloudRenderer::create();
    if (!highlight_result) {
        spdlog::error("gm-view: failed to create highlight renderer: {}",
                      highlight_result.error().to_string());
        return 1;
    }
    gm::view::PointCloudRenderer highlight_renderer = std::move(*highlight_result);

    AppState state;
    auto runs = gm::view::list_available_runs(runs_base_dir);
    if (runs) {
        state.runs = std::move(*runs);
        if (!state.runs.empty()) {
            state.selected_run = 0;
            load_selected_run(state, renderer, mesh_renderer, highlight_renderer);

            if (!axes_spec.empty()) {
                int parsed_axes[3] = {0, 1, 2};
                int count = 0;
                std::stringstream ss(axes_spec);
                std::string token;
                bool bad = false;
                while (std::getline(ss, token, ',') && count < 3) {
                    try {
                        std::size_t consumed = 0;
                        const int value = std::stoi(token, &consumed);
                        if (consumed != token.size() || value < 0 || value >= state.embedding_dims) {
                            bad = true;
                            break;
                        }
                        parsed_axes[count++] = value;
                    } catch (const std::exception&) {
                        bad = true;
                        break;
                    }
                }
                if (bad || count != 3) {
                    spdlog::error("gm-view: --axes needs three comma-separated indices in [0,{}), "
                                   "got '{}'",
                                   state.embedding_dims, axes_spec);
                    return 1;
                }
                state.axis_x = parsed_axes[0];
                state.axis_y = parsed_axes[1];
                state.axis_z = parsed_axes[2];
            }

            if (!track_ticker.empty()) {
                // Verified against the frame's actual membership rather than
                // accepted on faith: a typo'd symbol that silently tracked
                // nothing would look identical to a working run.
                const auto& labels = state.available_ticker_labels;
                const auto found = std::find_if(labels.begin(), labels.end(), [&](const char* t) {
                    return track_ticker == t;
                });
                if (found == labels.end()) {
                    spdlog::error("gm-view: --track '{}' is not in this run's first frame",
                                   track_ticker);
                    return 1;
                }
                state.tracked_ticker = track_ticker;
                state.tracked_ticker_idx = static_cast<int>(std::distance(labels.begin(), found));
                state.trajectory_mode = start_in_trajectory_mode;
            } else if (start_in_trajectory_mode) {
                spdlog::error("gm-view: --trajectory needs --track to say whose path to draw");
                return 1;
            }
            // Seek BEFORE the first upload, not after. Uploading frame 0
            // first and then jumping fitted the camera to frame 0 - which
            // in trajectory mode holds a single point and no surface yet,
            // since the lookback window has not filled - and left that
            // framing in place for the frame actually asked for. The
            // symptom was a camera sitting inside the boundary surface,
            // looking at the inside of a wall.
            if (start_frame > 0 && !state.loaded.frames.empty()) {
                state.current_frame =
                    std::min(start_frame, static_cast<int>(state.loaded.frames.size()) - 1);
            }
            state.camera_initialized = false;
            upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);

            // Applied after upload_frame, which is what sets the distance:
            // this overrides the ANGLE only, leaving the automatic framing
            // it just computed intact.
            if (!tab_spec.empty()) {
                // Names rather than indices: "--tab 2" would silently point
                // somewhere else the moment a tab is inserted, and a
                // screenshot of the wrong tab still looks like a screenshot.
                const std::map<std::string, int> kTabs = {
                    {"manifold", 0}, {"pairs", 1}, {"sectors", 2}, {"evolution", 3}};
                const auto found = kTabs.find(tab_spec);
                if (found == kTabs.end()) {
                    spdlog::error("gm-view: --tab must be one of manifold, pairs, sectors, "
                                   "evolution; got '{}'",
                                   tab_spec);
                    return 1;
                }
                state.selected_tab = found->second;
            }

            if (!camera_spec.empty()) {
                // Parsed with the C++ facilities rather than sscanf, which
                // MSVC deprecates and which would also have accepted
                // "40,25,junk" while quietly ignoring the tail. A flag that
                // silently discards part of what was typed is a flag that
                // produces the wrong picture without saying so.
                float yaw_deg = 0.0f, pitch_deg = 0.0f;
                const auto comma = camera_spec.find(',');
                bool camera_ok = comma != std::string::npos;
                if (camera_ok) {
                    try {
                        std::size_t used_yaw = 0, used_pitch = 0;
                        const std::string yaw_text = camera_spec.substr(0, comma);
                        const std::string pitch_text = camera_spec.substr(comma + 1);
                        yaw_deg = std::stof(yaw_text, &used_yaw);
                        pitch_deg = std::stof(pitch_text, &used_pitch);
                        // Every character has to have been consumed, or part
                        // of the argument was thrown away.
                        camera_ok = used_yaw == yaw_text.size() && used_pitch == pitch_text.size();
                    } catch (const std::exception&) {
                        camera_ok = false;
                    }
                }
                if (!camera_ok) {
                    spdlog::error("gm-view: --camera needs YAW,PITCH in degrees, got '{}'",
                                   camera_spec);
                    return 1;
                }
                constexpr float kDegToRad = 3.14159265358979323846f / 180.0f;
                state.camera.yaw = yaw_deg * kDegToRad;
                // Same clamp orbit() applies, so a scripted angle cannot
                // reach a pole the mouse cannot.
                state.camera.pitch = std::clamp(pitch_deg * kDegToRad, -1.5f, 1.5f);
            }
        }
    } else {
        spdlog::error("gm-view: failed to list runs: {}", runs.error().to_string());
    }

    double last_time = glfwGetTime();

    while (!glfwWindowShouldClose(window)) {
        glfwPollEvents();

        double now = glfwGetTime();
        double dt = now - last_time;
        last_time = now;

        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();

        ImGuiIO& io = ImGui::GetIO();
        if (!io.WantCaptureMouse) {
            if (ImGui::IsMouseDragging(ImGuiMouseButton_Left)) {
                state.camera.orbit(-io.MouseDelta.x * 0.01f, io.MouseDelta.y * 0.01f);
            }
            if (io.MouseWheel != 0.0f) {
                state.camera.zoom(-io.MouseWheel * state.camera.distance * 0.1f);
            }
        }

        if (state.playing && state.has_loaded_run && !state.loaded.frames.empty()) {
            state.play_accum_seconds += dt;
            constexpr double kSecondsPerFrame = 0.15;
            if (state.play_accum_seconds >= kSecondsPerFrame) {
                state.play_accum_seconds = 0.0;
                state.current_frame =
                    (state.current_frame + 1) % static_cast<int>(state.loaded.frames.size());
                upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
            }
        }

        // AlwaysAutoResize, not the default: ImGui only auto-fits a
        // window's size once, on its very first frame - without this
        // flag, the control panel stays frozen at whatever it measured
        // before data finished loading (just the run selector, before
        // the frame slider/Play button/regime plot exist), and the
        // rest of the content silently clips instead of the window
        // growing to show it. Found by actually screenshotting the
        // running app, not by reading the ImGui docs and assuming.
        ImGui::SetNextWindowPos(ImVec2(0, 0), ImGuiCond_FirstUseEver);
        ImGui::SetNextWindowSize(ImVec2(400, 750), ImGuiCond_FirstUseEver);
        ImGui::Begin("gm-view Control Panel", nullptr, ImGuiWindowFlags_AlwaysAutoResize);
        ImGui::Text("Runs (%s)", runs_base_dir.c_str());
        if (state.runs.empty()) {
            ImGui::TextDisabled("No runs found - run gm-run first.");
        } else {
            std::vector<const char*> run_labels;
            run_labels.reserve(state.runs.size());
            for (const auto& r : state.runs) run_labels.push_back(r.run_id.c_str());
            if (ImGui::Combo("Run", &state.selected_run, run_labels.data(),
                              static_cast<int>(run_labels.size()))) {
                load_selected_run(state, renderer, mesh_renderer, highlight_renderer);
            }
        }

        if (state.has_loaded_run && !state.loaded.frames.empty()) {
            ImGui::Separator();
            ImGui::Text("Frame: %s (%d/%zu)",
                        state.loaded.frames[static_cast<std::size_t>(state.current_frame)].date.c_str(),
                        state.current_frame + 1, state.loaded.frames.size());
            int max_frame = static_cast<int>(state.loaded.frames.size()) - 1;
            if (ImGui::SliderInt("##frame", &state.current_frame, 0, max_frame)) {
                upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
            }
            ImGui::SameLine();
            if (ImGui::Button(state.playing ? "Pause" : "Play")) state.playing = !state.playing;

            ImGui::Text("Tickers this frame: %zu",
                        state.loaded.frames[static_cast<std::size_t>(state.current_frame)].tickers.size());
            ImGui::TextDisabled("Left-drag to orbit, scroll to zoom.");

            // Tab selection. Self-contained on purpose: everything emitted
            // between BeginTabBar and EndTabBar is laid out in the tab bar's
            // own context, and this block used to enclose the entire control
            // panel - so the surface checkbox, the axis pickers and each
            // tab's content were all drawn over one another and over the tab
            // strip itself. Nothing but the tab buttons belongs in here.
            ImGui::Separator();
            if (ImGui::BeginTabBar("ViewTabs")) {
                if (ImGui::TabItemButton("Manifold", state.selected_tab == 0 ? ImGuiTabItemFlags_SetSelected : 0)) {
                    state.selected_tab = 0;
                }
                if (ImGui::TabItemButton("2D Pairs", state.selected_tab == 1 ? ImGuiTabItemFlags_SetSelected : 0)) {
                    state.selected_tab = 1;
                }
                if (ImGui::TabItemButton("3D Sectors", state.selected_tab == 2 ? ImGuiTabItemFlags_SetSelected : 0)) {
                    state.selected_tab = 2;
                }
                if (ImGui::TabItemButton("Evolution", state.selected_tab == 3 ? ImGuiTabItemFlags_SetSelected : 0)) {
                    state.selected_tab = 3;
                }
                ImGui::EndTabBar();
            }
            ImGui::Separator();
            if (state.surface_available) {
                ImGui::Checkbox("Boundary surface", &state.show_surface);
                if (state.show_surface) {
                    if (!state.surface_label.empty()) {
                        ImGui::TextDisabled("%s", state.surface_label.c_str());
                    } else if (state.trajectory_mode && !state.tracked_ticker.empty()) {
                        // Distinguish "this run exported no tubes for this
                        // name" from "it did, but not yet this early" -
                        // they need different actions from the user and
                        // one shared message would fit neither.
                        if (state.surfaces.view_b_dates.count(state.tracked_ticker) == 0) {
                            ImGui::TextDisabled("no tube for %s in this run",
                                                state.tracked_ticker.c_str());
                            ImGui::TextDisabled("add it to boundaries.view_b_mesh_tickers");
                        } else {
                            ImGui::TextDisabled("no tube yet - its first %lld days of",
                                                static_cast<long long>(
                                                    state.surfaces.view_b_lookback_days));
                            ImGui::TextDisabled("history had not accumulated by this date");
                        }
                    } else {
                        ImGui::TextDisabled("no surface exported for this frame");
                    }
                }
            } else {
                ImGui::TextDisabled("No boundary surfaces in this run.");
                ImGui::TextDisabled("Re-run gm-boundaries with boundaries.write_meshes = true.");
            }

            ImGui::Separator();
            ImGui::Text("Embedding: %d dimensions", state.embedding_dims);
            if (state.embedding_dims > 3) {
                // Only meaningful when the run has axes to choose between.
                // A surface can only be drawn for the first three, because
                // that is the projection gm-boundaries exported; choosing
                // any other triple hides it rather than showing a shape
                // that belongs to different axes.
                std::vector<std::string> axis_names;
                for (int d = 0; d < state.embedding_dims; ++d) axis_names.push_back("dim" + std::to_string(d));
                std::vector<const char*> axis_labels;
                for (const auto& a : axis_names) axis_labels.push_back(a.c_str());
                bool changed = false;
                changed |= ImGui::Combo("axis X", &state.axis_x, axis_labels.data(), static_cast<int>(axis_labels.size()));
                changed |= ImGui::Combo("axis Y", &state.axis_y, axis_labels.data(), static_cast<int>(axis_labels.size()));
                changed |= ImGui::Combo("axis Z", &state.axis_z, axis_labels.data(), static_cast<int>(axis_labels.size()));
                if (changed) {
                    state.camera_initialized = false;
                    upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
                }
                if (!(state.axis_x == 0 && state.axis_y == 1 && state.axis_z == 2)) {
                    ImGui::TextDisabled("surface hidden: exported for dim0/1/2 only");
                }
            }

            ImGui::Separator();
            if (!state.available_ticker_labels.empty()) {
                if (ImGui::Combo("Track", &state.tracked_ticker_idx,
                                  state.available_ticker_labels.data(),
                                  static_cast<int>(state.available_ticker_labels.size()))) {
                    // Stored by NAME, not index: the index is into this
                    // frame's ticker list, and membership changes over
                    // time, so an index would silently start pointing at a
                    // different company as you scrub.
                    state.tracked_ticker =
                        state.available_ticker_labels[static_cast<std::size_t>(state.tracked_ticker_idx)];
                    state.camera_initialized = false;
                    upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
                }
                if (!state.tracked_ticker.empty()) {
                    ImGui::SameLine();
                    if (ImGui::Button("Clear")) {
                        state.tracked_ticker.clear();
                        state.tracked_ticker_idx = -1;
                        state.trajectory_mode = false;
                        upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
                    }
                    if (ImGui::Checkbox("Its path through time", &state.trajectory_mode)) {
                        state.camera_initialized = false;
                        upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
                    }
                    if (state.trajectory_mode) {
                        if (ImGui::SliderInt("days", &state.trajectory_lookback, 21, 1512)) {
                            state.camera_initialized = false;
                            upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
                        }
                        ImGui::TextDisabled("%s over %d days; red is this frame",
                                            state.tracked_ticker.c_str(), state.trajectory_lookback);
                        if (state.surfaces.view_b_lookback_days > 0 &&
                            state.trajectory_lookback !=
                                static_cast<int>(state.surfaces.view_b_lookback_days)) {
                            // Said plainly, because the symptom otherwise
                            // reads as a broken surface: a longer path than
                            // the tube was fitted to will leave it, and a
                            // shorter one will rattle around inside it.
                            ImGui::TextDisabled("tube was fitted to %lld days - path and",
                                                static_cast<long long>(
                                                    state.surfaces.view_b_lookback_days));
                            ImGui::TextDisabled("surface no longer cover the same window");
                        }
                        // The distinction that makes View B worth looking
                        // at: the tube is built from history BEFORE its own
                        // date, so the red point sitting outside it is the
                        // finding, not a glitch.
                        ImGui::TextDisabled("red outside the tube = today is unlike");
                        ImGui::TextDisabled("its own recent past");
                    }
                }
            }


            // Tab-specific controls
            if (state.selected_tab == 1) {
                ImGui::Separator();
                ImGui::Text("2D Pairs - Select Two Tickers");
                ImGui::Combo("Ticker 1", &state.selected_ticker1_idx,
                             state.available_ticker_labels.data(),
                             static_cast<int>(state.available_ticker_labels.size()));
                ImGui::Combo("Ticker 2", &state.selected_ticker2_idx,
                             state.available_ticker_labels.data(),
                             static_cast<int>(state.available_ticker_labels.size()));

                // Spread with bands (ADR §9): ticker1's full z-score
                // series across all dates gm-signals scored it for the
                // currently loaded run, plotted against the standard
                // +/-1, +/-2 sigma reference bands used everywhere else
                // in this codebase for excursion thresholds (ADR §6.5's
                // entry/exit z bands). Not filtered to the current
                // scrubber frame's date - spreads.parquet has one row
                // per (ticker, date), so a per-date filter here could
                // only ever produce zero or one point.
                if (state.selected_ticker1_idx >= 0 &&
                    static_cast<std::size_t>(state.selected_ticker1_idx) < state.available_ticker_labels.size() &&
                    state.has_loaded_run) {
                    const std::string t1 = state.available_ticker_labels[static_cast<std::size_t>(state.selected_ticker1_idx)];
                    auto spread_series = get_spread_series_for_ticker(state.loaded, t1);
                    if (!spread_series.empty()) {
                        std::vector<float> spread_z;
                        spread_z.reserve(spread_series.size());
                        for (const auto& [date, z] : spread_series) spread_z.push_back(static_cast<float>(z));
                        std::vector<float> upper1(spread_z.size(), 1.0f), lower1(spread_z.size(), -1.0f);
                        std::vector<float> upper2(spread_z.size(), 2.0f), lower2(spread_z.size(), -2.0f);
                        ImGui::Separator();
                        ImGui::Text("Spread (z) for %s (%zu dates, %s to %s)", t1.c_str(), spread_series.size(),
                                    spread_series.front().first.c_str(), spread_series.back().first.c_str());
                        if (ImPlot::BeginPlot("##spread_bands", ImVec2(-1, 150))) {
                            ImPlot::PlotLine("z", spread_z.data(), static_cast<int>(spread_z.size()));
                            ImPlot::PlotLine("+-1 sigma", upper1.data(), static_cast<int>(upper1.size()));
                            ImPlot::PlotLine("-1 sigma", lower1.data(), static_cast<int>(lower1.size()));
                            ImPlot::PlotLine("+-2 sigma", upper2.data(), static_cast<int>(upper2.size()));
                            ImPlot::PlotLine("-2 sigma", lower2.data(), static_cast<int>(lower2.size()));
                            ImPlot::EndPlot();
                        }
                    } else {
                        ImGui::TextDisabled("No spread data for %s.", t1.c_str());
                    }
                }
            } else if (state.selected_tab == 2) {
                ImGui::Separator();
                ImGui::Text("3D Sectors");
                if (ImGui::Checkbox("Color by Sector", &state.show_sectors)) {
                    upload_frame(renderer, mesh_renderer, highlight_renderer, state, state.current_frame);
                }
                ImGui::Text("Sectors in universe:");
                std::set<std::string> sectors_seen;
                std::map<std::string, int> sector_ticker_count;
                for (const auto& [ticker, meta] : state.loaded.ticker_metadata) {
                    sectors_seen.insert(meta.gics_sector);
                    sector_ticker_count[meta.gics_sector]++;
                }
                ImGui::Text("  %zu sectors, %zu tickers", sectors_seen.size(), state.loaded.ticker_metadata.size());
                for (const auto& sector : sectors_seen) {
                    ImGui::Text("  - %s (%d tickers)", sector.c_str(), sector_ticker_count[sector]);
                }
                ImGui::Separator();
                ImGui::Text("Sector Analysis (current frame):");
                if (state.has_loaded_run && !state.loaded.frames.empty()) {
                    const auto& frame = state.loaded.frames[static_cast<std::size_t>(state.current_frame)];
                    std::map<std::string, int> frame_sector_counts;
                    for (const auto& ticker : frame.tickers) {
                        auto meta_it = state.loaded.ticker_metadata.find(ticker);
                        if (meta_it != state.loaded.ticker_metadata.end()) {
                            frame_sector_counts[meta_it->second.gics_sector]++;
                        }
                    }
                    for (const auto& [sector, count] : frame_sector_counts) {
                        ImGui::Text("  %s: %d points", sector.c_str(), count);
                    }
                }
            } else if (state.selected_tab == 3) {
                ImGui::Separator();
                ImGui::Text("Structural change (Evolution)");
            }

            if (!state.loaded.structural_change.empty() && state.selected_tab == 3) {
                ImGui::Separator();
                if (ImPlot::BeginPlot("##regime", ImVec2(-1, 150))) {
                    ImPlot::PlotLine("structural_change", state.loaded.structural_change.data(),
                                     static_cast<int>(state.loaded.structural_change.size()));
                    ImPlot::EndPlot();
                }
            }

            // Learn panel - triggered by clicking 2D Pairs table or from manual selection
            if (state.show_learn_panel && !state.learn_panel_ticker.empty()) {
                ImGui::Separator();
                ImGui::Text("Learn Panel: %s", state.learn_panel_ticker.c_str());

                auto meta_it = state.loaded.ticker_metadata.find(state.learn_panel_ticker);
                if (meta_it != state.loaded.ticker_metadata.end()) {
                    ImGui::Text("Company: %s", meta_it->second.security_name.c_str());
                    ImGui::Text("Sector: %s", meta_it->second.gics_sector.c_str());
                }

                // SEC EDGAR profile (meta/profiles.json, ADR §8.2) - not
                // every run has this (older runs predate gm-profiles,
                // or a given ticker's fetch failed), so this degrades
                // gracefully to a plain status line rather than assuming
                // the entry exists.
                auto profile_it = state.loaded.profiles.find(state.learn_panel_ticker);
                if (profile_it != state.loaded.profiles.end()) {
                    const auto& profile = profile_it->second;
                    ImGui::Separator();
                    ImGui::Text("SEC Profile:");
                    if (!profile.company_name.empty()) {
                        ImGui::Text("  Entity: %s", profile.company_name.c_str());
                    }
                    if (!profile.sic_code.empty() || !profile.sic_description.empty()) {
                        ImGui::Text("  SIC: %s%s%s", profile.sic_code.c_str(),
                                    profile.sic_description.empty() ? "" : " - ",
                                    profile.sic_description.c_str());
                    }
                    if (!profile.edgar_url.empty()) {
                        ImGui::TextWrapped("  EDGAR: %s", profile.edgar_url.c_str());
                    }
                } else if (state.has_loaded_run) {
                    ImGui::Separator();
                    ImGui::TextDisabled("No SEC profile data for %s.", state.learn_panel_ticker.c_str());
                }

                if (state.has_loaded_run && !state.loaded.frames.empty()) {
                    const auto& frame = state.loaded.frames[static_cast<std::size_t>(state.current_frame)];

                    // The "Learn about <pair ticker>" jump buttons below
                    // refer back to whatever pair is currently selected
                    // on the 2D Pairs tab, so the panel for one ticker
                    // can jump straight to the panel for its comparison
                    // partner. Guarded against an empty/out-of-range
                    // selection (no run loaded yet, or an empty universe).
                    const std::string ticker1 =
                        (state.selected_ticker1_idx >= 0 &&
                         static_cast<std::size_t>(state.selected_ticker1_idx) < state.available_ticker_labels.size())
                            ? state.available_ticker_labels[static_cast<std::size_t>(state.selected_ticker1_idx)]
                            : "";
                    const std::string ticker2 =
                        (state.selected_ticker2_idx >= 0 &&
                         static_cast<std::size_t>(state.selected_ticker2_idx) < state.available_ticker_labels.size())
                            ? state.available_ticker_labels[static_cast<std::size_t>(state.selected_ticker2_idx)]
                            : "";

                    // Renders the two "Learn about <ticker>" jump buttons
                    // shared by every section below. `scope` gives each
                    // call site's button pair its own ImGui ID scope, so
                    // the six buttons across the three sections (which,
                    // with at most two distinct visible labels - or all
                    // six identical and empty when no 2D-Pairs pair is
                    // selected yet - previously collided onto the first
                    // button's ID) no longer alias each other. Each
                    // ticker's own button is also skipped entirely when
                    // that ticker string is empty, rather than rendering
                    // a "Learn about " button that, if clicked, would set
                    // learn_panel_ticker to "" and immediately close this
                    // panel via the !empty() guard above.
                    auto learn_jump_buttons = [&](const char* scope) {
                        ImGui::PushID(scope);
                        if (!ticker1.empty()) {
                            ImGui::PushID(0);
                            if (ImGui::Button(("Learn about " + ticker1).c_str(), ImVec2(-1, 0))) {
                                state.show_learn_panel = true;
                                state.learn_panel_ticker = ticker1;
                            }
                            ImGui::PopID();
                        }
                        if (!ticker2.empty()) {
                            ImGui::PushID(1);
                            if (ImGui::Button(("Learn about " + ticker2).c_str(), ImVec2(-1, 0))) {
                                state.show_learn_panel = true;
                                state.learn_panel_ticker = ticker2;
                            }
                            ImGui::PopID();
                        }
                        ImGui::PopID();
                    };

                    // Scores (Position & Depth in all views) - indexed
                    // lookup (built once in load_run) rather than a
                    // linear scan of all 1.82M+ real scores rows on
                    // every rendered frame (ADR-9's <1ms decode budget).
                    std::map<std::string, std::vector<std::pair<std::string, double>>> scores_by_view;
                    auto scores_it =
                        state.loaded.scores_by_ticker_date.find({state.learn_panel_ticker, frame.date});
                    if (scores_it != state.loaded.scores_by_ticker_date.end()) {
                        for (const auto& score : scores_it->second) {
                            scores_by_view[score.view].push_back({score.estimator, score.depth});
                        }
                    }

                    if (!scores_by_view.empty()) {
                        ImGui::Separator();
                        ImGui::Text("Position & Depth (View A/B/C):");
                        if (ImGui::BeginTable("scores_tbl", 3, ImGuiTableFlags_Borders)) {
                            ImGui::TableSetupColumn("View");
                            ImGui::TableSetupColumn("Estimator");
                            ImGui::TableSetupColumn("Depth");
                            ImGui::TableHeadersRow();
                            for (const auto& [view, depths] : scores_by_view) {
                                for (const auto& [est, depth] : depths) {
                                    ImGui::TableNextRow();
                                    ImGui::TableSetColumnIndex(0); ImGui::Text("%s", view.c_str());
                                    ImGui::TableSetColumnIndex(1); ImGui::Text("%s", est.c_str());
                                    ImGui::TableSetColumnIndex(2); ImGui::Text("%.4f", depth);
                                }
                            }
                            ImGui::EndTable();
                        }
                        learn_jump_buttons("scores_learn_buttons");
                    }

                    // Peer basket - indexed lookup rather than a linear
                    // scan of all 3.92M+ real basket rows every frame.
                    std::vector<std::pair<std::string, double>> basket;
                    auto basket_it =
                        state.loaded.baskets_by_ticker_date.find({state.learn_panel_ticker, frame.date});
                    if (basket_it != state.loaded.baskets_by_ticker_date.end()) {
                        for (const auto& b : basket_it->second) {
                            basket.push_back({b.neighbor_ticker, b.weight});
                        }
                    }
                    if (!basket.empty()) {
                        ImGui::Separator();
                        ImGui::Text("Peer Basket (Weights):");
                        if (ImGui::BeginTable("basket_tbl", 2, ImGuiTableFlags_Borders)) {
                            ImGui::TableSetupColumn("Ticker");
                            ImGui::TableSetupColumn("Weight");
                            ImGui::TableHeadersRow();
                            for (const auto& [ticker, weight] : basket) {
                                ImGui::TableNextRow();
                                ImGui::TableSetColumnIndex(0); ImGui::Text("%s", ticker.c_str());
                                ImGui::TableSetColumnIndex(1); ImGui::Text("%.4f", weight);
                            }
                            ImGui::EndTable();
                        }
                        learn_jump_buttons("basket_learn_buttons");
                    }

                    // Excursion history - indexed lookup, built once in load_run.
                    const auto& excursions = get_excursions_for_ticker(state.loaded, state.learn_panel_ticker);
                    if (!excursions.empty()) {
                        ImGui::Separator();
                        ImGui::Text("Excursion History (%zu total):", excursions.size());
                        if (ImGui::BeginTable("exc_hist", 5, ImGuiTableFlags_ScrollY | ImGuiTableFlags_Borders)) {
                            ImGui::TableSetupColumn("Start");
                            ImGui::TableSetupColumn("End");
                            ImGui::TableSetupColumn("Duration");
                            ImGui::TableSetupColumn("Peak Depth");
                            ImGui::TableSetupColumn("Reverted");
                            ImGui::TableHeadersRow();
                            for (const auto& exc : excursions) {
                                ImGui::TableNextRow();
                                ImGui::TableSetColumnIndex(0); ImGui::Text("%s", exc.start_date.c_str());
                                ImGui::TableSetColumnIndex(1); ImGui::Text("%s", exc.end_date.c_str());
                                ImGui::TableSetColumnIndex(2); ImGui::Text("%d", exc.duration_days);
                                ImGui::TableSetColumnIndex(3); ImGui::Text("%.4f", exc.peak_depth);
                                ImGui::TableSetColumnIndex(4); ImGui::Text("%s", exc.reverted ? "Yes" : "No");
                            }
                            ImGui::EndTable();
                        }
                        learn_jump_buttons("excursion_learn_buttons");
                    }
                }
            }
        }
        ImGui::End();

        int fb_width = 0, fb_height = 0;
        glfwGetFramebufferSize(window, &fb_width, &fb_height);
        glViewport(0, 0, fb_width, fb_height);
        glClearColor(0.08f, 0.08f, 0.10f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        glEnable(GL_DEPTH_TEST);

        if (fb_height > 0) {
            float aspect = static_cast<float>(fb_width) / static_cast<float>(fb_height);
            gm::view::Mat4 projection = gm::view::mat4_perspective(0.9f, aspect, 0.01f, 1000.0f);
            gm::view::Mat4 view = state.camera.view_matrix();
            gm::view::Mat4 mvp = gm::view::mat4_multiply(projection, view);
            // Surface first, points second: the points are the subject and
            // must win the depth test against the envelope around them.
            if (state.show_surface) {
                mesh_renderer.draw(mvp, 0.24f, 0.85f, 0.36f, 0.28f);
            }
            renderer.draw(mvp, state.trajectory_mode ? 5.0f : 8.0f);
            // Last and largest: the tracked equity must be findable
            // whatever it is sitting behind.
            highlight_renderer.draw(mvp, 22.0f);
        }

        ImGui::Render();
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
        glfwSwapBuffers(window);
    }

    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImPlot::DestroyContext();
    ImGui::DestroyContext();
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}
