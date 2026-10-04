#pragma once

#include <gm-core/error.hpp>

#include <array>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace gm::view {

struct RunInfo {
    std::string run_id;
    std::filesystem::path run_dir;
};

[[nodiscard]] Result<std::vector<RunInfo>> list_available_runs(
    const std::filesystem::path& runs_base_dir);

struct Frame {
    std::string date;
    std::vector<std::string> tickers;
    /// The first three embedding dimensions, kept under their historical
    /// name so existing callers are undisturbed.
    std::vector<std::array<float, 3>> positions;
    /// Every embedding dimension gm-geometry wrote, laid out
    /// [ticker][dimension]. When the run is three-dimensional this
    /// duplicates `positions`; when it is not, this is the only place the
    /// rest of the embedding exists. Kept because a viewer that silently
    /// truncated a 10-D embedding to its first three axes would look
    /// exactly like a working one.
    std::vector<std::vector<float>> coords;
};

struct TickerMetadata {
    std::string ticker;
    std::string security_name;
    std::string gics_sector;
};

struct Score {
    std::string date;
    std::string ticker;
    std::string view;
    std::string estimator;
    double depth;
    double pvalue;
    bool inside;
};

struct Spread {
    std::string date;
    std::string ticker;
    double z;
    double spread;
    double half_life;
    int n_neighbors;
};

struct BasketWeight {
    std::string date;
    std::string ticker;
    std::string neighbor_ticker;
    double weight;
};

struct Excursion {
    std::string ticker;
    std::string start_date;
    std::string end_date;
    double peak_depth;
    bool reverted;
    int duration_days;
};

/// SEC EDGAR company profile for the Learn panel (ADR §8.2, meta/profiles.json).
/// Field names and types here are the canonical schema and MUST match what
/// apps/gm-profiles/main.cpp writes exactly - see the comment there. There is
/// no separate "description"/"sic_industry"/"economic_links" - gm-profiles
/// does not fetch or produce that data, so this struct only carries what the
/// writer actually produces: ticker, company_name, sic_code (string - SIC
/// codes are conventionally treated as codes, not numbers), sic_description,
/// edgar_url.
struct TickerProfile {
    std::string ticker;
    std::string company_name;
    std::string sic_code;
    std::string sic_description;
    std::string edgar_url;
};

struct LoadedRun {
    std::vector<Frame> frames;
    std::vector<std::string> regime_dates;
    std::vector<double> structural_change;
    std::map<std::string, TickerMetadata> ticker_metadata;
    std::vector<Score> scores;
    std::vector<Spread> spreads;
    std::vector<BasketWeight> baskets;
    std::vector<Excursion> excursions;
    std::map<std::string, TickerProfile> profiles;

    // Built once here (not on every rendered frame - ADR-9's <1ms decode
    // budget) so the viewer's Learn panel can look a ticker/date up in
    // O(log n) instead of linear-scanning the full scores/baskets vectors
    // (1.82M / 3.92M rows on the real M6 run) on every single frame.
    std::map<std::pair<std::string, std::string>, std::vector<Score>> scores_by_ticker_date;
    std::map<std::pair<std::string, std::string>, std::vector<BasketWeight>> baskets_by_ticker_date;
    std::map<std::string, std::vector<Excursion>> excursions_by_ticker;
};

[[nodiscard]] Result<LoadedRun> load_run(const std::filesystem::path& run_dir);

/// What boundary surfaces a run actually exported.
///
/// Built once per run rather than probed per frame, because View B's
/// question is not "does this exact file exist" but "what is the newest
/// surface for this ticker at or before this date" - gm-boundaries
/// exports View B on a stride, so most dates have no mesh of their own
/// and the answer is almost always some earlier date's.
struct SurfaceIndex {
    /// False for a run made without boundaries.write_meshes, which has no
    /// surfaces/ directory at all. Distinguished from "directory exists
    /// but holds nothing for this view", which is a different message to
    /// the user.
    bool directory_exists = false;

    /// Dates with a View A surface - the market's envelope that day.
    std::set<std::string> view_a_dates;

    /// ticker -> the dates that ticker has a View B surface for, ascending.
    /// ISO dates sort lexicographically, so this is directly binary-searchable.
    std::map<std::string, std::vector<std::string>> view_b_dates;

    /// boundaries.view_b_lookback_days as recorded in the stage manifest,
    /// or 0 when it could not be read. The viewer needs it because the
    /// tube encloses exactly that many prior days: drawing a trajectory of
    /// some other length inside it would show a path leaving a surface it
    /// was never fitted to, which reads as a rendering fault rather than
    /// as the two different numbers it actually is.
    std::int64_t view_b_lookback_days = 0;

    /// The newest date at or before `date` that has a View B surface for
    /// `ticker`, or nullopt. Never returns a LATER date: the tube is
    /// fitted to history prior to its own date, so showing a future one
    /// against today's points would put information on screen that was
    /// not available then - the exact look-ahead ADR-011 forbids in the
    /// scores, and no more acceptable in a picture.
    [[nodiscard]] std::optional<std::string> view_b_surface_for(const std::string& ticker,
                                                                 const std::string& date) const;
};

/// Scans `run_dir`/gm-boundaries/surfaces. A missing directory is not an
/// error - it is the normal state of a run made without meshes.
[[nodiscard]] SurfaceIndex index_surfaces(const std::filesystem::path& run_dir);

} // namespace gm::view
