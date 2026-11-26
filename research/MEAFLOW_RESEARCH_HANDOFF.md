# MEAFLOW Research Handoff / Continuity Ledger

Last updated: 2026-11-27
Ledger revision: v2 — reconciled with pre-existing Binance microstructure research branch
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

## Current experiment status
- No experiment is currently running in this ledger snapshot.
- Most recent completed funding-carry parameter study: causal inverse-volatility sizing, experiment 9 above. Do not rerun without a methodological correction.
- Existing market-microstructure pilot tests are already recorded as EXP-010 through EXP-013 below. They were present on `research/binance-data-pipeline` and were missed by the previous chat summary; do not repeat them as untested work.

## Experiment registry — Binance microstructure work reconciled 2026-11-27

This section was added after auditing the existing `research/binance-data-pipeline` branch. These are NOT new tests performed in this chat; they were already present in the repository and must be treated as prior work.

10. Official Binance aggTrades + 1m kline acquisition / QA
   - Branch: `research/binance-data-pipeline`.
   - Code: `research/binance_public_pipeline.py`; workflow: `.github/workflows/maker-trade-through.yml` and related research workflow.
   - Report: https://github.com/MeaAi/mea/blob/research/binance-data-pipeline/research-results/qa_report.json
   - Pilot period: 2024-05 through 2024-06; BTCUSDT, ETHUSDT, SOLUSDT.
   - Downloads official free Binance Vision USD-M monthly 1m klines and aggTrades; SHA256 checksums verified; aggregates aggressive buyer/seller quote/base volume, trade counts, whale-notional aggregates, and trade-through min/max prices.
   - This was data acquisition/QA, not a strategy profitability result. The data manifest shows 86,400 minutes per symbol-month (2 months); BTC May alone: 44,640 kline rows, 38,945,717 aggTrades, zero missing kline minutes, checksums verified.
   - Whale definition is a configurable individual aggTrade notional threshold (default 100,000 USDT); it does not identify a trader or wallet.

11. BookDepth acquisition / coverage QA
   - Branch: `research/binance-data-pipeline`.
   - Code: `research/binance_bookdepth_pipeline.py`; report: https://github.com/MeaAi/mea/blob/research/binance-data-pipeline/research-results/bookdepth_qa_report.json
   - Pilot period: 2024-05 through 2024-06; BTCUSDT, ETHUSDT, SOLUSDT.
   - Official Binance Vision USD-M daily bookDepth archives; SHA256 verified; 30-second snapshots aggregated into minute-level percentage-band depth features.
   - This is aggregated percentage-band depth, NOT full per-price L2 order book, order additions/cancellations, or queue position.
   - Coverage QA is recorded per symbol/month, including missing minute ranges. Never assume complete coverage.

12. Order-flow and OBI/OFI predictive diagnostics
   - Branch: `research/binance-data-pipeline`.
   - Taker-flow diagnostic code: `research/orderflow_diagnostic.py`; report: https://github.com/MeaAi/mea/blob/research/binance-data-pipeline/research-results/orderflow_diagnostic.json
   - BookDepth signal diagnostic code: `research/bookdepth_signal_diagnostic.py`; report: https://github.com/MeaAi/mea/blob/research/binance-data-pipeline/research-results/bookdepth_signal_diagnostic.json
   - OBI/OFI report uses chronological 50% train / 20% validation / 30% OOS, thresholds frozen from training, exact timestamp intersections, no interpolation. OOS is only the last 30% of the same May–June 2024 pilot; not a new-year or independent market-regime OOS.
   - OBI uses aggregate +/-1% and +/-2% depth-band notionals. OFI is aggressive taker buy-vs-sell quote imbalance from aggTrades, not order-book OFI. No fees, spread, slippage, funding, maker fills, or liquidation in the predictive diagnostic.
   - Key OOS directional mean returns (bp) from the existing report:
     - BTC: OBI 1m -0.032; 5m -0.1756; 15m -0.6713; 60m -2.6044. OFI 1m +0.0724; 5m +0.0287; 15m -0.4654; 60m -0.3593.
     - ETH: OBI 1m -0.1037; 5m -0.0981; 15m -0.3272; 60m -1.2296. OFI 1m +0.0240; 5m -0.1971; 15m -0.8256; 60m -1.2407.
     - SOL: OBI 1m -0.0993; 5m -0.6073; 15m -1.4450; 60m -3.0697. OFI 1m +0.2722; 5m +0.0226; 15m -0.6626; 60m -0.7459.
   - These are gross directional diagnostics, not net strategy results. Most horizons are negative; 1m positives are tiny and cannot establish tradable edge.

13. BookDepth cost-aware backtest and maker trade-through simulation
   - Branch: `research/binance-data-pipeline`.
   - Cost-aware code: `research/bookdepth_cost_backtest.py`; workflow: `.github/workflows/bookdepth-cost-backtest.yml`; report: https://github.com/MeaAi/mea/blob/research/binance-data-pipeline/research-results/bookdepth_cost_backtest.json
   - Maker code: `research/bookdepth_maker_trade_through_backtest.py`; workflow: `.github/workflows/maker-trade-through.yml`; report: https://github.com/MeaAi/mea/blob/research/binance-data-pipeline/research-results/maker_trade_through_backtest.json
   - Pilot period: 2024-05 through 2024-06; BTCUSDT, ETHUSDT, SOLUSDT; 86,340 matched minutes per symbol.
   - Cost-aware backtest tests 5/15/60m horizons, taker-taker and deterministic maker fill-rate sensitivities (25/50/75%), 1x/2x/3x and 2/4/6/8bp round-trip slippage. Important: maker fill is timestamp-modulo sampling, not empirical fill probability or queue simulation. Funding and liquidation are not modeled.
   - Maker trade-through test uses a 1-minute passive limit at signal-minute close. It counts a fill only if next-minute aggressive trade prints strictly through the limit; unfilled orders cancelled after one minute. This is a conservative trade-through proxy, but NOT proof of queue fill; no queue position/available quantity reconstruction. Entry maker fee 2bp, exit taker fee 5bp; exit slippage scenarios 0/2/4/6bp; no funding, 1x only.
   - Existing maker OOS (last 30% of the two-month pilot) results at 2bp exit slippage, net return with 100% equity compounded per trade:
     - BTC 5m long -82.7894%, short -80.9429%; 15m long -63.6350%, short -56.5482%; 60m long -32.0354%, short -21.3332%.
     - ETH 5m long -83.3921%, short -83.1125%; 15m long -64.4012%, short -60.6211%; 60m long -31.9167%, short -21.1187%.
     - SOL 5m long -84.4063%, short -84.7528%; 15m long -66.4998%, short -65.8094%; 60m long -36.3899%, short -27.5882%.
   - Observed trade-through fill ratios in this test are roughly 82.7%–91.6%, but these are NOT queue-aware real fill probabilities. All listed OOS strategy returns are strongly negative even before treating the proxy limitations as unresolved. Do not rerun as if untested; do not promote.
   - Workflow run IDs were not recovered in this audit; report files and workflow definitions exist in the branch. If needed, recover run metadata from GitHub Actions history rather than inventing IDs.

## Registry protocol — mandatory for every future experiment
- Assign sequential ID `EXP-###` before starting. Record status: `PLANNED`, `RUNNING`, `COMPLETED`, `FAILED`, or `BLOCKED`.
- Every record must include: hypothesis; exact code path and immutable commit SHA; research branch; data source and exact date range; symbol universe; train/validation/OOS boundaries; execution/fill model; fees/slippage/funding assumptions; starting capital/leverage/position sizing; metrics; workflow run ID + status; report path/link; limitations; decision (promote/reject/inconclusive).
- On completion, update this ledger in the same research branch/commit sequence as the report. Update the current status and next queue. Never leave a completed experiment labeled in progress.
- Before any new experiment, search this ledger, `research/binance-data-pipeline`, workflow definitions, reports, and Actions history for an equivalent prior test. If equivalent exists, cite it and extend only the missing dimension.
- Distinguish a test that has code/report from a test with a recovered completed Actions run. Never infer a successful run solely from a workflow file.
- No repeated parameter sweeps unless there is a methodological correction or a new independent dataset/window.

## Updated next queue (do not repeat completed pilots)
1. Recover exact Actions run IDs / timestamps for EXP-010–013 and record immutable commit SHAs.
2. Audit the existing `bookdepth_cost_backtest.json` and its accounting assumptions, then reconcile with maker trade-through report; avoid assuming its synthetic fill-rate sweep is measured fill probability.
3. Extend free Binance aggTrades + bookDepth data beyond May–June 2024 only after checking archive availability and data volume. Prefer a genuinely separate period for external validation, not a random split of the same 2-month pilot.
4. Improve maker execution only with a defensible queue model or label current trade-through results as an upper-bound proxy; no invented fill probability.
5. Then test whether taker-flow / depth features add incremental net value to frozen MEAFLOW-72 signals. Keep signal discovery and execution validation separated.


## EXP-014 — independent-period order-flow validation
- Status: PLANNED (not run; no result may be claimed).
- Hypothesis: previously observed taker-flow / aggregated-depth effects from May–June 2024 do not necessarily persist; test whether they generalize to a separate later period before any strategy integration.
- Proposed window: 2024-07-01 through 2024-08-31 UTC; BTCUSDT, ETHUSDT, SOLUSDT.
- Data: official free Binance Vision USD-M monthly aggTrades + daily bookDepth + 1m klines; verify every archive checksum and minute coverage before modeling.
- Train/calibration: freeze all signal thresholds using only the existing 2024-05 through 2024-06 pilot. Validation/OOS: 2024-07 through 2024-08 only; no refitting thresholds on the new window. Exact UTC joins only; no interpolation.
- Tests: (a) taker buy/sell imbalance alone, (b) whale-notional imbalance alone, (c) aggregated depth OBI alone, (d) agreement filters, (e) incremental value over frozen MEAFLOW-72 baseline signals. Separate BTC/ETH/SOL.
- Execution: next-minute taker entry/exit with 5bp one-way fee + 2bp one-way slippage and stress scenarios; maker trade-through reported only as a queue-agnostic proxy. Do not call it fill probability. Funding and liquidation must be modeled if holding extends through funding or leverage is above 1x.
- Capital: 100 USDT, 1x; explicit sizing and no compounding between independent symbol/window comparisons unless the test design specifies portfolio compounding.
- Acceptance: positive net expectancy after costs, stable across all three symbols or a justified narrowly scoped result, and no parameter refit on OOS. A positive signal-only mean is insufficient.
- Required implementation: separate calibration and test input paths; add checks that no OOS timestamps enter threshold estimation; immutable code SHA and completed Actions run ID; report all trades, missed/unfilled orders, fill-proxy counts, gross/net bp, fees, slippage, drawdown, ending equity, and BTC/ETH/SOL attribution.
- Blocker: current GitHub connector exposes read/write repository operations but no workflow-dispatch action. This plan remains PLANNED until a supported Actions run is actually started and completed; do not treat a pushed workflow definition as a test result.
