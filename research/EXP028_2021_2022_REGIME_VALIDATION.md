# EXP-028 — Independent 2021-2022 MEAFLOW-72 regime validation

**Status:** COMPLETED  
**Research branch:** `research/exp028-2021-2022-regime-validation-v1`  
**Evaluator commit:** `779ceac07d67601f7b33e8d012193d598a250d78`  
**Simulator commits:** event handling `8594b0bc4403f149b2f7b690e4a2b468feba8248`; rebalance gate `683deb30597b8252396bfd5fe69ff3f231493d7b`  
**Final Actions run:** `46132144557`, job `140939435063`, success  
**Artifact:** `exp028-2021-2022-regime-report`, ID `15258171771`, SHA-256 `b6d5411c3b2e29c26b32ecf271732d8ea5930371e2d5fdb060a064e02cc52183`

## Scope and data quality

- Evaluation: 2021-10-01 00:00 UTC through 2022-12-31 23:00 UTC.
- Context: September 2021 loaded for the trailing 30-day BTC regime and funding lookback.
- Frozen universe: BTC, ETH, BNB, XRP, ADA, DOGE, SOL, LINK, LTC, BCH, DOT, TRX, AVAX (13/13 loaded).
- Sources: free Binance Vision USD-M monthly fundingRate and 1h markPriceKlines. Monthly ZIP CRCs were checked. Funding timestamps were normalized to the nearest hour only when offset was <=100 ms (observed maximum offset 47 ms).
- Historical funding schedules were mixed: 1,371 common 13-symbol settlement events plus 75 SOL-only settlement events. The simulator now processes each symbol's valid funding settlement independently, while restricting portfolio rebalances to events with >=80% symbol coverage. This avoids dropping SOL's 4-hour settlements or rebalancing on a SOL-only event.
- 18 missing daily mark archives were supplemented from Binance Vision daily 1h markPriceKlines; every supplement passed its SHA-256 sidecar and ZIP CRC. Final hourly mark coverage is 100% for all 13 symbols.
- 1,446 usable funding events; 1,371 had full 13-symbol coverage. No unresolved data errors.

## Frozen MEAFLOW-72 result

Assumptions: 100 USDT, 1x, 7-day funding lookback, 7-day rebalance, 20% tails, BTC trailing 30-day regime threshold +/-5%, bull=both, bear=short-only, sideways=hold, unknown=flat, 5 bp one-way fee + 2 bp one-way slippage.

| Metric | Result |
|---|---:|
| Final equity | **218.133618 USDT** |
| Net return | **+118.1336%** |
| Hourly adverse-mark max DD | **-47.1792%** |
| Liquidation | No |
| Rebalances | 145 |
| Hourly adverse checks | 10,960 |
| Fees | 8.872895 USDT |
| Slippage | 3.549158 USDT |

## Controls and acceptance checks

| Configuration | Final equity | Net return | Max DD |
|---|---:|---:|---:|
| Frozen MEAFLOW-72 (sideways hold) | 218.133618 | +118.1336% | -47.1792% |
| Same regime policy, flatten in sideways | 169.316379 | +69.3164% | -48.2095% |
| Unfiltered both-side funding rank in every regime | 100.000036 | +0.0000% | -36.7618% |

- **Sideways hold vs sideways flat:** hold improved return by 48.8172 percentage points and improved max DD by 1.0303 percentage points. This passes the joint comparison gate in this independent historical window and supports retaining the existing sideways-hold behavior.
- **Regime policy vs unfiltered:** return improved by 118.1336 percentage points, but max DD worsened by 10.4174 percentage points. The joint gate fails; this does not justify a new strategy promotion.

## Regime coverage and attribution

| Regime | Hour count | Share | Rebalance events | Net PnL contribution |
|---|---:|---:|---:|---:|
| Bull | 2,732 | 24.909% | 35 | -31.309900 USDT |
| Bear | 5,761 | 52.526% | 53 | +121.397824 USDT |
| Sideways | 2,474 | 22.557% | 57 | +28.045694 USDT |
| Unknown | 1 | 0.009% | 0 | 0 |

Sideways had zero order deltas because the strategy held existing positions. Bull-regime PnL was negative while bear-regime PnL was strongly positive. This suggests a targeted bull-exposure hypothesis for a separate experiment, but does not itself prove that bull exposure should be removed.

## Symbol attribution (net contribution)

| Symbol | Net contribution |
|---|---:|
| BTCUSDT | +20.523844 USDT |
| ETHUSDT | +60.243948 USDT |
| SOLUSDT | +40.611026 USDT |
| LTCUSDT | -88.990700 USDT |
| DOGEUSDT | -6.935400 USDT |
| LINKUSDT | -5.153500 USDT |

The full 13-symbol attribution is retained in the JSON artifact.

## Fee sensitivity

| One-way fee | Net return | Max DD |
|---:|---:|---:|
| 2 bp | +123.6265% | -46.7093% |
| 5 bp | +118.1336% | -47.1792% |
| 8 bp | +112.7722% | -47.6453% |

## Limitations and decision

This is an independent historical validation window, not a future/live test. The adverse-mark DD and liquidation model remains an hourly OHLC approximation rather than Binance's exact portfolio-margin engine. Slippage is fixed at 2 bp one-way; no event-level L2 fills, partial fills, or market impact are modeled.

**Decision:** retain the existing sideways-hold rule as supported by this additional window; do not promote a new strategy. The frozen MEAFLOW-72 regime policy still shows a large -47.18% max DD in this historical bear/bull cycle and fails the joint gate against the unfiltered control. A separate, predeclared bull-exposure hypothesis may be screened on a research copy only.
