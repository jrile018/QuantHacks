# Data

The notebook and `run_all.py` download data directly from Massive and store raw API responses in the root `.massive_cache/` directory. A clean checkout has no study data. The command-line runner writes derived tables and a settings manifest to `data/processed/` by default.

If you export data while researching, put source records in `data/raw/` and derived tables in `data/processed/`. Both directories are ignored by Git because the data may be licensed. Keep download and reproduction instructions in the root `README.md` and notebook.
