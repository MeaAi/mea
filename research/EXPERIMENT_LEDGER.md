# MEAFLOW72 Research Ledger

Last updated: 2026-11-28
Protected strategy base: `MEAFLOW-72` at `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`

## Operating rules
- Never modify the protected `MEAFLOW-72` strategy branch for experiments.
- Run all experiments on isolated research branches/copies.
- Initial capital: 100 USDT; default leverage: 1x; baseline costs: 5 bp commission + 2 bp slippage unless an experiment explicitly specifies otherwise.
- Promotion gate: net return must increase AND hourly adverse-mark maximum drawdown must become less negative versus the matched baseline. If either condition fails, reject.
- Report test dates, data source, initial/final capital, net return, hourly adverse-mark max drawdown, rebalance/trade counts (label accurately), fees, slippage, liquidation status, and bull/bear/sideways breakdown where available.
- Do not repeat prior experiments without checking this ledger and the repository history first.
- Preserve scripts, reports, useful data, and failed experiment records. Do not delete useful files just to reduce repository size.

## Completed experiment: EXP-038 STH-SOPR
- Branch: `research/exp038-sth-sopr`
- Base SHA: `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`
- Final experiment SHA: `a257de34b3c1c2c30b3a30c21a74a67908c6f23e`
- GitHub Actions run: [46145537743](https://github.com/MeaAi/mea/actions/runs/46145537743)
- Artifact: `exp038-sth-sopr-results` (artifact ID `15263277954`; expires 2026-12-28)
- Data: Black Almanak daily STH-SOPR source, 1,427 rows, 2023-01-01 through 2026-11-27. Binance USD-M universe: 13 symbols.
- Matched OOS period: 2025-09-09T04:00Z through 2026-10-31T16:00Z.
- Assumptions: 100 USDT, 1x, 5 bp fee + 2 bp slippage.
- Baseline: final 172.942810 USDT; net +72.9428%; hourly adverse-mark max DD -26.5454%; 98 rebalances; fees 4.498733 USDT; slippage 1.799493 USDT; no liquidation.
- Variants:
  - Flat when 7d SOPR < 1: final 116.038297; +16.0383%; DD -26.5454%.
  - Half exposure when 7d SOPR < 1: final 137.965532; +37.9655%; DD -26.5454%.
  - Freeze new positions when 7d SOPR < 1: final 113.155573; +13.1556%; DD -26.5454%.
  - Wait for 2d recovery above 1: final 115.112158; +15.1122%; DD -26.5454%.
- Decision: REJECT all variants. None improves both return and max drawdown; full-period drawdown is unchanged while return is materially lower.
- Caveats: SOPR methodology includes self-transfers and is not equivalent to every commercial SOPR implementation. OOS is the matched overlapping period, not full 2023–2026 history. The reported rebalance count is not necessarily a count of individual fills. Review implementation details before relying on overlay semantics.

## Next experiments: proposed, NOT YET RUN
Priority 1 — Binance taker buy/sell pressure:
- Derive aggressive buy/sell volume imbalance from Binance USD-M public aggTrades or kline taker-buy fields.
- This is distinct from the previously explored OBI/OFI/order-book/whale signals, but check prior order-flow diagnostics and branches before implementation to avoid duplicating an equivalent feature.
- Use only completed candles/trades available at each decision timestamp; prevent lookahead.
- Test as an isolated overlay on a copy of MEAFLOW-72.

Priority 2 — Binance volume-weighted price/cost-zone proxy:
- Evaluate 7d, 30d, and 155d volume-weighted price references from public Binance data.
- Explicitly label as a market-volume price proxy, NOT actual holder cost basis.
- Check overlap with existing basis/carry research before implementing.

Priority 3 — Combined signal:
- Only combine signals if at least one standalone experiment shows credible out-of-sample promise; do not tune a combined model blindly.

## Current status
- EXP-038 is complete and rejected.
- The next taker-pressure experiment is only planned; no script, run, or result exists yet as of 2026-11-28.
- Keep the MEAFLOW-72 strategy branch unchanged.
