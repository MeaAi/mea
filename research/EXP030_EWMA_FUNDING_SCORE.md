# EXP-030 — Causal EWMA funding-score screen

**Status:** COMPLETED — 24h half-life passes the exploratory joint gate; not promoted pending multiwindow validation  
**Research branch:** `research/exp030-ewma-funding-score-v1`  
**Simulator commit:** `15f6c00015423ce5bfc08863af02b22b5c87de00`  
**Evaluator commit:** `487348a448e365d216ffdb59736215675b471df8`  
**Workflow commit:** `f6ff1555a55317d20f48390f41c1e5e94d8089f1`  
**Actions run:** `46132632109`, job `140940946725`, success  
**Artifact:** `exp030-ewma-funding-score-report`, ID `15257894361`, SHA-256 `67a92353c9d71141add9d7c10408737bbb190b5f85259428d3f65b544ccb322f`

## Hypothesis and method

The frozen MEAFLOW-72 score is the simple sum of funding settlements over a causal 7-day lookback. EXP-030 tests whether emphasizing more recent settlements improves cross-sectional ranking.

For each funding settlement at time (t_i), the variant applies:

[
w_i = e^{-ln(2)cdot age_i / H}
]

where (H) is the half-life in hours. Only funding observations at or before the decision timestamp are included. Three predeclared half-lives were screened: 24h, 72h, and 168h.

All other strategy settings were unchanged: 2021-10-01 through 2022-12-31 UTC, 13 symbols, 100 USDT, 1x, 7-day lookback, 7-day rebalance, 20% tails, frozen MEAFLOW-72 regime policy, 5 bp one-way fee + 2 bp one-way slippage. Data quality and hourly mark coverage use the corrected EXP-028 pipeline.

## Results

| Configuration | Final equity | Net return | Max DD | Return delta vs baseline | DD delta vs baseline |
|---|---:|---:|---:|---:|---:|
| Frozen simple sum | 218.133618 | +118.1336% | -47.1792% | — | — |
| EWMA 24h | **229.888048** | **+129.8880%** | **-44.5344%** | **+11.7544 pp** | **+2.6448 pp** |
| EWMA 72h | 187.646998 | +87.6470% | -53.6416% | -30.4866 pp | -6.4624 pp |
| EWMA 168h | 220.846619 | +120.8466% | -47.1613% | +2.7130 pp | +0.0179 pp |

- **24h EWMA passes the joint gate** on this screening window: both return and max DD improve.
- 72h EWMA fails both metrics.
- 168h EWMA technically passes, but its DD improvement is only 0.0179 percentage points and is not meaningful evidence of a robust improvement.

## Decision

**24h EWMA is a candidate for multiwindow robustness validation, not promotion.** This is the same 2021-2022 period used to identify the hypothesis, so it is exploratory rather than independent confirmation. The next step is to test the preselected 24h variant across the previously inspected 2023-2026 windows, with each window reported separately. MEAFLOW-72 remains unchanged.
