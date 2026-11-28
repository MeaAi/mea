# MEAFLOW-72 — Active Research Strategy

**Status:** Active research candidate; not approved for live trading.  
**Parent research snapshot:** research/sideways-transition-management-v1  
**Previous strategy:** MEAFLOW-52 remains preserved and unchanged.

## Lineage and scope

MEAFLOW-72 is a controlled successor candidate built from the MEAFLOW-52-era funding-carry configuration as represented in the causal research simulator. It is not a claim that the current experiment branch is a byte-for-byte clone of a separately versioned MEAFLOW-52 production codebase. The tested implementation reuses the same core funding-rank framework and baseline parameter set, then changes sideways-regime position handling.

## Frozen strategy rules

- Funding-rate lookback: 7 days.
- Portfolio rebalance interval: 7 days, with a rebalance when the detected market regime changes.
- Cross-sectional selection: bottom 20% funding-score symbols for longs and top 20% for shorts, subject to regime policy.
- Regime detector: BTC mark-price return over the trailing 30 days, using the last fully completed hourly mark candle.
- Bull regime: both long and short legs.
- Bear regime: short-only.
- Sideways regime: **hold the existing portfolio unchanged**; do not open new positions or add to existing positions until the regime changes.
- Unknown regime: flat.
- Research accounting: 100 USDT initial equity, 1x leverage.
- Reference cost case: 5 bp fee per side plus 2 bp slippage per side. Cost sensitivity also tested at 2 bp and 8 bp fee per side, with 2 bp slippage per side.

## Matched OOS result that motivated the candidate

Experiment: research-results/sideways_transition_management.json  
Window: 2025-09-06 18:24 UTC to 2026-10-31 16:00 UTC.

At 5 bp fee per side + 2 bp slippage per side:
- Net return: +72.9428%.
- Ending equity from 100 USDT: 172.9428 USDT.
- Maximum drawdown: -26.5454%.
- No simulated liquidation.

Cost sensitivity for the hold-existing variant:
- 2 bp fee per side: +76.4356%.
- 5 bp fee per side: +72.9428%.
- 8 bp fee per side: +69.5166%.

The OOS window was already inspected in prior research; it is not pristine unseen data. The simulator is an hourly OHLC stress approximation, not an exchange-accurate liquidation or order-book execution model.

## Promotion gates still open

Before live deployment or merging into a production branch, MEAFLOW-72 must pass:
1. A genuinely untouched forward/out-of-sample window.
2. Bull, bear, and sideways regime-specific attribution and transition-error analysis.
3. Higher slippage and fee stress, plus spread/market-impact sensitivity.
4. Maker/taker execution and limit-order fill-probability modelling.
5. Symbol-universe and leave-one-symbol-out robustness.
6. More realistic liquidation brackets and intrabar execution assumptions.
7. Reproducible comparison against the frozen MEAFLOW-52 baseline on identical dates and costs.

**Safety rule:** Do not edit or overwrite MEAFLOW-52. All further experiments must branch from MEAFLOW-72 or its research descendants. Do not describe MEAFLOW-72 as production-ready until the promotion gates pass.


## EXP-045 — Cross-crypto peer return incremental to funding rank (2026-11-28)
- Branch: `research/exp045-leadlag-funding-incremental`
- Preregistration: `research/EXP045_leadlag_funding_incremental_preregistration.md`
- Final corrected run: [GitHub Actions run 46171072438](https://github.com/MeaAi/mea/actions/runs/46171072438); artifact ID `15273284997`; code SHA `0ee8407dfbc678fb8942f8a6b69ae108d2d6b19b`.
- Data: Binance Vision USD-M 1h mark-price and funding archives, 2023-01-01 through 2026-10-31 UTC; 13 symbols; 33,552 common hourly timestamps; 1,196 archives; no load errors; archive QA reports checksums verified.
- Timing correction: peer signal shifted to the last completed bar (t-1), removing contemporaneous-return lookahead found in the earlier invalid run.
- Corrected output: incremental OOS R² of M2 over M1 was 0.000000 for both 1h and 4h; all three chronological OOS subperiods were effectively 0. The 9/13 positive train-only peer-slope gate was not met (0/13).
- **Interpretation / design limitation:** the chosen peer-ex-target arithmetic mean, when cross-sectionally demeaned at each timestamp alongside own lag, is algebraically collinear with demeaned own lag: demeaned peer mean = - demeaned own return / 12 for a 13-asset universe. This estimator therefore cannot identify an independent coefficient for that peer mean. The zero incremental result is not evidence that every possible cross-asset lead-lag signal has no value; it shows this particular peer-mean feature is not separately identifiable under the preregistered timestamp fixed-effects specification.
- Decision: advancement gates fail; no portfolio simulation, no final equity/DD, no strategy integration, no promotion. Do not retune horizons or thresholds on this OOS. Any future cross-asset study must preregister a genuinely identifiable feature (e.g. independently defined peer groups/leader basket) and a separate design before testing.
- Protected MEAFLOW-72 lineage remains unchanged.


## EXP-046 — Large-coin leader–follower diagnostic (2026-11-28; in progress)
- Branch: `research/exp046-large-coin-leadership`; all work is isolated from the protected MEAFLOW-72 lineage.
- Preregistration: `research/EXP046_large_coin_leadership_preregistration.md`; script: `research/exp046_large_coin_leadership.py`; workflow: `.github/workflows/exp046-large-coin-leadership.yml`.
- Research question: do completed hourly returns from a fixed large-coin leader basket (BTC, ETH, BNB, XRP, LTC) add predictive information for eight follower coins beyond each follower's own last completed hourly return and its trailing 7-day settled funding score?
- Universe: frozen 13-symbol set; 8 followers; hourly USD-M mark-price and funding archives, Jan 2023–Oct 2026. LTC is used as an available-universe proxy for EOS from the cited literature's leader set; it is not asserted to be a historical market-cap rank.
- Model plan: baseline OLS (own lag + funding) versus standardized LASSO (own lag + funding + five leader lags); chronological 50% train / 20% validation / 30% OOS; 1h and 4h forward returns; BTC 30-day regime classification. Scaling is now nested inside chronological CV folds to avoid validation-fold leakage.
- Workflow history: run `46175088617` failed on a script indentation issue; run `46175098253` failed on the installed scikit-learn LassoCV API; run `46175583344` completed successfully on an earlier model version, but is not accepted as final because the subsequent leakage review required nested scaling. Run `46175617447` on commit `a544279e63fb884fbbc30190170455547c5c8585` failed while extracting coefficients from the fitted GridSearchCV pipeline.
- Latest code correction: commit `25aab78585f299aa5d26cea47aa3fa9cdebe5c85`; coefficient extraction now uses the fitted best estimator pipeline. A fresh successful run of this corrected commit has not yet been verified.
- Decision/status: **no valid EXP-046 predictive result yet**. No portfolio simulation has been run; therefore no final capital, net return, or maximum drawdown exists for EXP-046. Do not interpret failed workflow attempts as negative strategy results.
- Advancement gates remain those in the preregistration: positive pooled OOS incremental R², paired 24h moving-block bootstrap CI above zero, lower OOS MSE for at least 5/8 followers, positive result in at least 2/3 OOS thirds and not confined to one regime, and clean data/timing QA. Even if predictive gates pass, a separate preregistered portfolio simulation is required; MEAFLOW-72 integration is not authorized by this diagnostic.
- Literature motivating the hypothesis: Guo, Sang, Tu & Wang (2024), *Cross-cryptocurrency return predictability*, JEDC 163, 104863, DOI 10.1016/j.jedc.2024.104863; Jia et al. (2023), *A seesaw effect in the cryptocurrency market*, Journal of Empirical Finance 74, 101428, DOI 10.1016/j.jempfin.2023.101428. These papers motivate a hypothesis, not proof of transfer to this hourly USD-M futures setup.
