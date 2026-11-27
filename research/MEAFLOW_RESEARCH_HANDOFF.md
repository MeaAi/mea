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


## External research update — free market-data routes (2026-11-27)

Sources reviewed:
- Official Binance public-data repository: https://github.com/binance/binance-public-data
- Binance historical futures order-book documentation: https://github.com/binance/binance-public-data/blob/master/README.md (historical order-book download documentation)
- Tardis historical data details: https://docs.tardis.dev/historical-data-details
- Tardis downloadable CSV access: https://docs.tardis.dev/downloadable-csv-files
- Independent data audit (mm-lab): https://github.com/batuhanboztepe0/mm-lab/blob/main/docs/DATA.md

Findings / constraints:
1. Binance Vision publishes daily/monthly public archives. Official README confirms USD-M aggTrades, trades and klines; these remain the primary free historical trade source. Verify each target file and checksum rather than assuming archive completeness.
2. Binance Vision BookDepth is cumulative percentage-band depth, not a full event-level L2 book. Our existing OBI tests use that proxy and were weak/negative at most horizons. Do not build maker queue simulation from BookDepth.
3. An independent 2026-07 audit reports Binance USD-M bookTicker event-level L1 archives only from 2023-05-16 through 2024-03-30, after which publication stopped. This needs file-by-file verification for our selected symbols; it is not official confirmation of all symbols/dates.
4. Tardis documentation says historical downloadable CSV data includes trades, quotes, book snapshots and incremental L2; first day of each month is available without an API key. For Binance, confirm the exact futures exchange identifier, symbols, and actual files by GET/download before relying on it. Free monthly sample days can support queue-model calibration/cross-source QA, but not full continuous-period strategy validation.
5. Binance's historical futures L2 download docs describe T_DEPTH incremental L2 data, but access requires an API key whitelisted for the data download service; bulk requests can take hours and are limited to ranges under 7 days. Treat as access-controlled / not assumed free; do not make this the critical path.
6. Binance futures metrics endpoints for open interest and long/short ratios currently expose only a recent rolling lookback (documentation states latest 1 month for OI history and latest 30 days for top-trader ratios). These REST endpoints cannot provide the multi-year historical OOS dataset required. Use only for a future live/paper observation layer unless a verified free archive is found.

Research implications:
- Keep EXP-014 focused on free Binance Vision aggTrades + BookDepth + klines for a truly separate period. It can validate flow/price-impact features, but cannot claim queue-aware maker fills.
- Add a distinct queue-calibration experiment using Tardis's no-key first-of-month Binance Futures samples, if GET confirms data availability. Compare reconstructed L2 state and trade-through events to quantify how optimistic the existing maker proxy is. Do not extrapolate a one-day-per-month sample into a full-period fill rate.
- Candidate features worth testing against frozen MEAFLOW-72 signals: multi-horizon signed trade imbalance (1m/5m/15m/1h), CVD slope/acceleration, large-trade net flow (not just gross whale volume), trade intensity, price impact per unit signed volume, absorption (high signed flow with low subsequent price response), and depth imbalance only as a secondary confirmation. Use walk-forward thresholds and test incremental net PnL, not standalone classification accuracy.
- Do not add open-interest or long/short ratio filters to historical backtests until a verified historical source and point-in-time publication timestamps are available.
- These are research discoveries and proposed work, not completed experiments or profitability evidence.

## EXP-015 — free L2 sample / maker queue-model calibration
- Status: PLANNED (not run).
- Objective: quantify whether the existing aggTrade strict trade-through fill proxy overstates maker execution versus an event-level L2 replay.
- Candidate source: Tardis downloadable CSV / HTTP historical API, first day of each month available without API key according to provider docs; Binance USD-M futures exchange identifier and BTCUSDT/ETHUSDT/SOLUSDT must be verified by actual download first.
- Sample design: one first-of-month UTC day per month across available historical range; report coverage and gaps. This is execution-model calibration only, not a strategy OOS.
- Reconstruct book from snapshot + incremental L2 updates, enforce sequence/order integrity, then replay historical trades. Model queue ahead, cancellations, executions, partial fills, order expiry, and adverse selection where source fields support it. If public feed lacks enough information to determine queue priority, report lower/upper fill bounds rather than a point fill probability.
- Compare against existing strict trade-through proxy on identical signal timestamps and prices; report fill-rate bias, partial-fill distribution, missed fills, and post-fill adverse selection.
- No paid source. If data access requires payment/API key, mark BLOCKED and do not substitute synthetic fills.
- No strategy integration or main-branch changes.


## EXP-015 source audit update — 2026-11-27
- Tardis exchange identifier for Binance USD-M Futures is `binance-futures` (not `binance`, which is spot). The public downloadable CSV docs explicitly state that first-of-month historical files are available without an API key and that `incremental_book_L2` is available for FUTURES.
- Candidate file pattern to verify: `https://datasets.tardis.dev/v1/binance-futures/incremental_book_L2/YYYY/MM/01/BTCUSDT.csv.gz` and matching `trades` file. Candidate sample dates: 2024-07-01, 2024-08-01, 2024-09-01; symbols BTCUSDT, ETHUSDT, SOLUSDT.
- Documentation and public code references confirm the exchange slug and data types, but actual file existence, non-empty payload, gzip integrity, schema and date coverage have NOT yet been verified in this repository/runtime. Keep EXP-015 PLANNED. Do not report data as downloaded.
- Public research repo found: `Rubin-S/order-flow-imbalance` uses Tardis free first-of-month Binance Futures L2 + trades for 2026, with chronological development/holdout days. This is a methodology reference only; do not copy its results as our results. It demonstrates that the free sample-day approach is used for event-level OFI research.
- Additional external research repos demonstrate similar Tardis sample use, but no equivalent queue-aware maker test has been found in our repository. Still check the user repo registry before building any new code.
- New verification checklist: HTTP status; response byte count; gzip integrity; header/schema; symbol identity; min/max exchange and local timestamps; snapshot/reset flags; sequence continuity; trade/book timestamp alignment; empty-file vs missing-file distinction; first/last event coverage. Save manifest and SHA256.
- If files are available, EXP-015 must be explicitly a sampled-day execution calibration (not continuous OOS), and maker queue fill must be reported as bounds unless queue priority can be reconstructed from the feed semantics.


## EXP-016 — multi-horizon taker-flow absorption extension — COMPLETED (2026-11-26)
- Status: COMPLETED; workflow run succeeded.
- Hypothesis: unusually strong 5/15/60-minute signed taker quote flow with weak same-window signed price response indicates passive absorption; fade aggressive-flow direction.
- Prior-work distinction: EXP-012 tested same-minute OFI-extreme + candle-direction-failure proxies. EXP-016 uses cumulative multi-minute signed quote flow plus a conditional price-response quantile. Still an aggTrades + 1m OHLC proxy, not event-level L2 absorption.
- Branch: `research/meaflow-exp016-multihorizon-absorption-v1`.
- Evaluator: `research/exp016_multihorizon_absorption.py`, code commit `76c8103d015395ffc5700a829f4595f1933ee011`.
- Workflow: `.github/workflows/exp016-multihorizon-absorption.yml`; trigger commit `63b4da7b9427be4417e24ddf381ccb4c319c93b4`.
- Report commit: `acb214079097c363f3bbdaf5475a32b1076b42f9`.
- Actions run: `45902943168`, completed success; report: https://github.com/MeaAi/mea/blob/research/meaflow-exp016-multihorizon-absorption-v1/research-results/exp016_absorption.json
- Data: official free Binance Vision USD-M monthly 1m klines + aggTrades. Calibration 2024-05-01 00:00 UTC through 2024-07-01 00:00 UTC; OOS 2024-09-01 00:00 UTC through 2024-11-01 00:00 UTC. BTCUSDT, ETHUSDT, SOLUSDT. 87,840 minute rows per symbol in both calibration and OOS.
- Frozen thresholds: per horizon, calibration q80 absolute signed quote-flow imbalance; conditional q20 signed price response among high-flow windows. Contrarian signal; next-minute open entry; horizon close exit; non-overlapping trades.
- Execution/capital: 100 USDT per independent symbol/horizon series; 1x; full equity notional; 5bp one-way fee +2bp one-way slippage charged on entry and exit notionals. Market orders assumed filled. Funding not explicitly charged.
- OOS results (net return / max DD; ending equity):
  - BTC 5m: -94.9887% / -94.9887%; 2,128 trades; 100 -> 5.0113 USDT.
  - BTC 15m: -76.1938% / -76.1938%; 990 trades; 100 -> 23.8062 USDT.
  - BTC 60m: -31.4647% / -31.4866%; 277 trades; 100 -> 68.5353 USDT.
  - ETH 5m: -97.4891% / -97.4891%; 2,649 trades; 100 -> 2.5109 USDT.
  - ETH 15m: -82.9289% / -82.9289%; 1,202 trades; 100 -> 17.0712 USDT.
  - ETH 60m: -34.7657% / -34.7657%; 367 trades; 100 -> 65.2343 USDT.
  - SOL 5m: -97.7576% / -97.7576%; 2,705 trades; 100 -> 2.2424 USDT.
  - SOL 15m: -85.4321% / -85.4376%; 1,406 trades; 100 -> 14.5679 USDT.
  - SOL 60m: -50.8222% / -51.9936%; 428 trades; 100 -> 49.1778 USDT.
- Mean gross bp/trade for 60m was BTC +0.4175, ETH +2.4509, SOL -2.4094; all are below the 14bp round-trip fee+slippage assumption. Net mean bp/trade: BTC -13.5831, ETH -11.5491, SOL -16.4097. At 5m/15m gross edge is also near zero or negative. Win rates and profit factors in report.
- Decision: REJECT this contrarian multi-horizon absorption rule under tested assumptions. No integration into MEAFLOW-72 or MEAFLOW-52. Do not rerun as an untested idea.
- Limitations: OOS is a two-month 2024 window and may have been inspected in other research; not pristine unseen history. Not true event-level L2 absorption; no queue model, market impact or liquidation engine; fixed slippage; funding omitted for rare trades crossing 8h timestamps. Compounding full equity per trade makes large losses visible but is an aggressive sizing assumption; the negative per-trade expectancy is independently clear.


## EXP-014 — independent-period order-flow validation — RUNNING
- Triggered by branch-scoped workflow push after code/workflow freeze; this is an actual Actions run, not merely a prepared workflow.
- Run ID: `45957519970`; status last checked 2026-11-27 07:21 UTC: `in_progress`.
- Branch: `research/meaflow-exp014-independent-oos-v1`; workflow trigger commit: `8525c6980ae744da0c7d77dbbc40e1a868a9912c`.
- Current job state: checkout and Python setup succeeded; May-June calibration acquisition still in progress; July-August OOS acquisition, frozen evaluation, and report publication pending.
- No result/report exists yet. Do not infer success or failure from the workflow being queued/running.
- Scope remains frozen: May-June 2024 calibration, July-August 2024 OOS; BTC/ETH/SOL; OBI, taker imbalance, whale imbalance and agreement cohorts; 5/15/60m; 5bp one-way fee +2bp one-way slippage; 100 USDT 1x per independent series.


## EXP-014 run 45957519970 — FAILED BEFORE EVALUATION; syntax corrected
- Run `45957519970` completed with failure on 2026-11-27 07:44 UTC.
- Data acquisition succeeded for both calibration (May-June 2024) and OOS (July-August 2024). Binance Vision daily BookDepth archives had no missing days and checksums verified. Per-month feature coverage was approximately 99.93-99.94%; missing minute gaps were recorded by the pipeline.
- Evaluation did NOT execute: Python raised `SyntaxError: unmatched '}'` at line 183 in `research/exp014_independent_oos.py`. Therefore there is no EXP-014 performance result from run 45957519970.
- Corrected the extra closing brace in evaluator commit `858e8054bcb60a9cf388997b69e66415938c259e`.
- Added evaluator path to the one-time branch push trigger; follow-up run `45960711569` was created 2026-11-27 07:45 UTC and is currently running. It reacquires official data and reruns the frozen evaluator; no result exists yet.


## EXP-014 run 45960711569 — second failure; date-boundary fix
- Run completed failure 2026-11-27 08:11 UTC.
- Both calibration and OOS acquisition steps succeeded; evaluator ran after syntax fix but stopped on BTC pilot date validation.
- Root cause: pilot max timestamp lower bound incorrectly used 2024-07-01 00:00 UTC instead of 2024-06-30 00:00 UTC. This excluded the actual final June observation.
- Corrected bound to `1719705600000 <= pilot_max < 1719792000000` in commit `771d0898da9719b4a79bf44f371500a5dcd36559`.
- New run `45964033868` created 2026-11-27 08:13 UTC; status last checked: in_progress, calibration acquisition step running. No EXP-014 performance result yet.
