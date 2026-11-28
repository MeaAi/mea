# EXP-043 — Spot–Perpetual Basis Screen: Results and Decision

- Status: **Rejected at signal-screen stage; no portfolio backtest**
- Branch: `research/exp043-basis-factor-screen`
- Workflow run: [46161810096](https://github.com/MeaAi/mea/actions/runs/46161810096)
- Artifact: `exp043-basis-screen-results` (artifact ID `15269538906`)
- Run head SHA: `e181e71f0bd77218a5567b71837b3e0645251668`
- Data: Binance Vision official spot and USD-M futures monthly 1h klines; SHA256 verified
- Period: 2023-01-01 through 2026-10-31
- Universe: 13 requested symbols; all 13 loaded; no load errors
- Sample: 1,400 paired daily dates; 1,395 daily cross-sections; mean cross-section size 13

## Signal definition

At the completed UTC 23:00 hourly candle:
`basis_bp = (USD-M perpetual close / spot close - 1) * 10,000`.

Daily cross-sectional Pearson information coefficient (IC) was calculated between basis level and subsequent perpetual returns over 1 and 5 days. Confidence intervals use a 7-day moving-block bootstrap.

## Results

| Metric | Result |
|---|---:|
| 1d mean IC | +0.005704 |
| 1d median IC | -0.005903 |
| 1d 95% block-bootstrap CI | [-0.010362, +0.022331] |
| 5d mean IC | +0.005295 |
| 5d median IC | +0.003734 |
| 5d 95% block-bootstrap CI | [-0.020645, +0.035103] |
| High-basis minus low-basis quintile gross mean daily proxy | +0.013602% |
| Net mean daily proxy after assumed 10bp round-trip cost | **-0.086398%** |
| Positive daily proxy fraction | 46.81% |

Yearly 1d mean IC:
- 2023: -0.004619
- 2024: +0.004365
- 2025: +0.007194
- 2026: +0.018125

Regime 1d mean IC:
- Bull: -0.012665
- Sideways: +0.021072
- Bear: +0.020616

## Preregistered gate assessment

The preregistered conditions to advance were:
1. 1d IC bootstrap lower bound must be positive — **FAIL** (lower bound -0.010362).
2. High-minus-low mean daily proxy after 10bp round-trip cost must be positive — **FAIL** (-0.086398%).
3. Positive 1d IC in at least 3 calendar years — **PASS** (2024, 2025, 2026).

Overall: **FAIL**. The candidate is rejected before portfolio simulation. No parameter tuning and no portfolio test are authorized by this result.

## Interpretation and limitations

The raw average IC is near zero, the median 1d IC is negative, its confidence interval includes zero, and the simple spread proxy does not cover the assumed cost. The signal is also regime-dependent: the bull-regime IC is negative while sideways and bear ICs are positive. This is not sufficient evidence of robust incremental alpha.

This run did **not** implement the preregistration's planned incremental comparison against the existing 7-day realized funding-rank signal. That comparison is therefore **not measured**. However, the candidate already failed two independent preregistered advancement gates, so no extra data download or follow-up tuning is justified. Do not claim that basis has been proven to add no information beyond funding; the supported conclusion is narrower: this raw basis screen failed the pre-set advancement criteria.

Other limitations:
- Fixed 13-symbol universe introduces survivorship bias; delisted historical constituents are absent.
- Basis is sampled once daily and is not an intraday executable basis.
- The spread proxy is a diagnostic, not an account simulation; it excludes actual funding cashflows, per-symbol fees, slippage, spread, borrow, liquidation and compounding.
- No account-level final equity or maximum drawdown was computed.

## Final decision

- EXP-043: **Rejected; do not promote or integrate into MEAFLOW72.**
- No final capital or maximum drawdown is reported because no MEAFLOW72 portfolio backtest was run.
- MEAFLOW72 main remains untouched. All work stayed on the isolated research branch.
- Do not repeat this raw basis screen with alternative lookbacks/thresholds. Revisit only if genuinely new data or a materially different, independently justified hypothesis becomes available.
