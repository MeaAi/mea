# Strategy preservation and promotion rules

## Immutable reference (do not edit)

- Archive branch: `archive/baseline-7d-7d-20pct-2026-11-25`
- Baseline commit: `fc52095f1d44f13dc591ea42ea0a263e1306c0e9`
- Experiment branch: `research/experiments-v1`
- Strategy: 7-day trailing funding rank; weekly rebalance; bottom 20% long / top 20% short; validation-frozen BTC 30-day regime policy.
- Capital: 100 USDT; leverage: 1x; one-way fee: 5 bp; one-way slippage: 2 bp.
- Frozen OOS return: +52.5355%; ending equity: 152.535542 USDT.
- Corrected hourly adverse-mark maximum drawdown: -25.5281%.
- Earlier event-close maximum drawdown: -15.6567%. This is a different and less conservative metric; do not compare it directly with the corrected hourly measure.

## Mandatory experiment protocol

1. Never edit the archive branch.
2. Start every new experiment from a copy of the current promoted strategy. Do not overwrite or mutate the promoted baseline.
3. Change one strategy dimension per experiment. Record the parent commit and exact change.
4. Keep data, dates, initial capital, leverage, fees, slippage, sizing convention, and drawdown calculation identical for matched comparisons.
5. Choose parameters on train/validation only; freeze the candidate before evaluating OOS. Never tune on OOS.
6. Promotion requires BOTH strictly higher OOS net return AND strictly less severe OOS maximum drawdown than the current promoted version, on the same corrected hourly adverse-mark basis, with no liquidation.
7. Also report costs, rebalance count, OOS subperiods, symbol concentration, and slippage sensitivity.
8. If either primary metric fails, reject the candidate and leave the promoted version unchanged.
9. When a candidate passes, create a new versioned archive snapshot. Only then may the next experiment branch from it.
10. Never label validation-only improvement as a successful strategy or production-ready.

Every report must include parent snapshot, single change tested, validation selection rule, matched OOS baseline and candidate, and promotion decision.
