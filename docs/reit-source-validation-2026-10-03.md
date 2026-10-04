# Live URL validation — 2026-10-03

## Coverage

- The inventory contains 181 unique URL strings: the 15-entry catalog, 53 SEC browse links in the source map, 59 saved SEC receipt URLs, 35 SEC document manifest URLs, one Realty Income PDF URL, and additional REIT research references.
- After removing citation punctuation and deduplicating, 173 concrete source URLs were opened in sequential web-tool batches, plus one official AGNC event page used to confirm the presentation link. The 15-entry catalog was not changed.
- Seven entries are unexpanded CIK/accession URL templates and cannot be requested as concrete endpoints without inventing identifiers. No concrete source URL remains unattempted.
- Source roles distinguish collected documents/retrieval endpoints, issuer-universe landing links, catalog discovery/examples, and auxiliary research citations. The auxiliary research set includes non-REIT-specific technical and macro sources; it is not all corpus ingestion evidence.

## Results

- 95 source URL opens rendered page content, plus the AGNC event page. The web tool provided content type and a rendered title or excerpt; it usually exposed no transport status, so the recorded HTTP status is null.
- One source URL returned explicit 403 Forbidden: the AGNC Q2 2026 presentation PDF. The official event page rendered as HTML, dated July 21, 2026, and its 821.8 KB Q2 Presentation link points to the exact PDF URL. Treat the 403 as access blocked, not as a dead link.
- One SEC filing exceeded the web tool content limit; the tool reported error 400 and a size greater than 4 MiB. This is a tool limit, not an HTTP status from the source.
- The other 76 opens returned tool-specific inaccessible errors without an HTTP status. These errors do not establish that the URLs are dead.
- The direct ranged urllib probe timed out after 15 seconds. A timeout alone does not prove that the local sandbox blocked networking.

## Catalog examples

The 15 unchanged examples cover EDGAR and SEC API discovery, SEC financial-statement datasets, Nareit classification, AMT 10-Q and September 14, 2026 8-K, AAT 8-K index and credit agreement, BXMT 10-Q and investor supplement, ABR 2025 10-K and 136-page annual-report PDF, EQR Q2 2026 results, DLR 30-page PDF, and the AGNC presentation. The web tool rendered most of these with matching title, MIME, or issuer/document cues; the BXMT 10-Q hit the 4 MiB tool limit, the ABR 10-K returned a tool access error on the current open, and AGNC returned 403. The parent’s earlier page review also observed AAT borrower/guarantor/agent roles and that the Nareit directory includes international listings and is not a complete U.S. REIT universe.

## Interpretation

Rendered page identity is evidence of page content and relevance. It does not establish every page’s semantic correctness, financial accuracy, or universe completeness. Cached byte integrity remains separate and was checked in the offline audit.

Per-URL provenance, role, rendered title, MIME, content cue, normalized URL, or exact tool error is in [live_urls.json](../data/processed/reit_source_validation/20261003/live_urls.json).


## Final normalization review

A CIK########## placeholder was reclassified as a template; the duplicate AGNC context row and notes-dataset punctuation variant were deduplicated. Original URL strings/provenance remain in the evidence. There are 173 unique concrete source endpoints, seven templates and one separate context endpoint. Rendered reference URLs do not establish final redirects; unverified final URL fields are null.
