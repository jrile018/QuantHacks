# REIT collector execution ledger

- Task 1: Selective PDF text/OCR tests failed first, then passed. Native-only PDF pages do not load Tesseract; mixed pages preserve order.
- Task 2: Company Facts tests failed before implementation, then passed. Facts retain CIK, accession, period, unit, tag, and SEC source links. Conflicting duplicate values make a bridge incomplete.
- Task 3: Offline collector tests failed before implementation, then passed. The SIC 6798 input currently has 53 candidate CIKs. A synthetic one-company pilot produced the manifest, source-linked text, facts, and checks.
- Review: Two Important findings fixed: stale/corrupt SEC metadata cache and conflicting duplicate fact values.
- Verification: 20 REIT/OCR tests passed after fixes; `py_compile`, CLI help, and `git diff --check` passed. A whole-repository run reached 70 tests and failed in newly appeared, unrelated `document_language`, `document_report`, and `document_transcript` tests. Those parallel workspace files were left untouched.
- Ruling: Live SEC requests require a real contact email; none was provided or configured. The live one-company pilot remains unrun, and the CLI requires `--contact-email` for it.
