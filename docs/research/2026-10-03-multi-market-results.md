# What the first tests actually tell us

## Recommendation

Start the implementation pilot with **ES/MES index futures** and a **forecast comparison**. It connects to equity and equity-option exposure. Test risk filtering and trading direction separately. This recommendation selects a useful first experiment; it does not claim a winning trading strategy.

## What was tested

We extended Lattice's idea into two measurable inputs: relationships after removing shared moves, and changes in the relationship graph. We tested both across equities and four futures markets. Every comparison used the same eligible observations and included simple alternatives. Features use prior data; futures outcomes stay in the same actual contract.

| Market | Initial forecast result |
|---|---|
| Equities | Best Lattice improvement was only 0.13%; simple past-average prediction was better. |
| ES/MES index | Residual feature improved on the ordinary model, but lost to simple predictions. MES is the same economic exposure. |
| ZN rates | Graph feature improved on the ordinary model, but lost to simple predictions. |
| CL oil | Residual feature improved on the ordinary model, but lost to simple predictions. |
| GC gold | Small graph improvement; simple predictions were better. |
| Options | Full quotes now downloaded and processed; 18 qualifying matched events remain insufficient for the fixed diagnostic gate. |

**None of the tested Lattice forecasting features passes our promotion rule.** The frozen graph risk filter worsened the downside measure against the training-scaled ordinary policy in all four futures markets, at similar average exposure. Other exposure mismatches remain explicit. Direct-signal evidence is inconclusive against simple controls. These are price diagnostics; no net profitability or hedging benefit is established.

## How it fits the larger project

FDS and disclosure processing supply dated company facts. Market data supplies prices and measurable outcomes. Lattice can supply numerical market context. These are separate inputs: a plot or an extracted fact becomes a useful signal only when adding it improves an honest comparison. The current tests do not show that improvement.

## Extensions still worth investigating

The next economically grounded candidates are futures term structure and option volatility surfaces. Then consider constrained hedge sizing and dated links between companies. These need their own fixed comparisons and suitable observations; copying equity geometry into every market is insufficient.

Data cost for this pilot: **$8.53**. Conservative total actual/reserved Databento spending: **$31.67** of the exclusive $250 cap. Nine new batches and 5,169 files were downloaded and hash-verified remotely. The previously purchased full options batch also completed: 32 files reduced to 82,843 daily quote marks. No duplicate option purchase was made.

Verification: **69 focused tests passed**. Completed market reports, source hashes and data receipts are saved locally; large raw processing ran on home-pc.

Detailed evidence and limits: [execution record](2026-10-03-multi-market-execution-status.md). Extension mechanisms and rejection criteria: [research note](2026-10-03-lattice-extensions.md).
