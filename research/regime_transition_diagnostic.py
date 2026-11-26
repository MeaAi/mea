#!/usr/bin/env python3
"""MEAFLOW-52 regime-transition attribution on free Binance Vision data.

Uses the frozen 7d funding-rank / weekly rebalance strategy and its causal
30d BTC regime gate. No API keys, private endpoints, or live orders.
"""
import argparse, bisect, json
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import funding_carry_liquidation as base

DAY = 86_400_000
HOUR = 3_600_000
SYMBOLS = "BTCUSDT,ETHUSDT,BNBUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,SOLUSDT,LINKUSDT,LTCUSDT,BCHUSDT,DOTUSDT,TRXUSDT,AVAXUSDT".split(",")

def regime_factory(data):
    times = {s: sorted(data[s]["marks"]) for s in data}
    btc = data["BTCUSDT"]["marks"]
    bt = times["BTCUSDT"]
    def at(ts):
        j = bisect.bisect_right(bt, ts) - 1
        k = bisect.bisect_right(bt, ts - 30*DAY) - 1
        if j < 0 or k < 0:
            return "unknown"
        r = btc[bt[j]][3] / btc[bt[k]][3] - 1
        return "bull" if r > .05 else ("bear" if r < -.05 else "sideways")
    return at, times

def simulate(data, period, fee_bp, slip_bp=2):
    symbols = list(data)
    regime_at, mark_times = regime_factory(data)
    first, last = period
    all_events = sorted(set(t for s in symbols for t in data[s]["fund"] if first <= t <= last))
    events = [t for t in all_events if sum(t in data[s]["fund"] and t in data[s]["marks"] for s in symbols) >= (len(symbols)*.8)]
    if len(events) < 20:
        raise RuntimeError("Insufficient aligned OOS funding events")
    equity = peak = 100.0
    maxdd = 0.0
    qty = {s: 0.0 for s in symbols}
    prev = {}
    last_rebal = None
    last_regime = None
    fee_total = slip_total = price_pnl = funding_pnl = 0.0
    hourly_checks = rebalances = 0
    current_segment_start = None
    current_segment_entry_regime = None
    segments = []
    liquidated = False
    current = {}

    for ix, t in enumerate(events):
        current = prev.copy()
        if ix and current:
            start = events[ix-1]
            for ht in range(start, t, HOUR):
                worst = equity
                notion = 0.0
                for s in symbols:
                    q = qty[s]
                    bar = data[s]["marks"].get(ht)
                    if not q or s not in current or bar is None:
                        continue
                    adverse = bar[2] if q > 0 else bar[1]
                    worst += q * (adverse - current[s])
                    notion += abs(q * adverse)
                hourly_checks += 1
                peak = max(peak, equity)
                maxdd = min(maxdd, (worst/peak-1)*100 if peak else -100)
                if worst <= notion * .015:
                    equity = max(0.0, worst - notion*.01)
                    liquidated = True
                    break
                step = 0.0
                for s in symbols:
                    bar = data[s]["marks"].get(ht)
                    if s not in current or bar is None:
                        continue
                    close = bar[3]
                    if qty[s]:
                        step += qty[s] * (close-current[s])
                    current[s] = close
                equity += step
                price_pnl += step
            if liquidated:
                break

        px = {}
        for s in symbols:
            if s in current:
                px[s] = current[s]
            else:
                j = bisect.bisect_left(mark_times[s], t)-1
                if j >= 0:
                    px[s] = data[s]["marks"][mark_times[s][j]][3]
        rates = {s: data[s]["fund"][t] for s in symbols if t in data[s]["fund"]}
        fpnl = 0.0
        rg = regime_at(t)
        for s in symbols:
            if qty[s] and s in px and s in rates:
                fpnl += -qty[s]*px[s]*rates[s]
        equity += fpnl
        funding_pnl += fpnl
        if equity <= 0:
            liquidated = True
            equity = 0.0
            break

        due = ((last_rebal is None and t >= first+7*DAY) or
               (last_rebal is not None and (t-last_rebal >= 7*DAY or rg != last_regime)))
        if due:
            # Close the prior holding episode before charging the next rebalance.
            if current_segment_start is not None:
                key = f"{current_segment_entry_regime}->{rg}"
                segments.append({"transition": key,
                                 "entry_regime": current_segment_entry_regime,
                                 "exit_regime": rg,
                                 "net_pnl_usdt": equity-current_segment_start,
                                 "return_pct": (equity/current_segment_start-1)*100 if current_segment_start else 0.0,
                                 "start_equity": current_segment_start,
                                 "end_equity_before_rebalance": equity})
            scores = {}
            for s in symbols:
                vals = [r for et, r in data[s]["fund"].items() if t-7*DAY < et <= t]
                if len(vals) >= 12 and s in px:
                    scores[s] = sum(vals)
            ordered = sorted(scores, key=scores.get)
            k = max(1, int(len(ordered)*.20))
            target = {s: 0.0 for s in symbols}
            if len(ordered) >= 2*k:
                longs, shorts = ordered[:k], ordered[-k:]
                leg = max(0.0, equity)
                if rg == "bull":
                    leg *= .5
                    for s in longs:
                        target[s] = leg/k/px[s]
                    for s in shorts:
                        target[s] = -leg/k/px[s]
                elif rg == "bear":
                    for s in shorts:
                        target[s] = -leg/k/px[s]
                # sideways / unknown => flat
            turnover = sum(abs((target[s]-qty[s])*px[s]) for s in symbols if s in px)
            fee = turnover*fee_bp/10000
            slip = turnover*slip_bp/10000
            equity -= fee+slip
            fee_total += fee
            slip_total += slip
            qty = target
            last_rebal = t
            last_regime = rg
            rebalances += 1
            current_segment_start = equity
            current_segment_entry_regime = rg

        prev = px.copy()
        peak = max(peak, equity)
        maxdd = min(maxdd, (equity/peak-1)*100 if peak else -100)
        if equity <= 0:
            liquidated = True
            equity = 0.0
            break

    if current_segment_start is not None and not liquidated:
        end_rg = regime_at(events[-1])
        segments.append({"transition": f"{current_segment_entry_regime}->{end_rg}",
                         "entry_regime": current_segment_entry_regime,
                         "exit_regime": end_rg,
                         "net_pnl_usdt": equity-current_segment_start,
                         "return_pct": (equity/current_segment_start-1)*100 if current_segment_start else 0.0,
                         "start_equity": current_segment_start,
                         "end_equity_before_rebalance": equity})

    grouped = {}
    for seg in segments:
        g = grouped.setdefault(seg["transition"], {"segments": 0, "net_pnl_usdt": 0.0, "returns": [], "wins": 0})
        g["segments"] += 1
        g["net_pnl_usdt"] += seg["net_pnl_usdt"]
        g["returns"].append(seg["return_pct"])
        g["wins"] += int(seg["return_pct"] > 0)
    summary = {}
    for key, g in grouped.items():
        vals = sorted(g["returns"])
        n = len(vals)
        summary[key] = {
            "segments": n,
            "net_pnl_usdt": round(g["net_pnl_usdt"], 6),
            "mean_segment_return_pct": round(sum(vals)/n, 5),
            "median_segment_return_pct": round(vals[n//2], 5),
            "win_rate_pct": round(100*g["wins"]/n, 2)
        }
    return {
        "fee_bp_one_way": fee_bp, "slippage_bp_one_way": slip_bp,
        "start_equity_usdt": 100.0, "end_equity_usdt": round(equity, 6),
        "net_return_pct": round((equity/100-1)*100, 5),
        "max_drawdown_pct": round(maxdd, 5),
        "rebalances": rebalances, "hourly_adverse_checks": hourly_checks,
        "liquidated": liquidated, "price_pnl_usdt": round(price_pnl, 6),
        "funding_pnl_usdt": round(funding_pnl, 6),
        "fees_usdt": round(fee_total, 6), "slippage_usdt": round(slip_total, 6),
        "transition_attribution": summary, "segments": segments
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2023-01")
    ap.add_argument("--end", default="2026-10")
    ap.add_argument("--out", default="research-results/regime_transition_oos.json")
    a = ap.parse_args()
    months = list(base.months_between(a.start, a.end))
    data, errors = {}, {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(base.load_symbol, s, months, Path("research-output")): s for s in SYMBOLS}
        for f in as_completed(futures):
            s = futures[f]
            try:
                _, fund, marks = f.result()
                data[s] = {"fund": fund, "marks": marks}
                print("LOADED", s, "funding", len(fund), "mark_bars", len(marks), flush=True)
            except Exception as e:
                errors[s] = str(e)
                print("SKIP", s, str(e), flush=True)
    if len(data) < 8 or "BTCUSDT" not in data:
        raise RuntimeError("Insufficient symbols for the cross-sectional baseline: "+json.dumps(errors))
    all_times = sorted(t for s in data for t in data[s]["fund"]
                       if sum(t in data[z]["fund"] for z in data) >= int(len(data)*.8))
    if len(all_times) < 100:
        raise RuntimeError("Insufficient aligned funding events")
    first, last = all_times[0], all_times[-1]
    span = last-first
    oos = (first+int(span*.70), last)
    # Use the same fixed OOS dates and original policy/configuration for a direct control.
    policy = {"bull": "both", "bear": "short_only", "sideways": "flat", "unknown": "flat"}
    control = base.run(data, oos, 1.0, 5, slip_bp=2,
                       lookback_days=7, rebalance_days=7, tail_fraction=.20,
                       regime_policy=policy, regime_threshold_pct=5.0)
    results = {}
    for fee in (2, 5, 8):
        results[f"fee_{fee}bp"] = simulate(data, oos, fee, 2)
    report = {
        "experiment": "MEAFLOW-52 regime-transition attribution",
        "parent_snapshot": "archive/baseline-7d-7d-20pct-2026-11-25",
        "strategy": "7d trailing funding rank; 7d rebalance; bottom 20% long / top 20% short; bull both, bear short-only, sideways/unknown flat",
        "regime": "causal BTC 30d mark-price return; bull > +5%, bear < -5%, otherwise sideways",
        "split": "chronological 50/20/30; only final 30% OOS reported",
        "oos_utc": {"start": datetime.fromtimestamp(oos[0]/1000, timezone.utc).isoformat(),
                    "end": datetime.fromtimestamp(oos[1]/1000, timezone.utc).isoformat()},
        "capital_usdt": 100, "leverage": 1,
        "data_source": "official free Binance Vision monthly fundingRate and 1h markPriceKlines",
        "data_errors": errors,
        "method_note": "Transition segment is the holding interval between consecutive strategy rebalances; its label is entry regime -> exit regime. Regime changes trigger the same immediate rebalance condition as the frozen baseline. Hourly adverse DD uses simultaneous adverse OHLC extremes. Funding cashflow is applied at settlement.",
        "frozen_baseline_control_fee5": {
            k: control[k] for k in ("net_return_pct", "end_equity_usdt", "max_drawdown_pct",
                                     "rebalance_count", "hourly_adverse_checks", "liquidated",
                                     "price_pnl_usdt", "funding_pnl_usdt", "trading_fees_usdt", "slippage_usdt")
        },
        "transition_results": results
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", a.out, flush=True)

if __name__ == "__main__":
    main()
