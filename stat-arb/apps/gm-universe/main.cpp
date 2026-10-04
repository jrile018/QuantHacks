// gm-universe: point-in-time S&P 500 universe construction (ADR-001,
// ADR 7.1). For every trading day in [start_date, end_date], emits one
// row per ticker that was a member on that day.
//
// Two sources, and the manifest always says which was used:
//
//   current_snapshot     - the constituent table as it stands today,
//                          with each member's own join date. Correct
//                          about arrivals, blind to departures: a name
//                          removed from the index before today is not
//                          in the file at all, so it is missing from
//                          every historical day it belonged to. That is
//                          survivorship bias, and it flatters results,
//                          because the names that leave are
//                          disproportionately the ones that did badly.
//
//   membership_history   - dated observations reconstructed from the
//                          article's revision history
//                          (tools/sp500_membership_history.py), which
//                          DO contain the departed names.
//
// The second is the one to use. The first is kept because it is the
// only source of security name, sector and CIK, and because a run that
// predates the history file should still reproduce.
//
// Where the two disagree, this stage does not paper over it. A
// point-in-time member that the current snapshot has never heard of
// gets its row with metadata_available = false and empty metadata, and
// the manifest counts exactly how many such rows and tickers there
// were. A downstream stage that needs a CIK can then refuse loudly
// instead of quietly treating an unknown name as a known one.

#include <gm-core/calendar.hpp>
#include <gm-core/stage_main.hpp>
#include <gm-core/instrument.hpp>
#include <gm-data/membership.hpp>
#include <gm-data/universe.hpp>
#include <gm-io/parquet.hpp>
#include <gm-io/table.hpp>

#include <spdlog/spdlog.h>

#include <set>

namespace {

gm::VoidResult run_gm_universe(const gm::Config& config, const std::filesystem::path& output_dir,
                                gm::Manifest& manifest) {
    auto snapshot_path_str = config.get_string("universe.snapshot_csv");
    if (!snapshot_path_str) return tl::unexpected(snapshot_path_str.error());

    // Absent means "use the current snapshot" - the behaviour every run
    // before the history file existed had, so those runs still
    // reproduce.
    const std::string membership_csv = config.get_string_or("universe.membership_csv", "");

    auto start_str = config.get_string("universe.start_date");
    if (!start_str) return tl::unexpected(start_str.error());
    auto end_str = config.get_string("universe.end_date");
    if (!end_str) return tl::unexpected(end_str.error());

    auto start_date = gm::Date::parse_iso(*start_str);
    if (!start_date) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "universe.start_date is not a valid ISO date",
                                               *start_str));
    }
    auto end_date = gm::Date::parse_iso(*end_str);
    if (!end_date) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "universe.end_date is not a valid ISO date",
                                               *end_str));
    }
    if (*end_date < *start_date) {
        return tl::unexpected(gm::Error::make(gm::ErrorCode::kInvalidArgument,
                                               "universe.end_date is before universe.start_date"));
    }

    auto universe = gm::data::Universe::load_sp500_snapshot(*snapshot_path_str);
    if (!universe) return tl::unexpected(universe.error());

    std::optional<gm::data::MembershipHistory> history;
    if (!membership_csv.empty()) {
        auto loaded = gm::data::MembershipHistory::load(membership_csv);
        if (!loaded) return tl::unexpected(loaded.error());
        history = std::move(*loaded);

        // Before the first observation the history knows nothing, and
        // members_as_of() correctly says so by returning nothing. Those
        // days would land in the artifact as trading days with an empty
        // index, which is not a gap any downstream stage can tell apart
        // from a real answer - so refuse here, where the cause is still
        // legible.
        const auto& first = history->observation_dates().front();
        if (*start_date < first) {
            return tl::unexpected(gm::Error::make(
                gm::ErrorCode::kInvalidArgument,
                "universe.start_date precedes the first membership observation, which would "
                "emit trading days with an empty index",
                *start_str + " < " + first.to_iso()));
        }
    }

    gm::NyseCalendar calendar;
    auto trading_days = calendar.trading_days_in_range(*start_date, *end_date);

    std::vector<std::string> dates;
    std::vector<std::string> tickers;
    std::vector<std::string> security_names;
    std::vector<std::string> gics_sectors;
    std::vector<std::int64_t> ciks;
    std::vector<std::uint8_t> metadata_available;
    // ADR-023. A ticker is a display label that issuers change and
    // exchanges reassign; the CIK behind it is permanent. Emitting the
    // permanent key alongside the ticker is what lets a consumer join
    // BK's history to BNY's without also welding two unrelated issuers
    // together when a symbol is reused.
    std::vector<std::string> instrument_ids;

    gm::InstrumentRegistry registry;

    std::int64_t rows_without_metadata = 0;
    std::set<std::string> tickers_without_metadata;

    for (const auto& day : trading_days) {
        auto members = history ? history->members_as_of(day) : universe->members_as_of(day);
        for (const auto& ticker : members) {
            auto rec = universe->find(ticker);

            dates.push_back(day.to_iso());
            tickers.push_back(ticker.value());

            // A name with no metadata row gets a namespaced stand-in
            // rather than a fabricated key, so a consumer can always
            // tell a real identity from a placeholder. Those names are
            // disproportionately the old departures - exactly where a
            // rename would hide - so the count matters and is reported.
            const std::optional<std::int64_t> row_cik =
                rec ? std::optional<std::int64_t>(static_cast<std::int64_t>((*rec)->cik.value()))
                    : std::nullopt;
            auto instrument = gm::InstrumentId::resolve(row_cik, ticker.value());
            if (!instrument) return tl::unexpected(instrument.error());
            instrument_ids.push_back(instrument->value());
            if (auto r = registry.observe(ticker.value(), row_cik); !r) {
                return tl::unexpected(r.error());
            }

            if (rec) {
                security_names.push_back((*rec)->security_name);
                gics_sectors.push_back((*rec)->gics_sector);
                ciks.push_back(static_cast<std::int64_t>((*rec)->cik.value()));
                metadata_available.push_back(1);
            } else {
                // A name the index once held and the current table no
                // longer lists. Emitting empty fields with the flag
                // beside them keeps the row - the membership fact is
                // the point - while making the missing metadata
                // impossible to mistake for a real value.
                security_names.emplace_back();
                gics_sectors.emplace_back();
                ciks.push_back(0);
                metadata_available.push_back(0);
                ++rows_without_metadata;
                tickers_without_metadata.insert(ticker.value());
            }
        }
    }

    gm::io::Table table;
    if (auto r = table.add_string_column("date", std::move(dates)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_string_column("ticker", std::move(tickers)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_string_column("security_name", std::move(security_names)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_string_column("gics_sector", std::move(gics_sectors)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_int64_column("cik", std::move(ciks)); !r) return tl::unexpected(r.error());
    if (auto r = table.add_bool_column("metadata_available", std::move(metadata_available)); !r)
        return tl::unexpected(r.error());
    if (auto r = table.add_string_column("instrument_id", std::move(instrument_ids)); !r)
        return tl::unexpected(r.error());

    auto write_result = gm::io::write_parquet(table, output_dir / "universe.parquet");
    if (!write_result) return tl::unexpected(write_result.error());

    manifest.set_int("rows_written", static_cast<std::int64_t>(table.num_rows()));
    manifest.set_int("trading_days", static_cast<std::int64_t>(trading_days.size()));
    manifest.set_int("snapshot_size", static_cast<std::int64_t>(universe->size()));
    manifest.set_string("start_date", *start_str);
    manifest.set_string("end_date", *end_str);
    manifest.set_string("membership_source", history ? "membership_history" : "current_snapshot");
    // The two pathologies a ticker-keyed panel suffers, counted rather
    // than assumed. An alias is one instrument wearing two tickers - a
    // departure the survivorship correction would otherwise have
    // counted, and a price history it would have cut in two. A reused
    // ticker is the opposite and the more dangerous: two issuers sharing
    // a string, which a naive join welds into one series with a
    // discontinuity no data screen would flag.
    const auto aliases = registry.aliases();
    const auto reused = registry.reused_tickers();
    manifest.set_int("instruments", static_cast<std::int64_t>(registry.num_instruments()));
    manifest.set_int("instrument_tickers_observed", static_cast<std::int64_t>(registry.num_tickers()));
    manifest.set_int("instruments_provisional",
                      static_cast<std::int64_t>(registry.num_provisional()));
    manifest.set_int("ticker_aliases", static_cast<std::int64_t>(aliases.size()));
    manifest.set_int("reused_tickers", static_cast<std::int64_t>(reused.size()));
    {
        std::string alias_summary;
        for (const auto& a : aliases) {
            if (!alias_summary.empty()) alias_summary += "; ";
            alias_summary += a.id.value() + "=";
            for (std::size_t i = 0; i < a.tickers.size(); ++i) {
                if (i > 0) alias_summary += "/";
                alias_summary += a.tickers[i];
            }
        }
        manifest.set_string("ticker_alias_detail",
                             alias_summary.empty() ? std::string{"none"} : alias_summary);
    }
    manifest.set_int("rows_without_metadata", rows_without_metadata);
    manifest.set_int("tickers_without_metadata",
                      static_cast<std::int64_t>(tickers_without_metadata.size()));

    if (history) {
        manifest.set_string("membership_csv", membership_csv);
        manifest.set_int("membership_observations",
                          static_cast<std::int64_t>(history->num_observations()));
        manifest.set_string("membership_first_observation",
                            history->observation_dates().front().to_iso());
        manifest.set_string("membership_last_observation",
                            history->observation_dates().back().to_iso());
        manifest.set_int("tickers_ever_member",
                          static_cast<std::int64_t>(history->all_tickers().size()));
        // The survivorship gap itself: names the index held at some
        // point and the current table cannot see.
        manifest.set_int("tickers_departed",
                          static_cast<std::int64_t>(history->departed_tickers().size()));
        spdlog::info(
            "gm-universe: point-in-time membership from {} observations ({} .. {}); {} tickers "
            "ever a member, {} of them gone from the current table",
            history->num_observations(), history->observation_dates().front().to_iso(),
            history->observation_dates().back().to_iso(), history->all_tickers().size(),
            history->departed_tickers().size());
    } else {
        // Not a warning by default - the snapshot path is a deliberate
        // choice, and a stage that cries wolf on every run stops being
        // read. But the artifact must never look point-in-time when it
        // is not.
        spdlog::info(
            "gm-universe: using the current-constituent snapshot; names removed from the index "
            "before today are absent from every historical day they belonged to (set "
            "universe.membership_csv to correct this)");
    }
    return {};
}

} // namespace

int main(int argc, char** argv) { return gm::run_stage_main(argc, argv, "gm-universe", run_gm_universe); }
