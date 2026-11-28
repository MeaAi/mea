# EXP-027 — Per-symbol hard-stop screening

**Status:** COMPLETED — rejected under the joint acceptance rule  
**Research branch:** `research/exp027-per-symbol-stop-loss-v1`  
**Final evaluator/simulator commit:** `b1d82160b381b3581700a3475bc683deff2fd1fa` / simulator `8a0bf367588b8f31e84c06134e5a8ab5a158ef6f`  
**Workflow:** Actions run `46131284255` (success), job `140936763175`  
**Artifact:** `exp027-per-symbol-stop-report`, ID `15258026545`, SHA-256 `2d86d2756b3fdf1ec6d30314fcdb655a47833406ea59fccbb8029175d5482add`

## Hypothesis and method

A hard adverse-price stop per symbol may reduce hourly adverse-mark drawdown without sacrificing net return. The experiment used a copy of the frozen MEAFLOW-72 simulator and the partial forward period 2026-11-01 00:00 UTC through 2026-11-26 23:00 UTC.

- Initial capital: 100 USDT; leverage: 1x.
- Universe: the frozen 13-symbol universe; all 13 loaded.
- Data: October monthly Binance Vision context, November 1-26 hourly markPriceKlines, public USD-M funding-rate mirror cross-checked against October Vision archive.
- 78 aligned funding events; 0 archive/data errors.
- Frozen strategy: 7-day funding lookback, 7-day rebalance, 20% tails, BTC trailing 30-day regime threshold +/-5%; bull both sides, bear short-only, sideways hold, unknown flat.
- Costs: 5 bp one-way fees + 2 bp one-way slippage.
- Stop trigger: hourly mark OHLC crosses the adverse stop from weighted-average entry; fill at stop, or worse hourly open if the bar gaps through. Stop exit pays the same one-way fee/slippage. Stopped symbols remain flat until the next scheduled/regime rebalance.
- Thresholds screened: 1%, 1.5%, 2%, 3%, 5%, 7.5%. No threshold was tuned or promoted.

## Results

Frozen baseline, no per-symbol stop: final equity **114.305877 USDT**, net return **+14.3059%**, hourly adverse-mark max DD **-14.7901%**.

| Stop threshold | Final equity | Net return | Max DD | Stop exits | Return delta vs baseline | DD delta vs baseline |
|---:|---:|---:|---:|---:|---:|---:|
| 1% | 113.712476 | +13.7125% | -4.8825% | 4 | -0.5934 pp | +9.9076 pp |
| 1.5% | 112.564058 | +12.5641% | -4.8825% | 4 | -1.7418 pp | +9.9076 pp |
| 2% | 111.421469 | +11.4215% | -5.4875% | 4 | -2.8844 pp | +9.3026 pp |
| 3% | 109.157749 | +9.1577% | -7.4077% | 4 | -5.1482 pp | +7.3824 pp |
| 5% | 113.547749 | +13.5477% | -9.2893% | 2 | -0.7582 pp | +5.5008 pp |
| 7.5% | 110.672481 | +10.6725% | -10.5362% | 2 | -3.6334 pp | +4.2539 pp |

## Decision

**REJECT / DO NOT PROMOTE.** Every stop threshold reduced maximum drawdown, but every threshold also reduced net return. None satisfied the required joint condition: net return must increase while maximum drawdown decreases.

The 1% stop gave the lowest observed DD (-4.8825%), but reduced return by 0.5934 percentage points. This is not an acceptable trade under the user's criterion.

## Limitations

- Only 26 calendar days and three scheduled rebalance events; all three occurred in bear regime. Bull and sideways behavior are not validated.
- Stops are modeled from hourly OHLC; intrabar path, queue position, market impact, and real stop execution are unavailable. Gap-through bars use the worse open, but fills otherwise assume the stop price plus fixed costs.
- This is an exploratory screen, not a full-month November validation or live execution approval.
- No MEAFLOW-72 or MEAFLOW-52 protected branch was modified.
