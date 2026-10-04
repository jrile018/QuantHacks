# Multi-market Databento pilot: bounded scope and metadata quotes

**Checked:** 2026-10-03 (UTC)  
**Purpose:** estimate a daily-to-next-session Lattice market-context pilot. Metadata queries only; no time-series data or batch jobs were submitted.

## Recommendation

Start with **ES and MES as context features**, with SPY as the equity-market counterpart. Keep the first model test forecast-only. Then add futures hedge/direct-signal analysis, and test ZN, CL, and GC as separate extensions. Do not add another OPRA request: the current acquisition ledger already records the selected 654 contracts and a pending `OPRA.PILLAR` `cbbo-1m` batch.

For the 2024–2025 window, use `GLBX.MDP3` continuous volume-ranked symbols `ES.v.0` and `MES.v.0` with `statistics`, `definition`, and optionally `ohlcv-1d`; pair these with SPY/QQQ daily bars from `EQUS.MINI`. The `.v.0` mapping selects the prior-day highest-volume contract, reducing look-ahead risk. Persist resolved raw symbols and daily instrument IDs because the contract changes across rolls. These continuous prices are unadjusted at roll boundaries. [Databento continuous symbology](https://databento.com/docs/standards-and-conventions/symbology)

Use CME `statistics` as daily session context: it carries official settlement, cleared volume, and open interest, with `ts_ref` identifying the trading date. Select only the revision already published by the decision cutoff. A later final value cannot replace the earlier preliminary value in historical features; CME OI/cleared volume often arrive on the next UTC date. The first executed mark diagnostic uses sampled quotes rather than claiming settlement execution. `ohlcv-1d` is UTC-date aggregated. If session-aligned OHLC is needed, aggregate finer bars by the CME product trading session; do not label UTC bars as exchange-session bars. [GLBX.MDP3 statistics notes](https://databento.com/docs/venues-and-datasets/glbx-mdp3), [OHLCV date convention](https://databento.com/docs/knowledge-base)

## Exact bounded requests and quote results

All multi-day quotes below use `start=2024-01-01`, `end=2026-01-01` (end exclusive), `stype_in=continuous` for GLBX, and `raw_symbol` for equities. The endpoint was Databento’s read-only `metadata.get_cost`; values are quotes, not charges.

| Stage | Dataset / symbols / schema | Quoted USD | Use |
|---|---|---:|---|
| Forecast first | `GLBX.MDP3`, `ES.v.0,MES.v.0`, `statistics` | 0.046788 | Official futures session statistics |
| Forecast first | same, `definition` | 0.001041 | Contract mapping/attributes |
| Forecast first | same, `ohlcv-1d` | 0.012387 | Optional UTC-date bar comparison |
| Forecast first | `EQUS.MINI`, `SPY,QQQ`, `ohlcv-1d` | 0.001571 | Same-window equity prices; component-feed aggregate |
| Forecast first, official benchmark | `EQUS.SUMMARY`, `SPY,QQQ`, `ohlcv-1d`, 2024-07-01–2026-01-01 | 0.001183 | Consolidated daily benchmark on overlapping dates |
| Forecast first, sample only | GLBX `ESH4,MESH4` plus EQUS.MINI `SPY`, `bbo-1m`, 2024-01-02 14:35–14:36 UTC | 0.000070 total | Common 09:35 ET one-minute sample |
| Session feature extension | `GLBX.MDP3`, `ES.v.0,MES.v.0`, `bbo-1m`, full 2024–25 range | 1.910761 | All-session minute BBO, if daily forecast results justify it |
| Session feature extension | `EQUS.MINI`, `SPY`, `bbo-1m`, full 2024–25 range | 0.102441 | Equity counterpart quote series |
| Later risk/direct-signal stage | `GLBX.MDP3`, `ZN.v.0,CL.v.0,GC.v.0`, `statistics` | 0.044305 | Rates/commodity daily context |
| Later risk/direct-signal stage | same, `definition` | 0.001562 | Contract mapping/attributes |
| Later risk/direct-signal stage | same, `ohlcv-1d` | 0.018580 | Optional UTC-date comparison |
| Later session extension | same, `bbo-1m`, full 2024–25 range | 2.865710 | Minute BBO if the daily extension warrants it |

The recommended first-stage daily scope plus the 09:35 sample and official overlap benchmark quotes to about **$0.06304**. Adding full-range 2024–25 ES/MES and SPY `bbo-1m` raises that to about **$2.07624**. Adding daily ZN/CL/GC raises the daily-only scope by about **$0.06445**; adding their full-range minute BBO adds **$2.86571**. The combined quoted market-data scope is about **$5.00640**, including the optional schemas and samples above. Quotes are based on the API responses captured in [the metadata evidence JSON](../../data/processed/multi_market/metadata/databento_metadata_quotes_2026-10-03.json); actual billing is based on bytes delivered.

### Common 09:35 ET sample

On 2024-01-02, query `GLBX.MDP3` `bbo-1m` with raw symbols `ESH4`, `MESH4`, `ZNH4`, `CLG4`, `GCG4` over `2024-01-02T14:35:00Z`–`14:36:00Z`; query `EQUS.MINI` `SPY` over the same interval. This is the 09:35–09:36 ET bar in January. Databento’s free symbology resolution returned IDs `ESH4=17077`, `MESH4=763`, `ZNH4=110030`, `CLG4=686071`, `GCG4=41512`, and `SPY=15144` for that date. The combined one-minute quote estimate is $0.000070. `BBO-1m` is a minute-interval last-BBO sample, not a synchronized tick snapshot; intervals without qualifying updates/trades can be absent. [BBO schema conventions](https://databento.com/docs/schemas-and-data-formats/bbo)

## Coverage and constraints verified from live metadata

- `GLBX.MDP3` exposes `statistics`, `definition`, `bbo-1m`, `cbbo-1m`, and `ohlcv-1d`. Metadata reported these schemas beginning 2010-06-06; `cbbo-1m` begins 2017-05-21. CME’s `CBBO` is its merged real-plus-implied book interval view, not a cross-exchange NBBO. For ordinary per-contract BBO use `bbo-1m`; use `mbp-1` when every top-of-book update is required. [GLBX schema notes](https://databento.com/docs/venues-and-datasets/glbx-mdp3)
- `EQUS.MINI` supports `ohlcv-1d` and `bbo-1m`; both begin 2023-03-28. Its BBO is a composite from a selected blend of direct proprietary feeds, not the official SIP. `EQUS.SUMMARY` provides consolidated daily OHLCV, statistics and definitions, but its current metadata range begins **2024-07-01**. Therefore it cannot provide a consistent 2024-01-to-2025-12 counterpart for the full project window. Use `EQUS.MINI` for a consistent daily price feature across the pilot, and use `EQUS.SUMMARY` as an overlapping consolidated benchmark beginning July 2024. [EQUS.MINI product notes](https://databento.com/docs/venues-and-datasets/equs-mini), [EQUS.SUMMARY schemas](https://databento.com/docs/venues-and-datasets/equs-summary)
- The pilot’s 2024–2025 date span provides a temporal split within the project’s current in-sample window. The configured 2026 out-of-sample window should be added only after checking that the event outcome/option panel supports those same dates; the pending selected-contract OPRA history currently ends 2026-04-17 according to the acquisition ledger.
- Before direct trading/hedging evaluation, request exact outright-contract quote and execution fields around the chosen entry/exit times. A continuous front contract is a context series, not proof of tradable fills. Add later contract-month or spread coverage only if the strategy requires it.

## Existing cost and duplicate check

The inspected ledger snapshot showed a $250 ceiling and $23.13917 in actual-plus-quoted spend. It recorded the `OPRA.PILLAR` 654-selected-contract `cbbo-1m` request as `processing`, quoted at $4.7966, and the matching `ohlcv-1d` history as complete at $11.74521. No new OPRA quote was requested. The ledger snapshot can change as the pending job finalizes; re-read it before any future acquisition. No data purchase or batch submission occurred during this research.

## Reproducibility

Sanitized date ranges, schemas, symbol lists, metadata results, dataset range results, quote responses and sample-date symbology IDs are stored in [databento_metadata_quotes_2026-10-03.json](../../data/processed/multi_market/metadata/databento_metadata_quotes_2026-10-03.json). The API key was read only into memory for authenticated metadata calls and was not written to the evidence file or printed. One exploratory local call failed at the network boundary; the authorized read-only calls succeeded after sandbox escalation. No time-series data was downloaded.
