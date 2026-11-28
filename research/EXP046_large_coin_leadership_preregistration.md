# EXP-046 — Large-coin leader returns conditional on MEAFLOW-72 funding score

## Status
Preregistered diagnostic. No strategy integration or portfolio simulation unless predictive gates pass.

## Protected scope
- Branch: `research/exp046-large-coin-leadership`
- Parent research record: EXP-045 branch head `6c31d251ce0154496782ecd87446c424680de406`
- Protected MEAFLOW-72 lineage snapshot: `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`
- MEAFLOW-72 and MEAFLOW-52 are not modified.

## Research basis and hypothesis
The literature reports heterogeneous cross-crypto lead-lag effects: Guo et al. (2024) find positive cross-crypto return predictability in Binance spot data; Jia et al. (2023) report negative large-to-small coin predictability in intraday data. These are not assumed to transfer to our USD-M perpetual universe or hourly horizon.
Question: do lagged returns of a fixed large-coin proxy basket improve forecasts of non-leader symbols beyond own lagged return and the exact 7-day trailing funding score used by MEAFLOW-72?

## Fixed universe and feature design
- Data: Binance Vision public USD-M 1h markPriceKlines and fundingRate.
- Universe: same 13 symbols as EXP-045.
- Leader proxy basket, fixed before OOS: BTC, ETH, BNB, XRP, LTC.
- Follower targets: ADA, DOGE, SOL, LINK, BCH, DOT, TRX, AVAX.
- The paper's historical five largest set includes EOS; EOS is absent from our frozen 13-symbol universe, so LTC is used as the available fifth liquid large-coin proxy. This is an operational proxy, not a claim of contemporaneous market-cap ranking.
- For each follower target separately, predictors at decision time t are: target's last completed 1h log return; its trailing 7-day settled funding sum in (t-7d,t]; and the five leaders' last completed 1h log returns (each separate column).
- Outcomes: target forward 1h and 4h mark-price log returns from t to t+h.
- No cross-sectional demeaning or timestamp fixed effects: leader returns are common time-series predictors and would be absorbed by timestamp effects. Each follower is estimated separately, avoiding EXP-045's algebraic collinearity.
- Baseline: OLS using own lag + funding score.
- Candidate: LASSO using own lag + funding score + five separate leader lags. Alpha selected only inside the training split using chronological TimeSeriesSplit; scaling fit only on training data. No validation/OOS tuning.

## Sample and splits
- Fixed data window: 2023-01 through 2026-10 UTC.
- Strict common hourly mark-price timestamps across all 13 symbols.
- Chronological split: first 50% train, next 20% validation (reported, not used for tuning), final 30% OOS.
- Regimes use BTC trailing 30-day mark-price return: bull >= +5%, bear <= -5%, sideways otherwise.
- Report exact sample counts, archive QA, per-follower and pooled OOS metrics, alpha, selected leader coefficients, chronological thirds and regimes.

## Advancement gates
All required:
1. Pooled OOS incremental R² of candidate vs baseline is positive for at least one horizon.
2. Paired 24-hour moving-block bootstrap 95% CI for pooled incremental R² is entirely above zero.
3. At least 5/8 follower targets have lower OOS MSE than baseline.
4. Positive pooled incremental R² in at least 2/3 chronological OOS thirds and not confined to a single BTC regime.
5. No lookahead; data QA and model fit complete without leakage.

If any gate fails, reject this feature for MEAFLOW-72; do not retune horizons, universe or thresholds after seeing OOS.

## Portfolio authorization
This experiment is a prediction diagnostic only. It does not authorize a portfolio backtest. If all gates pass, preregister a separate portfolio experiment comparing matched MEAFLOW-72 baseline/candidate with 100 USDT, 1x, 5bp one-way fee + 2bp one-way slippage, hourly adverse-mark max drawdown and liquidation checks. Promotion requires both higher net return and lower max drawdown, chronological robustness and cost stress.

## Literature
- Guo, Sang, Tu & Wang (2024), *Cross-cryptocurrency return predictability*, Journal of Economic Dynamics and Control 163, 104863, DOI 10.1016/j.jedc.2024.104863.
- Jia, Wu, Yan & Liu (2023), *A seesaw effect in the cryptocurrency market*, Journal of Empirical Finance 74, 101428, DOI 10.1016/j.jempfin.2023.101428.
- Literature findings motivate the hypothesis only; neither paper validates this exact USD-M hourly test.
