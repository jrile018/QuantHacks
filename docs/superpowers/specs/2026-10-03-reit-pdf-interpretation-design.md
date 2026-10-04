# REIT PDF money interpretation design

Approved endpoint: the user explicitly requested planning and fixing the demonstrated zero-classification PDF gap, and supplied a SEC contact email for the already planned live collection.

Add bounded interpretation rules to the existing offline analyzer. Runtime parsing must not read the evaluation answer key. Supported annual cash-flow tables require a statement title, an explicit scale, a complete year header, and an exact recognized row label with the expected count of numeric columns. Keep the reported sign, individual year, currency, and combined investment categories. Unsupported or conflicting layouts remain reviewable.

Supported credit-note sentences distinguish committed capacity, conditional accordion expansion, unused available capacity, and outstanding balances. Require an explicit facility section and grammatical amount relationship. Preserve separate issuer/Fund scope and reported dates. A facility agreement or capacity is never itself a cash movement. Do not assign nearby interest rates, maturities, collateral, or notional amounts to loans.

Currency is derived from the original report's explicit reporting-currency declaration (Realty Income PDF page 70), not from the gold answers or the dollar symbol alone. Each record retains the selected amount text, exact page character span, header/section/date context, source/text hashes, and rule identifier. Preserve existing review candidates. Extend cache fingerprints with the new parser implementation.

Acceptance: the unchanged 14 assertions from pages 69 and 85 should be automatically classified with matching amount, currency, period, basis and role, or the remaining unsupported cases must be stated. Regression tests must include wrong/missing headers, years and currency, wrong numeric columns, sign conflicts, capacity versus flow, borrower scope, conditional capacity, and unrelated money amounts. A clean sample score is not a whole-report or industry accuracy claim.

Live collection uses the existing four configured companies and finite filing/exhibit limits. SEC access blocks stop the collector. A network failure does not prevent the local interpretation fix. No model training, paid API, full corpus, or OCR benchmarking is needed.
