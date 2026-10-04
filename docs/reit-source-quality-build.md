# REIT source quality audit build

The audit separates authority, document identity, retained integrity, representation,
availability history, financial observation completeness, conflicts, and point in
time evidence. There is no combined quality score. `eligible_as_primary` means the
retained source passes the implemented primary-document gates; it does not mean
all its amounts were extracted, independently verified, or usable in a backtest.

The initial 15 lines in `docs/reit_document_urls.txt` and their explanations are
unchanged. Additional registries are supplied separately with `--registry`.

## Offline commands

Run from the repository root with Python 3.11 or later. No network, paid data,
OCR, downloads, or collector/analyzer edits are involved.

```powershell
python scripts/audit_reit_source_quality.py --output data/processed/reit_source_quality/catalog
python scripts/audit_reit_source_quality.py --manifest data/processed/reit_financials/20261003-meaning-pilot/manifest.json --manifest data/processed/reit_filing_pilot/realty_income_2025_meaning_v2/manifest.json --output data/processed/reit_source_quality/retained
python scripts/audit_reit_source_quality.py --registry configs/my_reviewed_sources.json --receipts data/my_retained_receipts.json --output data/processed/reit_source_quality/reviewed
python -m unittest tests.test_reit_source_quality
```

`--registry`, `--manifest`, and `--receipts` can be repeated. A registry is a list
of source objects or an object with `sources`/`urls`. Receipt JSON accepts a list
or `receipts`/`http_receipts`/`urls`. `--live-evidence` defaults to the retained
2026-10-03 `live_urls.json`. Without registry or manifest inputs, the exact initial
catalog is used in its existing order. Provided registries and manifests retain
their individual source entries; byte duplicates are reported, not deleted.

Outputs are `source_quality.json` and `source_quality.md` in the required output
directory. The CLI reads source files and caches, detects an output collision with
retained input files, and writes separate reports. Relative source paths are
resolved against their input manifest/registry, then the repository root. Missing
retained files and unlinked extraction caches are recorded as gaps. Extracted PDF
text is read only if URL, accession, and raw hash agree with the source metadata.
This does not audit extraction fidelity or OCR.

## API and input contract

```python
audit_source(source: dict, raw_bytes: bytes | None = None,
             expected: dict | None = None) -> dict
audit_registry(sources: list[dict],
               receipts: list[dict] | None = None) -> dict
```

The API performs no file reads or network calls. `audit_registry` accepts retained
bytes in each source's `raw_bytes`, and optional independently established identity
in `expected`. CLI file IO is confined to its adapter.

Source fields:

| Field | Meaning |
|---|---|
| `url` | Exact source URL; `source_url` is accepted by the single-source API |
| `issuer`, `cik` | Established issuer identity; CIK is normalized only for comparison |
| `accession`, `document`, `form` | Filing accession, exact document filename, and document form |
| `period` | Report period; `report_date`, `reportDate`, `period_end` are accepted aliases |
| `sha256` | Expected retained raw SHA-256; `raw_sha256` is an alias |
| `content_type` | Declared MIME, compared with actual retained byte signatures/parser results |
| `source_path`, `text_path` | CLI paths to retained raw and extraction cache |
| `content_text`, `extracted_raw_sha256` | PDF text plus mandatory raw-byte hash binding for API callers |
| `reported_at`, `accepted_at`, `retrieved_at`, `first_public_at` | Separate timestamps; absent/unknown values remain null |
| `financial_evidence` | Explicit source-linked observations; omitted observations remain unassessed |
| `availability_history`, `live_validation` | Preserved receipts/tool evidence; not financial-document proof |

`document_name` and `filename` are document aliases. Independently supplied
`expected` issuer/CIK/accession/document/period/form disagreements are hard identity
failures. For SEC archive documents the URL CIK, compact accession, and filename
must agree. Text must contain the exact declared issuer and period cues; a missing
cue is unresolved, not proof of a contradictory issuer or period. Aliases and date
format variants need explicit reviewed input rather than invented normalization.

Exact official SEC hosts are allowlisted. Exact issuer hosts are curated in
`ISSUER_HOSTS` with references to the retained catalog and validation/integrity
documents. A source's `official`, `official_domains`, or arbitrary domain claim
cannot expand that allowlist. The issuer host must match its curated issuer name.
HTTP, embedded URL credentials, unsupported ports, malformed URLs, and local file
URLs are quarantined. URL authority plus supplied retained metadata is an offline
provenance check, not an independent cryptographic proof of server origin.

Each financial observation must supply `issuer`, `period`, `metric`, `value`,
`unit`, `scale`, `basis`, `quote`, and `locator`. The issuer and period must agree
exactly with the source identity; the quote must appear exactly in retained HTML
text, decoded JSON, or hash-bound PDF extraction text. Its numeric value must occur
in the quote. `complete` describes supplied metadata and these binding checks.
It does not independently prove the meaning of the metric, unit/scale, row/column,
accounting basis, dimensions, locator, or precision. Caller review must establish
these semantic details before using an amount. Unsupported formatting, computed
amounts, and incomplete context remain review work.

Concrete adapter for an existing collection manifest (no financial observations
are invented from document metadata):

```python
import json
from pathlib import Path
from src.reit_source_quality import audit_source

manifest = json.loads(Path('data/processed/reit_financials/20261003-meaning-pilot/manifest.json').read_text(encoding='utf-8'))
issuers = {c['cik']: c['company_name'] for c in manifest['companies']}
document = manifest['documents'][0]
source = dict(document, issuer=issuers.get(document['cik']),
              document=document['filename'], period=document.get('reportDate'))
result = audit_source(source, Path(document['source_path']).read_bytes())
```

This adapter uses manifest metadata, not independent identity proof. Supply
`expected` from separately reviewed identity evidence if available. To audit
analyzer records, explicitly map their reviewed issuer/period, value, metric,
currency/unit, scale, basis, exact source quote and locator to `financial_evidence`.
Missing or ambiguous analyzer fields stay missing. For example, the synthetic
test fixture binds this observation to retained bytes containing the exact issuer,
period and quote; it is not live financial data:

```python
source['financial_evidence'] = [{
    'issuer': 'American Tower Corporation', 'period': '2026-06-30',
    'metric': 'revenue', 'value': '100', 'unit': 'USD', 'scale': '1000000',
    'basis': 'reported', 'quote': 'Revenue USD 100 million', 'locator': 'body'
}]
```

## Decisions and output schema

| Eligibility | Use |
|---|---|
| `eligible_as_primary` | SEC archive identity, retained hash, exact issuer/period cues, and primary form gates pass |
| `supporting_only` | Allowlisted issuer document with exact issuer/period context; supplements remain support |
| `discovery_only` | Search, directories, landing pages, SEC non-document endpoints, or discovery entries without proved document identity |
| `quarantine` | Unsafe URL, declared hash/MIME disagreement, positively contradictory identity, access notice, or misaligned financial quote/value/context |
| `needs_review` | Insufficient evidence or unresolved comparable financial conflicts |

The authority axis separately labels SEC archive documents `primary_filed_source`,
including official credit agreements/exhibits. Financial eligibility can remain
`needs_review` for a non-periodic exhibit without changing its primary authority
as evidence of the filed agreement's terms.

Each result has `schema_version`, `url`, `quality_axes`, `eligibility`, `reasons`,
`evidence`, and `coverage`. Registry results additionally contain `sources`,
`eligibility_counts`, `duplicate_groups`, and `conflicts`. CLI results add the
audit timestamp and input file paths. The axes are `authority`, `content_identity`,
`integrity`, `representation`, `point_in_time`, `availability`, and
`financial_evidence`. Evidence contains the actual raw hash, identity/checks,
authority reference, and distinct timestamps. Coverage separates `source_grade`,
`observation_grade`, and `point_in_time`; financial accuracy, universe completeness,
extraction fidelity, and OCR remain explicitly unassessed/unknown.

Illustrative source summary:

```json
{
  "schema_version": "1.0",
  "eligibility": "eligible_as_primary",
  "coverage": {
    "source_grade": "eligible_as_primary",
    "observation_grade": "needs_review",
    "point_in_time": "needs_review",
    "universe_completeness": "unknown",
    "financial_accuracy": "not_assessed",
    "extraction_fidelity": "not_assessed",
    "ocr": "not_audited"
  }
}
```

Point in time support requires a timezone-qualified `first_public_at` and a
`first_public_evidence` object containing the same URL, raw SHA-256, timestamp,
`kind: public_availability_observation`, and `publicly_available: true`.
Even this yields `supported_observation`: the document was observed available by
that time. Its exact first public time remains unknown. SEC acceptance, reported
date, and retrieval time are not substituted for executable information time.

Receipt joins require exact URL equality, preserve each supplied receipt, and
never copy a newer receipt timestamp onto previously retained bytes. Multiple
receipts are reported as limited historical observations, without claiming an
uptime probability. Global 403/429 restrictions remain `access_restricted`;
tool errors/limits and missing status remain distinct from dead-link claims.
An HTTP 200 response containing an access notice is quarantined as document
evidence. HTML/PDF/JSON byte recognition is a MIME sanity check, not exhaustive
document validity, financial completeness, or content authenticity validation.

Duplicate groups require computed identical retained raw hashes; equal amounts
and caller-declared hashes alone never prove duplicates. These groups describe
byte lineage and do not collapse separate transactions. Conflict detection covers
explicit supplied observations with the same issuer, period, metric, unit, scale,
basis, and dimensions. Different scales/bases are not silently reconciled. Numeric
disagreements require review; no conflict found is not proof of agreement. Current
directories/aggregators are never accepted as a complete historical REIT universe.

## Verification evidence

Test-first cycles observed the missing module, missing CLI, quoted value mismatch,
missing-period classification, and unanchored public timestamp failures before
their implementation/fixes. The focused suite passed 21 tests. Cases include false
issuer expectations, HTTP 200 access notices, hash/MIME disagreement, malicious
URLs, self-declared issuer domains, unsigned issuer supplements, PDF text binding,
missing timestamps, repeated amounts without duplicate proof, exact-context
conflicts, receipt timestamp separation, directory coverage limits, and CLI input
byte preservation.

Offline smoke reports were written to a temporary directory and removed after
inspection. The initial catalog contained exactly 15 entries: 11 discovery-only
and four needing review. The two retained manifests contained 36 documents: all
36 raw hashes verified, 16 qualified as primary sources, and 20 needed review.
No retained source was quarantined. These counts describe the implemented checks
on this retained collection, not a whole-universe or financial-accuracy claim.
The parent build owns the final combined project suite and integration review.
