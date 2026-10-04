# Source-owned market evidence handoff

`src.lattice_completion.market_evidence.build_market_evidence_packet(observations, asset_evidence=None, protocol_evidence=None)` is a pure, bounded transformation of already normalized records. It performs no fetch, scan, replay, order, or accounting. The consumer owner is **Post Benchmark**. This package reports availability and source qualification; `consumer_economic_acceptance` is always `false`.

## Input rows and output

Pass a list of observation mappings. Each row needs `asset_class` (`equity`, `futures`, `option`), `source`, `raw_job_id`, `raw_file_sha256` (the hash of exact raw file bytes), `observation_date`, `instrument_id`, `raw_symbol`, `ts_event_at_utc`, `received_at_utc`, `available_at_utc`, `snapshot_at_utc`, `evidence_kind` (`update` or `snapshot`), `bid`, `ask`, `bid_size`, `ask_size`, `currency`, and `raw_price=true`. `quote_update_at_utc` is needed for canonical update qualification. `decision_at_utc` is optional; when present, availability after that clock is rejected. `ts_last_trade_at_utc` is optional and is preserved only as last-trade evidence. Timestamps require an explicit timezone.

The returned `lattice-market-evidence-v1` object contains:

| Key | Meaning |
|---|---|
| `observations` | All mapping rows retained for diagnostics, including sampled snapshots and rejected prices. Nonfinite JSON numbers become null. |
| `canonical_quotes` | Quote-shaped rows with `quote_id`, `instrument_id`, `at_utc`, `available_at_utc`, raw bid/ask and sizes, `currency`, `raw_price`, `evidence_kind=update`, plus all source IDs and distinct clocks. Only explicit valid updates appear. |
| `rejected` | Source row index, instrument, and all qualification reason codes. A sampled BBO is rejected *for canonical updates* while remaining an observation. |
| `qualification` | For each asset, separate `forecast_context`, `executable_quotes`, and `account_returns` `{status, reasons}` gates. |
| `consumer_economic_acceptance` | Always false. The source side cannot approve an economic result. |

No event or last-trade clock is substituted for `quote_update_at_utc`. A minute sampled BBO can establish partial observed context, but unknown update freshness remains unknown. Quotes with crossed or nonfinite prices, nonpositive sizes, missing source/identity, invalid clocks, or availability after the explicit decision clock do not enter `canonical_quotes`. Equity and option prices must be positive; finite ordered futures prices can be zero or negative. A source-qualified quote still carries `consumer_fill_freshness_protocol_pending` because the consumer must freeze its own depth, latency and fill assumptions.

## Per-asset evidence gates

`asset_evidence` is keyed by asset class. A metadata object satisfies a dated gate only with `qualified=true` and an explicit `available_at_utc`; an absent field, `false`, zero, or a presumed standard never satisfies one. Source-complete status is a request for consumer review, not acceptance.

| Asset | Account-return evidence required beyond quote updates |
|---|---|
| Equity | Explicit `side=long`, `short`, or `both`; `dated_identity`, `corporate_actions`, `costs`; for `short` or `both`, `borrow`. |
| Futures | `actual_contract_id` matching the quoted instrument, positive `definition_multiplier` backed by `contract_definition`, and a separate positive financial `dollar_per_point` with `dollar_per_point_basis=financial` and dated, qualified, source-named `dollar_per_point_definition`; `entry_contract_id` and `exit_contract_id`; if different, `explicit_roll_legs`; `sessions_match=true` backed by `sessions`; `margin`, `settlements`, `costs`. A contract multiplier is not assumed to be dollars per price point. |
| Option | `authoritative_deliverable`, positive `multiplier` with `multiplier_basis=authoritative` and `multiplier_definition`, `lifecycle`, matching `underlying_id` and `underlying_clocks_match=true` backed by `underlying_clocks`, `costs`. An assumed 100 multiplier does not qualify. |

All assets also need dated `protocol_evidence.frozen_protocol` and `protocol_evidence.account_basis`. These are source-side presence gates only; Post Benchmark determines semantic acceptance of definitions, sessions, lifecycle, size, costs, account denominators, and the frozen event/return protocol. No economic sizing rule is supplied here.

## Current evidence and open gates

The existing [option packet](../lattice-implementation/existing-option-packet.md) reports 82,843 derived daily OPRA marks across 712 selected contracts, with raw CBBO-1m bytes separately hashed. Its sampled marks have no authoritative quote-update sequence; inherited 100 share deliverables are unverified. The broader inventory reports raw OPRA CBBO-1m near 32 million records, GLBX definitions/BBO-1m/daily statistics/rank-1, and EQUS SPY/QQQ quotes/daily bars. These facts are availability observations, not accepted features or account returns. This contract does not change prior v1 packets or budget records. A first costed pilot remains gated on source qualification and Post Benchmark's economic protocol.
