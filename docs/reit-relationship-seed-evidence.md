# REIT relationship and financing event seed evidence

**Purpose.** Small offline evidence seed for graph implementation. Assertions are source-level candidates; they are not a complete legal-entity graph, adjudicated event ledger, or financial-accuracy review. Evidence is limited to retained filing text and selected Realty Income annual-report pages.

## Coverage

- 11 assertions: 9 based on 7 SEC documents across 4 accessions, plus 1 Realty Income annual-report document (one AAT filing contributes 2 assertions and one AMT 8-K contributes 3).
- Source inventory reviewed: all 35 SEC document records in the retained manifest were available for inspection; only the documents named below were used for this bounded seed. Realty Income input is a single annual-report PDF whose retained extracted text includes selected pages.
- Each assertion records the exact quote, source SHA-256, filing/document identity, and locator in [relationship_seed_assertions.json](/C:/Users/johnp/OneDrive/Documents/ChatGPT/QuantHaxs/data/processed/reit_build/20261003/relationship_seed_assertions.json).
- `available_at` is SEC acceptance time for the cited filing when recorded in the retained manifest. Realty Income's exact availability time is unknown and left null. Filing availability time is not treated as the effective date of a financing event.

## Supported seed assertions

| Evidence group | Supported assertion | Key limits |
|---|---|---|
| American Assets Trust, L.P., 2026 Q2 10-Q, accession `0001500217-26-000046` | The Operating Partnership entered a fourth amended and restated credit facility on 2026-04-01; it describes $500m revolver plus $100m Term Loan A. | The quoted material does not name lenders or administrative agent. Capacity and June 30 balance are not cash movements. |
| American Assets Trust, L.P., 2025 10-K, accession `0001500217-26-000008` | Exhibit-index descriptions identify AAT L.P. as issuer, AAT Inc. as guarantor, and U.S. Bank entities as trustee/successor trustee for a 2021 indenture; a 2024 officers' certificate describes the 6.150% notes due 2034. | These are descriptions in the 10-K exhibit index; the underlying indenture/certificate is not independently evidenced in the selected retained text. |
| American Tower Corporation, 2026-09-14 8-K and supplemental indenture, accession `0001193125-26-390605` | 8-K says the $1.6bn aggregate note offering (2031/2033/2036 series) was completed; it separately states intended uses of proceeds. The supplemental indenture names U.S. Bank Trust Company, N.A. as trustee. | Intended repayment is not completed repayment. Trustee is not lender evidence. Do not create actual debt-extinguishment events from the plan statement. |
| Blackstone Mortgage Trust, Inc., 2026-05-19 8-K, accession `0001193125-26-231141` | Completed $450m secured-note offering; BNY Mellon Trust Company is named trustee and notes collateral agent; certain wholly owned subsidiaries are collectively described as guarantors. | Guarantor entities are unnamed; trustee/collateral-agent role does not establish lender status. |
| AGNC Investment Corp., 2026-05-28 8-K, accession `0001423689-26-000121` | Fourteen named firms entered separate ATM Sales Agreements; offering authorization is up to $2bn; agents can act as agent and/or principal. | Agreement is not proof any named firm transacted. No sale quantity is allocated to an agent. |
| AGNC Investment Corp., 2026-07-20 8-K, accession `0001423689-26-000124` | AGNC reported 16.2m common shares issued through ATM offerings for $167m net proceeds. | Aggregate result only; the 8-K line does not name an agent or exact sale date. |
| Realty Income Corporation, 2025 annual report, local document `local-realty-income-2025-annual-report` | Selected extracted page 85 says new $4bn unsecured multicurrency revolver facilities were entered in April 2025, amending a prior $4.25bn facility; two $2bn facilities mature April 2027 and April 2029. | Do not infer drawings or cash flows. Named lenders/agent and exact April date are not in the retained page excerpt. |

## Review and counterexample rules

1. Preserve separate legal roles. A trustee, collateral agent, administrative agent, guarantor, borrower, issuer, and lender are different edges. No assertion equates an agent or trustee with a lender absent explicit source language.
2. Keep event modality. “Intends to use proceeds” is a planned-use assertion, not a completed repayment. Facility capacity is not a cash transfer. A reported balance snapshot is not itself a financing event.
3. Keep unknown identities unknown. AAT lender allocations and agent are absent from the cited excerpt; BXMT guarantors are unnamed; AGNC sales are not allocated to an ATM agent; Realty Income counterparties are absent from selected pages.
4. Instrument links remain reviewable. Where the source is an exhibit-index description, retain that evidence type so a later parser does not treat the underlying contract as directly collected text.
5. Exact source quotations and document hashes are preserved in the JSON. All dates/amounts should retain source precision and units; do not derive allocations or exact dates from aggregate or period-level facts.

## Integrity boundary

This seed uses cached content only. It does not test live URL reachability, verify any OCR layer, resolve all subsidiaries, establish completeness of the 35-document collection or REIT universe, or validate financial calculations. The JSON is intentionally a bounded starter set with explicit review items and unknown fields.
