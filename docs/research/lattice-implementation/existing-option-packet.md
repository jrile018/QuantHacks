# Existing option quote packet — no new acquisition

Bounded remote inspection: 82,843 daily option quote marks / 712 selected contracts. No fit, new order or bulk local retrieval.

## Exact paths and hash meanings

Root: `/home/john-riley/QuantHacks/multi-market-20261003/`.

| Artifact under root | SHA256 | Meaning |
|---|---|---|
| `full-options/results/gm-options-ingest/quotes.parquet` | `b599bab7566071a136edd5f67997441295abadf94a2ccb883be1b531cff5c648` | Derived selected daily quote marks |
| `full-options/results/gm-options-ingest/contracts.parquet` | `7af91cb5022d186b570715accfeb9864610a51e519426870ad7af77aeeec59f0` | Selected contract assignments; multiplier inherited |
| `full-options/data/raw/databento/OPRA-20261003-4APD3MDYPJ/opra-pillar-20240101-20240131.cbbo-1m.csv.zst` | `a4fe2c3504c9a4908f5f5e364e45e1fc3655e30e40977d9f4ef6902012198a58` | **Raw compressed data bytes**, independently hashed; not a JSON manifest hash |
| `full-options/data/raw/databento/OPRA-20261003-4APD3MDYPJ/manifest.json` | `d1a60109c6bfdc9528075f6ef25915d1308ec31c615cc33ec0371e285cee9e72` | Exact JSON file bytes |
| `full-options/data/raw/databento/OPRA-20261003-4APD3MDYPJ/download_manifest.json` | `e5233e0485f59a958432dbc704a23d85551c5263fe667a0a6a572fb1c54dd750` | Exact JSON file bytes |
| `full-options/data/raw/databento/OPRA-20261003-4APD3MDYPJ/metadata.json` | `b9b41899e2675859a29ecd7706c7c72a001468166a7dfcee4c9bbaf48be6f168` | Exact JSON file bytes |

The initial handoff called the raw-file digest a 'source manifest SHA', ambiguously. The consumer stopped that inspection. This table corrects the names; the raw bytes and all three metadata files were separately hashed. No model result changed.

## Actual bounded sample

Selected GD call `O:GD240202C00260000`, strike $260, expiry 2024-02-02; selected 2024-01-04. All three received minute marks are 21:00 UTC / 16:00 ET.

| Session | Bid | Ask | Bid size | Ask size |
|---|---:|---:|---:|---:|
| 2024-01-03 | 3.20 | 4.90 | 2 | 23 |
| 2024-01-04 | 2.75 | 3.60 | 10 | 9 |
| 2024-01-05 | 2.15 | 2.55 | 23 | 8 |

`scripts/build_databento_daily_quotes.py` selects the latest valid received CBBO-1m record in 09:30–16:00 ET. Derived marks retain mark time and source job, not authoritative exchange event time or tick update sequence. `stat-arb/tools/options_native.py` inherits/requires 100 shares per contract; this packet does not verify the deliverable/multiplier historically.

Open gates: authoritative definitions/adjustments; historical availability/update freshness; exercise/assignment/settlement; executable order/fill/fee/depth; option-specific event/return protocol. These are option event marks, not the equity study's daily stock labels.

Futures alternative `results/futures-v1/causal_features_and_labels.csv` uses 09:30 decisions, 09:36 entry and next-session 09:36 exit, so it does not align with equity close-to-next-close hedge outcomes. Point-risk normalization must remain distinct from dollar P&L and unverified contract multipliers.

Post Benchmark owns the consumer/economic capsule. This packet establishes existing artifact availability and explicit limitations only.
