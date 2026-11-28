# EXP-044 — Cross-cryptocurrency lead–lag signal screen (preregistration)

## Hypothesis
Lagged returns of liquid leading crypto assets may contain incremental information about subsequent returns of other assets, through delayed information diffusion / cross-asset spillovers. This is a diagnostic hypothesis, not an assumption of profitability.

## Prior evidence and limits
- Guo, Sang, Tu & Wang (2024), *Cross-cryptocurrency return predictability*, Journal of Economic Dynamics and Control 163, 104863, DOI 10.1016/j.jedc.2024.104863. Binance spot sample 2019–2021; reports out-of-sample cross-coin predictability and long-short returns after costs.
- Jia et al. (2023), *A seesaw effect in the cryptocurrency market*, Journal of Empirical Finance 74, 101428, DOI 10.1016/j.jempfin.2023.101428. Reports negative lead–lag relationships in its intraday sample, especially large-to-small coin effects.
- These studies use different periods, universes and intraday frequencies. Sign and persistence are not assumed to transfer to our 13-symbol USD-M universe or 2023–2026 sample.

## Frozen scope
- Parent SHA: a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1 (protected MEAFLOW-72 snapshot).
- Research branch only: research/exp044-cross-crypto-leadlag.
- Universe: same 13-symbol MEAFLOW72 universe; note static-universe survivorship limitation.
- Data: Binance Vision USD-M hourly klines, UTC, checksum verified.
- Screen horizons: 1h, 4h, 24h ahead; predictor lags only completed prior hourly bars.
- Predictors: lagged BTC return and equal-weighted lagged return of the other eligible symbols; no future information. For target i, the peer basket excludes i.
- Benchmarks: target's own lagged return and broad equal-weighted market lag return.
- Primary evaluation: chronological train/validation/OOS splits; per-target and pooled cross-sectional IC; block-bootstrap confidence intervals; yearly and BTC bull/bear/sideways breakdown; sign stability.
- No threshold/window parameter sweep and no portfolio backtest at this stage.

## Advancement gates
Advance only if all hold:
1. OOS pooled IC is positive for at least one predeclared horizon and its 95% moving-block bootstrap lower bound is above zero.
2. The effect is positive for at least 9 of 13 target symbols and does not depend on one target or one predictor.
3. Sign is positive in at least 2 of 3 chronological OOS subperiods and is not exclusively one BTC regime.
4. Cross-asset predictor adds explanatory/predictive value beyond target own-lag and market-lag benchmarks in validation/OOS.
5. Before any strategy integration, run a separate incremental test controlling for the frozen 7-day funding-rank score. If funding-adjusted increment is not robust, stop.

## Stop rules
- Any look-ahead, timestamp alignment, checksum or missing-data integrity failure invalidates the run.
- If the OOS bootstrap interval includes zero, or sign is unstable, reject without tuning thresholds/horizons.
- If predictive edge does not survive cost-aware portfolio simulation after the incremental funding gate, reject.
- No portfolio simulation or parameter optimization is authorized by a raw predictive screen pass alone.

## Required reporting
Report sample counts, exact period, data integrity, IC and confidence intervals, symbol/year/regime breakdown, benchmarks, limitations. Do not report final equity or max drawdown unless a portfolio simulation is actually performed.

## Protection
MEAFLOW72 and MEAFLOW-52 are not to be edited. Any eventual portfolio experiment must be on a separate branch/copy and compared to matched baseline with 100 USDT, 1x, 5bp fee + 2bp slippage per side. Promotion requires both higher net return and lower hourly adverse-mark max drawdown, no liquidation, chronological robustness and cost stress.
