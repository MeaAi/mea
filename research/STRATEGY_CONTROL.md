# Strategy preservation and promotion rules

## Immutable reference

- Archive branch: `archive/baseline-7d-7d-20pct-2026-11-25`
- Baseline source commit: `4022dae73d75e92d8ee1c8a7bf1667d495634a6c`
- Experimental branch: `research/experiments-from-baseline`
- Original strategy: 7-day trailing funding rank, weekly rebalance, bottom 20% long / top 20% short, validation-frozen BTC 30-day regime policy.
- Capital: 100 USDT; leverage: 1x; one-way fee: 5 bp; one-way slippage: 2 bp.
- Reference OOS net return: +52.5355% (end equity 152.5355 USDT).
- Corrected hourly adverse-mark max drawdown: -25.5281%.
- Earlier event-close drawdown: -15.6567%. This is a different, less conservative measurement and must never be compared directly with the corrected hourly figure.

## Non-negotiable workflow

1. Never edit the archive branch. It is the rollback/reference snapshot.
2. Every new idea starts from a fresh copy of the current promoted strategy, on an isolated experiment branch or a separately named experiment.
3. Keep the promoted strategy unchanged while testing. Do not replace its parameters, risk policy, universe, sizing, or costs merely to make a candidate look better.
4. Change one strategy dimension at a time. Keep the same data, dates, costs, capital, sizing convention, and drawdown calculation for matched comparisons.
5. Select parameters only on chronological train/validation data. Freeze the candidate before opening OOS results. Do not tune against OOS.
6. A candidate is not promoted unless its OOS net return is strictly higher AND its OOS maximum drawdown is strictly less severe than the promoted reference, measured on the same corrected hourly adverse-mark basis, with no liquidation and realistic costs.
7. Also report trade count/rebalances, cost breakdown, OOS subperiods, symbol concentration, and slippage sensitivity. If a candidate fails any primary criterion, label it rejected and retain the promoted strategy unchanged.
8. Promotion means creating a new versioned snapshot. The prior promoted snapshot remains archived. The next experiment must branch from the newly promoted snapshot, never from an unverified experiment.
9. Never describe an in-sample/validation improvement as a successful strategy or production-ready result.

## Reporting

Every experiment report must identify its parent snapshot, the single change tested, validation selection rule, frozen OOS result, matched baseline result, and promotion decision. Keep failed experiments in the experiment history, but never overwrite the reference results.
