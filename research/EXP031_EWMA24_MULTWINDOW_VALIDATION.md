# EXP-031 — 24h EWMA multiwindow robustness validation

**Status:** COMPLETED — REJECTED; the 24h EWMA candidate did not generalize  
**Research branch:** `research/exp031-ewma24-multiwindow-validation-v1`  
**Evaluator commit:** `7e41c3e4b3d7d7f16df2c044ae62c2f765842efb`  
**Workflow commit:** `527817a847d0ea5c57c0441a0d78ada67a3ade40`  
**Actions run:** `46132872854`, job `140941700940`, success  
**Artifact:** `exp031-ewma24-multiwindow-report`, ID `15257968107`, SHA-256 `ea959b220a492da09eb6773688d01cb8280fae1b7a75a40b6d6ca58a1c2254c4`

## Purpose

EXP-030's 24h EWMA funding score passed the joint gate on 2021-2022. EXP-031 tested that preselected 24h half-life, without retuning, on four previously inspected 2023-2026 windows. These are robustness windows, not pristine OOS.

The frozen baseline and EWMA candidate used identical data, costs, universe, and strategy settings within each window. Data source was free Binance Vision USD-M monthly fundingRate and 1h markPriceKlines; daily mark gaps were supplemented with SHA-256-sidecar-verified daily archives. 13/13 symbols loaded; 94 monthly archives per symbol; 26 daily supplement archives; no data errors.

## Results

| Window | Frozen return | Frozen max DD | EWMA24 return | EWMA24 max DD | Return delta | DD delta | Joint gate |
|---|---:|---:|---:|---:|---:|---:|---|
| 2023 | +64.9657% | -20.6707% | +20.8647% | -25.6427% | -44.1010 pp | -4.9720 pp | Fail |
| 2024 | -7.8040% | -34.5262% | -14.4680% | -51.3395% | -6.6640 pp | -16.8133 pp | Fail |
| 2025 Jan 1–Sep 6 | +6.9240% | -38.1966% | -9.2958% | -51.3744% | -16.2198 pp | -13.1778 pp | Fail |
| 2025 Sep 7–2026 Oct 31 | +96.8362% | -27.0350% | +90.2347% | -25.5061% | -6.6015 pp | +1.5289 pp | Fail |

The 24h EWMA failed the joint gate in **all four** windows. In 2023, 2024, and 2025 Jan-Sep it reduced return and worsened DD. In the late window it improved DD by 1.5289 pp but reduced return by 6.6015 pp.

## Regime coverage

All four windows contained bull, bear, and sideways hours:

| Window | Bull | Bear | Sideways |
|---|---:|---:|---:|
| 2023 | 53.836% | 16.849% | 29.315% |
| 2024 | 48.190% | 21.368% | 30.442% |
| 2025 Jan-Sep | 35.900% | 24.241% | 39.859% |
| Late 2025-2026 | 28.343% | 30.914% | 40.743% |

Event coverage was complete across all 13 symbols in each window (2023: 1,095; 2024: 1,098; 2025 Jan-Sep: 746; late 2025-2026: 1,260 usable funding events).

## Decision

**REJECT / DO NOT PROMOTE the 24h EWMA funding score.** Its positive 2021-2022 result did not generalize to the previously inspected windows. No half-life retuning will be performed on these windows. The 24h EWMA mechanism should not be added to MEAFLOW-72.

The 2023-2026 baseline numbers in this report come from the corrected research-copy simulator (per-symbol funding settlements, common-event rebalance gate, and verified daily mark supplements); they should not be silently substituted for earlier historical reports produced by older simulator revisions. The within-window candidate comparisons are matched and use the same corrected simulator.

No MEAFLOW-72 or MEAFLOW-52 protected branch was modified.
