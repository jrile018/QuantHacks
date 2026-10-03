# Data

The notebook and `run_all.py` download data directly from Massive and store raw API responses in the root `.massive_cache/` directory. A clean checkout has no study data. The command-line runner writes derived tables and a settings manifest to `data/processed/` by default.

If you export data while researching, put source records in `data/raw/` and derived tables in `data/processed/`. Both directories are ignored by Git because the data may be licensed. Keep download and reproduction instructions in the root `README.md` and notebook.

## Tiger Cloud copy

Run `python scripts/import_tiger.py --service-id YOUR_TIGER_SERVICE_ID` from the repository root after `tiger auth login`. It copies every `.massive_cache/*.json` response, each `data/processed/**/manifest.json`, and the CSVs beside those manifests into the `quant_hacks` schema. The source file bytes are retained in `quant_hacks.source_files`, while `quant_hacks.study_rows` makes individual CSV rows queryable. The import is repeatable and keeps local files intact.

For example, inspect the imported events with:

```bash
tiger db query YOUR_TIGER_SERVICE_ID --read-only --command "SELECT row_data->>'ticker' AS ticker, row_data->>'event_date' AS event_date FROM quant_hacks.study_rows WHERE table_name = 'events' LIMIT 10"
```

The initial import contains a **one-event smoke run**, not a complete study. Run a larger study locally and rerun the importer to add its files and rows.
