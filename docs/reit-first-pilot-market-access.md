# First REIT stock test: new market evidence

**Current result:** two correctly dated2024AmericanTower releases are retained, and an existing stock-data service returned202rawquote events. The backtest still has no qualified performance result.

## What this continuation actually added

- SixSEC originals: two2024releases, their8Ks and indexes. [Source handoff](reit-2024-pilot-source-handoff.md).
- An existing-entitlement Massive stockquote request for **AMT,2024-02-27,14:30:50Z through14:31:00Z**, at most1000records/onepage. Actualresult:202quotes, onecompletepage, no continuation. This checks access over10seconds; it does not select a trade date or cover a full trading session.
- A separate **2024-02-27** ticker-reference query: AMT,commonstock,XNYS,USD,CIK0001053507,share-classFIGI BBG001S5NPQ6. Both retainedSEC filing covers identify the commonshare as AMT on the NewYorkStockExchange. Their exact native-text spans are recorded. The cover's$0.01parvalue is a legal share attribute, not a stock market price.
- Explicit [field and proof gaps](../data/processed/reit_build/20261004-pilot-repair/market_observation_gap_report_v1.json), against Post's existing intake. Sourcehashes, current retrieval clocks and rawsource records are retained; historical local receipt remainsunknown. No fabricated availability or execution records were added.

Current [Massive documentation](https://massive.com/docs/rest/stocks/trades-quotes/quotes) describes NBBO quotes, sizes in shares, exchange-generation timestamps and SIP-receipt timestamps. These source clocks do not reconstruct our strategy's historical observation. The existing collector exposes SIPtime; complete participant/event metadata remain in the original rawresponse.

## What remains missing

1. Proof of when the complete selected release wording was public. The archive attempts have not supplied it; Organize Benchmark Data Push now owns independent archive-capture research.
2. Complete new scoring/aggregate and loaded-model binding from Benchmark; it reported selecting Februaryfirst. Post retains canonicalreview/replay.
3. Market coverage for the ultimately accepted entry, exit and holding window; approved security/action validity, quote availability and capacity. The ten-second probe is not that full horizon.
4. Dated fees/slippage, shortstock availability/rates, collateral, recall/dividend/financing obligations and intraday account exposure.

The simple backtest runner exists and its current actualdata gate withholds returns while evidence is incomplete. Root freshly checked its capsule SHA129de1147a00492838262f518b1e795d1d7514864a85cf0e283cf96caf0a536a. This is input rejection, not a measured zeroedge. Qualified-only reporting remains the human's chosen rule.

Next: finish these inputs, let the existing runner compare the wording strategy with always-long and cash, then use that evidence before the widerREIT/loan-network/options/futures/OOS work. The source lane created no additional engine, made no paid order and opened no finaltest. Current retainedSEC sources are nativeHTML with extractedtext; no PDF/imageOCRinput is required for this slice.