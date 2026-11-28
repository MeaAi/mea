# EXP-047 Preregistration — Basis Incremental to Funding

Date: 2026-11-28
Parent: MEAFLOW-72 protected SHA `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`
Branch: `research/exp047-basis-funding-incremental`
Status: preregistered; implementation and run pending.

## Question
Does spot/perpetual basis provide incremental out-of-sample cross-sectional predictive information beyond MEAFLOW-72's existing trailing 7-day settled funding score?

## Motivation and non-duplication
EXP043 was a univariate basis screen; it did not condition on funding. EXP044–046 examined peer/leader return features, not basis. EXP047 therefore tests a distinct unresolved question. It must not repeat the rejected EXP043 univariate gate or the algebraically non-identifiable EXP045 peer-mean feature.

## Frozen universe and data
BTCUSDT, ETHUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, SOLUSDT, LINKUSDT, LTCUSDT, BCHUSDT, DOTUSDT, TRXUSDT, AVAXUSDT. Free official Binance Vision archives only. Sample: 2023-01 through 2026-10. Spot and USD-M 1h klines plus USD-M funding-rate events; verify archive checksums where available and report missing symbols/timestamps. Use completed bars only.

## Definitions and timing
Primary basis premium in bp = 10,000 * (USD-M perpetual close / spot close - 1). This is explicitly the opposite sign of the quarterly-futures convention (spot - futures)/futures in Chi et al. (2023); signs must never be silently mixed.
At a weekly rebalance timestamp, use only the latest fully completed UTC hourly bar. Funding score is the sum of settled funding events in the preceding 7*24 hours, matching the strategy's trailing funding concept. Basis candidates are level and trailing 1d, 3d, 5d, and 7d changes, each calculated only from completed hourly bars. Target: next 7-day USD-M perpetual return (primary); next 1-day return secondary. Weekly samples are non-overlapping for the 7d target.

## Models
For each timestamp, form a cross-sectional model using the 13 symbols:
- M0: timestamp cross-sectional mean only (diagnostic reference).
- M1 baseline: funding score only.
- M2a: funding + basis level.
- M2b–M2e: funding + one prespecified basis change (1d/3d/5d/7d), tested separately.
No feature selection or OOS parameter tuning. Standardize predictors within each training sample only. Use chronological train/validation/OOS splits, with the last 30% of weekly timestamps reserved as OOS. Validation may select only the prespecified regularization strength from a small fixed grid; report it. Keep OOS untouched until final scoring.

## Structural-break and robustness checks
Report full OOS and pre/post 2025-09-18 08:01 UTC (Binance funding/mark calculation change) separately. Report bull/bear/sideways using the frozen BTC trailing-30d +/-5% regime definition. Report results per year and per symbol. A post-change-only result cannot be generalized to the full history.

## Advancement gates
1. At least one preregistered basis feature has positive incremental OOS R² versus M1, with paired 7-day moving-block bootstrap 95% CI lower bound > 0.
2. The feature's incremental effect is not solely driven by one year or one regime.
3. Its high-minus-low cross-sectional portfolio proxy is positive after conservative 10bp round-trip costs.
4. No leakage, timestamp misalignment, archive integrity failure, or unresolved structural-break artifact.
If any gate fails, reject without tuning. Passing this screen authorizes a separate MEAFLOW-72 portfolio simulation only; it does not authorize promotion.

## Portfolio stage (only if screen passes)
Copy MEAFLOW-72 unchanged except for the single passing basis overlay. Compare matched 100 USDT, 1x portfolios with 5bp fee + 2bp slippage per side. Require higher net return AND less-negative hourly adverse-mark maximum drawdown. Report final equity, return, DD, fees, slippage, rebalances, liquidation, and bull/bear/sideways attribution.

## Literature / interpretation cautions
- Chi et al. (2023), DOI 10.1002/fut.22425, studied dated quarterly futures, not perpetuals; its basis sign convention differs.
- Cao, Zhai & Luo (2024), “Anatomy of cryptocurrency perpetual futures returns,” is directly about perpetuals, but its abstract does not establish incremental value over this strategy's funding score.
- Binance mark price blends index, funding and order-book components; therefore mark-vs-spot is not the primary basis definition.
- Binance announced a funding/mark methodology change effective 2025-09-18 08:01 UTC; explicitly stratify.
