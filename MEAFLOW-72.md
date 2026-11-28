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


## Research log — continuity record

This section is the cross-chat continuity record. Update it after each completed experiment. The strategy rules above remain frozen; entries below are research findings only and do not authorize strategy promotion.

### EXP-039 — Binance VWAP overlay
- Branch: `research/exp039-binance-vwap`.
- Method: BTC hourly close versus trailing volume-weighted price proxy; short-only overlay below VWAP. This is a rolling market-volume VWAP proxy, **not** on-chain holder cost basis or realized price.
- Full OOS, 100 USDT, 1x, 5 bp fee + 2 bp slippage per side: baseline final equity 186.708376 USDT (+86.7084%), hourly adverse-mark max DD -22.9746%; 155-day VWAP candidate final equity 205.279758 USDT (+105.2798%), DD -20.5861%; no simulated liquidation.
- Important limitation: USD-M quote volume used as VWAP weight while the reference price series is mark price; static 13-symbol universe and hourly OHLC adverse-mark approximation.

### EXP-040 — VWAP robustness
- Branch: `research/exp040-vwap-robustness`; workflow run: [46147976996](https://github.com/MeaAi/mea/actions/runs/46147976996).
- Full OOS matched result repeated EXP-039: baseline 186.708376 USDT / +86.7084% / -22.9746% DD; 155-day candidate 205.279758 USDT / +105.2798% / -20.5861% DD.
- Cost stress (5+2, 10+4, 15+6 bp fee+slippage per side): candidate passed the joint return-and-DD gate over the full period at all three cost levels.
- Chronological robustness: block 1 failed (baseline +61.8047%, candidate +58.6641%, both DD -20.5861%); blocks 2 and 3 passed. Therefore the result was not robust across all chronological blocks.
- Continuous full-period regime PnL attribution (not separate regime-account drawdown): baseline bull +24.739364 USDT, bear +63.214552, sideways -1.245540; candidate bull +41.041415, bear +65.217312, sideways -0.978968.
- Decision: research-only; not promoted.

### EXP-041 — isolated regime test attempt
- Branch: `research/exp041-regime-isolated-robustness`.
- Status: invalid/incomplete; no valid result artifact. Segmenting the continuous portfolio into isolated regime blocks broke the 155-day VWAP warm-up and the simulator's minimum aligned funding-event sample guard. Do not treat as a pass and do not repeat by merely lowering sample thresholds.
- Preferred future method: keep one continuous portfolio simulation and compute regime-conditioned diagnostics on its hourly series; label conditional drawdown separately from account-level maximum drawdown.

### EXP-042 — multi-period VWAP validation
- Branch: `research/exp042-multi-period-vwap`; workflow run: [46157998375](https://github.com/MeaAi/mea/actions/runs/46157998375); artifact: `exp042-multi-period-vwap-results` (ID `15268283261`).
- Frozen base SHA: `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`. 13 symbols; 100 USDT initial equity; 1x; 5 bp fee + 2 bp slippage per side; 135/155/175-day VWAP windows; no simulated liquidation.
- 2023-07-01 to 2024-07-01: baseline final 165.946813 USDT (+65.9468%), DD -27.3765%; all three VWAP candidates final 161.298949 USDT (+61.2989%), DD -27.3765%. All fail joint gate.
- 2024-07-01 to 2025-07-01: baseline final 101.655989 USDT (+1.6560%), DD -45.6233%. 135d: 98.545538 USDT (-1.4545%), DD -45.5170%; 155d: 101.487072 USDT (+1.4871%), DD -45.5170%; 175d: 97.717943 USDT (-2.2821%), DD -46.2352%. All fail joint gate.
- 2025-07-01 to 2026-10-31: baseline final 139.790161 USDT (+39.7902%), DD -41.8225%. 135d: 153.104823 USDT (+53.1048%), DD -41.8225%; 155d: 153.694714 USDT (+53.6947%), DD -41.8225%; 175d: 152.951112 USDT (+52.9511%), DD -41.8225%. All fail because DD did not improve.
- Latest 30% OOS (EXP-042's own date alignment): baseline final 187.594152 USDT (+87.5942%), DD -22.9746%; 135d final 203.030798 (+103.0308%), DD -20.5861%; 155d final 206.253641 (+106.2536%), DD -20.5861%; 175d final 205.255750 (+105.2557%), DD -20.5861%. All three pass the joint gate in this slice only.
- Caution: latest 30% OOS date alignment differs slightly from EXP-039/040; compare baseline/candidate only within EXP-042 for this slice.
- Decision: VWAP overlay is **not robust across calendar periods**; do not promote to MEAFLOW-72. It remains an experimental candidate only.

### Current research state / next step
- Active protected strategy: MEAFLOW-72. Do not change its frozen rules or promote VWAP based on EXP-042.
- All future experiments must use isolated research branches/copies. Main strategy code and MEAFLOW-52 historical reference remain untouched.
- Next investigation: continuous portfolio regime-conditioned analysis of VWAP effect, filter lag at regime transitions, and window sensitivity. Do not split the account into independent short regime simulations; report final equity and account-level hourly adverse-mark max DD from 100 USDT, plus regime attribution/conditional diagnostics.
- Hard acceptance gate remains: candidate must improve **both** net return and hourly adverse-mark max drawdown versus a matched MEAFLOW-72 baseline, with no liquidation, and must survive multi-period/OOS and cost-stress checks. Otherwise reject; no promotion.
