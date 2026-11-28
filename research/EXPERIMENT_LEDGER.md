# MEAFLOW72 Research Ledger

Last updated: 2026-11-28
Protected strategy base: `MEAFLOW-72` at `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`

## Operating rules
- Never modify the protected `MEAFLOW-72` strategy branch for experiments.
- Run all experiments on isolated research branches/copies.
- Every experiment must be preregistered in this ledger (hypothesis, data, timing, metrics, decision gates) before code execution; after execution append exact run/artifact IDs, results, limitations, and decision.
- Initial capital: 100 USDT; default leverage: 1x; baseline costs: 5 bp commission + 2 bp slippage per side unless an experiment explicitly specifies otherwise.
- Promotion gate: net return must increase AND hourly adverse-mark maximum drawdown must become less negative versus the matched baseline. If either condition fails, reject.
- Report test dates, data source, initial/final capital, net return, hourly adverse-mark max drawdown, rebalance/trade counts (label accurately), fees, slippage, liquidation status, and bull/bear/sideways breakdown where available.
- A signal-screen/regression experiment is NOT a portfolio backtest. Do not invent final equity or account drawdown for such tests.
- Do not repeat prior experiments without checking this ledger and repository history first.
- Preserve scripts, reports, useful data, and failed experiment records. Do not delete useful files just to reduce repository size.
- Only public/free data sources unless the user explicitly changes this constraint.

## Frozen strategy context
- MEAFLOW-72 rules are defined in the strategy branch; research summary: 7-day trailing funding score, weekly rebalance, 20% tails, BTC 30-day regime threshold +/-5%; bull both legs, bear short-only, sideways hold existing positions, unknown flat.
- Universe: BTC, ETH, BNB, XRP, ADA, DOGE, SOL, LINK, LTC, BCH, DOT, TRX, AVAX (13 symbols).
- Baseline accounting: 100 USDT, 1x; 5 bp commission + 2 bp slippage per side; hourly adverse-mark drawdown.
- Main branch SHA remains `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`. MEAFLOW-52 remains separately preserved.

## Completed experiments and current decisions

### EXP-038 — STH-SOPR (REJECT)
- Branch `research/exp038-sth-sopr`; run 46145537743; artifact 15263277954.
- Matched OOS 2025-09-09T04:00Z–2026-10-31T16:00Z; 100 USDT; 1x; 5bp fee + 2bp slippage per side.
- Baseline final 172.942810 USDT (+72.9428%), hourly adverse-mark DD -26.5454%.
- Variants: flat below 7d SOPR 1 -> 116.038297 (+16.0383%), same DD; half exposure -> 137.965532 (+37.9655%), same DD; freeze new positions -> 113.155573 (+13.1556%), same DD; wait 2d recovery -> 115.112158 (+15.1122%), same DD.
- Decision: reject all; neither improves both return and DD. Do not repeat STH-SOPR overlay.

### EXP-039 — Binance VWAP overlay (PROMISING, NOT PROMOTED)
- Branch `research/exp039-binance-vwap`.
- Full OOS 2025-10-23 06:24Z–2026-10-31 16:00Z. 155d VWAP short-only below reference.
- Baseline final 186.708376 USDT (+86.7084%), DD -22.9746%; candidate final 205.279758 (+105.2798%), DD -20.5861%.
- 84 rebalances; 8,944 hourly checks; no liquidation.
- VWAP is a Binance market-volume weighted price proxy, NOT actual on-chain holder cost basis.

### EXP-040 — VWAP robustness (REJECT / NOT ROBUST)
- Branch `research/exp040-vwap-robustness`; run 46147976996; artifact 15264148254.
- Full OOS result matched EXP039. Cost stress 5+2, 10+4, 15+6 bp fee+slippage per side: full period candidate beat baseline on both measures.
- Chronological blocks: first block failed (baseline +61.8047%, candidate +58.6641%, both DD -20.5861%); blocks 2/3 passed.
- Regime PnL attribution is not regime-specific account drawdown: baseline bull +24.739364, bear +63.214552, sideways -1.245540 USDT; candidate bull +41.041415, bear +65.217312, sideways -0.978968.
- Decision: do not promote; block robustness failed.

### EXP-041 — isolated regime VWAP attempt (INVALID / INCOMPLETE)
- Branch `research/exp041-regime-isolated-robustness`.
- Segmented independent regime blocks broke VWAP warmup and the 100 aligned funding-event guard. Do not repeat by merely lowering thresholds.

### EXP-042 — multi-period VWAP (REJECT / NOT ROBUST)
- Branch `research/exp042-multi-period-vwap`; run 46157998375; artifact 15268283261; commit 6cb0729a9af602bf010025ea5b1e745e6d0f3f82.
- 2023-07–2024-07: baseline final 165.946813 (+65.9468%), DD -27.3765%; VWAP variants final 161.298949 (+61.2989%), same DD.
- 2024-07–2025-07: baseline 101.655989 (+1.6560%), DD -45.6233%; 135d 98.545538 (-1.4545%), DD -45.5170%; 155d 101.487072 (+1.4871%), DD -45.5170%; 175d 97.717943 (-2.2821%), DD -46.2352%.
- 2025-07–2026-10: baseline 139.790161 (+39.7902%), DD -41.8225%; VWAP variants +52.95% to +53.69%, but DD unchanged.
- Latest 30% OOS: baseline 187.594152 (+87.5942%), DD -22.9746%; 135d 203.030798 (+103.0308%), DD -20.5861%; 155d 206.253641 (+106.2536%), DD -20.5861%; 175d 205.255750 (+105.2557%), DD -20.5861%.
- Decision: no promotion; VWAP advantage not robust across calendar periods.

### EXP-043 — spot/perpetual basis screen (REJECTED AT SCREEN GATES)
- Branch `research/exp043-basis-factor-screen`; preregistered script `research/exp043_basis_screen.py`.
- Binance Vision spot + USD-M futures 1h klines; Jan 2023–Oct 2026; 13 symbols; 1,400 paired daily dates, 1,395 cross-sections.
- Definition used: (perpetual close / spot close - 1) * 10,000 at completed UTC 23:00 candle.
- 1d mean IC +0.005704; median -0.005903; 95% 7-day block bootstrap CI [-0.010362,+0.022331].
- 5d mean IC +0.005295; CI [-0.020645,+0.035103].
- Long high-basis / short low-basis quintile gross daily proxy +0.013602%; after assumed 10bp round-trip cost -0.086398%; positive fraction 46.81%.
- Annual 1d IC: 2023 -0.004619; 2024 +0.004365; 2025 +0.007194; 2026 +0.018125. Regime 1d IC: bull -0.012665; sideways +0.021072; bear +0.020616.
- Decision: reject at preregistered gates (CI lower bound >0 failed; cost-adjusted spread positive failed). This was a signal screen, NOT a portfolio backtest; no final capital or account DD.
- Important limitation: EXP043 did NOT test basis incremental to existing funding score. It also used perp/spot premium sign, which is opposite the quarterly-futures basis convention in Chi et al. (2023). Do not compare directions without reconciling definitions.

### EXP-044 — cross-crypto lead-lag screen (DIAGNOSTIC ONLY)
- Branch `research/exp044-cross-crypto-leadlag`; prereg commit 3eee502727798bf8fc5a6a876e839a7c0b6b5123; corrected run 46167682895; artifact 15272273830.
- Jan 2023–Oct 2026; 13 symbols; 33,600 common hours; 598 archives SHA256 verified.
- OOS mean cross-sectional IC: 1h +0.01627195 (95% 24h block CI [+0.00876059,+0.02396250]); 4h +0.01658947 (CI [+0.00904420,+0.02383730]); 24h +0.00095802 (CI [-0.00603225,+0.00795479]).
- Regime IC positive for 1h/4h across bull/bear/sideways; 24h weak/mixed. Target correlations positive for 12/13 at 1h and 10/13 at 4h.
- Limitation: no funding-adjusted model and no portfolio simulation; do not integrate based on this diagnostic alone.

### EXP-045 — peer return incremental to funding (REJECT / NOT IDENTIFIABLE)
- Branch `research/exp045-leadlag-funding-incremental`; corrected run 46171072438; artifact 15273284997; code SHA 0ee8407dfbc678fb8942f8a6b69ae108d2d6b19b.
- Jan 2023–Oct 2026; 13 symbols; 33,552 common hourly timestamps; 1,196 archives verified.
- After correcting signal timing to t-1, incremental OOS R² M2 over M1 = 0 for 1h and 4h; 0/13 positive train-only peer slopes.
- Critical design limitation: peer-ex-target arithmetic mean after cross-sectional demeaning is algebraically collinear with own demeaned return (peer mean = - own demeaned return / 12). This does not disprove all cross-asset effects; it invalidates this feature under timestamp FE.
- No portfolio simulation; no final equity or account DD. Do not repeat this exact peer-mean design.

### EXP-046 — large-coin leader/follower diagnostic (REJECT)
- Branch `research/exp046-large-coin-leadership`; final corrected run 46176178879; artifact 15275856936; code commit 25aab78585f299aa5d26cea47aa3fa9cdebe5c85.
- 13-symbol universe; 33,552 common hours 2023-01-01–2026-10-31; 1,196 archives/checksums verified.
- Model: baseline own lag + trailing 7d funding; candidate standardized LASSO adds five fixed leader lags (BTC, ETH, BNB, XRP, LTC); 8 follower symbols; chronological 50/20/30 split.
- 1h incremental OOS R² +0.0006422; paired 24h block CI [-0.0001562,+0.0014583] crosses zero; candidate lower MSE for 5/8 followers.
- 4h incremental OOS R² -0.0017966; paired CI [-0.0031657,-0.0002245]; candidate lower MSE for 1/8.
- Regime 1h increment: bull +0.0004336, bear +0.0001790, sideways +0.0013486; 4h all negative.
- Decision: reject; pooled significance and cross-horizon robustness gates fail. No portfolio simulation, final equity, or account DD.

## Literature review — basis and perpetual futures (2026-11-28)
1. Chi, Sang, Tu & Wang (2023), “An empirical investigation on risk factors in cryptocurrency futures,” Journal of Futures Markets, DOI: 10.1002/fut.22425. Uses dated current-quarter futures (not perpetuals), 12 largest OKEx coins, Nov 2017–Mar 2021. Basis convention is (spot - futures)/futures. Tests 1/3/5/7-day lookbacks; 5-day lookback/1-day holding strongest in their setup; effect weakened for week/month holding periods. This is a hypothesis source, not direct validation for Binance perpetuals.
2. Cao, Zhai & Luo (2024), “Anatomy of cryptocurrency perpetual futures returns,” Journal of Futures Markets. Directly studies perpetual futures and cost-of-carry/basis-related predictors; abstract reports 134 predictors and basis + price-volume factors explaining 48 strategies. Abstract alone does not establish basis incremental to MEAFLOW's trailing funding score.
3. PERP3 / funding-anchored perpetual futures asset-pricing paper surfaced with Dec 2026 metadata, which is after this ledger date (2026-11-28); treat publication timing cautiously and do not rely on it as an established published result.
4. Binance official public data: Binance Vision provides spot and USD-M archives; USD-M API documents funding history, mark-price klines, index-price klines and premium index. Binance defines Price Index as weighted spot prices; mark price incorporates index, funding and order-book-related components. Binance announced a funding/mark calculation change effective 2025-09-18 08:01 UTC. This is a structural-break candidate to explicitly audit.
5. Source references from web review: Chi et al. full text/methodology (web refs `turn585544view0`, `turn593878view2`); Edinburgh official research page for 2024 perpetual paper (`turn585544view1`); Binance public data/API/FAQ/announcement refs `turn266020search4`, `turn266020search0`, `turn700212search1`, `turn700212search2`, `turn700212search4`, `turn700212search3`.

## EXP-047 — preregistered next experiment; NOT YET RUN
**Title:** Does spot/perpetual basis add out-of-sample information beyond MEAFLOW-72's trailing 7-day funding score?

**Why this experiment is distinct:** EXP043 was only a univariate screen and did not condition on the existing funding score. EXP044–046 studied peer-return features, not basis. This experiment tests the unresolved incremental hypothesis, with basis convention and Binance structural break explicitly controlled.

**Hypothesis:** Point-in-time basis level and/or its 1/3/5/7-day changes may add incremental cross-sectional predictive information to the existing 7-day settled funding score for next 1-day and 7-day perpetual returns. Null: no stable incremental OOS improvement after controls and costs.

**Data:** Free official Binance Vision spot and USD-M hourly klines for the same 13-symbol frozen universe, Jan 2023–Oct 2026, checksums verified. Use only fully completed UTC hourly bars. Do not use mark-price spread as the primary basis because Binance mark incorporates funding and order-book components. Primary price: USD-M contract close vs spot close, clearly define premium = (perp/spot - 1)*10,000; secondary robustness uses inverse convention only as a sign transform, not an independently tuned feature. If official historical index-price archives are available, record as a separate robustness series, not silently substitute.

**Feature timing:** At each weekly MEAFLOW rebalance timestamp, features must use only data completed by that timestamp. Baseline model: existing trailing 7-day settled funding score (same definition as strategy). Candidate models: funding + basis level; funding + basis changes over 1/3/5/7d, tested as prespecified separate features; no broad hyperparameter search. Targets: next 1d and 7d cross-sectional perpetual returns. Use chronological train/validation/OOS; preserve a final untouched OOS. Explicitly report pre-2025-09-18 and post-2025-09-18 results due Binance formula change.

**Primary gates:** (1) incremental OOS R² > 0 with paired time-block bootstrap 95% CI lower bound >0 for at least one preregistered horizon; (2) sign/benefit not solely concentrated in one calendar year or one market regime; (3) candidate must improve net cross-sectional long/short proxy after conservative 10bp round-trip costs; (4) no leakage, sample alignment, survivorship or structural-break QA failure. If any critical gate fails, reject without parameter tuning.

**Second stage only if screen passes:** integrate the single passing feature into a copy of MEAFLOW-72, preserve weekly rebalance and all existing portfolio rules, then compare matched 100 USDT portfolios at 1x with 5bp fee + 2bp slippage per side. Report final capital, net return, hourly adverse-mark max DD, fees, slippage, rebalances, liquidation, and bull/bear/sideways attribution. Promotion still requires both higher net return AND lower DD.

**Expected limitations:** fixed-universe survivorship; daily studies in literature are not direct evidence for weekly portfolio; hourly Binance archive quality and symbol listing histories; basis can be mechanically related to funding; 2025-09-18 methodology change; signal screen does not create account-level equity/DD.

**Status:** Preregistered before implementation. Research branch created from protected SHA. Preregistration commit `0f0f33fdda3f63f9132bcc99857367b3c074c344`; analysis script commit `c07db05aad623469822d76184645e700f271782e`; workflow commit `0fe1ef850b33986baa362d008eee8f3d828d0fee`. First run `46178535457` (2026-11-28 18:56:32Z) failed after successfully downloading/checksum-verifying all 13 symbols' archives. Root cause: funding timestamps were stored in epoch-hour units, but the 7-day event-window comparison mistakenly multiplied the snapshot hour by milliseconds/hour, producing zero valid funding windows and zero complete cross-sections. This is an implementation bug, not a negative signal result. Fixed comparison to use hour units in commit `8fec4e7b510c6c0aa44cb1f2aa63f30720160a80`. Corrected run `46181004123` queued at 2026-11-28 19:24:22Z. No valid experiment result/artifact yet.

## Current status / handoff
- EXP038–046 records above; EXP039 VWAP looked promising in one window but EXP040/042 failed robustness, so it is not promoted.
- EXP043 rejected at univariate screen gates; EXP047 is the distinct funding-conditional follow-up.
- EXP047 is in implementation on `research/exp047-basis-funding-incremental`; first run failed due to an hour-vs-millisecond timestamp unit bug; corrected run 46181004123 queued. Do not restart EXP043 or repeat EXP045 peer-mean/EXP046 leader-LASSO.
- Protected MEAFLOW-72 branch remains at `a1e5293e9e7b7258ab43b6c95ff13bfeefe2abb1`; no experiment changes it.
