# EXP-029 — Bull-flat regime policy screen

**Status:** COMPLETED — REJECTED under the joint acceptance rule  
**Research branch:** `research/exp029-bull-flat-regime-policy-v1`  
**Evaluator commit:** `b5cc13a854b3fbc81659fcc29e0504215e498bcd`  
**Workflow commit:** `ae3022e23b467accda15490290a16e3fde78cace`  
**Actions run:** `46132399208`, job `140940218312`, success  
**Artifact:** `exp029-bull-flat-policy-report`, ID `15258172111`, SHA-256 `8000ccae20e8a69e2cc28b9712eeac41aa9b9efe9c91cbfc4bdf01eb5203e3d6`

## Hypothesis

EXP-028 found negative bull-regime net contribution (-31.3099 USDT) under frozen MEAFLOW-72. EXP-029 tested one predeclared policy only:

- Bull: flat (close exposure)
- Bear: short-only
- Sideways: hold existing positions
- Unknown: flat

All other settings and the data window were held constant: 2021-10-01 through 2022-12-31 UTC, 100 USDT, 1x, 7-day funding lookback, 7-day rebalance, 20% tails, 5 bp one-way fee + 2 bp one-way slippage. The 2021-2022 data window and all checksum-verified daily mark supplements are identical to final EXP-028.

## Results

| Metric | Frozen MEAFLOW-72 | Bull-flat variant |
|---|---:|---:|
| Final equity | **218.133618 USDT** | 207.480120 USDT |
| Net return | **+118.1336%** | +107.4801% |
| Hourly adverse-mark max DD | -47.1792% | **-43.3646%** |
| Liquidation | No | No |
| Rebalances | 145 | 145 |
| Fees | 8.872895 USDT | 5.891676 USDT |
| Slippage | 3.549158 USDT | 2.356670 USDT |

Variant versus frozen baseline:
- Net return: **-10.6535 percentage points** (worse)
- Maximum DD: **+3.8146 percentage points** (less severe)
- Joint acceptance gate: **FAILED**

The bull-flat variant removed most of the negative bull contribution, changing bull net contribution from -31.3099 USDT to +1.6012 USDT. However, it also reduced bear and sideways contribution, so total net return fell. It did not meet the requirement to increase return and reduce DD simultaneously.

## Decision

**REJECT / DO NOT PROMOTE.** The simple rule “go flat in bull” reduces drawdown but sacrifices too much return. Keep frozen MEAFLOW-72 unchanged. This was an exploratory screen on the same period that motivated the hypothesis, not independent confirmation; no further validation is warranted for this rejected mapping unless a materially different rationale is established.
