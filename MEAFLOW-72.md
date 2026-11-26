# MEAFLOW-72 — Active Research Strategy

**Status:** Active research candidate; not approved for live trading.  
**Parent research snapshot:** research/sideways-transition-management-v1  
**Previous strategy:** MEAFLOW-52 remains preserved and unchanged.

## Lineage and scope

MEAFLOW-72 is a controlled successor candidate built from the MEAFLOW-52-era funding-carry configuration as represented in the causal research simulator. It is not a claim that the current experiment branch is a byte-for-byte clone of a separately versioned MEAFLOW-52 production codebase. The tested implementation reuses the same core funding-rank framework and baseline parameter set, then changes sideways-regime position handling.

## Frozen strategy rules

- Funding-rate lookback: 7 days.
- Portfolio rebalance interval: 7 days, with a rebalance when the detected market regime changes.
- Cross-sectional selection: bottom 20% funding-score symbols for longs and top 20% for shorts, subject to regime policy.
- Regime detector: BTC mark-price return over the trailing 30 days, using the last fully completed hourly mark candle.
- Bull regime: both long and short legs.
- Bear regime: short-only.
- Sideways regime: **hold the existing portfolio unchanged**; do not open new positions or add to existing positions until the regime changes.
- Unknown regime: flat.
- Research accounting: 100 USDT initial equity, 1x leverage.
- Reference cost case: 5 bp fee per side plus 2 bp slippage per side. Cost sensitivity also tested at 2 bp and 8 bp fee per side, with 2 bp slippage per side.

## Matched OOS result that motivated the candidate

Experiment: research-results/sideways_transition_management.json  
Window: 2025-09-06 18:24 UTC to 2026-10-31 16:00 UTC.

At 5 bp fee per side + 2 bp slippage per side:
- Net return: +72.9428%.
- Ending equity from 100 USDT: 172.9428 USDT.
- Maximum drawdown: -26.5454%.
- No simulated liquidation.

Cost sensitivity for the hold-existing variant:
- 2 bp fee per side: +76.4356%.
- 5 bp fee per side: +72.9428%.
- 8 bp fee per side: +69.5166%.

The OOS window was already inspected in prior research; it is not pristine unseen data. The simulator is an hourly OHLC stress approximation, not an exchange-accurate liquidation or order-book execution model.

## Promotion gates still open

Before live deployment or merging into a production branch, MEAFLOW-72 must pass:
1. A genuinely untouched forward/out-of-sample window.
2. Bull, bear, and sideways regime-specific attribution and transition-error analysis.
3. Higher slippage and fee stress, plus spread/market-impact sensitivity.
4. Maker/taker execution and limit-order fill-probability modelling.
5. Symbol-universe and leave-one-symbol-out robustness.
6. More realistic liquidation brackets and intrabar execution assumptions.
7. Reproducible comparison against the frozen MEAFLOW-52 baseline on identical dates and costs.

**Safety rule:** Do not edit or overwrite MEAFLOW-52. All further experiments must branch from MEAFLOW-72 or its research descendants. Do not describe MEAFLOW-72 as production-ready until the promotion gates pass.
