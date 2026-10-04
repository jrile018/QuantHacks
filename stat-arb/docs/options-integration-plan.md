# QuantHaxs options bridge (completed first slice)

This describes the completed CSV bridge. It does not make options a native
Lattice data type or stage. The [native integration plan](superpowers/plans/2026-10-03-native-options-integration.md)
covers that work.

## Goal

Make QuantHaxs 8-K option-study rows usable beside Lattice's causal equity scores without changing Lattice's equity geometry or claiming that its scores predict option returns.

## First slice

1. Read a manifested QuantHaxs study directory (`events.csv`, `results.csv`, `capacity.csv`, `manifest.json`). Validate its event keys and dates.
2. Write an immutable `gm-options` artifact with event IDs, option outcomes, capacity rows, and source hashes. Keep licensed raw Massive responses in QuantHaxs.
3. Optionally join `gm-boundaries/scores.parquet` (or a CSV export) by exact ticker and `t_pre` date, View B only. Keep each estimator distinct; a missing score stays missing. Never forward-fill from after the event.
4. Test duplicate keys, mismatched events, and an intentionally future-dated score. Run the importer on the existing one-event smoke study.

## Interface and limits

The bridge is a Python tool under `tools/`; it does not enter the C++ stage chain yet. It writes CSV and JSON so the schema and provenance are inspectable without a Lattice build. Reading Parquet scores requires `pyarrow`; CSV scores work with the standard library. A future options geometry stage needs synchronized historical chain quotes, contract identities, and an explicit expiry/roll model. The current QuantHaxs close-and-volume bars are insufficient for that stage.
