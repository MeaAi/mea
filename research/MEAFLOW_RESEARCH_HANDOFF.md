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


## EXP-014 — independent-period OOS completed (rejected)
- Branch: `research/meaflow-exp014-independent-oos-v1`; evaluator/report commit: `a20fd7b1688239770116774ed241a4789dfd916b`; Actions run `45967810555` completed success.
- Report: `research-results/exp014_independent_oos.json`.
- Calibration: 2024-05-01 to 2024-07-01 UTC; independent OOS: 2024-07-01 to 2024-09-01 UTC. BTC/ETH/SOL; 89,223 matched OOS minutes per symbol.
- Frozen q20/q80 thresholds from pilot only. Signals: OBI, taker quote-flow imbalance (OFI; not order-book OFI), >100k USDT aggTrade whale imbalance, and agreement combinations. 5/15/60m horizons.
- Execution: next 1m open entry, horizon close exit; 100 USDT per independent symbol/strategy/horizon, 1x, 100% current-equity sizing and within-series compounding; 5bp one-way fee +2bp one-way slippage (14bp round trip); market fills assumed. Funding not charged explicitly; no market impact or partial fills.
- Result: all 54 symbol/strategy/horizon combinations negative net return; all mean net bp/trade negative. Best net mean was still below costs: SOL three-way agreement 60m gross +3.5941bp, net -10.4060bp; SOL OFI+whale 60m gross +3.5619bp, net -10.4375bp. Example SOL three-way 60m: -61.9657% return, -64.0114% DD, final 38.0343 USDT. BTC OBI 60m: -73.1138%, -73.3972% DD, final 26.8862 USDT.
- Decision: reject; do not add to MEAFLOW-72/52. OBI/OFI/whale direction and simple agreement variants have now been explicitly tested out-of-period; do not repeat as novel.
- Limitations: coarse +/-1%/+/-2% BookDepth bands, not event-level L2; no queue position/maker fill reconstruction; taker market fills assumed; fixed slippage; no market impact; no explicit funding; 100% equity compounding is aggressive. July-August 2024 is independent within EXP-014 but may have been inspected in other broader research.
- Next candidate: EXP-015 event-level L2/maker fill calibration remains unverified/planned only. First verify a freely accessible source and schema; no claims of Tardis data availability until download and QA are actually complete.


## Continuity audit update — 2026-11-28 (EXP-017 through EXP-025 reconciliation)

This update records an audit of existing repository artifacts and the two workflows inadvertently started before the prior ledger had been read. No strategy experiment was started in this audit. Protected branches `MEAFLOW-72` and `MEAFLOW-52` were not modified.

### EXP-017 / EXP-019 full OOS order export — verified
- The full OOS export is `research-results/exp019_full_oos_order_events.json` on `research/meaflow-exp019-full-oos-order-events-v1`; blob SHA: `246f452f0b16b01cf9df50d085846dcda45967c1`.
- It contains 98 rebalance events, 56 events with order deltas, and 268 order deltas.
- The event split remains: bull 31 events / 177 order deltas; bear 25 / 91; sideways 42 / 0 (hold behavior).
- The report is an event export for execution research, not a new profitability result.

### EXP-018 / EXP-022 execution-sample overlap audit — completed
- EXP-022 report: `research-results/exp022_cryptohftdata_actual_order_replay.json`, branch `research/meaflow-exp022-cryptohftdata-order-replay-v1`, blob SHA `a36791a30be88b7f80dc26872b927122623ba57a`.
- EXP-022 contains 39 replayed order deltas. All 39 match an order in the 268-order EXP-019 full OOS export by exact UTC timestamp + symbol + side (and matching notional in inspected examples). Thus EXP-022 is a subset of the 268-event population, not 39 additional unique strategy orders.
- The earlier 15-order first-of-month sample (the EXP-018/Tardis probe sample) has 0 exact event-key overlaps with the 39 EXP-022 orders. Therefore do not add 15 + 39 as duplicated observations; they are disjoint order samples within the 268-order parent population.
- EXP-022 metrics: 39 total; 33 valid full-depth sweeps; 6 invalid/stale; valid-sample mid-price cost median 0.3807 bp, P90 0.807 bp, max 0.9422 bp, notional-weighted 0.3383 bp. Notional-weighted mark-reference difference 0.9820 bp (max 8.271 bp) includes signal-to-book timing movement and is not pure execution cost.
- Coverage is 39/268 = 14.55% of the parent order deltas. This is still a sample, not full-universe execution validation. Do not extrapolate its costs to every strategy order without qualification.

### EXP-019 stratified L2 duplicate workflow — invalid/inconclusive, not a strategy result
- Inadvertently started before the ledger audit: branch `research/meaflow-exp019-stratified-l2-sweep-v1`, Actions run `46105126975` (workflow job completed success).
- Report `research-results/exp019_stratified_l2_sweep.json`, blob SHA `eb371e5b559d0dad8b48d7ce36fa512f9244d823`, reports `completed_with_errors`; 6 selected events / 27 selected order deltas, but `summary_overall.orders_selected = 0`, no full-depth fills and no usable cost distribution. It therefore did not produce a valid L2 cost result despite the workflow job's green status.
- Treat as a duplicate procedural mistake and invalid L2 sample attempt. Do not count it as a successful execution-cost experiment and do not repeat it unchanged.

### EXP-025 November forward-validation workflow — FAILED before evaluation
- Inadvertently started before the ledger audit: branch `research/meaflow-exp025-nov-forward-validation-v1`; Actions run `46105517551`; job `140857266260`; final conclusion `failure`.
- Research evaluator blob SHA: `970e9cb1de72ac066525f4548be740c6421576b6`; simulator-copy blob SHA: `a855a2218d5caa92641e823d4f1133e481b15e03`.
- Intended UTC window: 2026-11-01 00:00 through 2026-11-27 16:00; 13-symbol frozen MEAFLOW-72 universe; monthly October context plus November daily Binance Vision fundingRate and 1h markPriceKlines.
- Configuration source was checked directly: `sim.run(data, (first, last), 1.0, 5, slip_bp=2, ...)`; simulator signature makes these 1.0x leverage and 5 bp one-way fee. Initial equity inside simulator is 100 USDT. Thus the prior chat's suspicion that this call used 5x leverage / 1 USDT capital was incorrect; configuration agrees with the report's stated 100 USDT / 1x / 5 bp fee / 2 bp slippage.
- The actual blocker was data acquisition: all 13 symbols had monthly context loaded (93 funding events and 1,368 hourly mark bars each), but November daily archive downloads failed across the symbols. The evaluator stopped with `Only 0 aligned forward funding events; need at least 60`. No strategy simulation ran, no performance report was published, and no net return / drawdown result exists.
- Status: FAILED / NO RESULT. Do not present this as a negative or positive strategy result. Do not rerun unchanged; first diagnose the daily archive URL/availability issue and obtain a complete, verified forward dataset. No change to MEAFLOW-72 or MEAFLOW-52.

### Ledger maintenance actions and remaining reconciliation
- This file was stale at revision v2: it ended at EXP-016 and did not include EXP-017 through EXP-025. The above audit entries reconcile the verified later artifacts and record the two accidental workflows.
- EXP-020 through EXP-024 remain represented in the prior conversation audit; retain their existing run IDs and decisions there: EXP-020 failed; EXP-021 source QA succeeded; EXP-022 completed as summarized above; EXP-023 Binance exchangeInfo QA failed with HTTP 451; EXP-024 min-notional sensitivity completed but all scenarios rejected (none increased net return while reducing drawdown). EXP-024 assumed filters are not verified historical exchange filters.
- Still to recover: exact Actions run IDs / immutable trigger and report commit SHAs for EXP-010–013; exact EXP-017/018 workflow metadata and report path for the 15-order sample; complete EXP-020/021/023/024 report-level code SHA and run provenance in one place.
- No new experiment is authorized by this audit. Next action is artifact/provenance recovery only; do not dispatch another workflow or create another experiment branch until the user explicitly asks to resume experiments.


### EXP-024 — minimum-notional sensitivity report cross-check
- Report `research-results/exp024_min_notional_backtest.json`, branch `research/meaflow-exp024-min-notional-backtest-v1`, blob SHA `aa203c88314ee222738203449254a29c1cb11503`; OOS data window 2025-09-06 18:24 UTC to 2026-10-31 16:00 UTC; 100 USDT, 1x, 5 bp one-way fee + 2 bp one-way slippage.
- Baseline: 100 -> 172.9428 USDT (+72.9428%), max DD -26.5454%.
- BTC/ETH historical minimums with modeled reduce-only exemption: 100 -> 170.8010 (+70.8010%), max DD -27.9299%.
- Default 5 USDT all-symbol floor with modeled reduce-only exemption: 100 -> 170.9526 (+70.9526%), max DD -27.9008%.
- Default 5 USDT all-symbol floor without reduce-only exemption: 100 -> 170.6170 (+70.6170%), max DD -28.4002%.
- All three filter scenarios reduce return and worsen drawdown versus baseline; reject. Historical non-BTC/ETH filter values were assumed, not verified. Binance exchangeInfo access was blocked with HTTP 451; quantity step sizes/minQty and actual live reduceOnly behavior are not validated.

### Existing EXP-013 maker trade-through and BookDepth cost report audit — 2026-11-28
- Existing maker report: `research-results/maker_trade_through_backtest.json` on `research/binance-data-pipeline`, blob SHA `9368508dd032a3071a309a38142647bf0eef50db`. BTC/ETH/SOL each have 86,340 matched minutes. The report uses train-only q80 thresholds, signal at minute t, passive limit at close(t), fill only if next-minute aggressive trade prints strictly through the limit, and exit at horizon close. Unfilled orders expire after one minute.
- Assumptions: 100 USDT, 100% equity notional compounded per filled trade, maker entry fee 2 bp, taker exit fee 5 bp, 0/2/4/6 bp exit-slippage sensitivity, 1x, no funding or liquidation. The reported observed fill ratio is only a strict trade-through proxy; it is not a queue-aware fill probability.
- OOS at 2 bp exit slippage (100 USDT independently per symbol/direction/horizon):
  | Symbol | Horizon | Long return / DD | Short return / DD |
  | BTC | 5m | -82.7894% / -82.8122% | -80.9429% / -80.9506% |
  | BTC | 15m | -63.6350% / -63.7293% | -56.5482% / -56.5510% |
  | BTC | 60m | -32.0354% / -32.2227% | -21.3332% / -22.4529% |
  | ETH | 5m | -83.3921% / -83.4123% | -83.1125% / -83.1125% |
  | ETH | 15m | -64.4012% / -64.5051% | -60.6211% / -60.6981% |
  | ETH | 60m | -31.9167% / -32.6206% | -21.1187% / -21.7586% |
  | SOL | 5m | -84.4063% / -84.4301% | -84.7528% / -84.7528% |
  | SOL | 15m | -66.4998% / -66.6063% | -65.8094% / -65.8444% |
  | SOL | 60m | -36.3899% / -38.1311% | -27.5882% / -31.5558% |
- All 18 OOS return cells are negative. Trade-through observed fill ratios are approximately 82.74%–91.58%, but queue position, quantity ahead, cancellation priority and partial fills are not reconstructed. The maker proxy does not establish a real execution edge. Do not rerun or promote.
- The expected `research-results/bookdepth_cost_backtest.json` on the same branch currently fetches as an empty file (zero content bytes; blob SHA `1206deff50fbe030fb883a1960f1e46b3d37e644`). Therefore its prior reported sensitivity results cannot be independently audited from that artifact as currently stored. The corresponding code/workflow may exist, but an empty JSON artifact is not an auditable result. Mark the report artifact as missing/invalid until recovered from the actual Actions artifact or a verified commit; do not infer a result from the workflow definition.
- Exact Actions run IDs for the EXP-013 workflows remain unrecovered. No rerun is authorized merely to reconstruct missing provenance.



### Correction — BookDepth cost report is present; previous empty-file diagnosis was a retrieval error (2026-11-28)
- Retract the statement above that `research-results/bookdepth_cost_backtest.json` is empty or missing. The GitHub Contents API confirms file size 1,327,223 bytes; blob SHA `1206deff50fbe030fb883a1960f1e46b3d37e644`. The earlier `fetch_file` response was incomplete for this large artifact; fetching the blob by SHA returned the complete JSON. Do not treat the artifact as missing.
- Verified Actions run for BookDepth cost-aware backtest: run `45283056380`, branch `research/binance-data-pipeline`, workflow `.github/workflows/bookdepth-cost-backtest.yml`, head commit `c62f8315f32d8b32c971d5ef64d85dc3a77d3b90`, completed success on 2026-11-23 22:47:50Z.
- Verified Actions run for maker trade-through: run `45357701812`, same branch, workflow `.github/workflows/maker-trade-through.yml`, head commit `b8079e7c328508c94ce9645e035f2df71532e2ba`, completed success on 2026-11-24 08:37:10Z.
- BookDepth report method: train-only q80 thresholds; non-overlapping events per symbol/direction/horizon; next-minute open entry and horizon-close exit; full-equity compounding. It is a sensitivity grid, not a queue-aware execution replay. Assumptions include 100 USDT, maker entry fee 2 bp, taker fee 5 bp per side, round-trip slippage scenarios 2/4/6/8 bp, maker fill-rate scenarios 25/50/75% selected deterministically by timestamp modulo 100, leverage 1/2/3x, funding omitted, liquidation not simulated.
- Complete report contains 864 OOS metric cells across BTC/ETH/SOL, horizons/directions, fee/fill/slippage/leverage scenarios. **0/864 OOS cells are positive**. Best OOS cell is SOL short 60m, synthetic 50% maker fill, 2 bp round-trip slippage, 1x: final equity 93.4062 USDT, return -6.5938%, max DD -13.6974%, 189 fills. This remains a negative result and is not evidence for promoting maker execution.
- Interpretation: deterministic fill-rate selection is a sensitivity assumption, not observed fill probability; no queue position, cancellation priority, partial-fill dynamics, funding or liquidation is simulated. Reject as a strategy improvement; retain as execution-cost sensitivity only.
- EXP-013 run IDs are now recovered for its two workflows above. The prior statement that those IDs remain unrecovered is superseded.



### EXP-010–013 Actions provenance recovery — 2026-11-28
- EXP-010 aggTrades + 1m kline acquisition / QA, EXP-011 BookDepth acquisition / coverage QA, and EXP-012 taker-flow / OBI-OFI diagnostics were all executed by the combined `Binance public-data research pilot` workflow. Verified successful run `45285733460` on `research/binance-data-pipeline`, workflow `.github/workflows/binance-research.yml`, run head SHA `3b430cdc7d720bf9a39800603493a5e11802bb40`, created 2026-11-23 23:05:41Z. Its job `138081444725` completed successfully and logs confirm production of `qa_report.json`, `bookdepth_qa_report.json`, `orderflow_diagnostic.json`, `bookdepth_signal_diagnostic.json`, and `report_strategy_backtest.json`. This run combines the three registry stages; do not count it as three separate workflows.
- An earlier successful run `45279379794` on the same branch/workflow, head SHA `730613558cb04b5ec80bc63780ea2bdbef986b9d`, also completed the `acquire-and-qa` job (`138059497908`) and produced the same family of reports. It is an earlier successful iteration, not an independent data period.
- EXP-013 BookDepth cost-aware workflow provenance: run `45283056380`, run head SHA `c62f8315f32d8b32c971d5ef64d85dc3a77d3b90`, job `138072189972` success. Its logs explicitly confirm 86,340 matched minutes per symbol and publication of `research-results/bookdepth_cost_backtest.json`.
- EXP-013 maker trade-through workflow provenance: run `45357701812`, run head SHA `b8079e7c328508c94ce9645e035f2df71532e2ba`, job `138319549492` success. Its logs confirm publication of `research-results/maker_trade_through_backtest.json`.
- These are workflow run head SHAs, not necessarily the final report-blob SHAs: the jobs themselves commit generated reports after running. Report blob SHAs are separately recorded above. No report artifact ZIPs were retained by these runs; the committed repository reports are the durable outputs.
- EXP-010–013 run IDs and run head SHAs are now recovered sufficiently to establish successful execution provenance. Earlier queue wording that their IDs were unrecovered is superseded. The exact per-file publishing commit SHA for the generated QA/diagnostic reports remains to be recovered from Git history; do not substitute the workflow head SHA for it.

### Queue status correction
- Queue item 1 (recover EXP-010–013 Actions IDs and run head SHAs): COMPLETED to the extent described above; exact generated-report publishing commit SHA remains an archival detail.
- Queue item 2 (audit BookDepth cost report and reconcile maker model): COMPLETED. BookDepth JSON is valid and fully retrieved by blob SHA; 864 OOS cells were checked, none positive. Maker trade-through remains a separate, queue-unaware proxy and all listed OOS returns are negative.
- Next work is provenance/report reconciliation for EXP-014–024, then independent-period data availability research. No new strategy experiment is authorized by this audit; do not dispatch a workflow or create an experiment branch merely to recover missing provenance.


### EXP-017–024 artifact and Actions provenance reconciliation — 2026-11-28

The following run SHAs are GitHub Actions `head_sha` values (workflow-trigger commits); code-file and report blob SHAs are listed separately. A green workflow means the job completed, not that its market-data sample was sufficient or its hypothesis passed.

| Experiment | Actions run(s) | Run head SHA (latest relevant) | Code blob SHA | Report blob SHA | Status / decision |
|---|---|---|---|---|---|
| EXP-017 signal alignment | `46071286731` | `d879ba61308648d49f8132884fb288e49682fbc0` | `9d9ec9feeb2ad4e0da6a7da6329f9c31fa60d364` | `5bba880eeaafbc23618a60a3f98f8bc4a848d364` | Completed audit; 268 order deltas across 98 events; no PnL claim |
| EXP-018 Tardis source probe | `46073949436` | `1ba34e79df586487973f909b6dcaf4f3b85c4fd5` | `da66859bfd99669d555069c5f815403ed9201865` | `e49631d2348a11934f9f0f0d202a84cddda658b7` | 22/22 range probes returned valid gzip prefixes; source probe only |
| EXP-018 actual order L2 | `46074200877` | `7d82a5f8860e644249ade995296a6f9ebcc99306` | `bb780f5b7d58acd07b55eea461ee531641f859ef` | `9988b30aa33251a14d5bc1d74f518d8f5ffd9d8a` | 12/12 displayed-depth sweeps completed |
| EXP-018B February L2 | `46076614948` | `954e11b7cfc9e6e826ddf251f961d0b2efc5d4e7` | `8f5d93c291d2fe4280af1efb259ca7bc0e2011f3` | `e5083745148b7718f4b0645fea69f7315801d1ee` | 3/3 displayed-depth sweeps completed |
| EXP-019 full OOS event export | `46098433866` | `768f7601a35c4b2d3f7ad940beb89dd3df9a03a6` | `75034ef49d523c5103b65f7fa17f919aa2dd630e` | `246f452f0b16b01cf9df50d085846dcda45967c1` | Completed event export |
| EXP-020 expanded L2 sample | `46098712772` (also failed attempt `46098669063`) | `b6f7a02d66d0f305da57e222a26a3bbe04563b94` | `e0c0d20f6f19819e0d7a0931845912b986ac2afa` | `d445769185b9309861672bab86e90a6a91187956` | Blocked by source access; no fill/cost inference |
| EXP-021 CryptoHFTData source QA | `46103131490` (earlier iterations also exist) | `2530a60375242882821ddedfa406469e603f40ec` | `0548dede4ac67b353655e1569a0139c72567e058` | `fe06b922d761d7fa51ea09e25c44314060708e35` | Workflow success, report status partial: 31 files tested, 23 downloaded/read, 8 failed, 3 sequence-gap files; not complete source coverage |
| EXP-022 actual order replay | `46103343368` (multiple earlier iterations) | `84f89ff8101ca3a6a15ed2b24657fa3003d2bcf2` | `ba726d61287ee8909ddb798730d59fad3b6566e4` | `a36791a30be88b7f80dc26872b927122623ba57a` | 39 selected; 33 valid full-depth; 6 invalid/stale; sample only |
| EXP-023 Binance filter audit | `46104388719` | `0e216cda40f059430d8facb2081946e41b67295f` | `29dd2c786c80d827ffc861eea70043d381129268` | No valid report artifact | Failed: exchangeInfo HTTP 451; no verified exchange filters |
| EXP-024 min-notional backtest | `46104587286` | `936c431f6395c69d9a86defe5e1c0d771e03c9c9` | `0ba7de3ce1eb1741d84e9ada29726426da243e0f` | `aa203c88314ee222738203449254a29c1cb11503` | Completed sensitivity; all variants rejected by joint return/DD criterion |

#### EXP-018 combined 15-order sample clarification
- The 15 direct L2 orders are 12 orders from 2025-10-01 and 2026-06-01 in report `exp018_actual_order_l2_sweep.json`, plus 3 orders from 2026-02-01 in `exp018_february_actual_order_l2_sweep.json`.
- Across all 15, mid-price execution cost median = 0.1757 bp, P90 = 0.6196 bp, max = 2.2041 bp, notional-weighted mean = 0.3038 bp. These are book-sweep execution costs versus mid; do not confuse with mark-reference differences, which also include signal-to-book price movement.
- All 15 orders had sufficient displayed depth in the captured snapshot. This is not proof of queue-aware passive fills or continuous market-wide execution quality.

#### EXP-021 source QA interpretation
- The final report has non-standard JSON `NaN` values in optional fields; when parsing for audit only, those values were normalized to null. Preserve the original report blob unchanged.
- Workflow success is only a successful QA script run. The report's own `status=partial`, 8 failed files and 3 sequence-gap files mean EXP-021 is not a complete validated historical L2 archive. EXP-022 replay used only the valid subset; retain its 33/39 valid coverage caveat.

#### EXP-022 replay interpretation
- The 39 replayed events are all members of the 268-order EXP-019 parent set; they are not additional independent strategy events. Exact timestamp + symbol + side matching confirmed 39/39.
- Do not add 39 to the 268 event count. EXP-018's 15 sampled orders are disjoint from these 39 by exact event key, but also belong to the same 268-order parent population.



### EXP-015 — source probe and queue-fill calibration are completed; prior PLANNED label is superseded
- Source probe branch `research/meaflow-exp015-l2-source-probe-v1`; report blobs: `exp015_source_probe.json` SHA `b6b1b687ba0be3c46f3547a366f147a1a1b30930`, `exp015_multisymbol_probe.json` SHA `235e643e0328ac66c97e2c9e43f65138d7769007`. Code/report metadata retained in the branch. Latest relevant source-probe run: `46027532688`, successful; workflow `.github/workflows/exp015-multisymbol-probe.yml`, run head SHA `4811612e8f213185ee8070a8a9c0cdb8e0715238`. Earlier source probe run `45999397797` also succeeded.
- Tardis public Binance Futures CSV archives were directly downloaded and gzip/schema-validated for 2024-07-01. BTC, ETH and SOL incremental_book_L2 plus trades were all usable. L2 file sizes were approximately 472.2 MB BTC, 416.5 MB ETH, 245.9 MB SOL; trade files approximately 21.3 MB, 21.8 MB and 11.4 MB. Each L2 file contained roughly 51–85 million rows. This is a very large daily data footprint; it is not a practical small-data feed.
- Queue replay branch `research/meaflow-exp015-l2-replay-v1`; code SHA `a6096bf319b74c85f561e1e454a3fd4f86468421`; report `research-results/exp015_l2_replay.json` SHA `9076ab35f62c6d11e60334097754f93b7de549ab`. Latest replay workflow run `46068879515`, success; head SHA `f556667972a35e1ddf366c2053de00d28657d2f3`. Several earlier iterations on the same branch are historical attempts, not separate data periods.
- Replay scope: 2025-02-01, 1,440 minute quote observations per symbol, BTC/ETH/SOL, 100 USDT analytical passive order at first valid L2 quote per minute. Total probes: 8,640 (1,440 per side x 2 sides x 3 symbols). This was NOT MEAFLOW strategy signals and is NOT portfolio PnL.
- Queue-aware lower-bound fill rates: BTC buy 23.75%, sell 26.25%; ETH buy 22.71%, sell 26.81%; SOL buy 42.64%, sell 42.92%. Strict-through upper-bound rates: BTC 74.10% both sides; ETH 87.22% buy / 87.01% sell; SOL 86.11% buy / 85.21% sell. Exact-price trade-hit rates were 94.0%–97.4%, but must not be mistaken for queue fills.
- Method limitations: Tardis feed is market-by-price, not market-by-order; exact FIFO queue position unavailable. Lower bound treats all displayed quantity at the quote as ahead and only observed same-price taker volume consumes it; upper bound requires a later aggressive trade strictly through the quote within a 60-second window. No fees, funding, portfolio PnL, market impact or partial-fill path reconstruction. Raw data was not committed; only compact reports and hashes were retained.
- Decision: source and schema are verified for sampled dates, and queue-fill bounds are materially more informative than trade-through alone. However, the pilot does not prove MEAFLOW-72 passive fill rates or profitability. Keep as execution-calibration evidence only; do not repeat the one-day probe unchanged or promote a maker strategy.
- This supersedes the EXP-015 source-audit wording that the actual download/schema remained unverified/planned. EXP-015 is COMPLETED as a sampled-day source and queue-bound calibration pilot, not a continuous strategy validation.

### EXP-014 provenance note
- EXP-014 final successful workflow run `45967810555`, branch `research/meaflow-exp014-independent-oos-v1`, evaluator/report commit `a20fd7b1688239770116774ed241a4789dfd916b`; report blob SHA `e642172899e8b712fbaa6a6116c0218a613a58df`; evaluator code blob SHA `0d8225dfd46183d8de793dde0bfa52901f298250`. Earlier failed attempts and their fixes remain recorded above. Final decision remains REJECT: 54/54 OOS combinations negative.

### Queue status correction after EXP-015 audit
- EXP-015 is no longer PLANNED: sampled-day Tardis L2/trades source QA and a 2025-02-01 queue-bound replay have both completed, with limitations recorded above.
- Next research question is not whether Tardis exists; it does for the sampled dates. The remaining gap is whether a larger, genuinely independent and affordable/free data window can be obtained and replayed with robust sequence reconstruction without committing raw multi-gigabyte archives. No new strategy workflow is started by this audit.


### EXP-025 failure root-cause correction — invalid daily fundingRate archive path (2026-11-28)
- Direct inspection of the failed evaluator `research/exp025_november_forward_validation.py` (blob SHA `970e9cb1de72ac066525f4548be740c6421576b6`) and Actions job `140857266260` logs identifies a code-level archive-cadence error, not a general Binance Vision outage.
- The loader requests `/data/futures/um/daily/fundingRate/{symbol}/{symbol}-fundingRate-YYYY-MM-DD.zip` for every day 2026-11-01 through 2026-11-27. Binance USD-M `fundingRate` archives are monthly, not daily. The public archive catalog distinguishes monthly fundingRate from daily-only BookDepth/bookTicker/metrics families; Binance's public-data docs describe daily/monthly archive publication, and independent archive tooling explicitly lists `fundingRate: monthly archives only`.
- The run log confirms 27 fundingRate download errors per symbol (13 symbols); this alone leaves zero forward funding events. In contrast, the November daily 1h markPriceKlines files had loaded through 2026-11-26; only the 2026-11-27 mark archive was not yet available at the 04:08 UTC run time. Each symbol showed 1,368 loaded mark bars (October monthly context plus November daily data through Nov 26).
- Therefore supersede the earlier statement that all November daily archives failed. The actual primary failure is that the code requests a nonexistent daily fundingRate archive family; the final day's mark archive was an additional publication-timing gap.
- Correct data design for a later rerun: load October and November fundingRate monthly archives (November archive only after Binance's monthly publication), and obtain November markPriceKlines from daily archives; exclude any not-yet-published final daily mark file or retry only after the next-day archive is available. Verify ZIP checksums and aligned timestamps before simulation. Do not rerun until the November monthly funding archive exists and the loader is corrected.
- Binance public-data docs state daily archives are published the next day and monthly archives on the first Monday of the month; therefore November's monthly funding archive is not assumed available on 2026-11-28. The first Monday of December 2026 is 2026-12-07; check the actual archive and checksum before use.
- This is a data-loader defect correction only. No strategy parameter change is implied. Keep the EXP-025 run failed/no-result until a separately versioned corrected run actually completes.

### Free data-source availability research — current findings
- Binance Vision remains the primary free source for continuous strategy data: public USD-M archives include monthly and daily aggTrades, daily/monthly klines and markPriceKlines, and monthly fundingRate. Daily files become available the next day; monthly files are published on the first Monday of the month. Official repository docs: https://github.com/binance/binance-public-data/blob/master/README.md
- Binance Vision BookDepth is a daily aggregated percentage-band depth archive; it is not event-level L2 and cannot reconstruct queue position. This data type was already used in EXP-010–014; do not relabel it as full L2.
- Tardis Binance Futures CSV is a useful no-key sampled-day source: its docs state first-day-of-month CSV datasets are downloadable without a Data API key, while its historical feed contains incremental L2 updates and trades. Source: https://docs.tardis.dev/historical-data-details/binance-futures
- Repository validation: EXP-015 successfully downloaded 2024-07-01 BTC/ETH/SOL L2 + trades, but those L2 files alone totaled about 1.13 GB for one day. EXP-018 probed first-of-month 2025/2026 dates and downloaded a small set of actual signal-time book observations. This confirms sampled-day availability, not a free continuous multi-month dataset.
- Practical conclusion: for free continuous OOS strategy validation, Binance Vision aggTrades + klines + monthly fundingRate + markPriceKlines are feasible. For queue-aware L2 calibration, Tardis can supply selected first-of-month samples, but a dense continuous multi-month replay has a prohibitive data-volume burden unless a carefully justified event subset is used. Do not start a full L2 download or new workflow without first measuring exact data volume and selecting a separate OOS period.



### Repository state check — 2026-11-28
- GitHub Actions query `status=in_progress` returned 0 active runs.
- Current `MEAFLOW-72` branch head observed: `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`. This audit made no writes to `MEAFLOW-72`; all ledger writes were confined to `research/meaflow-ledger-orderflow-audit-v1`.
- A branch named `MEAFLOW-52` is not currently returned by the repository branch search. No writes were made to any strategy branch or main branch during this audit. If the historical MEAFLOW-52 snapshot is needed, locate it by commit/tag or file history rather than assuming a current branch name.
- Current ledger branch head after this update will be the next audit checkpoint; new chats should read this file before any research action.


### EXP-025 corrected-loader preparation — isolated copy (2026-11-28)
- Created preparation-only branch `research/meaflow-exp025-monthly-funding-fix-prep-v1` from the failed EXP-025 branch head `f5a2e2f0433f813833efe572326e1bbd309ea5b4`; this is not the protected MEAFLOW-72/MEAFLOW-52 branch.
- Corrected loader commit: `93e032461343f5398949cafaf636175a89bcb836`; updated file `research/exp025_november_forward_validation.py`, blob SHA `2b55e741f7769e42b85f98055a9d74656aa1f161`.
- The copy now loads November 2026 funding from the single monthly USD-M `fundingRate` archive, while retaining daily 1h `markPriceKlines` for each date in the forward window. It verifies each November archive using Binance's sibling `.CHECKSUM` SHA-256 and ZIP CRC before parsing.
- The corrected copy requires all 13 symbols and all requested daily mark archives to pass; any missing archive/checksum blocks the simulation rather than silently changing the universe or producing a partial result.
- No workflow was added or dispatched. The existing workflow is push-triggered only on the original `research/meaflow-exp025-nov-forward-validation-v1` branch; the preparation branch is outside that trigger. No Actions run was intentionally started.
- Current date is 2026-11-28. November's monthly funding archive is not assumed available yet; check its actual presence and checksum after the documented first-Monday publication cycle (expected 2026-12-07), then verify every daily mark archive and timestamp alignment before any corrected run.
- This is code preparation only, NOT a completed experiment and NOT a strategy result. EXP-025 remains FAILED/NO RESULT until the separate corrected run completes. No MEAFLOW-72 or MEAFLOW-52 files or refs were changed.


### EXP-025 partial November forward test — public REST funding data (2026-11-28)
- User correctly noted that research need not wait for the November monthly funding archive. The isolated EXP-025 copy was adapted to retrieve November 1-26 funding settlements from Binance USD-M public `/fapi/v1/fundingRate` REST endpoint (no API key), while retaining October monthly history for lookback/regime context and November 1-26 daily 1h markPriceKlines.
- Forward window explicitly ends `2026-11-26T23:00:00+00:00`; Nov 27-30 are excluded. Any resulting report must be labelled PARTIAL NOVEMBER, not a full-month validation.
- Research branch: `research/meaflow-exp025-monthly-funding-fix-prep-v1`.
- Evaluator update commit: `e4213f9205f18bda6293ede9366015e7f645546e`; file blob SHA: `f70df9293b1343a4f863e4e582db5321b2a91344`.
- Isolated workflow added at `.github/workflows/exp025-partial-november.yml`; workflow commit: `22f9d3fa7459e0acc8c52b5466ed49fc01a4a83c`.
- GitHub Actions run `46128060060`, job `140926954658`, was observed IN_PROGRESS at 2026-11-28 08:55 UTC. This is a real run, but no performance result is available until it completes and its report is inspected.
- This run is a partial forward generalization check only; do not compare it as a complete November month. No MEAFLOW-72 or MEAFLOW-52 strategy files/branches were modified.


### EXP-025 partial November forward validation — completed result (2026-11-28)
- Final successful run: GitHub Actions run `46128516433`, job `140928355428`, head commit `134a75887ed6ae90f12227795152e806da7c737f`; artifact `exp025-partial-november-report`, artifact ID `15256941657`, SHA-256 `4a0da13fde73cdee4d646a72e432cbef5333da2a92e44f9204de29a03cde2358`.
- Period: `2026-11-01T00:00:00Z` through `2026-11-26T23:00:00Z` (26 calendar days inclusive; Nov 27-30 excluded). 13/13 symbols loaded; 78 aligned funding events; 0 archive/data errors.
- Funding source: public Binance USD-M funding-rate mirror at PipAI, cross-checked exactly against October monthly Binance Vision funding archives before accepting November values. Binance's direct REST host returned HTTP 451 from the runner; the mirror was publicly documented as unauthenticated and byte-identical to Binance's response schema. Funding timestamps had 1-5 ms offsets from exact hourly settlement boundaries; normalized only when within 10 ms. A separate run confirmed 78/78 timestamps align after normalization.
- MEAFLOW-72 frozen rules result: 100 USDT -> 114.305877 USDT; net return +14.3059%; hourly adverse-mark max DD -14.7901%; no liquidation; fees 0.211709 USDT; slippage 0.084684 USDT; 3 rebalances; 616 hourly adverse checks.
- Regime attribution: all 3 rebalance events occurred in bear regime (9 order deltas; 423.418314 USDT turnover). Bear net contribution +14.305877 USDT. Bull and sideways contributions were 0 in this sample; this period does not validate those regimes.
- Matched control with the same regime policy but `sideways_action=flat` produced identical metrics because no sideways rebalance event occurred. Therefore this period does not measure the hold-vs-flat effect.
- Unfiltered base funding-rank control (both long and short legs in all regimes), same data/costs/capital: final 101.286770 USDT; return +1.2868%; max DD -4.4752%. Regime-policy strategy gained +13.0191 percentage points more return but had 10.3149 percentage points worse max DD. The required joint gate (return up AND DD down) **FAILED**; no promotion is justified.
- The report's initial failed attempts were diagnostic, not performance results: run `46128060060` hit HTTP 451 on Binance REST; run `46128149929` exposed a 1-5 ms funding timestamp offset; run `46128193715` logged coverage; run `46128235908` exposed missing `rebalance_log`; run `46128324512` completed after the timestamp normalization; run `46128401155` had a transient HTTP 503 for TRX; run `46128452956` passed with matched sideways-flat control; final run `46128516433` passed with both controls.
- Research branch remains `research/meaflow-exp025-monthly-funding-fix-prep-v1`; final evaluator commit `134a75887ed6ae90f12227795152e806da7c737f`. Simulator-only reporting enhancement commit `0288ceb7638d75b0a6308c8629e09ec40812e961` adds the rebalance log; no strategy logic was changed.
- MEAFLOW-72 branch was not modified; its head remains expected to be checked independently after this entry. MEAFLOW-52 remains untouched. The partial November test is an early forward check, not a full-month validation or live-trading approval.


### EXP-026 — BookDepth backtest accounting audit (2026-11-28)
- Status: COMPLETED as a static code/report audit; no new Actions run or PnL rerun.
- Isolated audit branch: `research/exp026-bookdepth-accounting-audit-v1`; base microstructure branch head `2e0052cab074dd6828a390728d6ec7a2b83cda6a`; audit report commit `9ccc28e150aacac00e6e63e0f7e8f7f712e78874`; report `research/EXP026_BOOKDEPTH_ACCOUNTING_AUDIT.md`.
- Cost-aware BookDepth code: fees are consistent (5+5 bp taker/taker, 2+5 bp maker/taker); the 2/4/6/8 bp slippage parameter is explicitly a round-trip total and is charged once, so it must not be doubled. Equity compounds independently per symbol/direction/horizon/execution/leverage/split; trades are non-overlapping within each cell. Reported DD is trade-close-only, not intratrade adverse-mark DD. 2x/3x cells do not simulate maintenance margin/liquidation. Maker fill percentages are deterministic timestamp-modulo sensitivity samples, not empirical queue fills.
- Maker trade-through code: 2 bp maker entry + 5 bp taker exit fees are consistent. Slippage is explicitly exit-only; the taker/taker comparison does not include entry-side slippage and must not be described as a full two-sided taker execution-cost model. Funding is omitted even though a 5/15/60-minute trade can cross a 00:00/08:00/16:00 UTC funding settlement. Drawdown is trade-close-only. Trade-through is not queue fill proof.
- Decision: do not promote either microstructure strategy. Existing OOS results are deeply negative; the audit did not produce corrected PnL and makes no claim that cost corrections reverse the decision. Do not compare these DD figures to MEAFLOW-72 hourly adverse-mark DD.
- Protected branches remain read-only.

### Updated next queue after EXP-025 and EXP-026 (2026-11-28)
1. If revisiting the short-horizon maker/taker pilot, first build a separate corrected evaluator that charges funding on positions crossing actual settlement timestamps and explicitly models entry/exit slippage by execution side. Do not rerun the old model unchanged; prior OOS edge is strongly negative.
2. Extend Binance Vision aggTrades + BookDepth to a genuinely separate period (candidate 2024-07-01 through 2024-08-31) only after checking archive availability, checksums, and download volume. Keep the May-June 2024 pilot as training/calibration only; do not reuse its OOS split as independent validation.
3. For MEAFLOW-72 strategy work, prioritize a fresh independent market window and explicit regime coverage (bull/bear/sideways) before proposing another parameter tweak. EXP-025's Nov 1-26 partial period had only three rebalances, all bear; it does not validate bull or sideways behavior.
