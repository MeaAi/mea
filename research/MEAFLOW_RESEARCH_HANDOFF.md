# MEAFLOW Research Handoff / Continuity Ledger

Last updated: 2026-11-27
Repository: https://github.com/MeaAi/mea
Purpose: prevent repeated experiments across chat sessions. Read this file before proposing or running another experiment.

## Non-negotiable rules
- Never modify the protected strategy branches `MEAFLOW-72` or `MEAFLOW-52`.
- All experiments live on isolated `research/*` branches. Never merge or promote without explicit user approval.
- No live orders, API keys, or real-money trading.
- Use free official Binance Vision data (monthly `fundingRate` and 1h `markPriceKlines`) unless the user explicitly authorizes another free source. No paid data.
- Standard evaluation: 100 USDT initial capital, 1x leverage, 5 bp one-way fee + 2 bp one-way slippage. Include fee sensitivity when useful. Restart each independent window at 100 USDT; no compounding between windows.
- Report net-of-cost returns, max drawdown, ending equity, trade/rebalance counts, liquidation flags, symbol attribution (especially BTC/ETH/SOL), and limitations.
- Do not present estimates, synthetic data, in-sample results, or previously inspected windows as validated OOS profitability. Never claim a test ran unless a completed workflow/report proves it.
- Existing 1h OHLC adverse drawdown/liquidation calculation is an approximation, not Binance's exact liquidation engine. Maker queue/partial fills are not modeled in these funding carry tests; fixed slippage; static 13-symbol universe has survivorship bias.
- Do not force the strategy toward a target bp return. Accept only robust, realistic net results.

## Frozen MEAFLOW-72 baseline
- 7-day funding lookback; 7-day rebalance.
- Long lowest 20% funding scores; short highest 20%.
- BTC trailing 30-day mark-price regime threshold +/-5%.
- Bull: both long and short; bear: short-only; sideways: hold existing positions (no new entries/additions); unknown: flat.
- Standard capital/cost assumptions above.

## Fixed symbol universe
BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, SOLUSDT, LINKUSDT, LTCUSDT, BCHUSDT, DOTUSDT, TRXUSDT, AVAXUSDT.

## Completed experiments — do not repeat without a specific methodological correction
1. Causal determinism recheck
   - Branch `research/causal-determinism-recheck-v1`; run 45837832194.
   - CRC verified; no interpolation; reversed symbol order identical in 60/60 comparisons.
   - Window returns/DD: 2024 H1 +13.5181%/-25.90%; 2024 H2 -17.4381%/-32.04%; 2025 H1 +17.2985%/-32.4117%; 2025 H2 -20.0168%/-40.4355%; 2026 Jan-Oct +37.5261%/-17.2649%.

2. Sideways retention fixed anchor
   - Branch `research/meaflow72-sideways-retention-fixed-v1`; run 45867617649.
   - 100% hold +72.9428% / DD -26.5454%; 75% +64.2343%; 50% +55.6439%; 25% +47.1508%; 0% +38.8658%.
   - Fee sensitivity at 100% hold: 2bp +76.4356%; 5bp +72.9428%; 8bp +69.5166%.

3. Multiwindow sideways retention
   - Branch `research/meaflow72-retention-multiwindow-v1`; run 45868049092.
   - 2023: 100% +42.1559%, 75% +32.9301%, 50% +23.8838%, 25% +15.0386%, 0% +6.4565%.
   - 2024: 100% +14.1269%, 75% +13.2409%, 50% +11.9014%, 25% +10.0997%, 0% +7.9327%.
   - 2025 Jan-Sep data window: 100% +5.0690%, 75% +6.1313%, 50% +6.7169%, 25% +6.8464%, 0% +6.5722%.
   - Late window: 100% +72.9428%, 75% +64.2343%, 50% +55.6439%, 25% +47.1508%, 0% +38.8658%.
   - No universal retention winner.

4. Drawdown timing and attribution
   - Attribution branch `research/meaflow72-drawdown-attribution-v1`, run 45872432705; timing branch `research/meaflow72-drawdown-timing-v1`, run 45873577778.
   - Max DD: 2023 peak Mar 11 08:00 / trough Apr 18 11:00, -22.26%; 2024 peak Jul 5 09:00 / trough Aug 25 14:00, -35.68%; 2025 Jan-Sep peak Jun 22 20:00 / trough Jul 18 00:00, -34.44%; late window peak Oct 9 07:00 / trough Oct 10 21:00, -26.55%.
   - 2024 symbol net contribution estimates: BCH +28.47, BNB +26.65, ADA +15.53, AVAX +12.82, SOL -46.85, XRP -28.29 USDT. Attribution is approximate due to cross-margin/intrabar.
   - 2025 Jan-Sep: ADA -15.97, XRP -8.77, DOGE -4.27, ETH -2.95, DOT +12.79 USDT.

5. Regime cap and threshold sensitivity
   - Branches `research/meaflow72-regime-risk-cap-v1` run 45880867526; `research/meaflow72-regime-cap-isolation-v1` run 45881581252; `research/meaflow72-regime-threshold-sensitivity-v1` run 45883255212.
   - No universal best cap or +/-3/5/7.5/10% threshold. Adaptive caps reduce DD in some windows but can sacrifice returns. Do not blanket-reduce bear exposure.

6. Bear cohort attribution
   - Branch `research/meaflow72-bear-cohort-attribution-v1`; run 45885410622.
   - Bear-origin position PnL (price+funding, before costs): 2023 +32.59; 2024 -22.81; 2025 Jan-Sep -3.65; late +45.35 USDT.
   - PnL arising while market was bear (including execution costs): 2023 +9.31; 2024 -25.48; 2025 Jan-Sep -5.70; late +51.18 USDT. Severity cohorts not stable.

7. Regime persistence / debounce
   - Earlier 6h delayed-label test was not a true debounce; do not mislabel it.
   - True sequential debounce branch `research/meaflow72-true-regime-debounce-v1`; run 45889080062.
   - 6h debounce uncapped returns: 2023 +14.32% vs raw +42.16%; 2024 +38.05% vs +14.13%; 2025 Jan-Sep +0.94% vs +5.07%; late +69.42% vs +72.94%.
   - Bear cap 20% + 6h returns: 2023 +7.43%; 2024 +53.80%; 2025 Jan-Sep +9.48%; late +43.45%. Not universal.
   - Duration sweep branch `research/meaflow72-debounce-duration-sweep-v1`; run 45890192796. 3h/6h/12h were tested; no universal winner. Late 12h returns were high but not robust across prior windows.
   - Cost stress branch `research/meaflow72-debounce-cost-stress-v1`; run 45890472535. 3h beat raw in 32/64 paired comparisons; it won all 2024 and late cost cases but lost all 2023 and 2025 Jan-Sep cases. Not promoted.
   - Cost stress report: https://github.com/MeaAi/mea/blob/research/meaflow72-debounce-cost-stress-v1/research-results/meaflow72_debounce_cost_stress.json

8. Drawdown-based exposure scaling
   - Branch `research/meaflow72-drawdown-scaling-v1`; run 45891543975.
   - Baseline vs Gentle vs Moderate net return / max DD:
     - 2023: +42.1559%/-22.2601%; +22.7836%/-18.7305%; +21.2845%/-17.5213%.
     - 2024: +14.1269%/-35.6759%; -12.7918%/-27.6489%; -9.0960%/-26.8593%.
     - 2025 Jan-Sep data cut: +5.0690%/-34.4392%; +8.0217%/-32.0972%; +2.3553%/-29.8877%.
     - Late data cut: +72.9428%/-26.5454%; +47.8230%/-26.5454%; +24.8796%/-26.5454%.
   - No overlay promoted. Exact date cuts in report, not full calendar September. Report: https://github.com/MeaAi/mea/blob/research/meaflow72-drawdown-scaling-v1/research-results/meaflow72_drawdown_scaling.json

## Completed experiment 9: causal inverse-volatility sizing
- Branch `research/meaflow72-volatility-sizing-v1`; Actions run 45896022724; completed success.
- Report: `research-results/meaflow72_volatility_sizing.json`.
- 13/13 symbols loaded; no data errors. Official free Binance Vision fundingRate + 1h markPriceKlines.
- Compared equal weights, 168h inverse-vol, 720h inverse-vol; 100 USDT, 1x, one-way fee 2/5/8bp and 2bp slippage. Causal hourly log-return volatility uses only completed candles strictly before rebalance; each side's gross exposure preserved after 0.5x-2.0x relative caps.
- At standard 5bp fee, net return / max DD:
  - 2023: equal +42.1559% / -22.2601%; 7d +22.8231% / -26.3818%; 30d +17.2909% / -25.9156%.
  - 2024: equal +14.1269% / -35.6759%; 7d +33.8113% / -32.0751%; 30d +29.5087% / -34.9079%.
  - 2025 Jan-06 Sep data cut: equal +5.0690% / -34.4392%; 7d +15.9660% / -22.9974%; 30d +9.4225% / -27.2171%.
  - 2025-09-07 to 2026-10-31: equal +72.9428% / -26.5454%; 7d +58.4721% / -20.9887%; 30d +61.1042% / -21.9849%.
- No liquidation in simplified model. At 5bp, 7d wins 2024 and 2025 Jan-Sep, but loses 2023 and late window; 30d likewise loses 2023 and late. Not universal; do not promote to baseline.
- 2025 first window dates are exact data cut 2025-01-01 08:00 to 2025-09-06 16:00 UTC, not full Sep. Late window 2025-09-07 00:00 to 2026-10-31 16:00 UTC. Prior historical windows already inspected; not pristine forward OOS.
- BTC/ETH/SOL attribution is included per config in report; note it is a simulator contribution estimate, not independent asset strategy performance.
- Workflow and report are reproducible from the branch; baseline protected branches unchanged.

## Current experiment in progress
- Branch: `research/meaflow72-volatility-sizing-v1`
- Experiment: compare equal weights against causal inverse-volatility weighting with 168h and 720h realized volatility.
- Only completed hourly mark-price candles strictly before each rebalance are used. Raw relative weights capped 0.5x-2.0x the basket mean, then renormalized so gross notional per long/short basket is preserved.
- Tests: 2023, 2024, 2025-01-01 through actual data cut 2025-09-06 18:24 UTC, and 2025-09-06 18:24 UTC through 2026-10-31 16:00 UTC. 100 USDT, 1x; fee sensitivity 2/5/8 bp one-way; slippage 2bp one-way.
- Report path expected: `research-results/meaflow72_volatility_sizing.json`.
- Workflow: `.github/workflows/meaflow72-volatility-sizing.yml`.
- Simulator copy: `research/funding_carry_liquidation_volatility.py`.
- Research driver: `research/meaflow72_volatility_sizing.py`.
- Completed; see section 9 above. Do not rerun unless correcting methodology.

## Next research queue after current experiment
- Inspect volatility-sizing results; if no stable net benefit, do not promote.
- Then prioritize missing market-microstructure validation: maker/taker split, limit-order non-fill and missed-trade simulation, fill probability, whale-size trade analysis, BTC/ETH/SOL separate results, realistic execution costs and out-of-sample design. Current funding carry data alone does not satisfy those order-flow requirements.
- Before any new experiment, check this ledger and the corresponding report/run to avoid repeating prior tests.
