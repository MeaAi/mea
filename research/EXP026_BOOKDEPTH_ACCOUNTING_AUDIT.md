# EXP-026 — BookDepth backtest accounting audit

**Status:** COMPLETED (static code/report audit; no new performance run)  
**Date:** 2026-11-28  
**Branch:** `research/exp026-bookdepth-accounting-audit-v1`  
**Base commit:** `2e0052cab074dd6828a390728d6ec7a2b83cda6a`  
**Scope:** `research/bookdepth_cost_backtest.py`, `research/bookdepth_maker_trade_through_backtest.py`, and their existing JSON reports on `research/binance-data-pipeline`.

## Findings

### A. Cost-aware BookDepth backtest

1. **Fee arithmetic is internally consistent.** Taker/taker charges 5 bp on entry plus 5 bp on exit; maker/taker charges 2 bp plus 5 bp. Fees are charged against the current compounded trade notional.
2. **Slippage is a round-trip total, charged once.** The report explicitly calls these `round_trip_slippage_bp_scenarios`; code subtracts `notional * slip_bp / 10000` once. Do not double this cost when interpreting its existing 2/4/6/8 bp scenarios.
3. **Equity compounding is per independent strategy cell.** Every direction/horizon/execution/leverage/split starts from the configured capital; selected trades are greedy non-overlapping events, and each trade risks the full current equity times leverage. It is not one combined portfolio across symbols, directions, horizons, or scenarios.
4. **Drawdown is trade-close-only.** `summarize()` updates equity and peak only after each trade closes. It does not include intratrade adverse excursion, so its reported max drawdown is not comparable to MEAFLOW-72 hourly adverse-mark DD.
5. **Leverage outputs are not liquidation-safe.** The report declares full-equity margin but explicitly does not simulate maintenance margin, liquidation, or liquidation fees. Treat 2x/3x as gross sensitivity only.
6. **Maker fill-rate cases are synthetic.** Timestamp-modulo sampling produces a deterministic fraction of selected events; it is not observed queue fill probability and has no partial-fill reconstruction.

### B. Maker trade-through backtest

1. **Maker/taker fee arithmetic is consistent with its stated model:** 2 bp maker entry + 5 bp taker exit. The taker/taker comparison charges 5+5 bp.
2. **Slippage is exit-only by design.** The parameter is named `exit_slippage_bp_scenarios` and the code deducts one slippage amount. For maker/taker this is a reasonable one-sided exit-cost sensitivity. For taker/taker, entry slippage is not modeled; therefore those results are not a full two-sided taker execution-cost estimate. Any future comparison must either label it explicitly as exit-only or add a separate entry-side cost sensitivity.
3. **Funding is omitted, but the <=60-minute horizon does not guarantee zero funding.** A position can cross a UTC 00:00, 08:00, or 16:00 funding settlement even when held for 5, 15, or 60 minutes. The existing report therefore does not establish a funding-neutral sample. A corrected rerun would need to identify trades overlapping settlement timestamps and apply symbol-specific funding rates.
4. **Drawdown is trade-close-only**, not intratrade adverse-mark DD.
5. **Trade-through is an upper-bound execution proxy, not a queue fill.** A trade printing through the limit does not prove that the hypothetical order would have been filled given queue priority and available size.

## Interpretation of existing OOS results

The existing maker report's OOS returns are deeply negative across BTC/ETH/SOL and the tested horizons. Correcting the missing taker-entry slippage or adding funding at settlement crossings cannot plausibly turn those results into a positive edge; however, no exact corrected PnL is claimed here.

The existing cost-aware report also contains negative OOS cells. Its round-trip slippage accounting is not double-counted; the main limitations are synthetic maker fills, trade-close-only drawdown, and absent funding/liquidation.

## Decision

- **Do not promote** either BookDepth strategy.
- Do not use these microstructure report drawdowns as substitutes for MEAFLOW-72 hourly adverse-mark DD.
- The most consequential unmodeled dimensions for any future short-horizon futures execution test are funding settlements for trades crossing 00/08/16 UTC and intratrade adverse excursion.
- This was a static audit only. No strategy, signal threshold, or protected MEAFLOW branch was modified. No Actions run was started.
