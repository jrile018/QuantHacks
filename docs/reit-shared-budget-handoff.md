# Shared Databento budget handoff

Current retained [budget checkpoint](../data/processed/reit_build/20261004-continuation/budget_checkpoint.json): all six existing REIT orders are settled. The cap is **$249.99**; $31.67 legacy high-water spend plus $47.40 settled REIT actual ledger cents gives **$79.07** committed and **$170.92** remaining. No new paid order was made in the continuation. Cross-chat guard adoption, future external activity and account-wide invoice completeness remain unverified. Provider job costs are not confirmed invoices.

The 2026-10-04T03:29:56.413493+00:00 audit below is a **superseded baseline snapshot**. Keep its hashes and detailed legacy/job proof for provenance, but use the checkpoint above for current commitments and balance.

Audit: `C:/Users/johnp/OneDrive/Documents/ChatGPT/QuantHaxs/data/processed/reit_build/20261003/market/shared_budget_audit.json`
SHA-256: `4e6317cb6365185ddb97ee06682caca2213441e4df286699a3954d59975b5317`

SQLite logical snapshot SHA-256: `307d0999aebc4244955308fe4bb08277123ea52cbcf8211b14f206deb0796d0a`. Read through URI `mode=ro`, `query_only`, and one explicit transaction. SQLite component hashes and legacy bytes were unchanged across capture. No ledger constructor, checkpoint, provider request, acquisition, or paid order ran.

## Recorded commitments in the superseded baseline

| REIT request suffix | Exact provider job ID | Ledger / receipt state | Exact quote USD | Receipt actual USD | Held or settled USD |
| --- | --- | --- | ---: | ---: | ---: |
| pilot-options-minute | OPRA-20261004-A6EMTKRU9R | submitted / processing at baseline; now settled | 38.719514161348 | unknown at baseline; now 38.72098788619041 | 40.67 at baseline; now 38.73 |
| pilot-equity-minute | EQUS-20261004-KKDF3Y7WHQ | settled / done | 0.306424498558 | 0.30642449855804 | 0.31 |
| pilot-futures-minute | GLBX-20261004-GCJLACYFJP | settled / done | 6.790824830532 | 6.79082483053207 | 6.80 |
| pilot-options-minute-definition | OPRA-20261004-VXSWEM8X4D | settled / done | 1.479050517082 | 1.47905051708221 | 1.48 |
| pilot-equity-minute-definition | EQUS-20261004-NTU68UXQ59 | settled / done | 0.013464689255 | 0.01346468925476 | 0.02 |
| pilot-futures-minute-definition | GLBX-20261004-W3C9PV4TUM | settled / done | 0.053202591836 | 0.05320259183645 | 0.06 |

At the baseline, six quotes rounded individually totaled **$47.39**, original reservations **$49.83**, five settled actuals **$8.67**, and the options minute job retained **$40.67**, giving then-current REIT commitments of **$49.34**. The options minute job later settled at **$38.73** ledger cents, so current REIT commitments are **$47.40**. The receipt preserves the provider's precise cost; ledger cents round conservatively upward.

Legacy has 15 rows and 12 unique provider job IDs. Actual sum is **$31.45551528409123**; outstanding quote fallbacks total **$0.213895351811**; actual-else-quote sum is **$31.66941063590223**. All present quote fields sum to **$25.285924500037002**, but settled quote fields are not added again. The declared highwater **$31.669410635902793** is slightly higher and rounds upward to **$31.67**.

No duplicate provider job IDs within either store or across the stores, and no repeated unreleased SQLite fingerprints, were found. No identified job double count exists in this capture. Distinct jobs can buy overlapping data; unbound direct rows and unrecorded account activity remain outside job-ID overlap proof. The audit lists all 18 exact known provider job IDs, costs, and recorded states across both stores.

**Historical baseline only:** $249.99 cap − ($31.67 external highwater + $49.34 then-current REIT commitments) = $168.98 then remaining. **Current checkpoint:** $249.99 − $79.07 = **$170.92 remaining**. This balance is a reservation limit for recorded activity, not a spending authorization or invoice guarantee.

## Adopt the shared guard

Use callable `src.reit_budget.BudgetLedger` and guarded `src.reit_market_data.DatabentoClient` from the authorized implementation. Every purchasing checkout/worktree must point to the same absolute files:

- SQLite: `C:\Users\johnp\OneDrive\Documents\ChatGPT\QuantHaxs\data\processed\reit-market\budget.sqlite`
- Legacy ledger: `C:\Users\johnp\OneDrive\Documents\ChatGPT\QuantHaxs\data\raw\databento\acquisition_ledger.json`

Explicitly pass that absolute legacy path as `DatabentoClient(..., legacy_ledger=Path(...))`; its default follows its own checkout and can diverge across worktrees. Pass the absolute SQLite path to `BudgetLedger(Path(...), cap="249.99", ...)`. Existing cap metadata is immutable. Relative paths or copied ledgers cannot coordinate shared reservations.

`DatabentoClient.submit` refreshes external spend before reservation and again before marking submission; external cents are monotonic (`MAX(previous, ceil(legacy_spend × 100))`) with a $23.14 floor. `legacy_spend` deduplicates identical legacy job IDs by maximum actual-else-quote amount, includes direct quotes, and uses the larger declared total. Future external purchases must be recorded and refreshed before any further spend. Concurrent unrelated purchasers still require shared adoption and timely external updates.

Preserve existing request IDs and provider job IDs. Do not retry a request that reached submission, or create a fresh request ID to bypass a held reservation. Reconcile submitting, unknown-held, or submitted orders against exact provider identity and selectors; download existing jobs. Released orders alone stop contributing automatically. Never release ambiguous submissions on assumption.

Remaining gaps: guard adoption by other purchasing chats is unverified; account-wide invoices and future external activity are not reconciled by these receipts. The completed six-job delivery does not establish any new spending authorization, financial performance or trading readiness. No chat was contacted by the baseline audit.
