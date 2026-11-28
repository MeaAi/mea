# EXP-043 — Spot–Perpetual Basis Factor: preregistered signal screen

Status: design only; no backtest result exists yet. This is a research branch, not a strategy change.

## Why this candidate
Prior EXP-039/040/042 VWAP work did not establish a robust improvement over MEAFLOW-72. Do not continue parameter-tuning that overlay.
Published empirical work on crypto futures reports that cross-sectional basis is a stronger return-predictor than momentum in its sample, and that daily factor returns were stronger than weekly/monthly horizons (Chi et al., Journal of Futures Markets, 2023, DOI: 10.1002/fut.22425). A 2024 study of perpetual-futures returns also identifies basis and price-volume factors as explanatory factors (Cao, Zhai & Luo, Journal of Futures Markets, 2024). These are hypotheses from external samples, not evidence that this implementation will work on our data.

## Hypothesis
The cross-sectional spot–perpetual basis contains information about subsequent relative returns that is not already captured by the 7-day realized-funding rank used by MEAFLOW-72. If incremental predictive information survives out-of-sample tests and realistic costs, a basis-aware ranking overlay may improve the portfolio.

## Required data
- Binance Vision spot 1h klines and USD-M perpetual 1h klines for the same 13-symbol universe.
- USD-M funding history and mark prices retained for matched baseline accounting.
- Synchronize timestamps; exclude incomplete bars and missing pairs; no forward-fill across gaps.
- Construct basis from synchronized spot and perpetual prices. Record both raw basis (bps) and annualized basis; do not use future settlement values.
- Keep the existing 13-symbol universe fixed for the first screen and document survivorship limitations.

## Stage gates — do not run a full portfolio test unless Stage 1 passes
1. **Data integrity:** timestamp alignment, missingness, symbol coverage, basis distribution, and no look-ahead unit tests.
2. **Incremental predictive screen:** compare basis rank with realized-funding rank and their combined rank. Evaluate next 1-day and 5-day relative returns using point-in-time features. Report cross-sectional rank IC, IC stability by calendar block and bull/bear/sideways regime, turnover, and confidence intervals using time-block bootstrap.
3. **Kill criteria:** stop if basis has no stable positive incremental IC over funding rank, if the sign flips materially across blocks, or if predicted gross edge is below estimated round-trip costs. Do not proceed to parameter grid search to rescue a failed signal.
4. **Portfolio test only if screen passes:** compare frozen MEAFLOW-72 baseline with one predeclared basis-aware candidate on identical timestamps, 100 USDT, 1x, fee/slippage assumptions. Test daily and 5-day signal holding periods as separately predeclared variants; do not optimize on final OOS.
5. **Acceptance:** candidate must improve both net return and hourly adverse-mark maximum drawdown versus matched baseline, with no liquidation; also survive chronological OOS blocks and 2x/3x cost stress. Otherwise reject and retain the negative result.

## Reporting requirements
For every portfolio run report final equity from 100 USDT, net return, hourly adverse-mark maximum drawdown, fees, slippage, funding PnL, price PnL, turnover, liquidation status, sample count, and bull/bear/sideways attribution. Regime attribution is not a separate account drawdown.

## Explicit exclusions
- Do not alter MEAFLOW-72 or MEAFLOW-52.
- Do not add VWAP to the main strategy.
- Do not repeat OBI/OFI, whale/order-flow, leverage, inverse-volatility sizing, beta-neutral, stop-loss, or sideways-position-management experiments under a new name.
- No live trading or API credentials.
- No claim of profitability from literature or an in-sample screen.

## References
- Chi, Y., Hao, W., Hu, J. & Ran, Z. (2023), “An empirical investigation on risk factors in cryptocurrency futures,” Journal of Futures Markets 43(8), 1161–1180. DOI: 10.1002/fut.22425.
- Cao, Y., Zhai, J. & Luo, P. (2024), “Anatomy of cryptocurrency perpetual futures returns,” Journal of Futures Markets.
