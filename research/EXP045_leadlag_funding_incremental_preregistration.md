# EXP-045 — Incremental cross-crypto signal conditional on MEAFLOW-72 funding rank

## Status
Preregistered research diagnostic. No strategy integration and no portfolio backtest until all gates pass.

## Protected baseline
- Parent experiment branch: research/exp044-cross-crypto-leadlag
- Parent snapshot: 12ee5ac2a92bb06e53370e7bab0c7a809d460d1c
- Protected MEAFLOW-72 lineage snapshot: a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1
- This experiment branch only. Do not modify MEAFLOW-72 or MEAFLOW-52.
- Frozen MEAFLOW-72 logic: 7-day trailing sum of completed funding events; 7-day rebalance; bottom 20% funding score long and top 20% short; BTC trailing 30-day mark return regime; bull both legs, bear short-only, sideways hold existing positions, unknown flat.

## Question
Does the 1h/4h cross-asset peer-return predictor from EXP-044 contain incremental information about subsequent target returns after conditioning on:
1. the target's own completed 1h return;
2. the broad market's completed 1h return;
3. the exact cross-sectional 7-day trailing funding score/rank used by MEAFLOW-72?

This is a predictive diagnostic, not a profitability claim.

## Data and timing
- Binance Vision public USD-M monthly fundingRate and 1h markPriceKlines; no keys or private endpoints.
- Universe fixed to the same 13 symbols as EXP-044.
- Funding score at decision time t is the sum of funding events in (t-7d, t], only when the event timestamp and its value are already observable at t.
- Price predictors use the last fully completed hourly bar before the forecast interval.
- Outcomes are forward log returns over 1h and 4h.
- Use strict common timestamps and record all dropped observations, missing archives and checksum/ZIP integrity status.
- Chronological split remains 50% train / 20% validation / 30% OOS. No OOS tuning.

## Estimator
At each timestamp, cross-sectionally demean target returns and predictors to remove the common market component. Estimate nested models:
- M0: own lag + market lag;
- M1: M0 + 7-day funding score/rank;
- M2: M1 + peer-ex-target lagged return.
Use timestamp-clustered inference with a 24-hour moving-block bootstrap over timestamps. Report incremental OOS R-squared of M2 over M1, peer coefficient, confidence interval, and per-symbol results. Also report the same comparisons by three chronological OOS subperiods and BTC bull/bear/sideways regimes.
Do not treat a raw correlation or an in-sample coefficient as proof of incremental value.

## Advancement gates
All required:
1. For 1h or 4h horizon, M2 improves OOS prediction over M1 (positive incremental OOS R-squared).
2. 95% moving-block bootstrap CI for incremental OOS R-squared excludes zero on the positive side.
3. Peer coefficient sign is positive for at least 9/13 symbols and is not dominated by a single symbol.
4. Incremental effect is positive in at least 2/3 chronological OOS subperiods and is not confined to one BTC regime.
5. Results survive the strict data QA and no-lookahead audit.
If any gate fails, reject the signal for MEAFLOW-72; do not tune horizons or thresholds after seeing OOS.

## Important implementation check
The frozen MEAFLOW-72 source documents sideways = hold existing positions. EXP-045 must use this exact policy definition when reconstructing the funding score and must not silently substitute sideways-flat behavior. The predictive regression itself does not change portfolio positions.

## Portfolio test authorization
No portfolio test is authorized by this diagnostic alone. If passed, a separately preregistered portfolio experiment must compare matched baseline and candidate on the same dates with 100 USDT, 1x, 5bp one-way fee + 2bp one-way slippage, hourly adverse-mark drawdown and liquidation checks. Promotion requires both higher net return and lower max drawdown, chronological robustness and cost stress.

## Reporting
Report exact sample window/counts, funding observations per symbol, timestamp alignment, all model coefficients and CIs, incremental OOS R-squared, subperiod/regime results, data integrity and limitations. Do not report final equity or max drawdown because no portfolio simulation is performed here.
