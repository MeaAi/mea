# EXP-048 — MEAFLOW-72 leverage sweep (preregistration)
Date: 2026-11-28
Parent immutable strategy SHA: `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`
Branch: `research/exp048-meaflow72-leverage-regimes`

## Question
How do 1.5x, 2x and 3x leverage affect MEAFLOW-72 final equity, hourly adverse-mark maximum drawdown and liquidation risk across bull, bear and sideways regimes?

## Frozen implementation
- Use the exact MEAFLOW-72 strategy implementation from the parent SHA; no strategy signal/selection/holding rule changes.
- 100 USDT initial equity; leverage sweep includes 1x matched baseline plus 1.5x, 2x, 3x.
- 7-day settled funding score; weekly rebalance plus regime-change rebalance.
- Bull: both legs; bear: short-only; sideways: hold existing positions; unknown: flat.
- Public Binance Vision fundingRate and 1h markPriceKlines, frozen 13-symbol universe, 2023-01 through 2026-10.
- Costs: 5bp fee per side + 2bp slippage per side.
- Continuous portfolio simulation across regime transitions. Report final equity and max DD for each leverage, plus bull/bear/sideways PnL/cost attribution. Do not reset portfolio to flat at regime boundaries: that would misrepresent sideways hold semantics.
- Liquidation check: existing simulator's conservative hourly adverse OHLC stress with 0.5% maintenance-margin and 1% liquidation-fee assumptions; label as approximation, not exact Binance liquidation.
- No parameter tuning; do not promote any leverage based on return alone. Risk/return and liquidation must be evaluated together.

## Reporting
For each leverage: final equity, net return, hourly adverse-mark max DD, liquidation flag/time, rebalance count, price PnL, funding PnL, fees, slippage, and market-regime attribution. Also report baseline 1x.
This is a continuous multi-regime portfolio test; regime attribution is not a separate fresh-100-USDT backtest per regime. The sideways strategy carries positions from prior regimes by design, so standalone sideways tests starting flat are invalid.

## Decision gate
No change to MEAFLOW-72. Leverage is a risk-sizing parameter only. A candidate leverage is not accepted merely because it increases return; assess DD and liquidation. No live deployment.
