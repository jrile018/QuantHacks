# Retained REIT histories and relationship graph

The offline builders preserve financial observations and instrument-specific role assertions. They do not reconstruct bank transactions, allocate syndicate positions, or make a complete financing ledger from a partial filing corpus.

## APIs

```python
from src.reit_histories import build_histories
from src.reit_relationships import (
    build_relationships,
    discover_relationship_candidates,
    normalize_assertions,
)

# records: money_records.jsonl dictionaries produced by reit_money_records.
# documents: retained manifest document dictionaries.
histories = build_histories(records, documents)

# Preserve the original seed file. Recover only whitespace-equivalent native
# quote spans, recording both the supplied and corrected evidence in changes.
normalization = normalize_assertions(seed_assertions, documents)
network = build_relationships(normalization['assertions'], documents)

# Read cached native prose into human-review candidates; never adjudicated edges.
discovery = discover_relationship_candidates(documents)

# Inclusive endpoint; an aware UTC offset is required.
known_then = build_histories(records, documents, as_of='2024-01-01T00:00:00Z')
network_then = build_relationships(
    normalization['assertions'], documents, as_of='2024-01-01T00:00:00Z'
)
```

All results are JSON serializable. There are no paid/model/network calls, OCR, retained-file writes, or publication actions. Documents use `sha256`, `source_path`, `text_path`, `cik`, `accession`, `filename`, and `acceptanceDateTime` from the existing manifests. Explicit `document_id` is supported; a local-report accession itself identifies a local document. In-memory fixtures can use UTF-8 `raw_text` and source-bound `pages`.

## Evidence and time gates

Raw bytes must recompute to the manifest hash. Each evidence hash must match that document. Cached native extraction must identify the same raw source hash; available extraction-artifact hashes are also checked. Quotes must occur in retained source/native text. Structured page and character locators must reproduce the quote; XML element identifiers must bind the actual element text. Numeric quotes appearing elsewhere cannot validate a wrong XML locator. Document and XML quote indexing are cached once per builder invocation.

`normalize_assertions` performs only whitespace-equivalent quote recovery, including native line breaks and nonbreaking spaces. It preserves exact native characters and fixes the locator from actual offsets. It records `original_evidence` and `normalized_evidence` in `changes`, and leaves ambiguous, substantively different, or integrity-failed assertions in `review`. It never changes availability or entity identifiers.

Availability must include a timezone. The endpoint is inclusive. Filing calendar dates, report periods, and effective dates never supply a missing publication timestamp. Assertion availability remains unknown when the seed says unknown, even if a document has other metadata. For money observations, a verified filing acceptance timestamp can supply availability; the latest supplied aware acceptance/availability timestamp is retained conservatively. Unknown or future availability is excluded from eligible PIT collections and issuer metadata nodes. Review collections retain exclusions with reasons for audit and should not be used as model observations.

## Financial histories

`build_histories` returns `financial_history`, `review`, `reconciliation`, and `coverage`. It separates `stock_balance`, `period_flow`, `commitment`, `terms`, planned events, and completed events. Standard source classification comes from `reit_money_records`; unresolved classifications, context/issuer mismatches, precision/duplicate flags, bad evidence, and Companyfacts comparison sources remain review items.

All rows are `additive: false`. Same-filing conflicting values are review items. Equivalent observations and different-filing observations have explicit reconciliation entries. Reporting-period overlap and prior-period restatements are preserved as source observations; the builder neither sums them nor picks a synthetic transaction date. Evidence unavailable at the PIT cutoff cannot invalidate an earlier known observation.

Relationship event histories preserve literal, unallocated reported amount expressions. A reported note principal, authorized equity ceiling, or facility capacity does not establish a realized cash receipt. A completed-event label also requires completed-offering/issuance or explicit issued-equity/net-proceeds language in the quote. Planned proceeds use remains a planned event; it does not extinguish debt. Aggregate ATM results are never attached to a particular agreement agent.

## Entities, instruments, roles, and intersections

`build_relationships` returns `entities`, `company_entities`, `instruments`, `instrument_links`, `role_edges`, `financial_history`, `intersections`, `review`, and `coverage`.

Named parties without supported identifiers use unresolved `name:` IDs. A standalone CIK requires explicit named identifier evidence or agreement with the retained issuer metadata and a name supported in that source. Counterparties cannot inherit the source issuer CIK merely because their name appears in a filing; provided issuer names must agree, and unnamed issuer metadata cannot identify an operating partnership. A descriptive reference such as `CIK ...; issuer's Operating Partnership` cannot identify the partnership. A mismatched seed CIK remains an asserted identifier with an identity review issue. `company_entities` provides separate manifest issuer CIK/name nodes and source hashes for rendering; it never aliases a named operating partnership to that issuer. Missing issuer names remain unknown.

Instruments start with assertion-local source identities. Equal amounts, rates, or dates do not merge them. An explicit same-facility assertion reference can link the same named facility within the same document/company; these links retain evidence.

Trustees, collateral agents, administrative agents, arrangers, sales agents, guarantors, borrowers, and issuers retain distinct roles. An asserted lender or other counterparty role must have literal matching role evidence; a trustee quote cannot create a lender edge. Conflicting reuse of an assertion ID is excluded. Explicit named compound clauses and ATM firm lists expand to human-review candidates. A successor trustee stays distinct from its predecessor. Unnamed guarantor subsidiaries and unspecified security purchasers do not become fabricated entity nodes.

Intersections require a shared source-supported counterparty role across different company IDs. Sector membership cannot create an intersection. Exact-name matches have `basis: shared_exact_name_counterparty`, unresolved identity, and `eligibility.eligible: false`. A shared supported party identifier can produce `shared_verified_counterparty`; any candidate role expansion still requires review.

Every row separates source eligibility, PIT eligibility, and overall eligibility. Coverage always states the retained scope and `complete: false`; this is neither full-universe coverage nor a graph of every financing relationship.

## Verification and retained-input findings

The focused command is `python -m unittest tests.test_reit_histories tests.test_reit_relationships tests.test_reit_money_records`. It passed **51 tests**, including **33 new tests** for financial semantics, exact evidence, tampering, temporal boundaries, unknown availability, conflict handling, conservative identities, role validation, successor roles, issuer metadata nodes, and all fourteen literal AGNC agent names. Tests demonstrated failing behavior before each implementation/fix. The root coordinator owns whole-repository testing, integrated artifacts, and remote benchmarking.

A read-only smoke check over 35 retained SEC documents plus the Realty Income selected-page extraction recovered **10 of 11** seed quotes, produced **8 primary role edges**, **6 role candidates**, and **one AAT/AMT exact-name trustee intersection candidate**. There were **zero resolved intersections** and **zero primary edges eligible on January 1, 2024**. The original AGNC agent-list quote remains review because its punctuation differs and cached text contains replacement characters; native discovery preserves the exact retained paragraph and all fourteen names with a decode-loss review flag.

AAT borrower/capacity quotes name only the Operating Partnership, so the supplied full LP attribution remains review rather than acquiring the issuer CIK. The BXMT seed CIK differs from the retained issuer CIK and remains identity review. Realty Income has unknown publication availability and selected pages only: it can support retained full-view facility terms, but cannot enter the eligible PIT graph or establish unnamed lenders.

An obsolete, uncached local benchmark reached 638 retained observations (394 balances and 244 period flows) from 5,108 input records; it was stopped before its second PIT pass. Those counts describe that prior run, not a runtime claim for the final optimized implementation. Benchmarking of the current implementation is assigned to `home-pc` via detached tmux.
