# REIT discovery and historical inventory build

The two new modules are pure builders. They do not make network requests, buy data, or publish datasets. The root acquisition broker supplies immutable metadata and source evidence. The observed current Nareit HTML imports **126 unverified candidates**, and the observed SEC exchange JSON imports **10,434 mapping rows**. This lane has verified **zero real securities as eligible**; synthetic fixtures exercise eligibility rules. The existing 53 CIK screen is not a complete or validated universe.

## Observed official discovery sources

The [Nareit ticker table](https://www.reit.com/data-research/reit-indexes/reits-by-ticker-symbol) renders ticker and company columns and explicitly includes REITs and real estate operating companies. It offers broader discovery than SIC 6798, including newer or renamed candidates. It does not by itself prove tax status, U.S. common-share eligibility, CIK identity, or historical membership.

The [Nareit directory](https://www.reit.com/investing/reit-directory) displayed 156 results on the research date, but the browser text exposed only nine rows. Membership includes international and non-REIT real estate companies. That displayed number is not an imported or verified security count.

The linked [September 2026 REITWatch](https://www.reit.com/sites/default/files/reitwatch/RW2609.pdf) is a dated PDF snapshot as of August 31, 2026. Its industry fact sheet reports 180 constituents in the All REITs index. Its constituent and M&A tables are useful for dated discovery and exits. Index membership is a separate population from all eligible U.S. listed REIT common shares. A source's effective date is not its public availability timestamp. The [2024 archive](https://www.reit.com/investing/investing-tools/nareit-statistical-publications/reitwatch/reitwatch-2024) exposes monthly source links; no full set of monthly PDFs has been acquired in this lane.

The [SEC exchange map](https://www.sec.gov/files/company_tickers_exchange.json) was observed as columnar JSON with `fields` and `data`. `parse_sec_exchange_map(payload)` imports that exact format and normalizes CIKs. Current ticker/exchange mappings remain discovery metadata. Issuer 10-K cover pages, REIT election disclosures, exchange and corporate action notices must supply dated security-class, listing, REIT status, identity, alias, merger and exit evidence. A ticker is not a stable security identifier.

The [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) describes recent columnar arrays and additional historical JSON files. `build_inventory` traverses every advertised historical file supplied by the broker. Missing, malformed, unreferenced, mismatched and conflicting metadata remain visible. No count cap silently truncates the study period.

Source discovery registry: `configs/reit_universe_discovery_sources.json`. These are observed source formats and limits, not invented feeds or a claim of exhaustive acquisition.

`parse_nareit_ticker_table(payload: str | bytes, *, source_url=official_url, retrieved_at=None)` imports the actual saved Drupal HTML table by its observed `RTC Ticker` and `Company name` headers. It retains decoded names, profile links, source hash and row locator. CIK is unresolved and `source_classification` is `unknown_reit_or_reoc`; the observed source has no row-level REIT/REOC classification. A missing, truncated, ambiguous or malformed table raises. Supply the broker receipt's aware `retrieved_at`; parsing does not invent a historical publication clock. The source SHA256 checked in this build is `745cfd7fcd396ed2ff66a2db8b9c6bf5c645e027dd2e1d1d3aafc8f249ac7e79`. The SEC snapshot SHA256 is `2df6dbed748a66dfbb6ed403e1e88b4d7b5590e61188ea74d5548d0f8aec09c1`.

## Universe input and output

```python
from src.reit_universe import build_universe

candidates = [{"cik": "123", "name": "Example Trust", "ticker": "EX", "security_id": "example-common"}]
base = {"cik": "123", "security_id": "example-common", "valid_from": "2024-06-01",
        "known_from": "2024-06-02T00:00:00Z", "source_url": "https://www.sec.gov/example",
        "locator": "cover page", "quote": "Synthetic test evidence"}
evidence = [{**base, "kind": "reit_status", "value": True},
            {**base, "kind": "listing", "value": True, "exchange": "NYSE"},
            {**base, "kind": "security_type", "value": "common"}]
universe = build_universe(candidates, evidence, "2026-10-03")
assert universe["coverage"]["validated_count"] == 1  # synthetic only
```

Evidence requires exact HTTPS `source_url` plus `source_sha256`, or `locator` and `quote`. `known_from`/`known_to` require aware timestamps, normalized to UTC. If supplied, `accepted_at`, `source_available_at`, and `published_at` cannot follow `known_from`. Effective intervals use date-only `valid_from` and optional exclusive `valid_to`. A date-only `as_of` selects the UTC end of that day. No later source is automatically projected into earlier historical knowledge.

`issuers` retain CIK-based identity, aliases and REIT/merger/exit history. `securities` retain independent identity and all associated evidence. Supply stable `security_id` wherever available; the fallback `CIK:ticker:class` is a provisional discovery key, not a corporate-action reconciliation. Duplicate discovery rows are preserved under `candidate_sources`. Missing CIKs remain unresolved candidates; malformed supplied CIKs raise.

`validated`, `candidates` and `exclusions` partition the current snapshot. Common, preferred and debt classification requires class-specific evidence. Conflicting active proof prevents validation. `eligibility_intervals` are historical intersections of positive proof; overlapping negative/class/exit proof is recorded in `blocking_evidence_ids` with `requires_dated_blocker_resolution`. These intervals must not be replayed as unconditional membership; use the builder's dated snapshot and supporting knowledge clocks. Coverage always states that exhaustive discovery and historical membership remain unproven.

## Inventory input and output

```python
from src.reit_inventory import build_inventory

scope = {"ciks": ["123"], "start_date": "2024-01-01", "end_date": "2026-10-03",
         "predecessor_ciks": [], "context_accessions": [], "document_evidence": []}
metadata = [{"cik": "123", "submissions": submissions_json,
             "source_url": "https://data.sec.gov/submissions/CIK0000000123.json",
             "source_sha256": source_hash, "retrieved_at": retrieval_clock,
             "historical_pages": [{"name": historical_filename, "data": historical_json}]}]
inventory = build_inventory(scope, metadata)
```

An explicit `end_date` or `as_of` is required for determinism. Default forms are 10-K, 10-Q, 8-K and their amendments. Selection is by filing date, with every in-scope filing from January 2024 onward. The latest original annual filing before the start supplies opening context, while explicit `context_accessions` can select older agreement or predecessor filings. `predecessor_ciks` expands the identity scope without merging issuer CIKs. `issuers` or `validated` can supply CIKs when `ciks` is omitted.

`filings` retains all parsed metadata, `selected` and `excluded` retain selection reasons, and `documents` contains selected primary URLs plus externally evidenced exhibits. Exact primary SEC URL, filing index URL, accession, original arrays, report date and acceptance timestamp remain attached. Identical duplicate accessions combine provenance; conflicting accessions are quarantined from selection. Source SHA256, input JSON fingerprint, retrieval time and source path remain distinguishable.

`coverage.filing_metadata_complete` concerns supplied filing metadata only. `history_complete` remains false because a submissions feed cannot verify all required agreements, exhibits, predecessor history or source public availability. Missing opening context, CIK metadata and historical pages are explicit. An accepted filing timestamp never becomes verified original public availability.

## Validation record

Initial tests failed because the two production modules did not exist. Subsequent focused runs demonstrated missing coverage and blocker behavior before the corresponding fixes. The final focused run passed **21 tests** in 0.006 seconds. Run `python -m unittest tests.test_reit_universe tests.test_reit_inventory -v`. System Python has no pytest installed. The root coordinator owns whole-repository testing, integrated acquisition, candidate resolution counts, benchmark review and publication.

Remaining factual work: cross-source candidate identity resolution; monthly 2024–2026 constituents and exit/entry reconciliation; issuer proof for REIT election and common listing; source availability clocks; history pages and exact exhibit inventories. The root owns further acquisitions and integration. No full-universe count is claimed.
