# Historical option quotes

Actual check on 2026-10-03: the repository's existing Massive credential returned HTTP 200 and historical bid/ask records for a cached AAPL option. This confirms endpoint access for that request. It does not establish coverage for the entire company/date universe.

The existing cache audit found contract metadata and daily OHLC bars but no historical bid/ask series. Use the bounded collector to acquire source records independently of their eventual returns.

Create an explicit JSONL request manifest:

```json
{"ticker":"O:AAPL240920C00250000","start_utc":"2024-08-13T13:30:00Z","end_utc":"2024-08-13T13:31:00Z","max_records":1000}
```

Then preview and collect:

```powershell
.venv\Scripts\python.exe scripts/collect_options_training_quotes.py --manifest requests.jsonl --output data/processed/quote_collection.json
.venv\Scripts\python.exe scripts/collect_options_training_quotes.py --manifest requests.jsonl --output data/processed/quote_collection.json --fetch
```

Each request is limited to one day, at most 50,000 records and a bounded number of pages. A manifest has at most 50 requests; large runs belong on remote compute. Pagination remains at the same provider and ticker. Access blocks stop collection; page/record caps are reported as truncation. Raw responses and their actual retrieval times are retained by hash. API credentials stay in the existing private environment and Authorization header.

The normalized output retains the exact SIP timestamp in nanoseconds. `receipt_at_utc` remains null: downloading a historical quote today does not prove the trading system received it back then. A retrospective latency assumption must be explicit and separately assessed; do not overwrite today's retrieval time with a historical event timestamp.

To construct learning rows, join quote records to independently dated issuer/contract/deliverable mappings and the actual options session calendar. Choose contracts before observing returns, build bounded as-of snapshots using the original tick times, and require decision, first executable entry and next-session-close coverage for the same contracts. See `docs/options-model-training.md`. These raw records alone are not eligible training labels.

Provider contract: [Massive historical options quotes](https://www.massive.com/docs/rest/options/trades-quotes/quotes).
