# Retained instrument history continuation

This packet extends the published, hash-bound instrument assertions without changing the canonical financial tables. It is a bounded evidence packet, not a complete loan ledger or a coverage claim.

## Build and validation

Run `python scripts/build_reit_instrument_history.py`. The optional `--as-of` accepts a timezone-aware information cutoff. The replacement output is `data/processed/reit_build/20261004-continuation/histories/v3/`, using `reit-instrument-history-extension-2`. Existing candidate files in the parent directory and v2 are preserved. The exporter requires a destination that does not exist; for another build, pass a new version directory with `--output`.

The runner reads only the prior manifest and four small JSONL tables: `instrument_financial_histories`, `instruments`, `role_edges`, and `entities`. Their SHA256 digests, byte lengths, and row counts must match the published manifest before output is written. Output paths inside the immutable source snapshot are rejected before any write. Any existing destination directory is also rejected, including an empty directory, so an earlier packet cannot be replaced. It does not read `inputs.json`, the full review table, the SQLite database, or native source files. It makes no acquisition calls. Native parsing and any corpus-wide validation remain the root runner's responsibility.

Source snapshot fingerprint: `419fe98b772e4b3116b6e29535e434dce97afcf6e4137aba75c8aaa0a0dc1f04`.

The verified inputs contain 7 history assertions, 8 instruments, 14 instrument role rows, and 9 legal entity rows. Role counts reconcile to 8 inherited eligible assertions plus 6 review candidates. No input row or prior snapshot was changed.

| Output | Count |
| --- | ---: |
| Chronological assertion events | 8 |
| Source-local components | 11 |
| Supported instrument relations | 2 |
| Preserved role assertions | 14 |
| Preserved legal entities | 9 |
| Unchanged canonical instruments | 8 |
| Ordered original observations | 19 |
| Ordered latest observations | 19 |
| Observations with unknown information time | 5 |
| Confirmed nonoverlapping flow observations | 0 |
| Missing-evidence items | 21 |
| Quarantined source URL claims | 2 |

`manifest.json` records input/output hashes, implementation hashes, counts, and limits. `packet.json` contains the complete result; JSONL tables and `views.json` provide bounded views. `retained_inputs.json` preserves the input subset. Packet SHA256: `66590046b0a4503347b174a35f2cad7502afa5eed3e3376fae2abad0dce1bd47`.

Local verification: `python -m unittest tests.test_reit_instrument_history -v` passed 28 tests. TDD failures were observed before implementation, including an actual multiline second-facility omission, unsupported date/issuer linkage across different trustees, an invalid February 30 reporting period, and missing instrument-scoped termination handling. A fresh code review identified the component-target type and unknown-time ordering issues; both were reproduced by failing regression tests and fixed. Full-suite verification is assigned to the root remote runner.

## What the retained evidence establishes

| Retained evidence | Supported result | Remaining limit |
| --- | --- | --- |
| AAT 2021 indenture description and September 2024 officers' certificate in the same annual-report exhibit index | Separate base agreement and 6.150% notes due 2034; a `series_under_agreement` relation supported by the dated reference and full named-party anchors within the same raw document version | Principal, proceeds, settlement, exact maturity, and trustee-succession effective date are unknown |
| AMT September 2026 completed offering | Three separate components: $500m at 5.300% due 2031, $500m at 5.560% due 2033, and $600m at 5.750% due 2036 | Aggregate principal is not measured cash proceeds; no noteholder allocation |
| AMT supplemental-indenture cover | A dated trustee role assertion is included as the eighth event | Cover-page amount/date overlap does not prove the offering-to-supplement series link |
| AMT planned use of proceeds | Existing 1.450% notes due 2026 and a $6bn multicurrency revolver remain separate referenced scopes | Planned repayment is not a completed repayment or facility closure |
| BXMT May 2026 issuance paragraph | $450m stated issued principal, 6.250% notes due 2031, and retained issuer/trustee/collateral-agent assertions | Specific guarantors, buyers, proceeds and exact maturity are unknown; this paragraph does not use a quarantined exhibit |
| Realty Income April 2025 facilities paragraph | Two separate $2bn capacity components maturing April 2027 and April 2029, each with two unnamed tranches; a prior $4.25bn capacity reference and `amends_and_restates_reference` relation | Exact day, currency allocations, named lenders/agent, loan balances, rates, and tranche IDs remain unknown |
| AGNC reported ATM sale result | $167m reported net proceeds remain an observation tied to the aggregate result | Exact transaction/reporting period, currency code, agreement/agent allocations are absent from the retained quote |

Amounts with a dollar symbol retain `currency_symbol: "$"` and an unknown ISO currency code. This extension does not silently equate a dollar symbol with USD or a multicurrency facility's reporting amount with each currency's commitment. Capacity, prior capacity, stated issued principal, planned repayment principal, and net proceeds have different amount kinds. No outstanding balance is invented.

Each new component retains its parent canonical instrument ID, subject ID, literal source scope, source SHA256, original quote locator, and quote-relative span. Its ID includes the document ID, raw source SHA, event ID, locator/page and clause span. Equal labels cannot collapse distinct source versions, events or clauses; an inconsistent identity collision raises an error instead of overwriting provenance. Components are source-local scopes; they do not establish cross-filing legal identity. Both supported relations have `identity_merge: false`. The AAT relation targets a canonical instrument; the prior-facility reference explicitly uses `target_kind: component` and `to_component_id`, without claiming a distinct canonical predecessor instrument. Cross-filing repeated agreement mentions, same-name affiliates, matching principal amounts, and shared counterparties require further identity evidence.

Borrower, issuer, lender, administrative agent, trustee, collateral agent, and guarantor roles remain distinct. All inherited review flags survive. The bank and trust-company legal entities remain available even when they are outside the REIT company universe. The two U.S. Bank legal names are not consolidated. A named agent or trustee does not become a lender, and syndicate shares and exposure amounts remain unknown. Shared graph nodes do not establish causal exposures.

## Dates and history views

Effective dates and information timestamps remain separate. Dates reported only to a month or year retain that precision. Original and latest observations use information order within a source/version/clause and metric/amount-kind/currency group. Different source-local components remain separate by default. Cross-source ordering requires explicit `reviewed_correspondences`: approved review status, a known review timestamp available at the requested cutoff, an identity rationale, and exact component document/SHA/locator/span anchors. Every linked component must have the same parent instrument, subject and component kind; ambiguous overlapping reviews are rejected. The original components and their source eligibility remain separate. No correspondence is supplied in the real v3 packet. These views do not manufacture a correction, refinance, or transaction chain between different instruments.

Ordered original/latest views use only eligible observations with known information timestamps. Five Realty Income facts remain in `information_time_unordered`, alongside their chronological assertion and original evidence. Unknown information time never outranks a dated observation. This default packet is not a point-in-time eligibility claim. With a cutoff, records disclosed later or without a timezone-aware information timestamp stay outside the original/latest eligible views. Every event's original first-public date remains unknown. The separate clock-provenance work owns assumed versus observed publication evidence.

The confirmed flow view requires an explicitly reported cash movement, an explicit ISO currency code, a valid exact reporting period, and no period overlap within the same scope. It performs no sums. Completed debt offering principal and reported aggregate ATM results cannot meet those gates in this packet. Missing later mentions never imply repayment or termination. An explicit termination requires a clause naming the same instrument; an amendment/restatement reference does not terminate its predecessor.

## Exact next evidence requests

The queue retains the quote and source locator motivating each request. Operative clauses may already exist elsewhere in the retained corpus; their availability outside this bounded packet has not been checked.

| Scope | Exact source or clause requested |
| --- | --- |
| AAT base agreement | Executed January 26, 2021 indenture among American Assets Trust, L.P., American Assets Trust, Inc., and U.S. Bank National Association; operative principal and amendment terms |
| AAT 2034 series | September 17, 2024 officers' certificate under that base agreement; principal, issuance/settlement, exact maturity, guarantee and trustee-succession clauses |
| AMT new note series | Operative September 14, 2026 Supplemental Indenture No. 3 to the June 2, 2025 Base Indenture, naming the 2031, 2033 and 2036 series; exact maturity/settlement/proceeds clauses. The retained `d156192dex41.htm` cover is insufficient by itself |
| AMT old notes and revolver | Actual repayment confirmation for the 1.450% notes due 2026; December 2021 amended/restated $6bn multicurrency credit agreement and later amendments, schedules naming lenders/agent and shares, and subsequent instrument-specific balance disclosures |
| BXMT 2031 notes | Operative May 19, 2026 indenture and named guarantor schedules for the $450m, 6.250% secured notes. The retained `d156837dex41.htm` is not one of the two conflicting URL claims |
| Realty Income facilities | Executed April 2025 agreements for the separate April 2027 and April 2029 $2bn facilities; prior $4.25bn agreement identity, four tranche schedules, currencies, lender/agent roles and shares, subsequent outstanding balances, and observed annual-report availability |
| AGNC aggregate result | Reporting-period context and named Sales Agreement/agent allocations; exact transaction dates only if explicitly disclosed |

Only the following two declared conflicting BXMT source claims stay quarantined:

- `https://www.sec.gov/Archives/edgar/data/1061630/000106163026000009/exhibit10504q25.htm`
- `https://www.sec.gov/Archives/edgar/data/1061630/000106163026000009/exhibit10664q25.htm`

Declaration: `data/processed/reit_build/20261003/integrated/source_adjudication_v2.json`, SHA256 `437afc3d89db0acdef2daf2336e347b2c698c38f6d72973b705705c6c1c85f51`. No unrelated source grade was changed. Reconcile these declared URL claims against retained-byte provenance before admitting either exhibit.

The continuation inherits source eligibility from the published assertions. Input-table hash validation does not revalidate raw source bytes or remove earlier source/text provenance gaps. No lender-share, exposure, outstanding-balance, realized-repayment, exact undisclosed date, or publication-history field is invented.


## Integration regression record

Root's integration review reproduced additional source-boundary defects after the earlier scoped review. Four new regressions were observed failing before the source-identity/output fixes: a February 10 cutoff selected $100 from the old source while the shared component pointed to a later $120 document; two proceeds clauses collapsed into one component; a base/series relation crossed two raw versions of the same declared document; and an existing packet destination was replaced. All four now pass. Positive multi-quote fixtures hash their complete shared document body, and the negative cross-version fixture uses two distinct complete body hashes.

Three further correspondence tests enforce separate unreviewed histories, approved provenance-bound ordering without component merges, and rejection of an unapproved review or mismatched SHA. The earlier repeat-report and flow-overlap cases now supply an explicit reviewed correspondence rather than relying on a shared label. This fix pass changes only the owned builder, exporter, tests, documentation and new version output; prior source snapshots and candidate packet files remain intact.


A further note-specific `seen(label, amount)` path was independently reproduced by the fresh reviewer and a new failing two-clause regression. It was removed, so identical quoted note terms in distinct clauses retain distinct source-local components. The final v3 packet has the same data SHA as v2 because the real bounded evidence contains no duplicate plural-note clauses; its receipt binds the corrected implementation. The fresh reviewer reported no remaining findings and independently checked invalid review clocks, source anchors, overlapping reviews and mixed instrument/entity/component-kind scopes. Old candidate artifact hashes and sizes were rechecked unchanged.
